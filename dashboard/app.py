"""
Versuni Mystery Shopping — Wave III BI Dashboard
=================================================
Landing page: KPI Overview (gauges + bar chart per country/retailer).

Run:  streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dashboard.branding import inject_css, render_header, theme_selector
from dashboard.auth import require_password
from dashboard.data_loader import (
    load_master, apply_filters, sidebar_filters,
    n_visits_caption, KPI_LABELS, KPI_COLORS, score_color,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Versuni MS — Overview",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)
require_password()
inject_css()


# ── Gauge helper ──────────────────────────────────────────────────────────────

def _gauge(value: float, label: str, color: str) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=round(value, 1),
        title={"text": label, "font": {"size": 13, "family": "Inter, sans-serif"}},
        number={"suffix": "%", "font": {"size": 22}},
        gauge={
            "axis": {"range": [0, 100], "tickfont": {"size": 10}},
            "bar": {"color": color, "thickness": 0.7},
            "steps": [
                {"range": [0, 40],  "color": "#FDECEA"},
                {"range": [40, 70], "color": "#FFF3E0"},
                {"range": [70, 100], "color": "#E8F5E9"},
            ],
            "threshold": {
                "line": {"color": "#333", "width": 2},
                "thickness": 0.75,
                "value": 70,
            },
            "shape": "angular",
        },
    ))
    fig.update_layout(
        height=170,
        margin=dict(l=15, r=15, t=35, b=5),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    df, is_demo = load_master()
    inject_css()
    render_header("Wave III — Results Dashboard")

    if is_demo:
        st.info(
            "⚠ No real data found — showing **demo data**. "
            "Run `python pipeline/roamler_etl.py` to load live data.",
            icon="⚠",
        )
        from dashboard.data_loader import PARQUET_PATH, EXCEL_PATH
        with st.expander("🔍 Debug: data path info", expanded=True):
            st.code(f"PARQUET_PATH = {PARQUET_PATH}\nexists = {PARQUET_PATH.exists()}\n\nEXCEL_PATH   = {EXCEL_PATH}\nexists = {EXCEL_PATH.exists()}\n\ndata/processed contents:\n" +
                    "\n".join(str(p) for p in PARQUET_PATH.parent.iterdir()) if PARQUET_PATH.parent.exists() else "(data/processed/ missing)")

    flt = sidebar_filters(df)
    filtered = apply_filters(df, **flt)

    st.caption(n_visits_caption(filtered))

    if filtered.empty:
        st.warning("No data matches the selected filters.")
        return

    # ── KPI gauges ────────────────────────────────────────────────────────────
    avg = {
        kpi: filtered[kpi].mean() if kpi in filtered.columns else 0.0
        for kpi in ["total_score", "kpi1_score", "kpi2_score", "kpi3_score"]
    }

    g_total, g1, g2, g3 = st.columns(4)
    with g_total:
        st.plotly_chart(_gauge(avg["total_score"],  "Total Score",           KPI_COLORS["total_score"]),  use_container_width=True)
    with g1:
        st.plotly_chart(_gauge(avg["kpi1_score"],   "Brand Availability",    KPI_COLORS["kpi1_score"]),   use_container_width=True)
    with g2:
        st.plotly_chart(_gauge(avg["kpi2_score"],   "Brand Visibility",      KPI_COLORS["kpi2_score"]),   use_container_width=True)
    with g3:
        st.plotly_chart(_gauge(avg["kpi3_score"],   "Brand Recommendation",  KPI_COLORS["kpi3_score"]),   use_container_width=True)

    # Unique visits count below gauges
    col_cnt = st.columns(4)
    col_cnt[0].metric("Total Visits",    f"{len(filtered):,}")
    col_cnt[1].metric("Markets",         filtered["market"].nunique() if "market" in filtered.columns else "?")
    col_cnt[2].metric("Categories",      filtered["category"].nunique() if "category" in filtered.columns else "?")
    col_cnt[3].metric("Unique Stores",   filtered["store_id"].nunique() if "store_id" in filtered.columns else "?")

    st.divider()

    # ── Toggle: per country vs per retailer ───────────────────────────────────
    ctrl1, ctrl2 = st.columns([3, 2])
    with ctrl1:
        view_by = st.radio(
            "View by", ["Country", "Retailer"], horizontal=True, key="overview_viewby"
        )
    with ctrl2:
        sort_by = st.radio("Sort", ["Score ↓", "A → Z"], horizontal=True, key="overview_sort")
    group_col = "market_name" if view_by == "Country" else "retailer"
    group_label = "Country" if view_by == "Country" else "Retailer"

    # Aggregate
    kpi_cols = ["kpi1_score", "kpi2_score", "kpi3_score", "total_score"]
    agg = (
        filtered.groupby(group_col)[kpi_cols]
        .mean()
        .round(1)
        .reset_index()
    )
    agg = (
        agg.sort_values(group_col)
        if sort_by == "A → Z"
        else agg.sort_values("total_score", ascending=False)
    )

    # Global average reference line
    global_avg = filtered["total_score"].mean()

    # Grouped bar chart
    fig = go.Figure()
    colors = {
        "total_score":  KPI_COLORS["total_score"],
        "kpi1_score":   KPI_COLORS["kpi1_score"],
        "kpi2_score":   KPI_COLORS["kpi2_score"],
        "kpi3_score":   KPI_COLORS["kpi3_score"],
    }
    labels = {
        "total_score":  "Total Score",
        "kpi1_score":   "Brand Availability",
        "kpi2_score":   "Brand Visibility",
        "kpi3_score":   "Brand Recommendation",
    }
    for kpi, color in colors.items():
        if kpi not in agg.columns:
            continue
        fig.add_trace(go.Bar(
            name=labels[kpi],
            x=agg[group_col],
            y=agg[kpi],
            marker_color=color,
            text=agg[kpi].apply(lambda v: f"{v:.1f}%"),
            textposition="outside",
            textfont=dict(size=10),
        ))

    # Reference line
    fig.add_hline(
        y=global_avg,
        line_dash="dash",
        line_color=KPI_COLORS["total_score"],
        annotation_text=f"Total avg: {global_avg:.1f}%",
        annotation_position="top left",
        annotation_font_color=KPI_COLORS["total_score"],
    )

    fig.update_layout(
        title=f"Global Score per KPI — per {group_label}",
        barmode="group",
        yaxis=dict(range=[0, 110], title="Score %"),
        xaxis_title=group_label,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=340,
        margin=dict(t=40, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Visit count table ─────────────────────────────────────────────────────
    st.subheader(f"Visits per {group_label}")
    visits_tbl = (
        filtered.groupby(group_col)
        .agg(visits=("submission_id", "count"))
        .reset_index()
        .sort_values("visits", ascending=False)
        .rename(columns={group_col: group_label, "visits": "#Visits"})
    )
    st.dataframe(visits_tbl, hide_index=True, use_container_width=True, height=220)


if __name__ == "__main__":
    main()
