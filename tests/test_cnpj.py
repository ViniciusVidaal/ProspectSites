import unittest

from fastapi.encoders import jsonable_encoder

from backend.cnpj import _safe_public_url, find_matching_cnpj, find_matching_cnpj_texts, normalize_cnpj, valid_cnpj
from backend.models import Lead


class CnpjDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.lead = Lead(
            date="13/08/2026",
            company_name="Padaria X",
            phone="+55 61 3333-4444",
            place_id="place-brasilia",
            address="Asa Norte, Brasília - DF, Brasil",
            city="Brasília",
            state="DF",
        )

    def test_normalizes_and_validates_cnpj(self):
        self.assertEqual(normalize_cnpj("11.222.333/0001-81"), "11222333000181")
        self.assertTrue(valid_cnpj("11.222.333/0001-81"))
        self.assertFalse(valid_cnpj("11.222.333/0001-82"))

    def test_rejects_same_name_from_wrong_location(self):
        page = '<div class="result__body">Padaria X Recife PE CNPJ 11.222.333/0001-81</div>'
        self.assertEqual(find_matching_cnpj(page, self.lead), "")

    def test_accepts_matching_name_and_location(self):
        page = '<div class="result__body">Padaria X Brasília DF CNPJ 11.222.333/0001-81</div>'
        self.assertEqual(find_matching_cnpj(page, self.lead), "11222333000181")

    def test_accepts_structured_search_snippet(self):
        snippets = ["Padaria X - CNPJ 11.222.333/0001-81, localizada em Brasília, DF"]
        self.assertEqual(find_matching_cnpj_texts(snippets, self.lead), "11222333000181")

    def test_accepts_matching_phone_when_location_is_absent(self):
        lead = self.lead.model_copy(update={"city": "", "state": "", "address": ""})
        snippets = ["Padaria X telefone (61) 3333-4444 CNPJ 11.222.333/0001-81"]
        self.assertEqual(find_matching_cnpj_texts(snippets, lead), "11222333000181")

    def test_public_payload_hides_cnpj_and_location(self):
        lead = self.lead.model_copy(update={"cnpj": "11222333000181", "cnpj_captured": True})
        payload = jsonable_encoder(lead)
        self.assertNotIn("cnpj", payload)
        self.assertNotIn("address", payload)
        self.assertTrue(payload["cnpj_captured"])

    def test_rejects_private_result_urls(self):
        self.assertFalse(_safe_public_url("http://127.0.0.1/internal"))
        self.assertFalse(_safe_public_url("http://localhost/internal"))
        self.assertTrue(_safe_public_url("https://example.com/company"))


if __name__ == "__main__":
    unittest.main()
