import unittest
from unittest.mock import AsyncMock

from backend.econodata import EconodataClient, EconodataInsufficientTokens, extract_matched_cnpj, normalize_cnpj, valid_cnpj
from backend.models import Lead


class EconodataTests(unittest.TestCase):
    def test_normalizes_and_validates_cnpj(self):
        self.assertEqual(normalize_cnpj("11.222.333/0001-81"), "11222333000181")
        self.assertTrue(valid_cnpj("11.222.333/0001-81"))
        self.assertFalse(valid_cnpj("11.222.333/0001-82"))

    def test_extracts_cnpj_from_nested_response(self):
        payload = {"correspondencias": [{"cnpj": "11.222.333/0001-81", "confianca": 0.92}]}
        self.assertEqual(extract_matched_cnpj(payload), "11222333000181")

    def test_ignores_other_numbers(self):
        payload = {"correspondencias": [], "telefone": "556133334444"}
        self.assertEqual(extract_matched_cnpj(payload), "")

    def test_reports_insufficient_tokens(self):
        response = AsyncMock()
        response.status_code = 402
        client = AsyncMock()
        client.post.return_value = response
        lead = Lead(date="13/08/2026", company_name="Empresa Teste", place_id="teste")
        with self.assertRaises(EconodataInsufficientTokens):
            __import__("asyncio").run(EconodataClient("secret").find_cnpj(client, lead))


if __name__ == "__main__":
    unittest.main()
