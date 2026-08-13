import unittest

from backend.econodata import extract_first_cnpj, normalize_cnpj, valid_cnpj


class EconodataTests(unittest.TestCase):
    def test_normalizes_and_validates_cnpj(self):
        self.assertEqual(normalize_cnpj("11.222.333/0001-81"), "11222333000181")
        self.assertTrue(valid_cnpj("11.222.333/0001-81"))
        self.assertFalse(valid_cnpj("11.222.333/0001-82"))

    def test_extracts_cnpj_from_nested_response(self):
        payload = {"resultados": [{"empresa": {"cnpj": "11.222.333/0001-81"}}]}
        self.assertEqual(extract_first_cnpj(payload), "11222333000181")

    def test_ignores_other_numbers(self):
        payload = {"telefone": "556133334444", "total": 25}
        self.assertEqual(extract_first_cnpj(payload), "")


if __name__ == "__main__":
    unittest.main()
