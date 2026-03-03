"""
View: Score Matrix — Market × Category heatmap (with retailer drill-down)
"""
from __future__ import annotations
import sys
from pathlib import Path
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import streamlit as st

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
from dashboard.branding import inject_css, render_header, theme_selector
from dashboard.auth import require_password
from dashboard.data_loader import (
    load_master, apply_filters, sidebar_filters,
    n_visits_caption, KPI_LABELS, score_color,
)

st.set_page_config(page_title="Score Matrix", page_icon="🗂️", layout="wide", initial_sidebar_state="collapsed")
require_password()


def _color_cell(val):
    """Background color for styled dataframe cells (0-100 scale)."""
    if pd.isna(val):
        return "background-color: #f5f5f5; color: #ccc"
    if val >= 70:
        return "background-color: #C8E6C9; color: #1B5E20"
    if val >= 40:
        return "background-color: #FFF9C4; color: #F57F17"
    return "background-color: #FFCDD2; color: #B71C1C"


def main():
    df, is_demo = load_master()
    inject_css()
    render_header("Score Matrix — Market × Category")
    if is_demo:
        st.info("⚠ Showing **demo data**.", icon="⚠")

    flt = sidebar_filters(df)
    filtered = apply_filters(df, **flt)

    st.caption(n_visits_caption(filtered))

    if filtered.empty:
        st.warning("No data matches the selected filters.")
        return

    # KPI selector
    kpi_col = st.selectbox(
        "KPI",
        options=list(KPI_LABELS.keys()),
        format_func=lambda k: KPI_LABELS[k],
        key="matrix_kpi",
    )

    # ── Market × Category pivot ───────────────────────────────────────────────
    c_sub, c_sort = st.columns([5, 2])
    with c_sub:
        st.subheader("Market × Category")
    with c_sort:
        sort_by = st.radio("Sort markets", ["A → Z", "Score ↓"], horizontal=True, key="matrix_sort")

    pivot = (
        filtered.groupby(["market_name", "category"])[kpi_col]
        .mean()
        .round(1)
        .reset_index()
        .pivot(index="market_name", columns="category", values=kpi_col)
    )
    pivot["Total"] = filtered.groupby("market_name")[kpi_col].mean().round(1)
    pivot = (
        pivot.sort_index()
        if sort_by == "A → Z"
        else pivot.sort_values("Total", ascending=False)
    )

    # Style
    styled = (
        pivot.style
        .applymap(_color_cell)
        .format("{:.1f}%", na_rep="—")
    )
    st.dataframe(styled, use_container_width=True)

    st.divider()

    # ── Market × Category × Retailer (expandable) ─────────────────────────────
    st.subheader("Market × Retailer × Category (drill-down)")

    pivot2 = (
        filtered.groupby(["market_name", "retailer", "category"])[kpi_col]
        .mean()
        .round(1)
        .reset_index()
        .pivot_table(
            index=["market_name", "retailer"],
            columns="category",
            values=kpi_col,
        )
    )
    pivot2["Total"] = (
        filtered.groupby(["market_name", "retailer"])[kpi_col]
        .mean()
        .round(1)
    )
    pivot2 = pivot2.reset_index()

    styled2 = (
        pivot2.style
        .applymap(
            _color_cell,
            subset=[c for c in pivot2.columns if c not in ("market_name", "retailer")],
        )
        .format("{:.1f}%", na_rep="—",
                subset=[c for c in pivot2.columns if c not in ("market_name", "retailer")])
    )
    st.dataframe(styled2, use_container_width=True)

    st.divider()

    # ── Plotly heatmap ────────────────────────────────────────────────────────
    st.subheader("Heatmap")
    heat_data = (
        filtered.groupby(["market_name", "category"])[kpi_col]
        .mean()
        .round(1)
        .reset_index()
        .pivot(index="market_name", columns="category", values=kpi_col)
    )
    # Apply same sort as table above
    heat_data = (
        heat_data.sort_index()
        if sort_by == "A → Z"
        else heat_data.assign(_total=heat_data.mean(axis=1)).sort_values("_total", ascending=False).drop(columns="_total")
    )
    fig = px.imshow(
        heat_data,
        color_continuous_scale="RdYlGn",
        zmin=0, zmax=100,
        text_auto=".1f",
        aspect="auto",
        title=f"{KPI_LABELS[kpi_col]} — Market × Category Heatmap",
    )
    fig.update_layout(
        height=max(230, len(heat_data) * 34 + 60),
        margin=dict(t=35, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
        coloraxis_colorbar=dict(title="Score %"),
    )
    st.plotly_chart(fig, use_container_width=True)


main()
