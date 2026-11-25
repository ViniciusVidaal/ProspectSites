from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

import firebase_admin
from firebase_admin import credentials, firestore
from google.api_core.exceptions import AlreadyExists

from .config import Settings
from .phones import normalize_phone


DEFAULT_STAGES = (
    ("aguardando_resposta", "Aguardando resposta", "#4f8cff"),
    ("em_atendimento", "Em atendimento", "#f59e0b"),
    ("analise_aceita", "Análise aceita", "#06b6d4"),
    ("em_negociacao", "Em negociação", "#8b5cf6"),
    ("encaminhado_equipe", "Encaminhado à equipe", "#16a36a"),
    ("perdido", "Perdido", "#d94a5d"),
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def stable_id(*parts: str) -> str:
    return sha256("|".join(parts).encode("utf-8")).hexdigest()[:40]


def json_value(value: Any):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_value(item) for item in value]
    return value


class CrmRepository:
    def __init__(self, settings: Settings):
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(settings.firebase_service_account_info))
        self.db = firestore.client()
        self.contacts = self.db.collection("crm_contacts")
        self.conversations = self.db.collection("crm_conversations")
        self.messages = self.db.collection("crm_messages")
        self.stages = self.db.collection("crm_stages")
        self.instances = self.db.collection("crm_whatsapp_instances")
        self.activities = self.db.collection("crm_activities")
        self.integration_events = self.db.collection("crm_integration_events")

    @staticmethod
    def _dict(snapshot) -> dict:
        data = snapshot.to_dict() or {}
        data["id"] = snapshot.id
        return json_value(data)

    def ensure_defaults(self) -> None:
        if next(self.stages.limit(1).stream(), None):
            return
        batch = self.db.batch()
        for position, (stage_id, name, color) in enumerate(DEFAULT_STAGES):
            batch.set(self.stages.document(stage_id), {
                "name": name,
                "color": color,
                "position": position,
                "created_at": firestore.SERVER_TIMESTAMP,
            })
        batch.commit()

    def list_stages(self) -> list[dict]:
        self.ensure_defaults()
        return [self._dict(item) for item in self.stages.order_by("position").stream()]

    def create_stage(self, name: str, color: str) -> dict:
        stage_id = stable_id(name.casefold(), str(utc_now().timestamp()))
        position = len(self.list_stages())
        self.stages.document(stage_id).set({
            "name": name.strip(), "color": color, "position": position,
            "created_at": firestore.SERVER_TIMESTAMP,
        })
        return self._dict(self.stages.document(stage_id).get())

    def update_stage(self, stage_id: str, values: dict) -> dict:
        reference = self.stages.document(stage_id)
        if not reference.get().exists:
            raise KeyError("Etapa não encontrada.")
        reference.update({**values, "updated_at": firestore.SERVER_TIMESTAMP})
        return self._dict(reference.get())

    def reorder_stages(self, stage_ids: list[str]) -> list[dict]:
        current = {item["id"] for item in self.list_stages()}
        if set(stage_ids) != current:
            raise ValueError("A reorganização precisa incluir todas as etapas atuais.")
        batch = self.db.batch()
        for position, stage_id in enumerate(stage_ids):
            batch.update(self.stages.document(stage_id), {"position": position})
        batch.commit()
        return self.list_stages()

    def delete_stage(self, stage_id: str, move_to_stage_id: str | None) -> None:
        if len(self.list_stages()) <= 1:
            raise ValueError("O Kanban precisa manter pelo menos uma etapa.")
        contacts = list(self.contacts.where("stage_id", "==", stage_id).stream())
        if contacts and not move_to_stage_id:
            raise ValueError("Escolha uma etapa de destino antes de excluir uma coluna com leads.")
        if move_to_stage_id and not self.stages.document(move_to_stage_id).get().exists:
            raise KeyError("Etapa de destino não encontrada.")
        for start in range(0, len(contacts), 250):
            batch = self.db.batch()
            for contact in contacts[start:start + 250]:
                batch.update(contact.reference, {"stage_id": move_to_stage_id, "updated_at": firestore.SERVER_TIMESTAMP})
            batch.commit()
        self.stages.document(stage_id).delete()

    def list_instances(self) -> list[dict]:
        return [self._dict(item) for item in self.instances.order_by("label").stream()]

    def save_instance(self, instance_name: str, values: dict, merge: bool = True) -> dict:
        reference = self.instances.document(instance_name)
        payload = {**values, "instance_name": instance_name, "updated_at": firestore.SERVER_TIMESTAMP}
        if not reference.get().exists:
            payload["created_at"] = firestore.SERVER_TIMESTAMP
            payload.setdefault("enabled", True)
            payload.setdefault("status", "unknown")
        reference.set(payload, merge=merge)
        return self._dict(reference.get())

    def delete_instance(self, instance_name: str) -> None:
        self.instances.document(instance_name).delete()

    def _default_stage_id(self) -> str:
        stages = self.list_stages()
        return stages[0]["id"]

    def list_contacts(
        self, *, instance_name: str = "", stage_id: str = "", query: str = "", limit: int = 250
    ) -> list[dict]:
        reference = self.contacts
        if stage_id:
            reference = reference.where("stage_id", "==", stage_id)
        snapshots = list(reference.limit(min(max(limit, 1), 500)).stream())
        items = [self._dict(item) for item in snapshots]
        term = query.casefold().strip()
        if instance_name:
            items = [item for item in items if instance_name in item.get("instance_names", [])]
        if term:
            items = [item for item in items if term in f"{item.get('name', '')} {item.get('phone', '')}".casefold()]
        return sorted(items, key=lambda item: item.get("last_interaction_at") or "", reverse=True)

    def list_messages(self, contact_id: str, limit: int = 300) -> list[dict]:
        snapshots = self.messages.where("contact_id", "==", contact_id).limit(min(max(limit, 1), 500)).stream()
        items = [self._dict(item) for item in snapshots]
        return sorted(items, key=lambda item: item.get("message_timestamp") or "")

    def list_activities(self, contact_id: str, limit: int = 100) -> list[dict]:
        snapshots = self.activities.where("contact_id", "==", contact_id).limit(min(max(limit, 1), 200)).stream()
        items = [self._dict(item) for item in snapshots]
        return sorted(items, key=lambda item: item.get("created_at") or "", reverse=True)

    def update_contact(self, contact_id: str, values: dict) -> dict:
        reference = self.contacts.document(contact_id)
        if not reference.get().exists:
            raise KeyError("Lead não encontrado no CRM.")
        payload = {**values, "updated_at": firestore.SERVER_TIMESTAMP}
        reference.update(payload)
        self.activities.document().set({
            "contact_id": contact_id,
            "action": "contact_updated",
            "actor": "user",
            "fields": sorted(values.keys()),
            "created_at": firestore.SERVER_TIMESTAMP,
        })
        return self._dict(reference.get())

    def move_contact(
        self,
        contact_id: str,
        stage_id: str,
        *,
        actor: str = "user",
        reason: str = "",
        source_event_id: str = "",
    ) -> dict:
        contact_ref = self.contacts.document(contact_id)
        stage_ref = self.stages.document(stage_id)
        if not stage_ref.get().exists:
            raise KeyError("Etapa não encontrada.")

        @firestore.transactional
        def move(transaction):
            snapshot = contact_ref.get(transaction=transaction)
            if not snapshot.exists:
                raise KeyError("Lead não encontrado no CRM.")
            before = (snapshot.to_dict() or {}).get("stage_id")
            if before == stage_id:
                return False
            transaction.update(contact_ref, {"stage_id": stage_id, "updated_at": firestore.SERVER_TIMESTAMP})
            activity = self.activities.document()
            transaction.set(activity, {
                "contact_id": contact_id, "action": "stage_moved", "from_stage_id": before,
                "to_stage_id": stage_id, "actor": actor, "reason": reason,
                "source_event_id": source_event_id,
                "created_at": firestore.SERVER_TIMESTAMP,
            })
            return True

        move(self.db.transaction())
        return self._dict(contact_ref.get())

    def resolve_stage(self, value: str) -> dict:
        target = (value or "").strip()
        if not target:
            raise ValueError("O evento do Hermes não informou a etapa de destino.")
        by_id = self.stages.document(target).get()
        if by_id.exists:
            return self._dict(by_id)
        normalized = target.casefold()
        for stage in self.list_stages():
            if str(stage.get("name", "")).casefold() == normalized:
                return stage
        raise KeyError("Etapa de destino não encontrada no CRM.")

    def upsert_contact(self, instance_name: str, data: dict) -> dict:
        phone = normalize_phone(str(data.get("phone") or data.get("jid") or "").split("@")[0])
        if not phone:
            raise ValueError("O evento do Hermes não informou um telefone válido.")
        contact_id = stable_id(phone)
        reference = self.contacts.document(contact_id)
        current = reference.get().to_dict() or {}
        instance_names = sorted(set(current.get("instance_names", [])) | {instance_name})
        payload = {
            "phone": phone,
            "name": str(data.get("name") or data.get("contact_name") or current.get("name") or phone),
            "stage_id": current.get("stage_id") or self._default_stage_id(),
            "instance_names": instance_names,
            "prospect_lead_id": (
                current.get("prospect_lead_id")
                or str(data.get("lead_place_id") or data.get("place_id") or "").strip()
                or self._find_existing_lead(phone)
            ),
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
        if not current:
            payload["first_contact_at"] = utc_now()
            payload["message_count"] = 0
        reference.set(payload, merge=True)
        self.save_instance(instance_name, {"last_event_at": utc_now(), "status": "connected", "provider": "hermes"})
        return self._dict(reference.get())

    def begin_integration_event(self, event_id: str, event: str, instance_name: str) -> bool:
        reference = self.integration_events.document(stable_id("hermes", event_id))
        @firestore.transactional
        def claim(transaction):
            snapshot = reference.get(transaction=transaction)
            if snapshot.exists:
                current = snapshot.to_dict() or {}
                if current.get("status") != "failed":
                    return False
                transaction.update(reference, {
                    "status": "processing",
                    "detail": "",
                    "attempts": firestore.Increment(1),
                    "updated_at": firestore.SERVER_TIMESTAMP,
                })
                return True
            transaction.set(reference, {
                "external_event_id": event_id,
                "event": event,
                "instance_name": instance_name,
                "status": "processing",
                "attempts": 1,
                "created_at": firestore.SERVER_TIMESTAMP,
            })
            return True
        return claim(self.db.transaction())

    def finish_integration_event(self, event_id: str, *, status: str = "processed", detail: str = "") -> None:
        self.integration_events.document(stable_id("hermes", event_id)).set({
            "status": status,
            "detail": detail[:500],
            "processed_at": firestore.SERVER_TIMESTAMP,
        }, merge=True)

    def ingest_normalized_message(self, instance_name: str, data: dict, occurred_at=None) -> dict:
        phone = normalize_phone(str(data.get("phone") or data.get("jid") or "").split("@")[0])
        message_id = str(data.get("message_id") or data.get("id") or "").strip()
        if not phone or not message_id:
            raise ValueError("Mensagem do Hermes sem telefone ou message_id.")
        timestamp = data.get("timestamp") or occurred_at
        if isinstance(timestamp, str):
            try:
                timestamp = int(datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp())
            except ValueError:
                timestamp = None
        raw_message = {
            "key": {
                "remoteJid": f"{phone}@s.whatsapp.net",
                "id": message_id,
                "fromMe": bool(data.get("from_me", data.get("fromMe", False))),
            },
            "pushName": data.get("contact_name") or data.get("name") or phone,
            "messageTimestamp": timestamp,
            "messageType": data.get("message_type") or data.get("type") or "conversation",
            "prospect_lead_id": str(data.get("lead_place_id") or data.get("place_id") or "").strip(),
            "message": {"conversation": str(data.get("text") or data.get("body") or "[Mensagem]")},
        }
        return self.ingest_message(instance_name, raw_message)

    def _find_existing_lead(self, phone: str) -> str | None:
        # Single-field equality queries use Firestore's automatic indexes and
        # avoid the previous 500-document scan for every unlinked contact.
        matches: set[str] = set()
        leads = self.db.collection("leads")
        for field in ("phone_digits", "cnpj_phone_digits"):
            matches.update(
                snapshot.id
                for snapshot in leads.where(field, "==", phone).limit(2).stream()
            )
        archived = list(
            self.db.collection("archived_lead_ids")
            .where("phone_digits", "==", phone)
            .limit(2)
            .stream()
        )
        for snapshot in archived:
            data = snapshot.to_dict() or {}
            matches.add(str(data.get("place_id") or snapshot.id))
        return next(iter(matches)) if len(matches) == 1 else None

    def ingest_message(self, instance_name: str, message: dict) -> dict:
        key = message.get("key") or {}
        remote_jid = str(key.get("remoteJid") or message.get("remoteJid") or "")
        if not remote_jid or remote_jid.endswith(("@g.us", "@broadcast", "@newsletter")):
            return {"ignored": True, "reason": "unsupported_conversation"}
        phone = normalize_phone(remote_jid.split("@")[0])
        message_id = str(key.get("id") or message.get("id") or "")
        if not phone or not message_id:
            return {"ignored": True, "reason": "missing_identity"}

        contact_id = stable_id(phone)
        conversation_id = stable_id(instance_name, phone)
        document_id = stable_id(instance_name, message_id)
        message_ref = self.messages.document(document_id)
        if message_ref.get().exists:
            return {"duplicate": True, "message_id": document_id}

        from_me = bool(key.get("fromMe", message.get("fromMe", False)))
        text = extract_message_text(message)
        raw_timestamp = message.get("messageTimestamp") or message.get("timestamp")
        try:
            message_time = datetime.fromtimestamp(int(raw_timestamp), timezone.utc)
        except (TypeError, ValueError, OSError):
            message_time = utc_now()
        name = str(message.get("pushName") or message.get("notifyName") or phone)

        contact_ref = self.contacts.document(contact_id)
        existing = contact_ref.get()
        existing_data = existing.to_dict() or {}
        instance_names = sorted(set(existing_data.get("instance_names", [])) | {instance_name})
        lead_id = (
            existing_data.get("prospect_lead_id")
            or str(message.get("prospect_lead_id") or "").strip()
            or self._find_existing_lead(phone)
        )
        latest_contact_at = existing_data.get("last_interaction_at")
        is_latest_contact = not isinstance(latest_contact_at, datetime) or message_time >= latest_contact_at
        existing_first_contact = existing_data.get("first_contact_at")
        first_contact_at = (
            min(existing_first_contact, message_time)
            if isinstance(existing_first_contact, datetime)
            else message_time
        )
        contact_payload = {
            "phone": phone,
            "name": name if name != phone else existing_data.get("name", name),
            "stage_id": existing_data.get("stage_id") or self._default_stage_id(),
            "instance_names": instance_names,
            "first_contact_at": first_contact_at,
            "message_count": firestore.Increment(1),
            "prospect_lead_id": lead_id,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
        if is_latest_contact:
            contact_payload.update({
                "last_instance_name": instance_name,
                "last_message": text,
                "last_message_direction": "outbound" if from_me else "inbound",
                "last_interaction_at": message_time,
            })
        conversation_ref = self.conversations.document(conversation_id)
        conversation_data = conversation_ref.get().to_dict() or {}
        existing_first_conversation = conversation_data.get("first_contact_at")
        first_conversation_at = (
            min(existing_first_conversation, message_time)
            if isinstance(existing_first_conversation, datetime)
            else message_time
        )
        latest_conversation_at = conversation_data.get("last_interaction_at")
        is_latest_conversation = not isinstance(latest_conversation_at, datetime) or message_time >= latest_conversation_at
        conversation_payload = {
            "contact_id": contact_id, "instance_name": instance_name, "phone": phone,
            "first_contact_at": first_conversation_at,
            "message_count": firestore.Increment(1), "updated_at": firestore.SERVER_TIMESTAMP,
        }
        if is_latest_conversation:
            conversation_payload.update({
                "last_message": text,
                "last_message_direction": "outbound" if from_me else "inbound",
                "last_interaction_at": message_time,
            })
        batch = self.db.batch()
        batch.set(contact_ref, contact_payload, merge=True)
        batch.set(conversation_ref, conversation_payload, merge=True)
        batch.create(message_ref, {
            "contact_id": contact_id, "conversation_id": conversation_id, "instance_name": instance_name,
            "external_message_id": message_id, "phone": phone, "from_me": from_me,
            "direction": "outbound" if from_me else "inbound", "text": text,
            "message_type": str(message.get("messageType") or "unknown"),
            "message_timestamp": message_time, "created_at": firestore.SERVER_TIMESTAMP,
        })
        try:
            batch.commit()
        except AlreadyExists:
            return {"duplicate": True, "message_id": document_id}
        self.save_instance(instance_name, {"last_event_at": message_time, "status": "connected"})
        return {"stored": True, "contact_id": contact_id, "message_id": document_id}

    def dashboard(self, instance_name: str = "") -> dict:
        stages = self.list_stages()
        contacts = self.list_contacts(instance_name=instance_name)
        counts = {stage["id"]: 0 for stage in stages}
        for contact in contacts:
            counts[contact.get("stage_id")] = counts.get(contact.get("stage_id"), 0) + 1
        return {
            "stages": stages,
            "instances": self.list_instances(),
            "contacts": contacts,
            "counts": counts,
            "total_contacts": len(contacts),
        }


def extract_message_text(message: dict) -> str:
    content = message.get("message") or {}
    if not isinstance(content, dict):
        return "[Mensagem]"
    direct = content.get("conversation")
    if direct:
        return str(direct)
    candidates = (
        ("extendedTextMessage", "text"), ("imageMessage", "caption"),
        ("videoMessage", "caption"), ("documentMessage", "caption"),
        ("buttonsResponseMessage", "selectedDisplayText"),
        ("listResponseMessage", "title"),
    )
    for group, field in candidates:
        value = (content.get(group) or {}).get(field)
        if value:
            return str(value)
    labels = {
        "audioMessage": "[Áudio]", "imageMessage": "[Imagem]", "videoMessage": "[Vídeo]",
        "documentMessage": "[Documento]", "stickerMessage": "[Figurinha]", "locationMessage": "[Localização]",
        "contactMessage": "[Contato]",
    }
    for key, label in labels.items():
        if key in content:
            return label
    return "[Mensagem não textual]"

