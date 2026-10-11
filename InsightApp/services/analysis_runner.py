"""Abstraction entre analyse locale et analyse déléguée à GitHub Actions."""
from __future__ import annotations

import base64
import io
import logging
import zipfile

import requests
from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)


class BaseRunner:
    def submit(self, analysis, content: bytes, request) -> str: ...
    def get_dashboard_data(self, analysis) -> dict | None: return None
    def get_pdf_bytes(self, analysis) -> bytes | None: return None


# ==========================================================
# MODE LOCAL — comportement historique inchangé
# ==========================================================
class LocalRunner(BaseRunner):
    def submit(self, analysis, content, request):
        from .csv_loader import (
            load_csv, detect_schema, enrich_revenue,
        )
        from .analyzer import compute_kpis

        df = load_csv(content)
        schema = detect_schema(df)
        df = enrich_revenue(df, schema)
        schema = detect_schema(df)
        kpis = compute_kpis(df, schema)

        analysis.rows = len(df)
        analysis.total_revenue = kpis.get("Total revenue")
        analysis.schema = schema
        analysis.csv_data = content
        analysis.status = "completed"
        analysis.save()
        return "completed"


# ==========================================================
# MODE GITHUB — délègue au workflow Actions
# ==========================================================
class GitHubRunner(BaseRunner):
    API = "https://api.github.com"

    def _headers(self):
        return {
            "Authorization": f"token {settings.GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
        }

    def submit(self, analysis, content, request):
        repo = settings.GITHUB_REPO
        headers = self._headers()

        # 1. Commit le CSV dans le dépôt
        path = f"uploads/{analysis.uuid}.csv"
        r = requests.put(
            f"{self.API}/repos/{repo}/contents/{path}",
            headers=headers,
            json={
                "message": f"upload csv for {analysis.uuid}",
                "content": base64.b64encode(content).decode(),
                "branch": settings.GITHUB_BRANCH,
            },
            timeout=30,
        )
        r.raise_for_status()

        # 2. Déclenche le workflow
        callback = request.build_absolute_uri(
            reverse("insight:analysis_webhook")
        )
        r = requests.post(
            f"{self.API}/repos/{repo}/actions/workflows/analyze_csv.yml/dispatches",
            headers=headers,
            json={
                "ref": settings.GITHUB_BRANCH,
                "inputs": {
                    "analysis_uuid": str(analysis.uuid),
                    "callback_url": callback,
                },
            },
            timeout=30,
        )
        r.raise_for_status()

        analysis.status = "pending"
        analysis.save(update_fields=["status"])
        return "pending"

    def get_dashboard_data(self, analysis):
        return analysis.dashboard_data or None

    def get_pdf_bytes(self, analysis) -> bytes | None:
        if not analysis.pdf_artifact:
            logger.warning("Pas d'artefact PDF pour %s", analysis.uuid)
            return None

        url = (
            f"{self.API}/repos/{settings.GITHUB_REPO}"
            f"/actions/artifacts/{analysis.pdf_artifact}/zip"
        )

        # ÉTAPE 1 : GitHub API — obtenir l'URL signée Azure (pas de suivi auto)
        try:
            r = requests.get(
                url,
                headers=self._headers(),
                timeout=10,
                allow_redirects=False,
                stream=True,
            )
        except requests.Timeout:
            logger.error("Timeout GitHub API artifact %s", analysis.pdf_artifact)
            return None
        except requests.RequestException as exc:
            logger.error("Erreur GitHub API : %s", exc)
            return None

        if r.status_code == 410:
            logger.warning("Artefact expiré : %s", analysis.pdf_artifact)
            return None
        if r.status_code == 401:
            logger.error("PAT invalide (401) pour %s", analysis.pdf_artifact)
            return None
        if r.status_code == 403:
            logger.error("PAT sans Actions:Read (403) pour %s", analysis.pdf_artifact)
            return None
        if r.status_code not in (200, 302):
            logger.warning("GitHub HTTP %s pour %s", r.status_code, analysis.pdf_artifact)
            return None

        # ÉTAPE 2 : Azure Blob — télécharger SANS header Authorization
        if r.status_code == 302:
            blob_url = r.headers.get("location")
            if not blob_url:
                logger.error("Pas de 'location' dans la redirection 302")
                return None
            try:
                # ⚠️ Aucun header d'auth : Azure utilise la signature dans l'URL
                r = requests.get(blob_url, timeout=15, stream=True)
            except requests.RequestException as exc:
                logger.error("Erreur téléchargement Azure : %s", exc)
                return None
            if r.status_code != 200:
                logger.warning("Azure Blob HTTP %s", r.status_code)
                return None

        # ÉTAPE 3 : lecture en streaming + décompression
        try:
            buf = io.BytesIO()
            for chunk in r.iter_content(chunk_size=8192):
                buf.write(chunk)
            buf.seek(0)
            with zipfile.ZipFile(buf) as z:
                for name in z.namelist():
                    if name.endswith(".pdf"):
                        return z.read(name)
        except (zipfile.BadZipFile, OSError) as exc:
            logger.error("ZIP corrompu : %s", exc)
            return None
        return None


def get_runner() -> BaseRunner:
    return GitHubRunner() if settings.ANALYSIS_MODE == "github" else LocalRunner()