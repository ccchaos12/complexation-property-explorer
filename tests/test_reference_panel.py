"""Bibliography actions retain provenance and operate on all search matches."""

from __future__ import annotations

import copy
import csv
import io
import unittest

from complexation_explorer.references import (
    DIRECT,
    bibliography_csv,
    bibliography_entries,
    bibliography_text,
    citation_links,
    filter_bibliography,
)
from tests.test_references import reference


def panel_fixture():
    import streamlit as st

    from complexation_explorer.reference_panel import render_reference_panel

    record = st.selectbox("Record", ["REC:1", "REC:2", "EMPTY"])
    refs = [
        {
            "reference_id": f"REF:{index}",
            "reference_code": f"R{index}",
            "reference_text": f"Author {index}, Journal, 2020, 1–10",
            "not_used": 0,
            "comment": None,
        }
        for index in range(25)
    ]
    detail = {"record_id": record, "verified_reference_id": "REF:0"}
    if record == "EMPTY":
        detail["verified_reference_id"] = None
        refs = []
    render_reference_panel(detail, refs)


class BibliographyTests(unittest.TestCase):
    def test_promote_exact_reference_once_without_losing_conflicting_metadata(self):
        refs = [reference(-1, "Note A"), reference(0, "Note B")]
        original = copy.deepcopy(refs)
        rows = bibliography_entries({"record_id": "REC:1", "verified_reference_id": "REF:1"}, refs)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Link type"], DIRECT)
        self.assertEqual(rows[0]["Source use status"], "Conflicting source flags")
        self.assertEqual(rows[0]["Comment"], "Note A\nNote B")
        self.assertEqual(len(rows[0]["raw_links"]), 2)
        rows[0]["raw_links"][0]["comment"] = "Changed copy"
        self.assertEqual(refs, original)

    def test_direct_reference_without_pair_links_remains_exportable(self):
        rows = bibliography_entries(
            {
                "record_id": "REC:1",
                "verified_reference_id": "DIRECT:1",
                "verified_reference_code": "D1",
                "verified_reference": "张, Author, 2024",
            },
            [],
        )
        exported = list(csv.DictReader(io.StringIO(bibliography_csv(rows).decode("utf-8-sig"))))
        self.assertEqual(exported[0]["Record ID"], "REC:1")
        self.assertEqual(exported[0]["Link type"], DIRECT)
        self.assertEqual(exported[0]["Reference"], "张, Author, 2024")
        self.assertNotIn("raw_links", exported[0])
        self.assertEqual(bibliography_text(rows), "张, Author, 2024")

    def test_search_matches_terms_across_citation_code_and_comments(self):
        rows = bibliography_entries({"record_id": "REC:1"}, [reference(-1, "Archive note")])
        self.assertEqual(filter_bibliography(rows, "  AUTHOR r1 archive  "), rows)
        self.assertEqual(filter_bibliography(rows, "2021"), [])
        self.assertEqual(filter_bibliography(rows, ""), rows)
        self.assertEqual(
            len(list(csv.DictReader(io.StringIO(bibliography_csv([]).decode("utf-8-sig"))))), 0
        )

    def test_links_require_explicit_safe_identifiers(self):
        self.assertEqual(citation_links("Author, Journal, 2024, 1–10"), [])
        self.assertEqual(
            citation_links("javascript:alert(1) https://user:secret@example.org/paper"), []
        )
        self.assertEqual(
            citation_links("DOI: 10.1234/abc(1). https://example.org/paper; 10.1234/abc(1)"),
            ["https://doi.org/10.1234/abc(1)", "https://example.org/paper"],
        )
        self.assertEqual(
            citation_links("(https://doi.org/10.1234/paper)."), ["https://doi.org/10.1234/paper"]
        )

    def test_panel_paginates_but_copy_contains_all_matches_and_search_resets(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_function(panel_fixture).run()
        self.assertEqual(list(app.exception), [])

        def cards():
            return [
                item.value
                for item in app.markdown
                if '<p class="sce-reference-citation">' in item.value
            ]

        self.assertEqual(len(cards()), 11)  # one direct plus ten related
        self.assertTrue(all("Not flagged as unused" not in card for card in cards()))
        self.assertIn("Author 24,", app.code[0].value)
        app.button(key="reference_show_more").click().run()
        self.assertEqual(len(cards()), 21)
        app.text_input(key="reference_search_REC:1").set_value("Author 24,").run()
        self.assertEqual(len(cards()), 1)
        self.assertEqual(app.code[0].value, "Author 24, Journal, 2020, 1–10")
        app.text_input(key="reference_search_REC:1").set_value("").run()
        self.assertEqual(len(cards()), 11)
        app.button(key="reference_show_more").click().run()
        app.selectbox[0].set_value("REC:2").run()
        self.assertEqual(len(cards()), 11)
        self.assertEqual(list(app.exception), [])

    def test_empty_search_disables_actions_and_empty_record_explains_absence(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_function(panel_fixture).run()
        app.text_input(key="reference_search_REC:1").set_value("No such paper").run()
        self.assertTrue(any("No references match" in item.value for item in app.info))
        self.assertTrue(app.get("download_button")[0].proto.disabled)
        app.selectbox[0].set_value("EMPTY").run()
        self.assertTrue(any("No direct or related references" in item.value for item in app.info))
        self.assertEqual(list(app.exception), [])

    def test_citation_html_is_escaped(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_string("""
from complexation_explorer.reference_panel import render_reference_panel
render_reference_panel({"record_id": "REC:1", "verified_reference_id": "REF:1", "verified_reference": '<script>alert(1)</script> & Author'}, [])
""").run()
        card = next(item.value for item in app.markdown if "sce-reference-citation" in item.value)
        self.assertIn("&lt;script&gt;", card)
        self.assertNotIn("<script>", card)
        self.assertEqual(list(app.exception), [])
