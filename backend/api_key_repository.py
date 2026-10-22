from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from firebase_admin import firestore

from .config import Settings


MONTHLY_FREE_REQUESTS = 1000


def current_billing_month() -> str:
    return datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m")


def next_renewal_date() -> str:
    now = datetime.now(ZoneInfo("America/Los_Angeles")).date()
    first_next_month = (now.replace(day=28) + timedelta(days=4)).replace(day=1)
    return first_next_month.isoformat()


class ApiKeyRepository:
    collection_name = "places_api_keys"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.collection = firestore.client().collection(self.collection_name)

    def _refresh_monthly_statuses(self) -> None:
        """Re-enables the previously exhausted selection after its new monthly cycle."""
        today = datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()
        exhausted = [
            item for item in self.collection.where("status", "==", "exhausted").stream()
            if (item.to_dict() or {}).get("renews_on", "") <= today
        ]
        if not exhausted:
            return
        active = list(self.collection.where("status", "==", "active").limit(1).stream())
        batch = firestore.client().batch()
        for item in exhausted:
            batch.update(item.reference, {
                "status": "inactive",
                "quota_exhausted_at": None,
                "last_error": "",
            })
        if not active:
            selected = sorted(
                exhausted,
                key=lambda item: str((item.to_dict() or {}).get("activated_at") or ""),
                reverse=True,
            )[0]
            batch.update(selected.reference, {
                "status": "active",
                "activated_at": firestore.SERVER_TIMESTAMP,
            })
        batch.commit()

    def active(self) -> tuple[str, str | None]:
        self._refresh_monthly_statuses()
        active = list(self.collection.where("status", "==", "active").limit(1).stream())
        if active:
            data = active[0].to_dict() or {}
            return str(data.get("api_key", "")), active[0].id
        if any(self.collection.limit(1).stream()):
            raise RuntimeError("Nenhuma API cadastrada está ativa. Abra Configurações e selecione uma API autorizada.")
        return self.settings.places_api_key, None

    def list_public(self) -> list[dict]:
        self._refresh_monthly_statuses()
        month = current_billing_month()
        items = []
        for snapshot in self.collection.stream():
            data = snapshot.to_dict() or {}
            used = int(data.get("usage_requests", 0) or 0)
            if data.get("usage_month") != month:
                used = 0
            items.append({
                "id": snapshot.id,
                "name": data.get("name", "API sem nome"),
                "status": data.get("status", "inactive"),
                "created_at": data.get("created_at"),
                "activated_at": data.get("activated_at"),
                "quota_exhausted_at": data.get("quota_exhausted_at"),
                "renews_on": data.get("renews_on", ""),
                "last_error": data.get("last_error", ""),
                "requests_used": used,
                "requests_remaining": max(MONTHLY_FREE_REQUESTS - used, 0),
                "monthly_request_limit": MONTHLY_FREE_REQUESTS,
                "usage_month": month,
                "next_renewal_on": next_renewal_date(),
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
            "usage_month": current_billing_month(),
            "usage_requests": 0,
            "last_usage_at": None,
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

    def record_usage(self, key_id: str | None) -> None:
        """Registers a successful Places request made by this application only."""
        if not key_id:
            return
        reference = self.collection.document(key_id)
        transaction = firestore.client().transaction()

        @firestore.transactional
        def update_usage(transaction, document_reference):
            snapshot = document_reference.get(transaction=transaction)
            if not snapshot.exists:
                return
            data = snapshot.to_dict() or {}
            month = current_billing_month()
            used = int(data.get("usage_requests", 0) or 0)
            if data.get("usage_month") != month:
                used = 0
            transaction.update(document_reference, {
                "usage_month": month,
                "usage_requests": used + 1,
                "last_usage_at": firestore.SERVER_TIMESTAMP,
            })

        update_usage(transaction, reference)

    def delete(self, key_id: str) -> dict:
        """Removes a stored key and promotes another one when necessary."""
        reference = self.collection.document(key_id)
        snapshot = reference.get()
        if not snapshot.exists:
            raise KeyError("API não encontrada.")

        data = snapshot.to_dict() or {}
        was_active = data.get("status") == "active"
        alternatives = sorted(
            (item for item in self.collection.stream() if item.id != key_id),
            key=lambda item: str((item.to_dict() or {}).get("name", "")).casefold(),
        )
        batch = firestore.client().batch()
        batch.delete(reference)
        activated_name = ""
        if was_active and alternatives:
            next_key = alternatives[0]
            next_data = next_key.to_dict() or {}
            batch.update(next_key.reference, {
                "status": "active",
                "activated_at": firestore.SERVER_TIMESTAMP,
                "last_error": "",
            })
            activated_name = str(next_data.get("name", "Outra API"))
        batch.commit()
        return {
            "id": key_id,
            "name": str(data.get("name", "API")),
            "activated_name": activated_name,
        }

    def mark_exhausted(self, key_id: str | None, detail: str = "") -> None:
        if not key_id:
            return
        self.collection.document(key_id).update({
            "status": "exhausted",
            "quota_exhausted_at": firestore.SERVER_TIMESTAMP,
            "renews_on": next_renewal_date(),
            "last_error": detail[:240],
        })
