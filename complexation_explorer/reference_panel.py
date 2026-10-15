"""A readable bibliography panel with explicit provenance and optional source metadata."""

from __future__ import annotations

import hashlib
from html import escape

import streamlit as st

from .formatting import display_value
from .references import (
    DIRECT,
    bibliography_csv,
    bibliography_entries,
    bibliography_text,
    filter_bibliography,
)

PAGE_SIZE = 10


def _show_more() -> None:
    st.session_state["reference_visible_count"] += PAGE_SIZE


def _reference_card(entry: dict) -> None:
    card_key = hashlib.sha256(entry["Reference ID"].encode()).hexdigest()[:12]
    with st.container(border=True, key=f"reference_card_{card_key}"):
        direct = entry["Link type"] == DIRECT
        tag = "DIRECT RECORD LINK" if direct else "RELATED LITERATURE"
        status = entry["Source use status"]
        note = ""
        if status not in {"Not flagged as unused", "Not applicable — no pair-level flag"}:
            label = "Source flag not reported" if status == "Not reported" else status
            note = f'<span class="sce-reference-note">{escape(label)}</span>'
        st.markdown(
            f'<div class="sce-reference-meta"><span class="sce-reference-tag '
            f'{"is-direct" if direct else ""}">{tag}</span>{note}</div>'
            f'<p class="sce-reference-citation">{escape(entry["Reference"])}</p>',
            unsafe_allow_html=True,
        )
        with st.container(horizontal=True):
            with st.popover("Copy citation", icon=":material/content_copy:"):
                st.caption("Use the copy button in the top-right corner of this citation.")
                st.code(entry["Reference"], language=None, wrap_lines=True)
            for index, url in enumerate(entry["Source links"].splitlines(), start=1):
                st.link_button("Open source" if index == 1 else f"Source link {index}", url)
        with st.expander("Reference details"):
            st.caption(f"Reference ID: {entry['Reference ID']} · Source code: {entry['Code']}")
            st.text(f"Source use status: {status}")
            if entry["Comment"] != "N/A":
                st.text(entry["Comment"])
            if entry["raw_links"]:
                st.caption(
                    "Legacy not_used flag: −1 (or 1) is interpreted as true; 0 as false. "
                    "A false flag does not verify this citation. Original values are retained."
                )
                st.dataframe(
                    [
                        {
                            "Raw not_used flag": display_value(link.get("not_used")),
                            "Comment": display_value(link.get("comment")),
                        }
                        for link in entry["raw_links"]
                    ],
                    hide_index=True,
                    width="stretch",
                )
            else:
                st.caption("No pair-level source flags are attached to this citation.")


def render_reference_panel(detail: dict, references: list[dict]) -> None:
    entries = bibliography_entries(detail, references)
    record_id = detail["record_id"]
    with st.container(key="reference_panel"):
        st.markdown(
            '<div class="sce-reference-heading"><span class="sce-reference-eyebrow">'
            "READ · TRACE · CITE</span><h2>Literature &amp; sources</h2>"
            "<p>Read the citations, see how they connect, and take your bibliography with you.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        if not entries:
            st.info("No direct or related references are available for this record.")
            return
        query = st.text_input(
            "Search these references",
            placeholder="Author, year, journal or keyword",
            key=f"reference_search_{record_id}",
        )
        filtered = filter_bibliography(entries, query)
        context = (record_id, query.strip().casefold())
        if st.session_state.get("reference_list_context") != context:
            st.session_state["reference_list_context"] = context
            st.session_state["reference_visible_count"] = PAGE_SIZE
        with st.container(horizontal=True):
            st.download_button(
                "Export references (CSV)",
                bibliography_csv(filtered),
                file_name="record_references.csv",
                mime="text/csv",
                on_click="ignore",
                disabled=not filtered,
            )
            with st.popover("Copy matching citations", disabled=not filtered):
                st.caption(f"All {len(filtered)} matching citations. Use the copy button below.")
                st.code(bibliography_text(filtered), language=None, wrap_lines=True)
        st.caption(
            f"{len(filtered)} of {len(entries)} references match. "
            "Copy and export include every match, including references not yet expanded below."
        )
        if not filtered:
            st.info("No references match your search. Try another author, year or keyword.")
            return
        direct = [entry for entry in filtered if entry["Link type"] == DIRECT]
        related = [entry for entry in filtered if entry["Link type"] != DIRECT]
        if direct:
            st.markdown("### Directly linked to this record")
            st.caption(
                "The database links this citation to the selected constant. "
                "This describes the stored association, not a new review of the original paper."
            )
            for entry in direct:
                _reference_card(entry)
        elif not detail.get("verified_reference_id"):
            st.caption("No exact record-level citation is stored for this constant.")
        if related:
            st.markdown(f"### Related to this ligand–metal system · {len(related)}")
            st.caption(
                "These are literature leads, not confirmed sources for this exact value. "
                "Source flags are not quality ratings; all references remain available."
            )
            visible_count = st.session_state["reference_visible_count"]
            for entry in related[:visible_count]:
                _reference_card(entry)
            if len(related) > visible_count:
                st.caption(f"Showing {visible_count} of {len(related)} related references.")
                st.button("Show 10 more references", on_click=_show_more, key="reference_show_more")
