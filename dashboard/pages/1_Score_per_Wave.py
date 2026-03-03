"""
View: Score per Wave — Trend over time
"""
from __future__ import annotations
import sys
from pathlib import Path
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
from dashboard.branding import inject_css, render_header, theme_selector
from dashboard.auth import require_password
from dashboard.data_loader import (
    load_master, apply_filters, sidebar_filters,
    n_visits_caption, WAVE_ORDER, KPI_COLORS,
)

st.set_page_config(page_title="Score per Wave", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")
require_password()


def main():
    df, is_demo = load_master()
    inject_css()
    render_header("Score Overview — per Wave")
    if is_demo:
        st.info("⚠ Showing **demo data**.", icon="⚠")

    flt = sidebar_filters(df)
    filtered = apply_filters(df, **flt)

    st.caption(n_visits_caption(filtered))

    if filtered.empty:
        st.warning("No data matches the selected filters.")
        return

    # Aggregate by wave
    kpi_cols = ["kpi1_score", "kpi2_score", "kpi3_score", "total_score"]
    agg = (
        filtered.groupby(["wave", "wave_num"])[kpi_cols]
        .mean()
        .round(1)
        .reset_index()
        .sort_values("wave_num")
    )

    # KPI gauges (overall across all waves in selection)
    avg_total = filtered["total_score"].mean()
    g0, g1, g2, g3 = st.columns(4)
    for col, kpi, label, color in zip(
        [g0, g1, g2, g3],
        ["total_score", "kpi1_score", "kpi2_score", "kpi3_score"],
        ["Total Score", "Brand Availability", "Brand Visibility", "Brand Recommendation"],
        [KPI_COLORS["total_score"], KPI_COLORS["kpi1_score"], KPI_COLORS["kpi2_score"], KPI_COLORS["kpi3_score"]],
    ):
        val = filtered[kpi].mean() if kpi in filtered.columns else 0
        with col:
            st.metric(label, f"{val:.1f}%")

    st.divider()

    # ── Line chart ─────────────────────────────────────────────────────────────
    fig = go.Figure()
    styles = {
        "total_score":  dict(color=KPI_COLORS["total_score"], dash="solid", width=3),
        "kpi1_score":   dict(color=KPI_COLORS["kpi1_score"],  dash="solid", width=2),
        "kpi2_score":   dict(color=KPI_COLORS["kpi2_score"],  dash="solid", width=2),
        "kpi3_score":   dict(color=KPI_COLORS["kpi3_score"],  dash="solid", width=2),
    }
    labels = {
        "total_score":  "Total Score",
        "kpi1_score":   "Brand Availability",
        "kpi2_score":   "Brand Visibility",
        "kpi3_score":   "Brand Recommendation",
    }

    for kpi, style in styles.items():
        if kpi not in agg.columns:
            continue
        last_val = agg[kpi].iloc[-1] if not agg.empty else 0
        fig.add_trace(go.Scatter(
            x=agg["wave"],
            y=agg[kpi],
            mode="lines+markers+text",
            name=labels[kpi],
            line=dict(**style),
            marker=dict(size=8),
            text=agg[kpi].apply(lambda v: f"{v:.1f}%"),
            textposition="top center",
        ))

    fig.update_layout(
        title="Global Score per KPI — Over Time",
        yaxis=dict(range=[0, 105], title="Score %", gridcolor="#eee"),
        xaxis_title="Wave",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=340,
        margin=dict(t=40, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Wave comparison table ──────────────────────────────────────────────────
    st.subheader("Score Summary per Wave")
    tbl = agg[["wave"] + [k for k in kpi_cols if k in agg.columns]].copy()
    tbl.columns = ["Wave"] + [
        {"kpi1_score": "Brand Availability", "kpi2_score": "Brand Visibility",
         "kpi3_score": "Brand Recommendation", "total_score": "Total Score"}.get(c, c)
        for c in kpi_cols if c in agg.columns
    ]
    st.dataframe(
        tbl.style.format({c: "{:.1f}%" for c in tbl.columns if c != "Wave"}),
        hide_index=True,
        use_container_width=True,
    )

    # Visits per wave
    visits = filtered.groupby("wave").size().reset_index(name="#Visits")
    st.caption("Visits per wave:")
    st.dataframe(visits, hide_index=True, use_container_width=True, height=130)


main()
