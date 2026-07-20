from __future__ import annotations

import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

from complexation_explorer.database import (
    DEFAULT_DB_PATH,
    SearchFilters,
    connect_readonly,
    count_constants,
    get_database_summary,
    get_ligand_identity_matches,
    get_record_detail,
    get_record_relationships,
    list_metals,
    resolve_database_path,
    search_constants,
    search_record_ids,
)
from complexation_explorer.formatting import (
    chemical_markup_to_unicode,
    equilibrium_to_unicode,
    formula_to_unicode,
    record_comparison_rows,
    short_record_id,
)


@unittest.skipUnless(DEFAULT_DB_PATH.is_file(), "rebuilt SRD 46 database not available")
class DatabaseTests(unittest.TestCase):
    def test_database_is_enforced_read_only(self):
        with closing(connect_readonly()) as connection:
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("CREATE TABLE should_fail (id INTEGER)")

    def test_environment_can_select_a_curated_database(self):
        configured = str(DEFAULT_DB_PATH.resolve())
        with patch.dict("os.environ", {"COMPLEXATION_DB_PATH": configured}):
            self.assertEqual(resolve_database_path(), DEFAULT_DB_PATH.resolve())

    def test_summary_matches_unified_sources(self):
        summary = get_database_summary()
        self.assertEqual(summary["source_ids"], ["NIST_SRD46", "SUPPLEMENT"])
        self.assertEqual(summary["ligands"], 5_931)
        self.assertEqual(summary["constants"], 90_105)
        self.assertEqual(summary["deduplicated_constants"], 90_090)
        self.assertEqual(summary["strict_duplicate_records"], 15)
        self.assertEqual(summary["exact_structure_ligand_links"], 50)
        self.assertEqual(summary["references_count"], 18_392)
        self.assertEqual(summary["log_k"], 60_771)
        self.assertEqual(summary["deduplicated_log_k"], 60_756)

    def test_all_metals_are_available(self):
        metals = list_metals()
        metal_codes = {row["metal_code"] for row in metals}
        self.assertEqual(len(metals), 230)
        self.assertTrue({"Ni", "Mn", "Co", "Fe", "Cu"}.issubset(metal_codes))

    def test_ni_two_log_k_count(self):
        ni_two = next(
            row for row in list_metals() if row["metal_code"] == "Ni"
        )
        filters = SearchFilters(metal_ids=(ni_two["metal_id"],), value_type="K")
        self.assertEqual(count_constants(filters), 4_154)
        rows = search_constants(filters, limit=5)
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(row["metal_id"] == ni_two["metal_id"] for row in rows))

    def test_literal_apostrophe_ligand_search(self):
        filters = SearchFilters(ligand_text="4,4'", value_type="K")
        self.assertGreater(count_constants(filters), 0)

    def test_empty_metal_filter_searches_all_metals(self):
        filters = SearchFilters(value_type="K")
        self.assertEqual(count_constants(filters), 60_756)
        self.assertEqual(
            count_constants(
                SearchFilters(value_type="K", include_strict_duplicates=True)
            ),
            60_771,
        )

    def test_duplicate_and_ligand_identity_relationships_are_queryable(self):
        relationships = get_record_relationships("SUPPLEMENT:CONSTANT:188")
        self.assertEqual(len(relationships), 1)
        self.assertEqual(relationships[0]["record_role"], "duplicate")
        self.assertEqual(
            relationships[0]["preferred_record_id"],
            "NIST_SRD46:CONSTANT:102025",
        )

        ligand_matches = get_ligand_identity_matches("SUPPLEMENT:LIGAND:178")
        self.assertEqual(len(ligand_matches), 1)
        self.assertEqual(
            ligand_matches[0]["matched_ligand_id"],
            "NIST_SRD46:LIGAND:5856",
        )

    def test_record_detail_round_trip(self):
        row = search_constants(SearchFilters(value_type="K"), limit=1)[0]
        detail = get_record_detail(row["record_id"])
        self.assertIsNotNone(detail)
        self.assertEqual(detail["record_id"], row["record_id"])

    def test_record_id_search_accepts_partial_case_insensitive_text(self):
        record_id = "NIST_SRD46:CONSTANT:100001"
        matches = search_record_ids("constant:100001".lower())
        self.assertIn(record_id, {row["record_id"] for row in matches})

    def test_record_id_search_prioritizes_exact_match_and_supports_exclusion(self):
        record_id = "NIST_SRD46:CONSTANT:100001"
        exact_matches = search_record_ids(record_id.lower())
        self.assertEqual(exact_matches[0]["record_id"], record_id)
        excluded_matches = search_record_ids("100001", exclude_record_id=record_id)
        self.assertNotIn(record_id, {row["record_id"] for row in excluded_matches})

    def test_record_id_search_treats_sql_wildcards_as_literal_text(self):
        self.assertEqual(search_record_ids("%_unlikely_literal_%"), [])

    def test_chemical_markup_formatting(self):
        self.assertEqual(chemical_markup_to_unicode("Ni<sup>2+</sup>"), "Ni²⁺")
        self.assertEqual(chemical_markup_to_unicode("ML<sub>2</sub>"), "ML₂")
        self.assertEqual(chemical_markup_to_unicode("H<sub>2</sub>O"), "H₂O")

    def test_nist_formula_formatting_is_conventional_and_non_destructive(self):
        self.assertEqual(formula_to_unicode("C7H7N1O2"), "C₇H₇NO₂")
        self.assertEqual(formula_to_unicode("Br1/-"), "Br⁻")
        self.assertEqual(formula_to_unicode("C6Fe1N6/3-"), "C₆FeN₆³⁻")
        self.assertEqual(formula_to_unicode("C8N8W/2-"), "C₈N₈W²⁻")
        self.assertEqual(formula_to_unicode("********"), "N/A")

    def test_equilibrium_quotient_formats_as_reaction_equation(self):
        self.assertEqual(
            equilibrium_to_unicode(
                "[ML<sub>2</sub>]/[M][L]<sup>2</sup>"
            ),
            "M + 2 L ⇌ ML₂",
        )
        self.assertEqual(
            equilibrium_to_unicode("[ML][H]/[M][HL]"),
            "M + HL ⇌ ML + H",
        )
        self.assertEqual(
            equilibrium_to_unicode("[M][L]/[ML(s)]"),
            "ML(s) ⇌ M + L",
        )
        self.assertEqual(equilibrium_to_unicode("*"), "N/A")

    def test_record_id_display_keeps_only_the_numeric_suffix(self):
        self.assertEqual(short_record_id("NIST_SRD46:CONSTANT:100001"), "100001")
        self.assertEqual(short_record_id("local-record"), "local-record")

    def test_record_comparison_formats_chemical_fields_and_labels_differences(self):
        selected = {
            "record_id": "NIST_SRD46:CONSTANT:100001",
            "metal": "Ni<sup>2+</sup>",
            "formula": "C7H7N1O2",
            "equilibrium_raw": "[ML<sub>2</sub>]/[M][L]<sup>2</sup>",
            "solvent_raw": "H<sub>2</sub>O",
        }
        comparison = {
            "record_id": "NIST_SRD46:CONSTANT:100002",
            "metal": "Ni<sup>2+</sup>",
            "formula": "Br1/-",
            "equilibrium_raw": "[ML]/[M][L]",
            "solvent_raw": "H<sub>2</sub>O",
        }
        rows = record_comparison_rows(selected, comparison)
        by_field = {row["Field"]: row for row in rows}
        self.assertEqual(by_field["Metal"]["Selected record"], "Ni²⁺")
        self.assertEqual(by_field["Record ID"]["Selected record"], "100001")
        self.assertEqual(by_field["Ligand formula"]["Selected record"], "C₇H₇NO₂")
        self.assertEqual(by_field["Equilibrium"]["Selected record"], "M + 2 L ⇌ ML₂")
        self.assertEqual(by_field["Solvent"]["Selected record"], "H₂O")
        self.assertEqual(by_field["Metal"]["Match"], "Same")
        self.assertEqual(by_field["Record ID"]["Match"], "Different")
        self.assertNotIn("Verification status", by_field)


if __name__ == "__main__":
    unittest.main()
