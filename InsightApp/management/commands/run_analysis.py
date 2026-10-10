"""
Analyse un CSV et génère dashboard_data.json + report.pdf.
Utilisé par GitHub Actions.
Usage :
    python manage.py run_analysis <uuid> <csv_path> <output_dir>
"""
import json
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand

from InsightApp.models import Analysis
from InsightApp.services.csv_loader import (
    load_csv, detect_schema, enrich_revenue, detect_currency,
)
from InsightApp.services.analyzer import compute_kpis
from InsightApp.services.pdf_generator import render_pdf
from InsightApp.views import (
    _build_kpi_entry, _build_chart_specs, _build_stats,
)


class Command(BaseCommand):
    help = "Analyse un CSV → dashboard_data.json + report.pdf."

    def add_arguments(self, parser):
        parser.add_argument("uuid")
        parser.add_argument("csv_path")
        parser.add_argument("output_dir")

    def handle(self, uuid, csv_path, output_dir, **kwargs):
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        content = Path(csv_path).read_bytes()
        df = load_csv(content)
        schema = detect_schema(df)
        df = enrich_revenue(df, schema)
        schema = detect_schema(df)
        currency = detect_currency(df, schema)
        kpis_raw = compute_kpis(df, schema)
        kpis_display = [_build_kpi_entry(k, v, currency) for k, v in kpis_raw.items()]
        stats = _build_stats(df, schema, kpis_raw, currency)

        charts_html = _build_chart_specs(df, schema, currency["symbol"], for_pdf=False)
        charts_png  = _build_chart_specs(df, schema, currency["symbol"], for_pdf=True)

        pdf_ctx = {
            "filename": Path(csv_path).name,
            "generated_at": datetime.now(),
            "rows": len(df),
            "columns": schema["all"],
            "schema": schema,
            "currency": currency,
            "kpis_list": kpis_display,
            "charts": charts_png,
            "stats": stats,
        }
        pdf_bytes = render_pdf("pdf/report.html", pdf_ctx, base_url=str(Path.cwd()))
        (out / "report.pdf").write_bytes(pdf_bytes)

        payload = {
            "filename": Path(csv_path).name,
            "kpis": kpis_display,
            "kpis_count": len(kpis_display),
            "charts": charts_html,
            "columns": schema["all"],
            "schema": schema,
            "currency": currency,
            "rows": len(df),
            "stats": stats,
            "total_revenue": kpis_raw.get("Total revenue"),
        }
        (out / "dashboard_data.json").write_text(
            json.dumps(payload, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

        a = Analysis.objects.get(uuid=uuid)
        a.rows = len(df)
        a.total_revenue = kpis_raw.get("Total revenue")
        a.schema = schema
        a.dashboard_data = payload
        a.status = "completed"
        a.save()

        self.stdout.write(self.style.SUCCESS(f"OK {uuid}"))