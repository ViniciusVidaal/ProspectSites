from __future__ import annotations

from datetime import datetime
import unicodedata
from zoneinfo import ZoneInfo

import firebase_admin
from firebase_admin import credentials, firestore

from .config import Settings
from .models import Lead


LEAD_FIELDS = (
    "date", "company_name", "phone", "whatsapp_link", "current_site",
    "site_platform", "review_count", "rating", "maps_link", "place_id",
    "sent", "sent_at", "archived", "cnpj", "cnpj_captured", "cnpj_phone",
    "address", "city", "state",
)


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold().strip()


def collected_on(date_value: str) -> str:
    try:
        return datetime.strptime(date_value, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()


class FirestoreRepository:
    collection_name = "leads"

    def __init__(self, settings: Settings):
        if not firebase_admin._apps:
            firebase_admin.initialize_app(
                credentials.Certificate(settings.firebase_service_account_info)
            )
        self.collection = firestore.client().collection(self.collection_name)

    def _document(self, lead: Lead) -> dict:
        data = {field: getattr(lead, field) for field in LEAD_FIELDS}
        data.update({
            "collected_on": collected_on(lead.date),
            "company_name_normalized": normalize_text(lead.company_name),
            "updated_at": firestore.SERVER_TIMESTAMP,
        })
        return data

    @staticmethod
    def _lead(snapshot) -> Lead:
        data = snapshot.to_dict() or {}
        data["place_id"] = data.get("place_id") or snapshot.id
        return Lead(**{field: data.get(field, "") for field in LEAD_FIELDS})

    def count(self) -> int:
        aggregate = self.collection.count().get()
        return int(aggregate[0][0].value) if aggregate else 0

    def list(self, include_archived: bool = False) -> list[Lead]:
        leads = [self._lead(item) for item in self.collection.stream()]
        if not include_archived:
            leads = [lead for lead in leads if not lead.archived]
        return sorted(
            leads,
            key=lambda lead: (-lead.review_count, -lead.rating, lead.company_name.casefold()),
        )

    def list_history(
        self,
        query: str = "",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[Lead]:
        reference = self.collection
        if start_date:
            reference = reference.where("collected_on", ">=", start_date)
        if end_date:
            reference = reference.where("collected_on", "<=", end_date)
        term = normalize_text(query)
        leads = [self._lead(item) for item in reference.stream()]
        if term:
            leads = [lead for lead in leads if term in normalize_text(lead.company_name)]
        return sorted(
            leads,
            key=lambda lead: (collected_on(lead.date), lead.company_name.casefold()),
            reverse=True,
        )

    def append_new(self, leads: list[Lead]) -> list[Lead]:
        unique = {lead.place_id: lead for lead in leads if lead.place_id}
        if not unique:
            return []
        references = [self.collection.document(place_id) for place_id in unique]
        existing = {snapshot.id for snapshot in firestore.client().get_all(references) if snapshot.exists}
        fresh = [lead for place_id, lead in unique.items() if place_id not in existing]
        if not fresh:
            return []
        batch = firestore.client().batch()
        for lead in fresh:
            batch.set(self.collection.document(lead.place_id), self._document(lead))
        batch.commit()
        return fresh

    def set_sent_status(self, place_id: str, sent: bool) -> dict[str, str | bool]:
        reference = self.collection.document(place_id)
        if not reference.get().exists:
            raise KeyError("Lead não encontrado no banco de dados.")
        sent_at = (
            datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M")
            if sent else ""
        )
        reference.update({
            "sent": sent,
            "sent_at": sent_at,
            "updated_at": firestore.SERVER_TIMESTAMP,
        })
        return {"place_id": place_id, "sent": sent, "sent_at": sent_at}

    def mark_sent(self, place_id: str) -> dict[str, str | bool]:
        return self.set_sent_status(place_id, True)

    def archive(self, place_id: str) -> None:
        reference = self.collection.document(place_id)
        if not reference.get().exists:
            raise KeyError("Lead não encontrado no banco de dados.")
        reference.update({"archived": True, "updated_at": firestore.SERVER_TIMESTAMP})

    def archive_many(self, place_ids: list[str]) -> int:
        requested = list(dict.fromkeys(place_ids))
        references = [self.collection.document(place_id) for place_id in requested]
        snapshots = firestore.client().get_all(references)
        existing = [snapshot.reference for snapshot in snapshots if snapshot.exists]
        if not existing:
            return 0
        batch = firestore.client().batch()
        for reference in existing:
            batch.update(reference, {"archived": True, "updated_at": firestore.SERVER_TIMESTAMP})
        batch.commit()
        return len(existing)

    def stats(self) -> dict[str, int]:
        leads = self.list(include_archived=True)
        today = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y")
        return {
            "total": len(leads),
            "active": sum(not lead.archived for lead in leads),
            "sent": sum(lead.sent for lead in leads),
            "sent_today": sum(lead.sent and lead.sent_at.startswith(today) for lead in leads),
            "archived": sum(lead.archived for lead in leads),
        }
