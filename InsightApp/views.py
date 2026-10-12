"""Vues d'InsightApp : upload, analyse et export PDF."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.db import connection
from django.db.utils import OperationalError
from django.http import (
    HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse, Http404,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.csrf import csrf_exempt

from .forms import UploadCSVForm
from .services.analysis_runner import get_runner
from .services.analyzer import compute_kpis
from .services.csv_loader import detect_currency
from .services.pdf_generator import render_pdf
from .services.dashboard_builder import (
    KPI_LABELS, KPI_META, DEFAULT_META,
    revenue_col as _revenue_col,
    prepare_dataframe as _prepare_dataframe,
    build_kpi_entry as _build_kpi_entry,
    build_chart_specs as _build_chart_specs,
    build_stats as _build_stats,
)

# ---- Façade unique DB (local) / cache (prod) --------------------------------
if settings.USE_LOCAL_DB:
    from .models import Analysis

    def _create_analysis(filename):
        return Analysis.objects.create(filename=filename)

    def _get_analysis_or_404(uuid):
        return get_object_or_404(Analysis, uuid=uuid)
else:
    from .store import AnalysisStore

    def _create_analysis(filename):
        return AnalysisStore.create(filename)

    def _get_analysis_or_404(uuid):
        a = AnalysisStore.get(uuid)
        if a is None:
            raise Http404("Analysis introuvable")
        return a
# -----------------------------------------------------------------------------

logger = logging.getLogger(__name__)


# ==========================================================
# VUES DE BASE
# ==========================================================
def home(request: HttpRequest) -> HttpResponse:
    return render(request, "dashboard/home.html", {"form": UploadCSVForm()})


def _render_home_with_error(request, form, msg, status=400):
    messages.error(request, msg)
    return render(request, "dashboard/home.html", {"form": form}, status=status)


# ----------------------------------------------------------
# ANALYZE
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
        return _render_home_with_error(request, form, _("Impossible de lire le fichier."))

    analysis = _create_analysis(uploaded.name)

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
        messages.success(
            request,
            ngettext(
                "Analyse terminée : %(count)d ligne traitée.",
                "Analyse terminée : %(count)d lignes traitées.",
                analysis.rows,
            ) % {"count": analysis.rows},
        )
        return redirect("insight:dashboard", uuid=analysis.uuid)

    messages.info(request, _("Analyse en cours…"))
    return redirect("insight:analysis_waiting", uuid=analysis.uuid)


# ----------------------------------------------------------
# DASHBOARD
# ----------------------------------------------------------
def dashboard(request: HttpRequest, uuid) -> HttpResponse:
    analysis = _get_analysis_or_404(uuid)

    if settings.ANALYSIS_MODE == "github":
        if analysis.status != "completed":
            return redirect("insight:analysis_waiting", uuid=analysis.uuid)
        data = dict(analysis.dashboard_data or {})
    else:
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
    df, schema = _prepare_dataframe(content)
    if df.empty:
        return {}
    currency = detect_currency(df, schema)
    kpis_raw = compute_kpis(df, schema)
    kpis = [_build_kpi_entry(k, v, currency) for k, v in kpis_raw.items()]
    charts = _build_chart_specs(df, schema, currency["symbol"], for_pdf=False)
    stats = _build_stats(df, schema, kpis_raw, currency)
    return {
        "filename":   analysis.filename,
        "kpis":       kpis,
        "kpis_count": len(kpis),
        "charts":     charts,
        "columns":    schema["all"],
        "schema":     schema,
        "currency":   currency,
        "rows":       len(df),
        "stats":      stats,
    }


# ----------------------------------------------------------
# WAITING + STATUS
# ----------------------------------------------------------
def analysis_waiting(request: HttpRequest, uuid) -> HttpResponse:
    analysis = _get_analysis_or_404(uuid)
    if analysis.status == "completed":
        return redirect("insight:dashboard", uuid=analysis.uuid)
    return render(request, "dashboard/analysis_waiting.html", {"analysis": analysis})


def analysis_status(request: HttpRequest, uuid) -> JsonResponse:
    a = _get_analysis_or_404(uuid)
    return JsonResponse({"status": a.status})


# ----------------------------------------------------------
# WEBHOOK (reçoit aussi dashboard_data)
# ----------------------------------------------------------
@csrf_exempt
def analysis_webhook(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return JsonResponse({"error": "method"}, status=405)

    token = request.headers.get("X-Webhook-Token", "")
    if token != settings.WEBHOOK_TOKEN:
        return JsonResponse({"error": "forbidden"}, status=403)

    try:
        payload = json.loads(request.body)
        a = _get_analysis_or_404(payload["analysis_uuid"])

        a.status = payload.get("status", "completed")
        if payload.get("pdf_artifact"):
            a.pdf_artifact = str(payload["pdf_artifact"])
        if payload.get("dashboard_data"):
            a.dashboard_data = payload["dashboard_data"]

        a.save()
        return JsonResponse({"ok": True})
    except Http404:
        return JsonResponse({"error": "not found"}, status=404)
    except Exception as exc:
        logger.exception("webhook : %s", exc)
        return JsonResponse({"error": str(exc)}, status=500)


# ----------------------------------------------------------
# EXPORT PDF
# ----------------------------------------------------------
def export_pdf(request: HttpRequest, uuid) -> HttpResponse:
    analysis = _get_analysis_or_404(uuid)

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
    df, schema = _prepare_dataframe(bytes(analysis.csv_data))
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


# ----------------------------------------------------------
# HEALTH (adapté DB / cache)
# ----------------------------------------------------------
def health(request: HttpRequest) -> JsonResponse:
    """
    Endpoint de santé utilisé par keep-alive.yml.
    - Mode DB    : SELECT 1
    - Mode cache : set/get d'une clé
    """
    start = time.monotonic()

    if not settings.USE_LOCAL_DB:
        try:
            cache.set("insight:health", "1", timeout=5)
            ok = cache.get("insight:health") == "1"
        except Exception as exc:
            logger.error("Health: cache inaccessible — %s", exc)
            return JsonResponse(
                {"status": "degraded", "cache": "down", "error": str(exc)},
                status=503,
            )
        latency_ms = int((time.monotonic() - start) * 1000)
        return JsonResponse({
            "status": "ok",
            "cache": "up" if ok else "degraded",
            "latency_ms": latency_ms,
        })

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
    return JsonResponse({"status": "ok", "db": "up", "latency_ms": latency_ms})