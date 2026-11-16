from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import firebase_admin
from firebase_admin import credentials, firestore

from .config import Settings


class GoogleAnalysisRepository:
    collection_name = "google_profile_analyses"
    tenant_key = "default"

    def __init__(self, settings: Settings):
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(settings.firebase_service_account_info))
        self.collection = firestore.client().collection(self.collection_name)

    def save(self, report: dict[str, Any]) -> dict[str, Any]:
        payload = {**report, "tenant_key": self.tenant_key, "updated_at": firestore.SERVER_TIMESTAMP}
        self.collection.document(report["id"]).set(payload)
        return report

    def get(self, report_id: str) -> dict[str, Any]:
        snapshot = self.collection.document(report_id).get()
        if not snapshot.exists:
            raise KeyError("Análise não encontrada.")
        data = snapshot.to_dict() or {}
        if data.get("tenant_key", self.tenant_key) != self.tenant_key:
            raise KeyError("Análise não encontrada.")
        data["id"] = snapshot.id
        for key in ("updated_at",):
            value = data.get(key)
            if hasattr(value, "isoformat"):
                data[key] = value.isoformat()
        return data

    def list(self, limit: int = 30) -> list[dict[str, Any]]:
        reference = self.collection.where("tenant_key", "==", self.tenant_key).limit(max(1, min(limit, 100)))
        results = []
        for snapshot in reference.stream():
            data = snapshot.to_dict() or {}
            data["id"] = snapshot.id
            data.pop("evidence", None)
            data.pop("checklist", None)
            results.append(data)
        return sorted(results, key=lambda item: item.get("collected_at", ""), reverse=True)

    def link_lead(self, report_id: str, place_id: str) -> dict[str, Any]:
        reference = self.collection.document(report_id)
        if not reference.get().exists:
            raise KeyError("Análise não encontrada.")
        reference.update({
            "lead_place_id": place_id,
            "linked_at": datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(),
            "updated_at": firestore.SERVER_TIMESTAMP,
        })
        return {"report_id": report_id, "lead_place_id": place_id, "linked": True}
