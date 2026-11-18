"""Isolated API integration test; never connects to a real Firebase project."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from backend.crm_repository import CrmRepository, stable_id
from backend.firestore_repository import FirestoreRepository
from backend.crm_router import router


@unittest.skipUnless(os.environ.get("FIRESTORE_EMULATOR_HOST") == "127.0.0.1:8787", "emulador isolado não iniciado")
class CrmEmulatorTests(unittest.TestCase):
    def test_hermes_lookup_and_move_persist_with_idempotent_retry(self):
        db = firestore.Client(project="demo-prospectsites-qa", credentials=AnonymousCredentials())
        run_id = uuid4().hex[:8]
        place_id = f"TESTE_QA_{run_id}"
        event_id = f"TESTE_QA_move_{run_id}"
        instance = f"teste_qa_{run_id}"
        phone = f"55619{int(run_id, 16) % 100000000:08d}"
        crm = object.__new__(CrmRepository)
        crm.db = db
        for attribute, name in (("contacts", "crm_contacts"), ("conversations", "crm_conversations"),
                                ("messages", "crm_messages"), ("stages", "crm_stages"),
                                ("instances", "crm_whatsapp_instances"), ("activities", "crm_activities"),
                                ("integration_events", "crm_integration_events")):
            setattr(crm, attribute, db.collection(name))
        leads = object.__new__(FirestoreRepository)
        leads.collection = db.collection("leads")
        leads.blocklist = db.collection("archived_lead_ids")
        leads.blocklist.document(place_id).set({
            "place_id": place_id, "company_name": "TESTE QA — Empresa Fictícia",
            "phone": phone, "phone_digits": phone, "archived": True,
        })
        contact_id = stable_id(phone)
        for reference in (leads.blocklist.document(place_id), crm.contacts.document(contact_id),
                          crm.instances.document(instance), crm.integration_events.document(stable_id("hermes", event_id))):
            self.addCleanup(reference.delete)
        self.addCleanup(lambda: [snapshot.reference.delete() for snapshot in crm.activities.where("contact_id", "==", contact_id).stream()])
        crm.stages.document("qa_atendimento").set({"name": "TESTE QA — Atendimento", "position": 0})
        crm.stages.document("qa_analise").set({"name": "TESTE QA — Análise", "position": 1})
        self.addCleanup(crm.stages.document("qa_atendimento").delete)
        self.addCleanup(crm.stages.document("qa_analise").delete)
        app = FastAPI()
        app.include_router(router)
        headers = {"X-Hermes-Secret": "local-test-only"}
        with patch("backend.crm_router.get_settings", return_value=SimpleNamespace(hermes_webhook_secret="local-test-only")), \
             patch("backend.crm_router.repository", return_value=crm), \
             patch("backend.crm_router.lead_repository", return_value=leads), TestClient(app) as client:
            lookup = client.post("/api/crm/integrations/hermes/prospects/lookup", json={"phone": phone}, headers=headers)
            self.assertEqual(lookup.status_code, 200, lookup.text)
            self.assertEqual(lookup.json()["matches"][0]["place_id"], place_id)
            body = {"event": "lead.stage.changed", "event_id": event_id, "instance": instance, "data": {
                "phone": phone, "name": "TESTE QA — Empresa Fictícia", "lead_place_id": place_id, "stage_id": "qa_analise", "reason": "Teste isolado"}}
            moved = client.post("/api/crm/integrations/hermes/events", json=body, headers=headers)
            self.assertEqual(moved.status_code, 202, moved.text)
            self.assertEqual(moved.json()["result"]["stage_id"], "qa_analise")
            repeated = client.post("/api/crm/integrations/hermes/events", json=body, headers=headers)
            self.assertTrue(repeated.json()["duplicate"])
            contact_id = moved.json()["result"]["id"]
            self.assertEqual(crm.contacts.document(contact_id).get().to_dict()["stage_id"], "qa_analise")
            self.assertEqual(len(list(crm.activities.where("contact_id", "==", contact_id).stream())), 1)


if __name__ == "__main__":
    unittest.main()
