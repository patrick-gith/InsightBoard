"""Vues d'InsightApp : upload, analyse et export PDF."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from django.db import connection
from django.db.utils import OperationalError
import time

from django.conf import settings
from django.contrib import messages
from django.http import (
    HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.csrf import csrf_exempt

from .forms import UploadCSVForm
from .models import Analysis
from .services.analysis_runner import get_runner
from .services.analyzer import compute_kpis, revenue_by, revenue_over_time
from .services.charts import (
    build_bar, build_line, build_donut, fig_to_data_uri, fig_to_html,
)
from .services.csv_loader import (
    detect_currency, detect_schema, enrich_revenue, load_csv,
)
from .services.formatting import format_amount, format_int
from .services.pdf_generator import render_pdf

logger = logging.getLogger(__name__)


# ==========================================================
# LIBELLÉS + META (inchangés)
# ==========================================================
KPI_LABELS = {
    "Rows":           _("Lignes"),
    "Total revenue":  _("Chiffre d'affaires"),
    "Average order":  _("Panier moyen"),
    "Total quantity": _("Quantité totale"),
    "Top product":    _("Produit le plus vendu"),
    "Top city":       _("Ville principale"),
}

KPI_META = {
    "Rows":           ("fa-list",          "lignes", "int"),
    "Total revenue":  ("fa-coins",         "",       "amount"),
    "Average order":  ("fa-cart-shopping", "",       "amount"),
    "Total quantity": ("fa-boxes-stacked", "unités", "int"),
    "Top product":    ("fa-crown",         "",       "raw"),
    "Top city":       ("fa-location-dot",  "",       "raw"),
}

DEFAULT_META = ("fa-chart-simple", "", "raw")


def _revenue_col(schema):
    return schema.get("revenue") or schema.get("amount")


def _prepare_dataframe(content: bytes):
    df = load_csv(content)
    if df.empty:
        return df, {}, {}
    schema = detect_schema(df)
    df = enrich_revenue(df, schema)
    schema = detect_schema(df)
    return df, schema, {}


# ==========================================================
# FICHE KPI (inchangée)
# ==========================================================
def _build_kpi_entry(en_key: str, value, currency: dict) -> dict:
    label = str(KPI_LABELS.get(en_key, en_key))
    icon, unit_hint, kind = KPI_META.get(en_key, DEFAULT_META)

    if kind == "amount":
        value_display = format_amount(value, currency["symbol"], mode="full")
        compact = format_amount(value, currency["symbol"], mode="short")
        value_multiple = "" if compact == value_display else compact
        unit = ""
    elif kind == "int":
        value_display = format_int(value)
        value_multiple = ""
        unit = unit_hint
    else:
        value_display = str(value)
        value_multiple = ""
        unit = ""

    return {
        "key":            en_key,
        "label":          label,
        "raw":            value,
        "value":          value_display,
        "value_display":  value_display,
        "value_multiple": value_multiple,
        "unit":           unit,
        "icon":           icon,
        "kind":           kind,
    }


# ==========================================================
# GRAPHIQUES (inchangée)
# ==========================================================
def _build_chart_specs(df, schema, currency_symbol: str, *, for_pdf=False):
    rev_col = _revenue_col(schema)
    charts: list[dict] = []

    def add(title, description, builder, data, *args, **kwargs):
        if data.empty:
            return
        fig = builder(data, *args, **kwargs)
        if for_pdf:
            try:
                charts.append({
                    "title": title,
                    "description": description,
                    "image": fig_to_data_uri(fig, width=900, scale=1.8),
                })
            except Exception as exc:
                logger.warning("Kaleido échec : %s", exc)
        else:
            charts.append({
                "title": title,
                "description": description,
                "html": fig_to_html(fig),
            })

    if schema.get("city") and rev_col:
        d = revenue_by(df, schema, schema["city"]).head(15)
        add(str(_("Chiffre d'affaires par ville")),
            str(_("Répartition du chiffre d'affaires par ville. "
                  "Les 15 villes les plus contributrices sont affichées, "
                  "triées par ordre décroissant.")),
            build_bar, d, schema["city"], rev_col,
            str(_("Chiffre d'affaires par ville")),
            currency_symbol=currency_symbol)

    if schema.get("product") and rev_col:
        d = revenue_by(df, schema, schema["product"]).head(10)
        add(str(_("Top 10 produits")),
            str(_("Classement des 10 produits générant le chiffre d'affaires le plus élevé.")),
            build_bar, d, schema["product"], rev_col,
            str(_("Top 10 produits")),
            currency_symbol=currency_symbol)

    if schema.get("product") and rev_col:
        d = revenue_by(df, schema, schema["product"])
        add(str(_("Répartition du CA par produit")),
            str(_("Poids de chaque produit dans le chiffre d'affaires total. "
                  "Les produits les moins significatifs sont regroupés sous « Autres ».")),
            build_donut, d, schema["product"], rev_col,
            str(_("Répartition du CA par produit")),
            currency_symbol=currency_symbol, top_n=6)

    if schema.get("date") and rev_col:
        d = revenue_over_time(df, schema)
        add(str(_("Évolution du chiffre d'affaires")),
            str(_("Évolution mensuelle du chiffre d'affaires. Chaque point "
                  "représente le total des transactions du mois correspondant.")),
            build_line, d, "period", rev_col,
            str(_("Évolution du chiffre d'affaires")),
            currency_symbol=currency_symbol)

    return charts


# ==========================================================
# VUES
# ==========================================================
def home(request: HttpRequest) -> HttpResponse:
    return render(request, "dashboard/home.html", {"form": UploadCSVForm()})


def _render_home_with_error(request, form, msg, status=400):
    messages.error(request, msg)
    return render(request, "dashboard/home.html", {"form": form}, status=status)


# ----------------------------------------------------------
# ANALYZE — délègue au runner (local OU github)
# ----------------------------------------------------------
def analyze(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return home(request)

    form = UploadCSVForm(request.POST, request.FILES)
    if not form.is_valid():
        return _render_home_with_error(
            request, form, _("Le formulaire contient des erreurs.")
        )

    uploaded = form.cleaned_data["file"]

    try:
        content = uploaded.read()
    except Exception as exc:
        logger.exception("Lecture upload : %s", exc)
        return _render_home_with_error(
            request, form, _("Impossible de lire le fichier.")
        )

    # Création AVANT soumission (le runner met à jour le reste)
    analysis = Analysis.objects.create(filename=uploaded.name)

    runner = get_runner()
    try:
        state = runner.submit(analysis, content, request)
    except ValueError as exc:
        logger.warning("CSV illisible (%s) : %s", uploaded.name, exc)
        analysis.status = "failed"
        analysis.save(update_fields=["status"])
        return _render_home_with_error(
            request, form,
            _("Impossible de lire le fichier CSV. Vérifiez son encodage et son format."),
        )
    except Exception as exc:
        logger.exception("Échec submit : %s", exc)
        analysis.status = "failed"
        analysis.save(update_fields=["status"])
        return _render_home_with_error(
            request, form, _("Erreur inattendue lors du traitement.")
        )

    if state == "completed":
        # Mode local → dashboard direct
        messages.success(
            request,
            ngettext(
                "Analyse terminée : %(count)d ligne traitée.",
                "Analyse terminée : %(count)d lignes traitées.",
                analysis.rows,
            ) % {"count": analysis.rows},
        )
        return redirect("insight:dashboard", uuid=analysis.uuid)

    # Mode github → page d'attente
    messages.info(request, _("Analyse en cours…"))
    return redirect("insight:analysis_waiting", uuid=analysis.uuid)


# ----------------------------------------------------------
# DASHBOARD — unifié local / github
# ----------------------------------------------------------
def dashboard(request: HttpRequest, uuid) -> HttpResponse:
    analysis = get_object_or_404(Analysis, uuid=uuid)

    if settings.ANALYSIS_MODE == "github":
        if analysis.status != "completed":
            return redirect("insight:analysis_waiting", uuid=analysis.uuid)
        data = dict(analysis.dashboard_data or {})
    else:
        # Mode local → régénère (comportement historique)
        data = _compute_dashboard_context(analysis)

    if not data:
        messages.error(request, _("Aucune donnée disponible pour cette analyse."))
        return redirect("insight:index")

    data["analysis_uuid"] = analysis.uuid
    return render(request, "dashboard/dashboard.html", data)


def _compute_dashboard_context(analysis) -> dict:
    """Rejoue l'analyse depuis csv_data (mode local uniquement)."""
    if not analysis.csv_data:
        return {}
    content = bytes(analysis.csv_data)
    df, schema, _ = _prepare_dataframe(content)
    if df.empty:
        return {}
    currency = detect_currency(df, schema)
    kpis_raw = compute_kpis(df, schema)
    kpis = [_build_kpi_entry(k, v, currency) for k, v in kpis_raw.items()]
    charts = _build_chart_specs(df, schema, currency["symbol"], for_pdf=False)
    stats = _build_stats(df, schema, kpis_raw, currency)
    return {
        "filename":    analysis.filename,
        "kpis":        kpis,
        "kpis_count":  len(kpis),
        "charts":      charts,
        "columns":     schema["all"],
        "schema":      schema,
        "currency":    currency,
        "rows":        len(df),
        "stats":       stats,
    }


# ----------------------------------------------------------
# PAGE D'ATTENTE + STATUS (mode github)
# ----------------------------------------------------------
def analysis_waiting(request: HttpRequest, uuid) -> HttpResponse:
    analysis = get_object_or_404(Analysis, uuid=uuid)
    if analysis.status == "completed":
        return redirect("insight:dashboard", uuid=analysis.uuid)
    return render(
        request,
        "dashboard/analysis_waiting.html",
        {"analysis": analysis},
    )


def analysis_status(request: HttpRequest, uuid) -> JsonResponse:
    a = get_object_or_404(Analysis, uuid=uuid)
    return JsonResponse({"status": a.status})


# ----------------------------------------------------------
# WEBHOOK appelé par GitHub Actions
# ----------------------------------------------------------
@csrf_exempt
def analysis_webhook(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return JsonResponse({"error": "method"}, status=405)

    # Vérification d'un token partagé (header X-Webhook-Token)
    token = request.headers.get("X-Webhook-Token", "")
    if token != settings.WEBHOOK_TOKEN:
        return JsonResponse({"error": "forbidden"}, status=403)

    try:
        payload = json.loads(request.body)
        a = Analysis.objects.get(uuid=payload["analysis_uuid"])
        a.status = payload.get("status", "completed")
        if payload.get("pdf_artifact"):
            a.pdf_artifact = str(payload["pdf_artifact"])
        a.save(update_fields=["status", "pdf_artifact"])
        return JsonResponse({"ok": True})
    except Analysis.DoesNotExist:
        return JsonResponse({"error": "not found"}, status=404)
    except Exception as exc:
        logger.exception("webhook : %s", exc)
        return JsonResponse({"error": str(exc)}, status=500)


# ----------------------------------------------------------
# EXPORT PDF — branche local / github
# ----------------------------------------------------------
def export_pdf(request: HttpRequest, uuid) -> HttpResponse:
    analysis = get_object_or_404(Analysis, uuid=uuid)

    if settings.ANALYSIS_MODE == "github":
        pdf_bytes = get_runner().get_pdf_bytes(analysis)
        if not pdf_bytes:
            messages.error(request, _("PDF indisponible (en cours ou expiré)."))
            return HttpResponseRedirect(
                reverse("insight:dashboard", kwargs={"uuid": uuid})
            )
    else:
        if not analysis.csv_data:
            messages.error(request, _("Les données sources ne sont plus disponibles."))
            return HttpResponseRedirect(reverse("insight:index"))
        try:
            pdf_bytes = _regenerate_pdf_local(analysis)
        except Exception as exc:
            logger.exception("Erreur WeasyPrint : %s", exc)
            messages.error(request, _("La génération du PDF a échoué."))
            return HttpResponseRedirect(reverse("insight:index"))

    pdf_name = f"insightboard-{analysis.filename.rsplit('.', 1)[0]}.pdf"
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{pdf_name}"'
    return response


def _regenerate_pdf_local(analysis) -> bytes:
    """Reprend exactement l'ancienne logique d'export_pdf (mode local)."""
    df, schema, _ = _prepare_dataframe(bytes(analysis.csv_data))
    if df.empty:
        raise ValueError("Fichier vide")

    currency = detect_currency(df, schema)
    kpis_raw = compute_kpis(df, schema)
    kpis_list = [_build_kpi_entry(k, v, currency) for k, v in kpis_raw.items()]
    charts = _build_chart_specs(df, schema, currency["symbol"], for_pdf=True)
    stats = _build_stats(df, schema, kpis_raw, currency)

    ctx = {
        "filename":     analysis.filename,
        "generated_at": datetime.now(),
        "rows":         len(df),
        "columns":      schema["all"],
        "schema":       schema,
        "currency":     currency,
        "kpis_list":    kpis_list,
        "charts":       charts,
        "stats":        stats,
    }
    return render_pdf("pdf/report.html", ctx, base_url=str(settings.BASE_DIR))


# ==========================================================
# STATS (inchangée)
# ==========================================================
def _build_stats(df, schema, kpis, currency) -> dict:
    import pandas as pd

    stats: dict = {
        "period_start": None,
        "period_end": None,
        "nb_products": None,
        "nb_cities": None,
        "min_transaction": None,
        "max_transaction": None,
        "currency_symbol": currency["symbol"],
        "currency_source": currency["source"],
        "currency_raw": currency.get("raw"),
    }

    date_col = schema.get("date")
    if date_col and date_col in df.columns:
        try:
            dates = pd.to_datetime(df[date_col], errors="coerce").dropna()
            if not dates.empty:
                stats["period_start"] = dates.min().strftime("%d/%m/%Y")
                stats["period_end"] = dates.max().strftime("%d/%m/%Y")
        except Exception:
            pass

    prod = schema.get("product")
    if prod and prod in df.columns:
        stats["nb_products"] = int(df[prod].nunique())

    city = schema.get("city")
    if city and city in df.columns:
        stats["nb_cities"] = int(df[city].nunique())

    rev = schema.get("revenue") or schema.get("amount")
    if rev and rev in df.columns:
        series = pd.to_numeric(df[rev], errors="coerce").dropna()
        if not series.empty:
            stats["min_transaction"] = format_amount(
                series.min(), currency["symbol"], mode="full"
            )
            stats["max_transaction"] = format_amount(
                series.max(), currency["symbol"], mode="full"
            )

    return stats




def health(request: HttpRequest) -> JsonResponse:
    """
    Endpoint de santé utilisé par keep-alive.yml.
    Force une requête SQL pour réveiller Neon s'il est endormi.
    """
    start = time.monotonic()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except OperationalError as exc:
        logger.error("Health: DB inaccessible — %s", exc)
        return JsonResponse(
            {"status": "degraded", "db": "down", "error": str(exc)},
            status=503,
        )

    latency_ms = int((time.monotonic() - start) * 1000)
    return JsonResponse({
        "status": "ok",
        "db": "up",
        "latency_ms": latency_ms,
    })