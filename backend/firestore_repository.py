from __future__ import annotations

from datetime import datetime
import unicodedata
from uuid import uuid4
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

    def list(self, include_archived: bool = False, limit: int | None = None) -> list[Lead]:
        # Filter in Firestore *before* applying a limit.  Filtering the first
        # page in Python meant that a recent run of archived leads could make
        # the dashboard look empty even though active leads still existed.
        reference = self.collection
        if not include_archived:
            reference = reference.where("archived", "==", False)
        if limit:
            reference = reference.limit(max(1, min(limit, 1000)))
        leads = [self._lead(item) for item in reference.stream()]
        return sorted(
            leads,
            key=lambda lead: (-lead.review_count, -lead.rating, lead.company_name.casefold()),
        )

    def list_history(
        self,
        query: str = "",
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[Lead], str | None]:
        reference = self.collection
        if start_date:
            reference = reference.where("collected_on", ">=", start_date)
        if end_date:
            reference = reference.where("collected_on", "<=", end_date)
        term = normalize_text(query)
        if term:
            leads = [self._lead(item) for item in reference.stream()]
            leads = [lead for lead in leads if term in normalize_text(lead.company_name)]
            leads = sorted(leads, key=lambda lead: (collected_on(lead.date), lead.company_name.casefold()), reverse=True)
            offset = int(cursor or 0) if str(cursor or "").isdigit() else 0
            page = leads[offset:offset + limit]
            next_cursor = str(offset + limit) if offset + limit < len(leads) else None
            return page, next_cursor

        reference = reference.order_by("collected_on", direction=firestore.Query.DESCENDING)
        if cursor:
            snapshot = self.collection.document(cursor).get()
            if snapshot.exists:
                reference = reference.start_after(snapshot)
        snapshots = list(reference.limit(limit + 1).stream())
        page = [self._lead(item) for item in snapshots[:limit]]
        next_cursor = snapshots[limit - 1].id if len(snapshots) > limit else None
        return page, next_cursor

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
            "sent_on": datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat() if sent else "",
            "updated_at": firestore.SERVER_TIMESTAMP,
        })
        return {"place_id": place_id, "sent": sent, "sent_at": sent_at}

    def mark_sent(self, place_id: str) -> dict[str, str | bool]:
        """Claim a lead before opening WhatsApp.

        The transaction makes this operation safe when two dashboard sessions
        have the same queue open: only the first session can claim the lead.
        """
        reference = self.collection.document(place_id)
        now = datetime.now(ZoneInfo("America/Sao_Paulo"))
        sent_at = now.strftime("%d/%m/%Y %H:%M")
        sent_on = now.date().isoformat()

        @firestore.transactional
        def claim(transaction):
            snapshot = reference.get(transaction=transaction)
            if not snapshot.exists:
                raise KeyError("Lead não encontrado no banco de dados.")
            data = snapshot.to_dict() or {}
            if data.get("sent"):
                return {
                    "place_id": place_id,
                    "sent": True,
                    "sent_at": data.get("sent_at", ""),
                    "already_sent": True,
                }
            transaction.update(reference, {
                "sent": True,
                "sent_at": sent_at,
                "sent_on": sent_on,
                "updated_at": firestore.SERVER_TIMESTAMP,
            })
            return {
                "place_id": place_id,
                "sent": True,
                "sent_at": sent_at,
                "already_sent": False,
            }

        return claim(firestore.client().transaction())

    def archive(self, place_id: str) -> None:
        reference = self.collection.document(place_id)
        snapshot = reference.get()
        if not snapshot.exists:
            raise KeyError("Lead não encontrado no banco de dados.")
        lead = self._lead(snapshot)
        batch = firestore.client().batch()
        batch.update(reference, {
            "archived": True,
            "archive_reason": "manual_delete",
            "archived_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        })
        batch.set(
            firestore.client().collection("lead_deletion_history").document(place_id),
            {
                "place_id": place_id,
                "company_name": lead.company_name,
                "phone": lead.phone,
                "date": lead.date,
                "deleted_at": firestore.SERVER_TIMESTAMP,
                "restored_at": None,
            },
        )
        batch.commit()

    def restore(self, place_id: str) -> None:
        reference = self.collection.document(place_id)
        if not reference.get().exists:
            raise KeyError("Lead não encontrado no banco de dados.")
        batch = firestore.client().batch()
        batch.update(reference, {
            "archived": False,
            "archive_reason": "",
            "archived_at": None,
            "updated_at": firestore.SERVER_TIMESTAMP,
        })
        batch.set(
            firestore.client().collection("lead_deletion_history").document(place_id),
            {"restored_at": firestore.SERVER_TIMESTAMP},
            merge=True,
        )
        batch.commit()

    def deletion_history(self) -> list[dict]:
        items = []
        for snapshot in firestore.client().collection("lead_deletion_history").stream():
            data = snapshot.to_dict() or {}
            items.append({
                "place_id": data.get("place_id", snapshot.id),
                "company_name": data.get("company_name", "Empresa sem nome"),
                "phone": data.get("phone", ""),
                "date": data.get("date", ""),
                "deleted_at": data.get("deleted_at"),
                "restored_at": data.get("restored_at"),
            })
        return sorted(items, key=lambda item: str(item.get("deleted_at") or ""), reverse=True)

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
        def count(reference) -> int:
            result = reference.count().get()
            return int(result[0][0].value) if result else 0

        today = datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
        return {
            "total": count(self.collection),
            "active": count(self.collection.where("archived", "==", False)),
            "sent": count(self.collection.where("sent", "==", True)),
            "sent_today": count(self.collection.where("sent_on", "==", today)),
            "archived": count(self.collection.where("archived", "==", True)),
        }
