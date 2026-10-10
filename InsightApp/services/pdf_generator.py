"""
Génération de PDF côté serveur avec WeasyPrint.

Pipeline :
    - On rend un template HTML dédié (pdf/report.html)
    - Les graphiques Plotly sont convertis en PNG base64 en amont
    - WeasyPrint lit le HTML + CSS et produit le PDF
"""
from __future__ import annotations

from io import BytesIO

from django.template.loader import render_to_string
from weasyprint import HTML


def render_pdf(template_name: str, context: dict, *, base_url: str | None = None) -> bytes:
    """
    Rend un template Django en PDF (bytes).

    Args:
        template_name: chemin du template (ex: 'pdf/report.html')
        context:       contexte Django à passer au template
        base_url:      racine pour résoudre les chemins relatifs (CSS, images)
                       → passer settings.BASE_DIR en pratique

    Returns:
        bytes du PDF, prêt à être envoyé en HttpResponse
    """
    html_string = render_to_string(template_name, context)
    pdf_buffer = BytesIO()
    HTML(string=html_string, base_url=base_url).write_pdf(pdf_buffer)
    return pdf_buffer.getvalue()