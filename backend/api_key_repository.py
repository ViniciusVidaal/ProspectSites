from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from firebase_admin import firestore

from .config import Settings


def next_renewal_date() -> str:
    now = datetime.now(ZoneInfo("America/Los_Angeles")).date()
    first_next_month = (now.replace(day=28) + timedelta(days=4)).replace(day=1)
    return first_next_month.isoformat()


class ApiKeyRepository:
    collection_name = "places_api_keys"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.collection = firestore.client().collection(self.collection_name)

    def active(self) -> tuple[str, str | None]:
        active = list(self.collection.where("status", "==", "active").limit(1).stream())
        if active:
            data = active[0].to_dict() or {}
            return str(data.get("api_key", "")), active[0].id
        if any(self.collection.limit(1).stream()):
            raise RuntimeError("Nenhuma API cadastrada está ativa. Abra Configurações e selecione uma API autorizada.")
        return self.settings.places_api_key, None

    def list_public(self) -> list[dict]:
        items = []
        for snapshot in self.collection.stream():
            data = snapshot.to_dict() or {}
            items.append({
                "id": snapshot.id,
                "name": data.get("name", "API sem nome"),
                "status": data.get("status", "inactive"),
                "created_at": data.get("created_at"),
                "activated_at": data.get("activated_at"),
                "quota_exhausted_at": data.get("quota_exhausted_at"),
                "renews_on": data.get("renews_on", ""),
                "last_error": data.get("last_error", ""),
            })
        return sorted(items, key=lambda item: (item["status"] != "active", item["name"].casefold()))

    def add(self, name: str, api_key: str, make_active: bool = True) -> dict:
        clean_name, clean_key = name.strip(), api_key.strip()
        if len(clean_name) < 2 or len(clean_key) < 20:
            raise ValueError("Informe um nome e uma chave válida da API do Google Maps.")
        batch = firestore.client().batch()
        if make_active:
            for snapshot in self.collection.where("status", "==", "active").stream():
                batch.update(snapshot.reference, {"status": "inactive"})
        reference = self.collection.document(str(uuid4()))
        batch.set(reference, {
            "name": clean_name,
            "api_key": clean_key,
            "status": "active" if make_active else "inactive",
            "created_at": firestore.SERVER_TIMESTAMP,
            "activated_at": firestore.SERVER_TIMESTAMP if make_active else None,
            "quota_exhausted_at": None,
            "renews_on": "",
            "last_error": "",
        })
        batch.commit()
        return {"id": reference.id, "name": clean_name, "status": "active" if make_active else "inactive"}

    def activate(self, key_id: str) -> None:
        reference = self.collection.document(key_id)
        if not reference.get().exists:
            raise KeyError("API não encontrada.")
        batch = firestore.client().batch()
        for snapshot in self.collection.where("status", "==", "active").stream():
            batch.update(snapshot.reference, {"status": "inactive"})
        batch.update(reference, {"status": "active", "activated_at": firestore.SERVER_TIMESTAMP, "last_error": ""})
        batch.commit()

    def mark_exhausted(self, key_id: str | None, detail: str = "") -> None:
        if not key_id:
            return
        self.collection.document(key_id).update({
            "status": "exhausted",
            "quota_exhausted_at": firestore.SERVER_TIMESTAMP,
            "renews_on": next_renewal_date(),
            "last_error": detail[:240],
        })
