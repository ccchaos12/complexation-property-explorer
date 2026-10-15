"""Reference status codes must not masquerade as scientific values or judgments."""

from __future__ import annotations

import copy
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from complexation_explorer.database import SearchFilters, get_candidate_references, search_constants
from complexation_explorer.formatting import candidate_reference_rows, source_reference_status
from tests.support import create_test_database


def reference(flag, comment=None, reference_id="REF:1"):
    return {
        "reference_id": reference_id,
        "reference_code": "R1",
        "reference_text": "Author, Journal, 2020, 1–10",
        "not_used": flag,
        "comment": comment,
    }


class ReferencePresentationTests(unittest.TestCase):
    def test_flags_have_explicit_non_scientific_labels(self):
        for flag in (-1, 1, -1.0, "-1"):
            self.assertEqual(source_reference_status(flag), "Flagged as not used")
        self.assertEqual(source_reference_status(0), "Not flagged as unused")
        for flag in (None, "", "N/A", float("nan")):
            self.assertEqual(source_reference_status(flag), "Not reported")
        for flag in (2, -2, "unexpected"):
            self.assertEqual(source_reference_status(flag), "Unrecognized source flag")

    def test_conflicting_links_show_one_citation_and_preserve_both_comments(self):
        references = [reference(-1, "First note"), reference(0, "Second note")]
        original = copy.deepcopy(references)
        rows = candidate_reference_rows(references)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Source use status"], "Conflicting source flags")
        self.assertEqual(rows[0]["Comment"], "First note\nSecond note")
        self.assertEqual(references, original)
        self.assertNotIn("not_used", rows[0])

    def test_same_flag_and_missing_comments_do_not_duplicate_citations(self):
        rows = candidate_reference_rows([reference(-1), reference(-1)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Source use status"], "Flagged as not used")
        self.assertEqual(rows[0]["Comment"], "N/A")
        self.assertEqual(candidate_reference_rows([]), [])

    def test_missing_and_unknown_flags_are_not_silently_overridden(self):
        rows = candidate_reference_rows([reference(0), reference(None), reference(9)])
        self.assertEqual(rows[0]["Source use status"], "Mixed source flags — review metadata")

    def test_different_source_ids_remain_separate_even_with_identical_citations(self):
        rows = candidate_reference_rows([reference(-1), reference(0, reference_id="REF:2")])
        self.assertEqual(len(rows), 2)

    def test_ui_explains_reference_flags_without_changing_negative_log_k(self):
        from streamlit.testing.v1 import AppTest

        with tempfile.TemporaryDirectory() as directory:
            database = create_test_database(Path(directory) / "references.db")
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute(
                    "UPDATE ligand_metal_reference_candidates SET not_used_flag = -1"
                )
                connection.execute(
                    "UPDATE constant_records SET reported_value_text = '-1', numeric_value = -1 "
                    "WHERE record_id = 'NIST_SRD46:CONSTANT:100001'"
                )
            before = database.read_bytes()
            references = get_candidate_references(
                "NIST_SRD46:LIGAND:EDTA", "NIST_SRD46:METAL:NI2", database
            )
            self.assertEqual(references[0]["not_used"], -1)
            with patch.dict(os.environ, {"COMPLEXATION_DB_PATH": str(database)}):
                app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(
                    timeout=30
                )
                app.text_input(key="explorer_ligand_text").set_value("EDTA").run()
                self.assertEqual(list(app.exception), [])
                card = next(
                    item.value
                    for item in app.markdown
                    if '<p class="sce-reference-citation">' in item.value
                )
                self.assertIn("Flagged as not used", card)
                self.assertNotIn("-1", card)
                self.assertIn("-1", app.dataframe[0].value["Value"].tolist())
                raw_table = next(
                    item.value
                    for item in app.dataframe
                    if "Raw not_used flag" in item.value.columns
                )
                self.assertEqual(raw_table.iloc[0]["Raw not_used flag"], "-1")
                next(
                    button for button in app.button if button.label == "Prepare filtered CSV"
                ).click().run()
                self.assertIn(",-1,", app.session_state["_explorer_export_csv"].decode("utf-8-sig"))
            self.assertEqual(database.read_bytes(), before)
            row = search_constants(SearchFilters(ligand_text="EDTA", numeric_only=True), database)[
                0
            ]
            self.assertEqual(row["numeric_value"], -1)
