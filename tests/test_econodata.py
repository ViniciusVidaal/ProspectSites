import unittest
from unittest.mock import AsyncMock, Mock, patch

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
        response = Mock()
        response.status_code = 402
        client = AsyncMock()
        client.post.return_value = response
        lead = Lead(date="13/08/2026", company_name="Empresa Teste", place_id="teste")
        with self.assertRaises(EconodataInsufficientTokens):
            __import__("asyncio").run(EconodataClient("secret").find_cnpj(client, lead))

    def test_waits_and_retries_rate_limit(self):
        limited = Mock()
        limited.status_code = 429
        limited.headers = {"Retry-After": "1"}
        success = Mock()
        success.status_code = 200
        success.json.return_value = {"correspondencias": [{"cnpj": "11.222.333/0001-81"}]}
        client = AsyncMock()
        client.post.side_effect = [limited, success]
        lead = Lead(date="13/08/2026", company_name="Empresa Teste", place_id="teste")
        with patch("backend.econodata.asyncio.sleep", new=AsyncMock()) as sleeper:
            result = __import__("asyncio").run(EconodataClient("secret").find_cnpj(client, lead))
        self.assertEqual(result, "11222333000181")
        self.assertEqual(client.post.await_count, 2)
        sleeper.assert_awaited_once_with(1.0)


if __name__ == "__main__":
    unittest.main()
