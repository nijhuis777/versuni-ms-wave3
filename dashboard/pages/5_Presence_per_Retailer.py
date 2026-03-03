"""
View: Presence of Categories per Retailer
  - Stacked bar: % stores where category is present (Yes) vs absent (No)
  - Line overlay: % stores where Philips is available
"""
from __future__ import annotations
import sys
from pathlib import Path
import plotly.graph_objects as go
import pandas as pd
import streamlit as st

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
from dashboard.branding import inject_css, render_header, theme_selector
from dashboard.auth import require_password
from dashboard.data_loader import (
    load_master, apply_filters, sidebar_filters, n_visits_caption,
)

st.set_page_config(page_title="Presence per Retailer", page_icon="🏪", layout="wide", initial_sidebar_state="collapsed")
require_password()

VERSUNI_BLUE   = "#003087"
PHILIPS_RED    = "#E31837"
ABSENT_COLOR   = "#FF6738"
PHILIPS_LINE   = "#00BCD4"


def main():
    df, is_demo = load_master()
    inject_css()
    render_header("Presence of Categories — per Retailer")
    if is_demo:
        st.info("⚠ Showing **demo data**.", icon="⚠")

    flt = sidebar_filters(df)
    filtered = apply_filters(df, **flt)

    st.caption(n_visits_caption(filtered))

    if filtered.empty or "kpi1_category_present" not in filtered.columns:
        st.warning("No data or required columns missing.")
        return

    # ── Aggregate ─────────────────────────────────────────────────────────────
    grp = (
        filtered.groupby("retailer")
        .agg(
            total=("submission_id", "count"),
            present=("kpi1_category_present", "sum"),
            philips=("kpi1_philips_available", "sum"),
        )
        .reset_index()
    )
    grp["pct_present"] = (grp["present"] / grp["total"] * 100).round(1)
    grp["pct_absent"]  = (100 - grp["pct_present"]).round(1)
    grp["pct_philips"] = (grp["philips"] / grp["total"] * 100).round(1)

    sort_by = st.radio("Sort", ["Score ↓", "A → Z"], horizontal=True, key="pres_ret_sort")
    grp = (
        grp.sort_values("retailer")
        if sort_by == "A → Z"
        else grp.sort_values("pct_present", ascending=False)
    )

    # ── Chart ─────────────────────────────────────────────────────────────────
    fig = go.Figure()

    # Yes bar
    fig.add_trace(go.Bar(
        name="Category present (Yes)",
        x=grp["retailer"],
        y=grp["pct_present"],
        marker_color=VERSUNI_BLUE,
        text=grp["pct_present"].apply(lambda v: f"{v:.0f}%"),
        textposition="inside",
        textfont=dict(color="white", size=9),
    ))

    # No bar
    fig.add_trace(go.Bar(
        name="Category absent (No)",
        x=grp["retailer"],
        y=grp["pct_absent"],
        marker_color=ABSENT_COLOR,
        text=grp["pct_absent"].apply(lambda v: f"{v:.0f}%" if v >= 5 else ""),
        textposition="inside",
        textfont=dict(color="white", size=9),
    ))

    # Philips % line
    fig.add_trace(go.Scatter(
        name="% Philips available",
        x=grp["retailer"],
        y=grp["pct_philips"],
        mode="lines+markers+text",
        line=dict(color=PHILIPS_LINE, width=2, dash="dash"),
        marker=dict(size=7),
        text=grp["pct_philips"].apply(lambda v: f"{v:.0f}%"),
        textposition="top center",
        textfont=dict(color=PHILIPS_LINE, size=9),
        yaxis="y2",
    ))

    fig.update_layout(
        title="% Presence Category by Retailer",
        barmode="stack",
        yaxis=dict(range=[0, 105], title="% of Stores", ticksuffix="%"),
        yaxis2=dict(
            range=[0, 105],
            title="% Philips Available",
            overlaying="y",
            side="right",
            ticksuffix="%",
            showgrid=False,
        ),
        xaxis=dict(tickangle=-45),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=370,
        margin=dict(t=40, b=80),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Detail table ──────────────────────────────────────────────────────────
    st.subheader("Detail Table")
    tbl = grp[["retailer", "total", "pct_present", "pct_absent", "pct_philips"]].copy()
    tbl.columns = ["Retailer", "# Visits", "% Present", "% Absent", "% Philips"]
    st.dataframe(
        tbl.style.format({
            "% Present": "{:.1f}%", "% Absent": "{:.1f}%", "% Philips": "{:.1f}%"
        }),
        hide_index=True,
        use_container_width=True,
    )


main()
