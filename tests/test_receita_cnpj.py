import sqlite3
import unittest

from colab.receita_cnpj import match_lead, name_similarity


def database_with(*rows):
    connection = sqlite3.connect(":memory:")
    connection.execute("""CREATE TABLE candidatos (
        cnpj TEXT PRIMARY KEY, fantasia TEXT, razao TEXT, cidade TEXT,
        uf TEXT, situacao TEXT, telefone TEXT
    )""")
    connection.execute("CREATE VIRTUAL TABLE candidate_search USING fts5(search_text)")
    for row in rows:
        cursor = connection.execute(
            "INSERT INTO candidatos VALUES (?,?,?,?,?,?,?)", row
        )
        connection.execute(
            "INSERT INTO candidate_search(rowid,search_text) VALUES (?,?)",
            (cursor.lastrowid, f"{row[1]} {row[2]}"),
        )
    return connection


class ReceitaCnpjMatcherTests(unittest.TestCase):
    def test_accepts_legal_suffix_without_weakening_the_name(self):
        score, coverage = name_similarity("Padaria X", "Padaria X LTDA")
        self.assertEqual(score, 100)
        self.assertEqual(coverage, 1)

    def test_rejects_generic_partial_name(self):
        score, coverage = name_similarity(
            "Centro Odontologico Dra Marcella Decarli", "Centro LTDA"
        )
        self.assertEqual((score, coverage), (0, 0))

    def test_only_marks_unique_name_and_location_as_automatic(self):
        connection = database_with(
            ("11222333000181", "PADARIA X", "PADARIA X LTDA", "BRASILIA", "DF", "02", "556133334444"),
            ("99888777000166", "PADARIA X", "PADARIA X LTDA", "NATAL", "RN", "02", "558433334444"),
        )
        match = match_lead(connection, "Padaria X", "Brasilia", "DF")
        self.assertEqual(match["cnpj"], "11222333000181")
        self.assertTrue(match["automatic"])

    def test_does_not_automate_generic_candidate(self):
        connection = database_with(
            ("11222333000181", "CENTRO", "CENTRO SERVICOS LTDA", "BRASILIA", "DF", "02", "556133334444"),
        )
        self.assertIsNone(
            match_lead(connection, "Centro Odontologico Dra Marcella Decarli", "Brasilia", "DF")
        )


if __name__ == "__main__":
    unittest.main()
