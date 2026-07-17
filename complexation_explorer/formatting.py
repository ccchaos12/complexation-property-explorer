"""Small display helpers kept separate from database queries."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping

SUPERSCRIPT = str.maketrans("0123456789+-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻")
SUBSCRIPT = str.maketrans("0123456789+-", "₀₁₂₃₄₅₆₇₈₉₊₋")

COMPARISON_FIELDS = (
    ("Record ID", "record_id", "record_id"),
    ("Metal", "metal", "chemical"),
    ("Ligand", "ligand", "plain"),
    ("Ligand formula", "formula", "formula"),
    ("Ligand class", "ligand_class", "plain"),
    ("Equilibrium", "equilibrium_raw", "equilibrium"),
    ("Value type", "value_type", "plain"),
    ("Reported value", "reported_value_text", "plain"),
    ("Parsed numeric value", "numeric_value", "plain"),
    ("Source standardized value", "source_standardized_value_text", "plain"),
    ("Uncertainty", "uncertainty_raw", "plain"),
    ("Temperature", "temperature_raw", "plain"),
    ("Ionic strength", "ionic_strength_raw", "plain"),
    ("Solvent", "solvent_raw", "chemical"),
    ("Electrolyte", "electrolyte_raw", "chemical"),
    ("Footnote", "footnote_raw", "chemical"),
)

FORMULA_TOKEN = re.compile(r"([A-Z][a-z]?)(\d*)")
EQUILIBRIUM_TERM = re.compile(
    r"\[([^\[\]]+)\](?:<sup>([^<>]*)</sup>)?",
    flags=re.IGNORECASE,
)

DATA_NOTE_LABELS = {
    "reported_value_not_strict_numeric": "Source value uses non-numeric notation",
    "unclassified_value_type": "Source value type is unclassified",
    "missing_equilibrium_definition": "Equilibrium definition unavailable",
}


def chemical_markup_to_unicode(value: str | None) -> str:
    if not value:
        return "N/A"

    def superscript(match: re.Match) -> str:
        return match.group(1).translate(SUPERSCRIPT)

    def subscript(match: re.Match) -> str:
        return match.group(1).translate(SUBSCRIPT)

    value = re.sub(r"<sup>(.*?)</sup>", superscript, value, flags=re.IGNORECASE)
    value = re.sub(r"<sub>(.*?)</sub>", subscript, value, flags=re.IGNORECASE)
    return value


def formula_to_unicode(value: str | None) -> str:
    """Render the compact NIST element-count and charge notation as a formula."""
    if not value:
        return "N/A"

    raw_value = value.strip()
    if not raw_value or set(raw_value) == {"*"}:
        return "N/A"

    formula_text, separator, charge_text = raw_value.partition("/")
    position = 0
    formatted_tokens = []
    for match in FORMULA_TOKEN.finditer(formula_text):
        if match.start() != position:
            return chemical_markup_to_unicode(raw_value)
        element, count = match.groups()
        formatted_tokens.append(element)
        if count and count != "1":
            formatted_tokens.append(count.translate(SUBSCRIPT))
        position = match.end()

    if not formatted_tokens or position != len(formula_text):
        return chemical_markup_to_unicode(raw_value)

    formatted = "".join(formatted_tokens)
    if separator:
        normalized_charge = charge_text.strip()
        if not re.fullmatch(r"(?:\d+)?[+-]", normalized_charge):
            return chemical_markup_to_unicode(raw_value)
        formatted += normalized_charge.translate(SUPERSCRIPT)
    return formatted


def _equilibrium_side_terms(value: str) -> list[str] | None:
    terms = []
    position = 0
    for match in EQUILIBRIUM_TERM.finditer(value):
        if value[position : match.start()].strip():
            return None
        species, coefficient = match.groups()
        formatted_species = chemical_markup_to_unicode(species)
        if coefficient:
            normalized_coefficient = coefficient.strip()
            if not re.fullmatch(r"\d+(?:\.\d+)?", normalized_coefficient):
                return None
            if normalized_coefficient != "1":
                terms.append(f"{normalized_coefficient} {formatted_species}")
            else:
                terms.append(formatted_species)
        else:
            terms.append(formatted_species)
        position = match.end()
    if value[position:].strip() or not terms:
        return None
    return terms


def _split_equilibrium_quotient(value: str) -> tuple[str, str] | None:
    """Split on the quotient slash while ignoring slashes in HTML closing tags."""
    separators = []
    inside_tag = False
    for index, character in enumerate(value):
        if character == "<":
            inside_tag = True
        elif character == ">":
            inside_tag = False
        elif character == "/" and not inside_tag:
            separators.append(index)
    if len(separators) != 1:
        return None
    separator = separators[0]
    return value[:separator], value[separator + 1 :]


def equilibrium_to_unicode(value: str | None) -> str:
    """Render a NIST equilibrium quotient as a symbolic reaction equation."""
    if not value:
        return "N/A"

    raw_value = value.strip()
    if not raw_value or raw_value == "*":
        return "N/A"
    quotient_sides = _split_equilibrium_quotient(raw_value)
    if quotient_sides is None:
        return chemical_markup_to_unicode(raw_value)

    products_text, reactants_text = quotient_sides
    products = _equilibrium_side_terms(products_text)
    reactants = _equilibrium_side_terms(reactants_text)
    if products is None or reactants is None:
        return chemical_markup_to_unicode(raw_value)
    return f"{' + '.join(reactants)} ⇌ {' + '.join(products)}"


def short_record_id(value: object) -> str:
    """Show only a Record ID's final numeric component without changing its key."""
    text = display_value(value)
    match = re.search(r"(\d+)$", text)
    return match.group(1) if match else text


def display_record_id(
    value: object,
    source_id: object | None = None,
    *,
    include_source: bool = False,
) -> str:
    """Keep IDs compact while adding a namespace when multiple sources coexist."""
    compact_id = short_record_id(value)
    if not include_source:
        return compact_id
    source = display_value(source_id)
    if source == "N/A":
        return compact_id
    normalized_source = source.upper()
    if normalized_source == "NIST_SRD46":
        source = "NIST"
    elif normalized_source == "LOCAL_XLSX":
        source = "LOCAL"
    return f"{source} · {compact_id}"


def data_note(row: Mapping[str, object]) -> str:
    """Translate internal quality flags into concise researcher-facing notes."""
    notes: list[str] = []
    raw_flags = row.get("quality_flags_json")
    try:
        parsed_flags = json.loads(str(raw_flags)) if raw_flags else []
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed_flags = []

    for flag in parsed_flags if isinstance(parsed_flags, list) else []:
        label = DATA_NOTE_LABELS.get(str(flag))
        if label and label not in notes:
            notes.append(label)

    formula = str(row.get("formula") or row.get("formula_raw") or "").strip()
    if not formula or set(formula) == {"*"}:
        notes.append("Ligand formula unavailable")

    reported_value = row.get("reported_value") or row.get("reported_value_text")
    if row.get("numeric_value") is None and reported_value not in (None, ""):
        numeric_note = "Source value uses non-numeric notation"
        if numeric_note not in notes:
            notes.append(numeric_note)

    return "; ".join(notes) if notes else "—"


def display_value(value: object) -> str:
    """Return a consistent display string without altering stored source values."""
    return "N/A" if value is None or value == "" else str(value)


def record_comparison_rows(
    selected: Mapping[str, object],
    comparison: Mapping[str, object],
    *,
    include_source_in_record_id: bool = False,
) -> list[dict[str, str]]:
    """Build an aligned, text-labelled comparison for two constant records."""
    rows = []
    for label, key, formatter in COMPARISON_FIELDS:
        selected_value = display_value(selected.get(key))
        comparison_value = display_value(comparison.get(key))
        if formatter == "chemical":
            selected_value = chemical_markup_to_unicode(selected_value)
            comparison_value = chemical_markup_to_unicode(comparison_value)
        elif formatter == "formula":
            selected_value = formula_to_unicode(selected_value)
            comparison_value = formula_to_unicode(comparison_value)
        elif formatter == "equilibrium":
            selected_value = equilibrium_to_unicode(selected_value)
            comparison_value = equilibrium_to_unicode(comparison_value)
        elif formatter == "record_id":
            selected_value = display_record_id(
                selected_value,
                selected.get("source_id"),
                include_source=include_source_in_record_id,
            )
            comparison_value = display_record_id(
                comparison_value,
                comparison.get("source_id"),
                include_source=include_source_in_record_id,
            )
        rows.append(
            {
                "Field": label,
                "Selected record": selected_value,
                "Comparison record": comparison_value,
                "Match": "Same" if selected_value == comparison_value else "Different",
            }
        )
    return rows
