"""
InsightApp/management/commands/run_analysis.py

Analyse un CSV et génère :
    - output/dashboard.json   (données du dashboard envoyées via webhook)
    - output/report.pdf       (rapport archivé en artefact GitHub)

Fonctionne SANS base de données : utilisé par GitHub Actions.
Usage :
    python manage.py run_analysis <uuid> <csv_path> <output_dir>
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from InsightApp.services.csv_loader import (
    load_csv, detect_schema, enrich_revenue, detect_currency,
)
from InsightApp.services.analyzer import compute_kpis
from InsightApp.services.dashboard_builder import (
    build_kpi_entry, build_chart_specs, build_stats,
)
from InsightApp.services.pdf_generator import render_pdf


class Command(BaseCommand):
    help = "Analyse un CSV → dashboard.json + report.pdf (sans DB)."

    def add_arguments(self, parser):
        parser.add_argument("uuid",       help="UUID de l'analyse (traçabilité)")
        parser.add_argument("csv_path",   help="Chemin du CSV à analyser")
        parser.add_argument("output_dir", help="Dossier de sortie")

    def handle(self, uuid, csv_path, output_dir, **kwargs):
        csv_file = Path(csv_path)
        if not csv_file.exists():
            raise CommandError(f"CSV introuvable : {csv_file}")

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        self.stdout.write(f"[{uuid}] Lecture de {csv_file.name}…")

        # ----------------------------------------------------------
        # 1. Chargement + enrichissement
        # ----------------------------------------------------------
        content = csv_file.read_bytes()
        df = load_csv(content)
        if df.empty:
            raise CommandError("Le CSV ne contient aucune donnée exploitable.")

        schema = detect_schema(df)
        df = enrich_revenue(df, schema)
        schema = detect_schema(df)

        # ----------------------------------------------------------
        # 2. Calculs (KPI, devise, stats)
        # ----------------------------------------------------------
        currency = detect_currency(df, schema)
        kpis_raw = compute_kpis(df, schema)
        kpis_display = [build_kpi_entry(k, v, currency) for k, v in kpis_raw.items()]
        stats = build_stats(df, schema, kpis_raw, currency)

        # ----------------------------------------------------------
        # 3. PDF — graphiques rendus en PNG base64
        # ----------------------------------------------------------
        charts_png = build_chart_specs(df, schema, currency["symbol"], for_pdf=True)
        pdf_ctx = {
            "filename":     csv_file.name,
            "generated_at": datetime.now(),
            "rows":         len(df),
            "columns":      schema["all"],
            "schema":       schema,
            "currency":     currency,
            "kpis_list":    kpis_display,
            "charts":       charts_png,
            "stats":        stats,
        }
        pdf_bytes = render_pdf("pdf/report.html", pdf_ctx, base_url=str(Path.cwd()))
        (out / "report.pdf").write_bytes(pdf_bytes)
        self.stdout.write(self.style.SUCCESS(f"[{uuid}] report.pdf écrit"))

        # ----------------------------------------------------------
        # 4. Dashboard JSON — graphiques en HTML interactif
        # ----------------------------------------------------------
        charts_html = build_chart_specs(df, schema, currency["symbol"], for_pdf=False)
        payload = {
            "filename":      csv_file.name,
            "kpis":          kpis_display,
            "kpis_count":    len(kpis_display),
            "charts":        charts_html,
            "columns":       schema["all"],
            "schema":        schema,
            "currency":      currency,
            "rows":          len(df),
            "stats":         stats,
            "total_revenue": kpis_raw.get("Total revenue"),
        }
        (out / "dashboard.json").write_text(
            json.dumps(payload, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        self.stdout.write(self.style.SUCCESS(f"[{uuid}] dashboard.json écrit"))

        self.stdout.write(self.style.SUCCESS(f"OK {uuid}"))