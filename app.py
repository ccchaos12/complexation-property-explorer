"""Streamlit front end for read-only stability-constant databases."""

from __future__ import annotations

import math

import pandas as pd
import streamlit as st

from complexation_explorer import (
    REACTION_TYPE_LABELS,
    SearchFilters,
    count_constants,
    get_candidate_references,
    get_database_summary,
    get_record_detail,
    list_ligand_classes,
    list_metals,
    resolve_database_path,
    search_constants,
    search_record_ids,
)
from complexation_explorer.formatting import (
    chemical_markup_to_unicode,
    data_note,
    display_record_id,
    display_value,
    equilibrium_to_unicode,
    formula_to_unicode,
    record_comparison_rows,
)
from complexation_explorer.ui import (
    inject_design_css,
    render_fact_grid,
    render_footer,
    render_page_header,
    render_pagination,
    render_section_heading,
    render_sidebar_intro,
    render_stat_strip,
    reset_page_when_filters_change,
    selected_record_id_from_rows,
)


st.set_page_config(
    page_title="Complexation Property Explorer",
    page_icon="⚗️",
    layout="wide",
)
inject_design_css()


@st.cache_data(show_spinner=False)
def load_summary(database_path: str) -> dict:
    return get_database_summary(database_path)


@st.cache_data(show_spinner=False)
def load_metals(database_path: str) -> list[dict]:
    return list_metals(database_path)


@st.cache_data(show_spinner=False)
def load_ligand_classes(database_path: str) -> list[str]:
    return list_ligand_classes(database_path)


@st.cache_data(show_spinner=False, ttl=300)
def run_count(database_path: str, filters: SearchFilters) -> int:
    return count_constants(filters, database_path)


@st.cache_data(show_spinner=False, ttl=300)
def run_search(
    database_path: str, filters: SearchFilters, limit: int, offset: int
) -> list[dict]:
    return search_constants(filters, database_path, limit=limit, offset=offset)


@st.cache_data(show_spinner=False, ttl=300)
def run_record_id_search(
    database_path: str,
    query: str,
    exclude_record_id: str,
) -> list[dict]:
    return search_record_ids(
        query,
        database_path,
        limit=25,
        exclude_record_id=exclude_record_id,
    )


def record_search_label(row: dict, *, include_source: bool = False) -> str:
    """Build a compact, chemically readable comparison option label."""
    metal = chemical_markup_to_unicode(row["metal"])
    ligand = display_value(row["ligand"])
    value = display_value(row["reported_value"])
    record_id = display_record_id(
        row["record_id"],
        row.get("source_id"),
        include_source=include_source,
    )
    return f"{record_id} · {metal} · {ligand} · {row['value_type']} {value}"


def result_frame(
    rows: list[dict],
    *,
    compact_record_ids: bool = True,
    include_source_in_record_id: bool = False,
    extended: bool = False,
) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["data_note"] = frame.apply(data_note, axis=1)
    frame["metal"] = frame["metal"].map(chemical_markup_to_unicode)
    if compact_record_ids:
        frame["record_id"] = frame.apply(
            lambda row: display_record_id(
                row["record_id"],
                row.get("source_id"),
                include_source=include_source_in_record_id,
            ),
            axis=1,
        )
    frame["formula"] = frame["formula"].map(formula_to_unicode)
    frame["equilibrium"] = frame["equilibrium"].map(equilibrium_to_unicode)
    frame["solvent"] = frame["solvent"].map(chemical_markup_to_unicode)
    frame["electrolyte"] = frame["electrolyte"].map(chemical_markup_to_unicode)
    frame["footnote"] = frame["footnote"].map(chemical_markup_to_unicode)
    frame["reaction_type"] = frame["reaction_type"].map(REACTION_TYPE_LABELS)
    frame["display_value"] = frame["reported_value"]
    frame = frame.rename(
        columns={
            "record_id": "Record ID",
            "source_id": "Source",
            "metal": "Metal",
            "ligand": "Ligand",
            "formula": "Formula",
            "ligand_class": "Ligand class",
            "equilibrium": "Equilibrium",
            "temperature": "Temperature (°C)",
            "ionic_strength": "Ionic strength",
            "solvent": "Solvent",
            "electrolyte": "Electrolyte",
            "value_type": "Value type",
            "reported_value": "Reported value",
            "numeric_value": "Parsed numeric value",
            "standardized_value": "Source standardized value",
            "error": "Error",
            "footnote": "Footnote",
            "reaction_type": "Reaction type",
            "display_value": "Value",
            "data_note": "Data note",
            "candidate_reference_count": "Linked references",
        }
    )
    compact_columns = [
        "Record ID",
        "Metal",
        "Ligand",
        "Formula",
        "Equilibrium",
        "Value",
        "Temperature (°C)",
        "Ionic strength",
    ]
    extended_columns = [
        "Record ID",
        "Source",
        "Metal",
        "Ligand",
        "Formula",
        "Ligand class",
        "Reaction type",
        "Equilibrium",
        "Value",
        "Temperature (°C)",
        "Ionic strength",
        "Solvent",
        "Electrolyte",
        "Value type",
        "Parsed numeric value",
        "Source standardized value",
        "Error",
        "Footnote",
        "Data note",
        "Linked references",
    ]
    return frame[extended_columns if extended else compact_columns]


EXPLORER_FILTER_DEFAULTS = {
    "explorer_all_metals": True,
    "explorer_metals": [],
    "explorer_value_type": "K",
    "explorer_ligand_text": "",
    "explorer_ligand_classes": [],
    "explorer_value_min": None,
    "explorer_value_max": None,
    "explorer_temperature_min": None,
    "explorer_temperature_max": None,
    "explorer_ionic_strength_min": None,
    "explorer_ionic_strength_max": None,
    "explorer_numeric_only": False,
    "explorer_reaction_types": [],
    "explorer_extended_columns": False,
    "explorer_page_size": 50,
    "explorer_page": 1,
}


def initialize_explorer_filters() -> None:
    """Initialize filter state without overriding an active browser session."""
    for key, value in EXPLORER_FILTER_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value.copy() if isinstance(value, list) else value


def reset_explorer_filters() -> None:
    """Restore all explorer controls to a predictable default state."""
    for key, value in EXPLORER_FILTER_DEFAULTS.items():
        st.session_state[key] = value.copy() if isinstance(value, list) else value
    for key in (
        "explorer_record_id",
        "explorer_compare_page_record_id",
        "explorer_compare_search_query",
        "explorer_compare_search_record_id",
        "explorer_compare_search_text",
        "explorer_compare_mode",
        "explorer_compare_differences_only",
        "explorer_results_table",
        "_explorer_results_signature",
        "_explorer_results_selection_token",
    ):
        st.session_state.pop(key, None)


try:
    database_path = resolve_database_path()
except FileNotFoundError:
    st.error(
        "The canonical SQLite database was not found. Run "
        "`python3 -m ingestion.build_canonical`."
    )
    st.stop()

database_path_text = str(database_path)
summary = load_summary(database_path_text)
metals = load_metals(database_path_text)
metal_labels = {
    row["metal_id"]: chemical_markup_to_unicode(row["metal_name"]) for row in metals
}
initialize_explorer_filters()
source_aware_record_ids = summary["source_count"] > 1
if source_aware_record_ids:
    source_badge = f"{summary['source_count']} DATA SOURCES"
elif summary["source_ids"][0] == "NIST_SRD46":
    source_badge = "NIST SRD 46"
else:
    source_badge = summary["sources"][0]["source_name"]

render_page_header(
    "Complexation Property Explorer",
    "Search stability constants by metal, ligand, reaction, and measurement conditions.",
    badges=[
        ("READ ONLY", True),
        (source_badge, False),
        ("LOCAL SQLITE", False),
    ],
)
render_stat_strip(
    [
        ("Ligands", f"{summary['ligands']:,}"),
        ("All constant records", f"{summary['constants']:,}"),
        ("All log K records", f"{summary['log_k']:,}"),
        ("Linked references", f"{summary['references_count']:,}"),
    ]
)

with st.sidebar:
    render_sidebar_intro(
        "Search filters",
        "Narrow the database before comparing individual records.",
    )
    all_metals = st.checkbox(
        "Search all metals and metal species",
        key="explorer_all_metals",
    )
    selected_metals = []
    if not all_metals:
        selected_metals = st.multiselect(
            "Metals and oxidation states",
            options=list(metal_labels),
            format_func=lambda metal_id: metal_labels[metal_id],
            key="explorer_metals",
        )
    value_type = st.selectbox(
        "Value type",
        options=["K", "H", "S", "*"],
        key="explorer_value_type",
        format_func=lambda value: {
            "K": "log K (stability constant)",
            "H": "ΔH",
            "S": "ΔS",
            "*": "Other / unclassified",
        }[value],
    )
    ligand_text = st.text_input(
        "Ligand name contains",
        placeholder="e.g. EDTA",
        key="explorer_ligand_text",
    )
    ligand_classes = st.multiselect(
        "Ligand classes",
        options=load_ligand_classes(database_path_text),
        key="explorer_ligand_classes",
    )
    reaction_types = st.multiselect(
        "Reaction / stoichiometry",
        options=list(REACTION_TYPE_LABELS),
        format_func=lambda value: REACTION_TYPE_LABELS[value],
        key="explorer_reaction_types",
    )
    numeric_only = st.checkbox(
        "Only records with parsed numeric values",
        key="explorer_numeric_only",
    )
    with st.expander("Numeric ranges", expanded=False):
        st.caption("Optional filters use parsed numeric fields; source text stays unchanged.")
        value_label = "log K" if value_type == "K" else "value"
        value_min = st.number_input(
            f"Minimum {value_label}",
            value=None,
            step=0.1,
            format="%.4f",
            key="explorer_value_min",
        )
        value_max = st.number_input(
            f"Maximum {value_label}",
            value=None,
            step=0.1,
            format="%.4f",
            key="explorer_value_max",
        )
        temperature_min = st.number_input(
            "Minimum temperature (°C)",
            value=None,
            step=1.0,
            format="%.2f",
            key="explorer_temperature_min",
        )
        temperature_max = st.number_input(
            "Maximum temperature (°C)",
            value=None,
            step=1.0,
            format="%.2f",
            key="explorer_temperature_max",
        )
        ionic_strength_min = st.number_input(
            "Minimum ionic strength",
            value=None,
            min_value=0.0,
            step=0.1,
            format="%.4f",
            key="explorer_ionic_strength_min",
        )
        ionic_strength_max = st.number_input(
            "Maximum ionic strength",
            value=None,
            min_value=0.0,
            step=0.1,
            format="%.4f",
            key="explorer_ionic_strength_max",
        )
    page_size = st.select_slider(
        "Records per page",
        options=[25, 50, 100, 250],
        key="explorer_page_size",
    )
    st.divider()
    st.button("Reset filters", on_click=reset_explorer_filters)

filters = SearchFilters(
    metal_ids=tuple(selected_metals),
    ligand_text=ligand_text,
    ligand_classes=tuple(ligand_classes),
    value_type=value_type,
    value_min=value_min,
    value_max=value_max,
    temperature_c_min=temperature_min,
    temperature_c_max=temperature_max,
    ionic_strength_min=ionic_strength_min,
    ionic_strength_max=ionic_strength_max,
    numeric_only=numeric_only,
    reaction_types=tuple(reaction_types),
)

invalid_ranges = [
    label
    for label, minimum, maximum in (
        (value_label, value_min, value_max),
        ("temperature", temperature_min, temperature_max),
        ("ionic strength", ionic_strength_min, ionic_strength_max),
    )
    if minimum is not None and maximum is not None and minimum > maximum
]
if invalid_ranges:
    st.sidebar.error(
        "Minimum cannot exceed maximum for: " + ", ".join(invalid_ranges) + "."
    )
    st.stop()

if not all_metals and not selected_metals:
    st.info("Select at least one metal or oxidation state.")
    st.stop()
reset_page_when_filters_change(
    "explorer_page",
    (filters, page_size, all_metals),
)
total_rows = run_count(database_path_text, filters)
total_pages = max(1, math.ceil(total_rows / page_size))
render_section_heading(
    f"Search results — {total_rows:,}",
    "The compact view prioritizes identity, equilibrium, value, and conditions.",
)
show_extended_columns = st.toggle(
    "Show extended columns",
    key="explorer_extended_columns",
    help="Show source, classification, uncertainty, notes, and linked-reference counts.",
)
page = render_pagination(
    page_key="explorer_page",
    total_rows=total_rows,
    page_size=page_size,
    total_pages=total_pages,
)
offset = (int(page) - 1) * page_size
rows = run_search(database_path_text, filters, page_size, offset)
frame = result_frame(
    rows,
    include_source_in_record_id=source_aware_record_ids,
    extended=show_extended_columns,
)

if frame.empty:
    st.warning("No records match the current filters.")
else:
    record_ids = [row["record_id"] for row in rows]
    if st.session_state.get("explorer_record_id") not in record_ids:
        st.session_state["explorer_record_id"] = record_ids[0]

    table_event = st.dataframe(
        frame,
        width="stretch",
        hide_index=True,
        height=560,
        key="explorer_results_table",
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Record ID": st.column_config.TextColumn(width="small"),
            "Source": st.column_config.TextColumn(width="small"),
            "Metal": st.column_config.TextColumn(width="small"),
            "Ligand": st.column_config.TextColumn(width="large"),
            "Formula": st.column_config.TextColumn(width="small"),
            "Equilibrium": st.column_config.TextColumn(width="medium"),
            "Value": st.column_config.TextColumn(width="small"),
            "Temperature (°C)": st.column_config.TextColumn(width="small"),
            "Ionic strength": st.column_config.TextColumn(width="small"),
        },
    )
    selected_row_indices = tuple(table_event.selection.rows)
    results_signature = tuple(record_ids)
    selection_token = (results_signature, selected_row_indices)
    previous_signature = st.session_state.get("_explorer_results_signature")
    previous_selection_token = st.session_state.get(
        "_explorer_results_selection_token"
    )
    st.session_state["_explorer_results_signature"] = results_signature
    st.session_state["_explorer_results_selection_token"] = selection_token
    if (
        previous_signature == results_signature
        and previous_selection_token != selection_token
    ):
        clicked_record_id = selected_record_id_from_rows(rows, selected_row_indices)
        if clicked_record_id:
            st.session_state["explorer_record_id"] = clicked_record_id

    selected_record_id = st.session_state["explorer_record_id"]
    selected_row = next(
        row for row in rows if row["record_id"] == selected_record_id
    )
    selected_display_id = display_record_id(
        selected_record_id,
        selected_row.get("source_id"),
        include_source=source_aware_record_ids,
    )
    st.caption(
        f"Selected record: {selected_display_id}. "
        "Click any result row to update "
        "the details below."
    )

    if st.button("Prepare filtered CSV"):
        export_limit = min(total_rows, 50_000)
        with st.spinner("Preparing the export file…"):
            export_rows = run_search(database_path_text, filters, export_limit, 0)
            export_frame = result_frame(
                export_rows,
                compact_record_ids=False,
                extended=True,
            )
        st.download_button(
            "Download CSV",
            data=export_frame.to_csv(index=False).encode("utf-8-sig"),
            file_name="stability_constants.csv",
            mime="text/csv",
        )
        if total_rows > export_limit:
            st.caption(
                f"To keep the app responsive, this export is limited to the first "
                f"{export_limit:,} records."
            )

    render_section_heading(
        "Record details",
        "The selected result controls these conditions, values, and literature candidates.",
    )
    detail = get_record_detail(selected_record_id, database_path_text)
    if detail is None:
        st.error("The selected record is no longer available. Refresh this page.")
        st.stop()
    render_fact_grid(
        [
            (
                "Record ID",
                display_record_id(
                    detail["record_id"],
                    detail.get("source_id"),
                    include_source=source_aware_record_ids,
                ),
            ),
            ("Metal", chemical_markup_to_unicode(detail["metal"])),
            ("Ligand", display_value(detail["ligand"])),
            ("Formula", formula_to_unicode(detail["formula"])),
            ("Equilibrium", equilibrium_to_unicode(detail["equilibrium_raw"])),
            ("Reported value", display_value(detail["reported_value_text"])),
            ("Parsed value", display_value(detail["numeric_value"])),
            ("Temperature", display_value(detail["temperature_raw"])),
            ("Ionic strength", display_value(detail["ionic_strength_raw"])),
            ("Solvent", chemical_markup_to_unicode(detail["solvent_raw"])),
            ("Electrolyte", chemical_markup_to_unicode(detail["electrolyte_raw"])),
            ("Data note", data_note(detail)),
        ]
    )

    render_section_heading(
        "Compare records",
        "Choose another result from this page or find a Record ID anywhere in the database.",
    )
    compare_mode = st.radio(
        "Comparison record source",
        options=["Choose from current page", "Search Record ID"],
        horizontal=True,
        key="explorer_compare_mode",
    )
    comparison_record_id = None
    if compare_mode == "Choose from current page":
        comparison_options = [
            record_id for record_id in record_ids if record_id != selected_record_id
        ]
        if st.session_state.get("explorer_compare_page_record_id") not in (
            comparison_options
        ):
            st.session_state["explorer_compare_page_record_id"] = None
        comparison_record_id = st.selectbox(
            "Comparison Record ID",
            options=comparison_options,
            index=None,
            placeholder="Select another Record ID",
            format_func=lambda record_id: display_record_id(
                record_id,
                next(
                    row.get("source_id")
                    for row in rows
                    if row["record_id"] == record_id
                ),
                include_source=source_aware_record_ids,
            ),
            key="explorer_compare_page_record_id",
        )
    else:
        with st.form("explorer_compare_search_form", border=False):
            search_record_text = st.text_input(
                "Record ID contains",
                placeholder="e.g. 100001 or CONSTANT:100",
                key="explorer_compare_search_text",
            )
            search_submitted = st.form_submit_button("Find matches")
        if search_submitted:
            normalized_query = search_record_text.strip()
            if normalized_query:
                st.session_state["explorer_compare_search_query"] = normalized_query
                st.session_state.pop("explorer_compare_search_record_id", None)
            else:
                st.session_state.pop("explorer_compare_search_query", None)
                st.session_state.pop("explorer_compare_search_record_id", None)
                st.error("Enter any part of a Record ID, then find matches.")

        search_query = st.session_state.get("explorer_compare_search_query", "")
        if search_query:
            matching_records = run_record_id_search(
                database_path_text,
                search_query,
                selected_record_id,
            )
            if matching_records:
                matching_ids = [row["record_id"] for row in matching_records]
                matching_labels = {
                    row["record_id"]: record_search_label(
                        row,
                        include_source=source_aware_record_ids,
                    )
                    for row in matching_records
                }
                stored_match = st.session_state.get(
                    "explorer_compare_search_record_id"
                )
                if stored_match not in matching_ids:
                    exact_match = next(
                        (
                            record_id
                            for record_id in matching_ids
                            if record_id.lower() == search_query.lower()
                        ),
                        None,
                    )
                    st.session_state["explorer_compare_search_record_id"] = exact_match
                comparison_record_id = st.selectbox(
                    "Matching records",
                    options=matching_ids,
                    index=None,
                    placeholder="Select a matching Record ID",
                    format_func=lambda record_id: matching_labels[record_id],
                    key="explorer_compare_search_record_id",
                )
                st.caption(
                    f"Showing up to 25 case-insensitive matches for “{search_query}”."
                )
            else:
                st.warning(
                    f"No Record IDs contain “{search_query}”. Shorten the query or "
                    "check the digits."
                )

    if comparison_record_id == selected_record_id:
        st.info("Choose a different Record ID to compare two records.")
    elif comparison_record_id:
        comparison_detail = get_record_detail(
            comparison_record_id, database_path_text
        )
        if comparison_detail is None:
            st.error(
                f"No record was found for {comparison_record_id}. Check the exact "
                "Record ID and try again."
            )
        else:
            comparison_frame = pd.DataFrame(
                record_comparison_rows(
                    detail,
                    comparison_detail,
                    include_source_in_record_id=source_aware_record_ids,
                )
            )
            show_differences_only = st.toggle(
                "Show differences only",
                key="explorer_compare_differences_only",
            )
            if show_differences_only:
                comparison_frame = comparison_frame[
                    comparison_frame["Match"] == "Different"
                ]
            st.dataframe(
                comparison_frame,
                width="stretch",
                hide_index=True,
                height="auto",
                column_config={
                    "Field": st.column_config.TextColumn(width="medium"),
                    "Selected record": st.column_config.TextColumn(width="large"),
                    "Comparison record": st.column_config.TextColumn(width="large"),
                    "Match": st.column_config.TextColumn(width="small"),
                },
            )

    render_section_heading(
        "Linked references",
        "Browse ligand-plus-metal literature links for the selected record.",
    )
    references = get_candidate_references(
        selected_row["ligand_id"], selected_row["metal_id"], database_path_text
    )
    st.warning(
        "The source database links references at the ligand-plus-metal level, "
        "not necessarily "
        "to one exact Record ID. Consult the cited source when the experimental context "
        "matters."
    )
    if references:
        reference_frame = pd.DataFrame(references).rename(
            columns={
                "reference_id": "Reference ID",
                "reference_code": "Code",
                "reference_text": "Reference",
                "not_used": "Not used flag",
                "comment": "Comment",
            }
        )
        st.dataframe(
            reference_frame[
                ["Reference ID", "Code", "Reference", "Not used flag", "Comment"]
            ],
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("No linked references were found for this ligand-metal combination.")

with st.expander("Data source and limitations"):
    st.markdown(
        f"""
        - **Dataset version:** {summary['dataset_version']}.
        - **Build timestamp:** `{summary['built_at_utc']}`.
        - **Schema version:** `{summary['schema_version']}`.
        - **Active records:** {summary['constants']:,} across {summary['source_count']} source(s).
        - Current database: `{database_path.name}`.
        - SQLite is opened with both URI `mode=ro` and `query_only` read-only controls.
        - Source text and parsed numeric fields are stored separately.
        - The app does not read or modify any external Excel database.
        """
    )
    source_checksum_lines = [
        f"{source['source_id']} source SHA-256: {source['source_checksum_sha256']}"
        for source in summary["sources"]
    ]
    st.code(
        "\n".join(
            [
                f"Database SHA-256: {summary['database_sha256']}",
                *source_checksum_lines,
            ]
        ),
        language="text",
    )

render_footer(
    f"{summary['dataset_version']} · schema {summary['schema_version']} · "
    f"{database_path.name} · read-only SQLite"
)
