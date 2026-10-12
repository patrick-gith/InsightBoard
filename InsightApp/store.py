"""
Store d'analyses : cache-only en production, compatible avec l'interface
de l'ancien modèle Analysis (create, get, save, csv_data en bytes).
"""
from __future__ import annotations

import base64
import uuid as uuid_lib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

from django.core.cache import cache


TTL = 60 * 60 * 24  # 24 heures


@dataclass
class AnalysisRecord:
    uuid: str
    filename: str
    status: str = "pending"
    rows: int = 0
    total_revenue: Optional[float] = None
    schema: dict = field(default_factory=dict)
    csv_data_b64: Optional[str] = None
    dashboard_data: Optional[dict] = None
    pdf_artifact: Optional[str] = None
    created_at: Optional[str] = None

    # Compat : analysis.csv_data renvoie des bytes (comme l'ancien modèle)
    @property
    def csv_data(self) -> Optional[bytes]:
        return base64.b64decode(self.csv_data_b64) if self.csv_data_b64 else None

    @csv_data.setter
    def csv_data(self, value: Optional[bytes]) -> None:
        self.csv_data_b64 = base64.b64encode(value).decode() if value else None

    def save(self, update_fields=None) -> None:
        AnalysisStore.save(self)


class AnalysisStore:
    KEY = "insight:analysis:{uuid}"

    @classmethod
    def _key(cls, uuid_val) -> str:
        return cls.KEY.format(uuid=str(uuid_val))

    @classmethod
    def create(cls, filename: str) -> AnalysisRecord:
        rec = AnalysisRecord(
            uuid=str(uuid_lib.uuid4()),
            filename=filename,
            created_at=datetime.utcnow().isoformat(),
        )
        cls.save(rec)
        return rec

    @classmethod
    def get(cls, uuid_val) -> Optional[AnalysisRecord]:
        data = cache.get(cls._key(uuid_val))
        return AnalysisRecord(**data) if data else None

    @classmethod
    def save(cls, rec: AnalysisRecord) -> None:
        cache.set(cls._key(rec.uuid), asdict(rec), timeout=TTL)