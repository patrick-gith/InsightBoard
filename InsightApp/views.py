"""Vues d'InsightApp : upload, analyse et export PDF."""
from __future__ import annotations

import logging
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from .forms import UploadCSVForm
from .models import Analysis
from .services.analyzer import compute_kpis, revenue_by, revenue_over_time
from .services.charts import (
    build_bar, build_line, build_donut, fig_to_data_uri, fig_to_html,
)
from .services.csv_loader import (
    detect_currency, detect_schema, enrich_revenue, load_csv,
)
from .services.formatting import format_amount, format_int, format_number
from .services.pdf_generator import render_pdf

logger = logging.getLogger(__name__)


# ==========================================================
# LIBELLÉS (clé anglaise → libellé traduit)
# ==========================================================
KPI_LABELS = {
    "Rows":           _("Lignes"),
    "Total revenue":  _("Chiffre d'affaires"),
    "Average order":  _("Panier moyen"),
    "Total quantity": _("Quantité totale"),
    "Top product":    _("Produit le plus vendu"),
    "Top city":       _("Ville principale"),
}

# ==========================================================
# MÉTA (icône, unité, type) — clés ANGLAISES, identiques à KPI_LABELS
# ==========================================================
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
# FICHE KPI UNIQUE (dashboard + PDF)
# ==========================================================
# ==========================================================
# FICHE KPI UNIQUE (dashboard + PDF)
# ==========================================================
def _build_kpi_entry(en_key: str, value, currency: dict) -> dict:
    """
    Normalise un KPI avec les mêmes clés pour le dashboard ET le PDF.

    - Affichage principal  : valeur EXACTE (mode="full"), pas de troncature
    - Affichage secondaire : forme compacte (k / M / G) en complément

    Clés renvoyées :
        key, label, raw, value, value_display, value_multiple, unit, icon, kind
    """
    label = str(KPI_LABELS.get(en_key, en_key))
    icon, unit_hint, kind = KPI_META.get(en_key, DEFAULT_META)

    if kind == "amount":
        # ⬇️  Exact, jamais tronqué
        value_display = format_amount(value, currency["symbol"], mode="full")
        # Forme compacte en complément (ex : ≈ 3,13 M $)
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
# GRAPHIQUES
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
        add(
            str(_("Chiffre d'affaires par ville")),
            str(_("Répartition du chiffre d'affaires par ville. "
                  "Les 15 villes les plus contributrices sont affichées, "
                  "triées par ordre décroissant.")),
            build_bar, d,
            schema["city"], rev_col,
            str(_("Chiffre d'affaires par ville")),
            currency_symbol=currency_symbol,
        )

    if schema.get("product") and rev_col:
        d = revenue_by(df, schema, schema["product"]).head(10)
        add(
            str(_("Top 10 produits")),
            str(_("Classement des 10 produits générant le chiffre d'affaires le plus élevé.")),
            build_bar, d,
            schema["product"], rev_col,
            str(_("Top 10 produits")),
            currency_symbol=currency_symbol,
        )

    if schema.get("product") and rev_col:
        d = revenue_by(df, schema, schema["product"])
        add(
            str(_("Répartition du CA par produit")),
            str(_("Poids de chaque produit dans le chiffre d'affaires total. "
                  "Les produits les moins significatifs sont regroupés sous « Autres ».")),
            build_donut, d,
            schema["product"], rev_col,
            str(_("Répartition du CA par produit")),
            currency_symbol=currency_symbol, top_n=6,
        )

    if schema.get("date") and rev_col:
        d = revenue_over_time(df, schema)
        add(
            str(_("Évolution du chiffre d'affaires")),
            str(_("Évolution mensuelle du chiffre d'affaires. Chaque point "
                  "représente le total des transactions du mois correspondant.")),
            build_line, d,
            "period", rev_col,
            str(_("Évolution du chiffre d'affaires")),
            currency_symbol=currency_symbol,
        )

    return charts


# ==========================================================
# VUES
# ==========================================================
def home(request: HttpRequest) -> HttpResponse:
    return render(request, "dashboard/home.html", {"form": UploadCSVForm()})


def _render_home_with_error(request, form, msg, status=400):
    messages.error(request, msg)
    return render(request, "dashboard/home.html", {"form": form}, status=status)


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
        df, schema, _ = _prepare_dataframe(content)
    except ValueError as exc:
        logger.warning("CSV illisible (%s) : %s", uploaded.name, exc)
        return _render_home_with_error(
            request, form,
            _("Impossible de lire le fichier CSV. Vérifiez son encodage et son format."),
        )
    except Exception as exc:
        logger.exception("Erreur lecture CSV : %s", exc)
        return _render_home_with_error(
            request, form, _("Erreur inattendue lors de la lecture du fichier.")
        )

    if df.empty:
        return _render_home_with_error(request, form, _("Le fichier CSV est vide."))

    # --- Devise ---
    currency = detect_currency(df, schema)

    # --- KPIs bruts ---
    kpis_raw = compute_kpis(df, schema)

    # --- KPIs normalisés (mêmes clés pour dashboard ET PDF) ---
    kpis_display = [_build_kpi_entry(en_key, v, currency) for en_key, v in kpis_raw.items()]

    # --- Persistance (hors boucle !) ---
    analysis = Analysis.objects.create(
        filename=uploaded.name,
        rows=len(df),
        total_revenue=kpis_raw.get("Total revenue"),
        csv_data=content,
        schema=schema,
    )

    # --- Statistiques détaillées ---
    stats = _build_stats(df, schema, kpis_raw, currency)

    # --- Graphiques HTML ---
    chart_specs = _build_chart_specs(df, schema, currency["symbol"], for_pdf=False)

    messages.success(
        request,
        ngettext(
            "Analyse terminée : %(count)d ligne traitée.",
            "Analyse terminée : %(count)d lignes traitées.",
            len(df),
        ) % {"count": len(df)},
    )

    return render(request, "dashboard/dashboard.html", {
        "filename": uploaded.name,
        "analysis_uuid": analysis.uuid,
        "kpis": kpis_display,
        "kpis_count": len(kpis_display),
        "charts": chart_specs,
        "columns": schema["all"],
        "schema": schema,
        "currency": currency,
        "rows": len(df),
        "stats": stats,
    })


def export_pdf(request: HttpRequest, uuid) -> HttpResponse:
    """Génère le PDF — mêmes valeurs / mêmes clés que le dashboard."""
    analysis = get_object_or_404(Analysis, uuid=uuid)

    if not analysis.csv_data:
        messages.error(request, _("Les données sources ne sont plus disponibles."))
        return HttpResponseRedirect(reverse("insight:index"))

    try:
        df, schema, _ = _prepare_dataframe(bytes(analysis.csv_data))
    except Exception as exc:
        logger.exception("Erreur regeneration PDF : %s", exc)
        messages.error(request, _("Impossible de régénérer les données."))
        return HttpResponseRedirect(reverse("insight:index"))

    if df.empty:
        messages.error(request, _("Le fichier source est vide."))
        return HttpResponseRedirect(reverse("insight:index"))

    # --- Devise ---
    currency = detect_currency(df, schema)

    # --- KPIs bruts ---
    kpis_raw = compute_kpis(df, schema)

    # --- MÊMES clés et MÊME mode que le dashboard ---
    # et
    kpis_list    = [_build_kpi_entry(en_key, v, currency) for en_key, v in kpis_raw.items()]

    # --- Graphiques PNG ---
    chart_specs = _build_chart_specs(df, schema, currency["symbol"], for_pdf=True)

    # --- Statistiques complémentaires ---
    stats = _build_stats(df, schema, kpis_raw, currency)

    context = {
        "filename": analysis.filename,
        "generated_at": datetime.now(),
        "rows": len(df),
        "columns": schema["all"],
        "schema": schema,
        "currency": currency,
        "kpis_list": kpis_list,
        "charts": chart_specs,
        "stats": stats,
    }

    try:
        pdf_bytes = render_pdf("pdf/report.html", context, base_url=str(settings.BASE_DIR))
    except Exception as exc:
        logger.exception("Erreur WeasyPrint : %s", exc)
        messages.error(request, _("La génération du PDF a échoué."))
        return HttpResponseRedirect(reverse("insight:index"))

    pdf_name = f"insightboard-{analysis.filename.rsplit('.', 1)[0]}.pdf"
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{pdf_name}"'
    return response


# ==========================================================
# STATS COMPLÉMENTAIRES POUR LE PDF
# ==========================================================
def _build_stats(df, schema, kpis, currency) -> dict:
    """Statistiques détaillées pour la section explicative du rapport."""
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