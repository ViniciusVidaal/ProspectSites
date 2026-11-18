import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import BackgroundTasks, HTTPException, Response
from pydantic import ValidationError

from backend.crm_models import HermesAnalysisRequest, HermesEvent, HermesProspectLookup
from backend.crm_repository import CrmRepository, extract_message_text, normalize_phone
from backend.crm_router import authenticate_hermes, hermes_archived_prospect, hermes_event, hermes_lookup_prospect, hermes_start_analysis
from backend.firestore_repository import FirestoreRepository


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

    @patch("backend.crm_router.lead_repository")
    @patch("backend.crm_router.get_settings")
    def test_hermes_can_read_archived_profile_by_place_id(self, get_settings, lead_repository):
        get_settings.return_value = SimpleNamespace(hermes_webhook_secret="secret-123")
        repo = MagicMock()
        repo.get_prospect_profile.return_value = {
            "place_id": "place-123",
            "company_name": "Empresa Arquivada",
            "address": "Rua A, 10 - Centro",
            "archived": True,
        }
        lead_repository.return_value = repo

        result = hermes_archived_prospect(
            "place-123",
            x_hermes_secret="secret-123",
            authorization=None,
        )

        self.assertEqual(result["company_name"], "Empresa Arquivada")
        self.assertTrue(result["archived"])
        repo.get_prospect_profile.assert_called_once_with("place-123")

    def test_crm_links_reply_to_archived_profile_by_phone(self):
        repo = object.__new__(CrmRepository)
        repo.db = MagicMock()
        active_collection = MagicMock()
        active_collection.limit.return_value.stream.return_value = []
        archived_collection = MagicMock()
        archived_snapshot = MagicMock()
        archived_snapshot.id = "place-archived"
        archived_snapshot.to_dict.return_value = {"place_id": "place-archived"}
        archived_collection.where.return_value.limit.return_value.stream.return_value = [archived_snapshot]
        repo.db.collection.side_effect = lambda name: active_collection if name == "leads" else archived_collection

        result = repo._find_existing_lead("5561999999999")

        self.assertEqual(result, "place-archived")
        archived_collection.where.assert_called_once_with("phone_digits", "==", "5561999999999")

    @patch("backend.crm_router.lead_repository")
    @patch("backend.crm_router.get_settings")
    def test_lookup_requires_secret_before_reading(self, get_settings, lead_repository):
        get_settings.return_value = SimpleNamespace(hermes_webhook_secret="secret-123")
        with self.assertRaises(HTTPException) as result:
            hermes_lookup_prospect(HermesProspectLookup(phone="61999999999"), Response(), "wrong", None)
        self.assertEqual(result.exception.status_code, 401)
        lead_repository.assert_not_called()

    def test_phone_lookup_reports_duplicates_and_scan_limit(self):
        repo = object.__new__(FirestoreRepository)
        repo.collection = MagicMock()
        repo.blocklist = MagicMock()
        snapshots = []
        for index in range(3):
            item = MagicMock()
            item.to_dict.return_value = {"phone": "61999999999" if index < 2 else ""}
            snapshots.append(item)
        repo.collection.limit.return_value.stream.return_value = snapshots
        repo.blocklist.where.return_value.limit.return_value.stream.return_value = []
        with patch.object(repo, "_lead", side_effect=[
            SimpleNamespace(place_id=str(i), company_name="Empresa", phone="61999999999", address="", neighborhood="", city="", state="", maps_link="", archived=False)
            for i in range(2)
        ]):
            result = repo.find_prospects_by_phone("5561999999999", scan_limit=2)
        self.assertEqual(len(result["matches"]), 2)
        self.assertTrue(result["active_scan_limited"])
        self.assertTrue(result["requires_confirmation"])

    @patch("backend.crm_router.get_settings")
    def test_analysis_requires_customer_acceptance(self, get_settings):
        import asyncio
        get_settings.return_value = SimpleNamespace(hermes_webhook_secret="secret-123")
        request = HermesAnalysisRequest(place_id="place-1", phone="61999999999", customer_accepted=False)
        with self.assertRaises(HTTPException) as result:
            asyncio.run(hermes_start_analysis(request, BackgroundTasks(), "secret-123", None))
        self.assertEqual(result.exception.status_code, 422)

    @patch("backend.crm_router.lead_repository")
    @patch("backend.crm_router.get_settings")
    def test_analysis_rejects_ambiguous_phone(self, get_settings, lead_repository):
        import asyncio
        get_settings.return_value = SimpleNamespace(hermes_webhook_secret="secret-123")
        lead_repository.return_value.find_prospects_by_phone.return_value = {
            "matches": [{"place_id": "place-1"}, {"place_id": "place-2"}],
            "active_scan_limited": False, "archived_results_limited": False,
        }
        request = HermesAnalysisRequest(place_id="place-1", phone="61999999999", customer_accepted=True)
        with self.assertRaises(HTTPException) as result:
            asyncio.run(hermes_start_analysis(request, BackgroundTasks(), "secret-123", None))
        self.assertEqual(result.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
