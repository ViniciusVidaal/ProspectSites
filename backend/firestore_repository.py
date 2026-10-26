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
    "sent", "sent_at", "archived",
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
    blocklist_collection_name = "archived_lead_ids"
    migration_collection_name = "system_migrations"
    settings_collection_name = "app_settings"

    def __init__(self, settings: Settings):
        if not firebase_admin._apps:
            firebase_admin.initialize_app(
                credentials.Certificate(settings.firebase_service_account_info)
            )
        self.collection = firestore.client().collection(self.collection_name)
        self.blocklist = firestore.client().collection(self.blocklist_collection_name)
        self.migrations = firestore.client().collection(self.migration_collection_name)
        self.settings = firestore.client().collection(self.settings_collection_name)

    @staticmethod
    def _blocklist_document(lead: Lead) -> dict[str, str]:
        return {"place_id": lead.place_id, "company_name": lead.company_name}

    def message_template(self) -> str:
        snapshot = self.settings.document("message_template").get()
        return str((snapshot.to_dict() or {}).get("message", "")) if snapshot.exists else ""

    def save_message_template(self, message: str) -> str:
        clean_message = message.strip()
        if not clean_message:
            raise ValueError("A mensagem não pode ficar vazia.")
        self.settings.document("message_template").set({"message": clean_message})
        return clean_message

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
        def aggregate_count(reference) -> int:
            aggregate = reference.count().get()
            return int(aggregate[0][0].value) if aggregate else 0

        return aggregate_count(self.collection) + aggregate_count(self.blocklist)

    def list(
        self,
        include_archived: bool = False,
        pending_only: bool = False,
        limit: int | None = None,
    ) -> list[Lead]:
        # Filter in Firestore *before* applying a limit.  Filtering the first
        # page in Python meant that a recent run of archived leads could make
        # the dashboard look empty even though active leads still existed.
        reference = self.collection
        if not include_archived:
            reference = reference.where("archived", "==", False)
        if pending_only:
            reference = reference.where("sent", "==", False)
        if limit:
            reference = reference.limit(max(1, min(limit, 100)))
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
        blocked_references = [self.blocklist.document(place_id) for place_id in unique]
        existing = {
            snapshot.id
            for snapshot in firestore.client().get_all(references + blocked_references)
            if snapshot.exists
        }
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
        batch.set(self.blocklist.document(place_id), self._blocklist_document(lead))
        batch.delete(reference)
        batch.commit()

    def restore(self, place_id: str) -> None:
        raise RuntimeError("Archived leads are retained only as a blocklist and cannot be restored.")

    def deletion_history(self) -> list[dict]:
        return []

    def archive_many(self, place_ids: list[str]) -> int:
        requested = list(dict.fromkeys(place_ids))
        references = [self.collection.document(place_id) for place_id in requested]
        snapshots = firestore.client().get_all(references)
        existing = [snapshot for snapshot in snapshots if snapshot.exists]
        if not existing:
            return 0
        for start in range(0, len(existing), 250):
            batch = firestore.client().batch()
            for snapshot in existing[start:start + 250]:
                lead = self._lead(snapshot)
                batch.set(self.blocklist.document(lead.place_id), self._blocklist_document(lead))
                batch.delete(snapshot.reference)
            batch.commit()
        return len(existing)

    def compact_legacy_archived_leads(self) -> int:
        """One-time migration to records with only Google Place ID and company name."""
        marker = self.migrations.document("archive_blocklist_v1")
        if marker.get().exists:
            return 0
        archived = list(self.collection.where("archived", "==", True).stream())
        for start in range(0, len(archived), 250):
            batch = firestore.client().batch()
            for snapshot in archived[start:start + 250]:
                lead = self._lead(snapshot)
                batch.set(self.blocklist.document(lead.place_id), self._blocklist_document(lead))
                batch.delete(snapshot.reference)
            batch.commit()

        history = list(firestore.client().collection("lead_deletion_history").stream())
        for start in range(0, len(history), 500):
            batch = firestore.client().batch()
            for snapshot in history[start:start + 500]:
                batch.delete(snapshot.reference)
            batch.commit()

        active = list(self.collection.where("archived", "==", False).stream())
        for start in range(0, len(active), 500):
            batch = firestore.client().batch()
            for snapshot in active[start:start + 500]:
                batch.update(snapshot.reference, {
                    "cnpj": firestore.DELETE_FIELD,
                    "cnpj_captured": firestore.DELETE_FIELD,
                    "cnpj_phone": firestore.DELETE_FIELD,
                })
            batch.commit()
        marker.set({"completed": True})
        return len(archived)

    def stats(self) -> dict[str, int]:
        def count(reference) -> int:
            result = reference.count().get()
            return int(result[0][0].value) if result else 0

        today = datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
        return {
            "total": count(self.collection) + count(self.blocklist),
            "active": count(self.collection.where("archived", "==", False)),
            "sent": count(self.collection.where("sent", "==", True)),
            "sent_today": count(self.collection.where("sent_on", "==", today)),
            "archived": count(self.blocklist),
        }
