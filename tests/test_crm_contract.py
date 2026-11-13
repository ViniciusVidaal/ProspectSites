import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from backend.crm_models import HermesEvent
from backend.crm_repository import extract_message_text, normalize_phone
from backend.crm_router import authenticate_hermes, hermes_event


class HermesContractTests(unittest.TestCase):
    def test_accepts_normalized_message_event(self):
        event = HermesEvent.model_validate({
            "event": "message.upsert",
            "event_id": "evt-message-001",
            "instance": "whatsapp-01",
            "occurred_at": "2026-11-13T15:00:00Z",
            "data": {
                "message_id": "BAILEYS-001",
                "phone": "55 (11) 99999-9999",
                "text": "Olá",
                "from_me": False,
            },
        })
        self.assertEqual(event.instance, "whatsapp-01")
        self.assertEqual(event.event, "message.upsert")

    def test_rejects_unknown_event(self):
        with self.assertRaises(ValidationError):
            HermesEvent.model_validate({
                "event": "unknown.event",
                "event_id": "evt-unknown",
                "instance": "whatsapp-01",
            })

    def test_normalizes_brazilian_phone(self):
        self.assertEqual(normalize_phone("(11) 99999-9999"), "5511999999999")
        self.assertEqual(normalize_phone("5511999999999@s.whatsapp.net"), "5511999999999")

    def test_extracts_baileys_text(self):
        self.assertEqual(
            extract_message_text({"message": {"extendedTextMessage": {"text": "Tenho interesse"}}}),
            "Tenho interesse",
        )

    @patch("backend.crm_router.get_settings")
    def test_authenticates_hermes_secret(self, get_settings):
        get_settings.return_value = SimpleNamespace(hermes_webhook_secret="secret-123")
        authenticate_hermes("secret-123", None)
        authenticate_hermes(None, "Bearer secret-123")

    @patch("backend.crm_router.get_settings")
    def test_rejects_invalid_hermes_secret(self, get_settings):
        get_settings.return_value = SimpleNamespace(hermes_webhook_secret="secret-123")
        with self.assertRaises(HTTPException) as context:
            authenticate_hermes("wrong-secret", None)
        self.assertEqual(context.exception.status_code, 401)

    @patch("backend.crm_router.repository")
    @patch("backend.crm_router.get_settings")
    def test_dispatches_hermes_stage_change(self, get_settings, repository):
        get_settings.return_value = SimpleNamespace(hermes_webhook_secret="secret-123")
        repo = MagicMock()
        repo.begin_integration_event.return_value = True
        repo.upsert_contact.return_value = {"id": "contact-1"}
        repo.resolve_stage.return_value = {"id": "contato"}
        repo.move_contact.return_value = {"id": "contact-1", "stage_id": "contato"}
        repository.return_value = repo
        event = HermesEvent.model_validate({
            "event": "lead.stage.changed",
            "event_id": "evt-stage-001",
            "instance": "whatsapp-01",
            "data": {"phone": "5511999999999", "stage": "Em contato", "reason": "Lead respondeu"},
        })

        result = hermes_event(event, x_hermes_secret="secret-123", authorization=None)

        self.assertTrue(result["accepted"])
        self.assertFalse(result["duplicate"])
        repo.move_contact.assert_called_once_with(
            "contact-1", "contato", actor="hermes",
            reason="Lead respondeu", source_event_id="evt-stage-001",
        )

    @patch("backend.crm_router.repository")
    @patch("backend.crm_router.get_settings")
    def test_does_not_process_duplicate_hermes_event(self, get_settings, repository):
        get_settings.return_value = SimpleNamespace(hermes_webhook_secret="secret-123")
        repo = MagicMock()
        repo.begin_integration_event.return_value = False
        repository.return_value = repo
        event = HermesEvent.model_validate({
            "event": "heartbeat",
            "event_id": "evt-heartbeat-001",
            "instance": "whatsapp-01",
            "data": {"status": "connected"},
        })

        result = hermes_event(event, x_hermes_secret="secret-123", authorization=None)

        self.assertTrue(result["duplicate"])
        repo.save_instance.assert_not_called()


if __name__ == "__main__":
    unittest.main()
