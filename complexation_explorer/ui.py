"""Shared presentation helpers for the Streamlit application."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from html import escape
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def clamp_page(page: int, total_pages: int) -> int:
    """Keep a requested page inside the available one-based page range."""
    return min(max(int(page), 1), max(int(total_pages), 1))


def reset_page_when_filters_change(
    page_key: str,
    filter_signature: object,
) -> None:
    """Return to page one when any result-shaping filter changes."""
    signature_key = f"_{page_key}_filter_signature"
    if st.session_state.get(signature_key) != filter_signature:
        st.session_state[signature_key] = filter_signature
        st.session_state[page_key] = 1


def _set_page(page_key: str, target_page: int, total_pages: int) -> None:
    st.session_state[page_key] = clamp_page(target_page, total_pages)


def selected_record_id_from_rows(
    rows: Sequence[dict], selected_row_indices: Sequence[int]
) -> str | None:
    """Resolve a safe Record ID from a single-row dataframe selection."""
    if not selected_row_indices:
        return None
    row_index = int(selected_row_indices[0])
    if row_index < 0 or row_index >= len(rows):
        return None
    record_id = rows[row_index].get("record_id")
    return str(record_id) if record_id else None


def render_pagination(
    *,
    page_key: str,
    total_rows: int,
    page_size: int,
    total_pages: int,
) -> int:
    """Render accessible first/previous/next/last controls and return the page."""
    current_page = clamp_page(st.session_state.get(page_key, 1), total_pages)
    st.session_state[page_key] = current_page

    controls = st.columns([1, 1, 1.25, 1, 1])
    controls[0].button(
        "First",
        key=f"{page_key}_first",
        disabled=current_page == 1,
        on_click=_set_page,
        args=(page_key, 1, total_pages),
    )
    controls[1].button(
        "Prev",
        key=f"{page_key}_previous",
        help="Previous page",
        disabled=current_page == 1,
        on_click=_set_page,
        args=(page_key, current_page - 1, total_pages),
    )
    page = int(
        controls[2].number_input(
            "Page",
            min_value=1,
            max_value=total_pages,
            step=1,
            key=page_key,
        )
    )
    controls[3].button(
        "Next",
        key=f"{page_key}_next",
        disabled=current_page == total_pages,
        on_click=_set_page,
        args=(page_key, current_page + 1, total_pages),
    )
    controls[4].button(
        "Last",
        key=f"{page_key}_last",
        disabled=current_page == total_pages,
        on_click=_set_page,
        args=(page_key, total_pages, total_pages),
    )

    if total_rows:
        first_row = (page - 1) * page_size + 1
        last_row = min(page * page_size, total_rows)
        st.caption(
            f"Page {page:,} of {total_pages:,} · showing records "
            f"{first_row:,}–{last_row:,} of {total_rows:,}."
        )
    else:
        st.caption("No records match the current filters.")
    return page


def inject_design_css() -> None:
    """Load the portable design tokens and Streamlit-specific stylesheet."""
    tokens = (PROJECT_ROOT / "tokens.css").read_text(encoding="utf-8")
    app_css = (PROJECT_ROOT / "assets" / "app.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{tokens}\n{app_css}</style>", unsafe_allow_html=True)


def render_page_header(
    title: str,
    description: str,
    badges: Iterable[tuple[str, bool]],
) -> None:
    """Render a compact, task-first page header."""
    badge_markup = "".join(
        (
            '<span class="sce-badge sce-badge--active">'
            if active
            else '<span class="sce-badge">'
        )
        + escape(label)
        + "</span>"
        for label, active in badges
    )
    st.markdown(
        f"""
        <header class="sce-page-header">
          <div>
            <h1 class="sce-page-header__title">{escape(title)}</h1>
            <p class="sce-page-header__description">{escape(description)}</p>
          </div>
          <div class="sce-page-header__meta">{badge_markup}</div>
        </header>
        """,
        unsafe_allow_html=True,
    )


def render_stat_strip(items: Iterable[tuple[str, str]]) -> None:
    """Render a four-up tabular summary strip."""
    cells = "".join(
        '<div class="sce-stat">'
        f'<span class="sce-stat__value">{escape(value)}</span>'
        f'<span class="sce-stat__label">{escape(label)}</span>'
        "</div>"
        for label, value in items
    )
    st.markdown(f'<section class="sce-stat-strip">{cells}</section>', unsafe_allow_html=True)


def render_section_heading(title: str, description: str = "") -> None:
    """Render a stacked, non-decorative section heading."""
    description_markup = (
        f'<p class="sce-section-head__description">{escape(description)}</p>'
        if description
        else ""
    )
    st.markdown(
        f"""
        <div class="sce-section-head">
          <h2 class="sce-section-head__title">{escape(title)}</h2>
          {description_markup}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_fact_grid(items: Iterable[tuple[str, str]]) -> None:
    """Render aligned record facts as one border-led definition list."""
    facts = "".join(
        '<div class="sce-fact">'
        f"<dt>{escape(label)}</dt>"
        f"<dd>{escape(value)}</dd>"
        "</div>"
        for label, value in items
    )
    st.markdown(
        f'<dl class="sce-fact-grid">{facts}</dl>',
        unsafe_allow_html=True,
    )


def render_sidebar_intro(title: str, description: str) -> None:
    """Render the side-rail heading used above filter controls."""
    st.markdown(
        f"""
        <div class="sce-sidebar-intro">
          <strong>{escape(title)}</strong>
          <span>{escape(description)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_footer(text: str) -> None:
    """Render the compact closing line."""
    st.markdown(f'<footer class="sce-foot-line">{escape(text)}</footer>', unsafe_allow_html=True)
