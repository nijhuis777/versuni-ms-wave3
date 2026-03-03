"""
View: Presence of Categories — per Wave
  - Stacked bar comparing Wave I / II / III
  - Line overlay: % Philips available per wave
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
    load_master, apply_filters, sidebar_filters,
    n_visits_caption, WAVE_ORDER,
)

st.set_page_config(page_title="Presence per Wave", page_icon="📊", layout="wide", initial_sidebar_state="collapsed")
require_password()

VERSUNI_BLUE = "#003087"
ABSENT_COLOR = "#FF6738"
PHILIPS_LINE = "#00BCD4"


def main():
    df, is_demo = load_master()
    inject_css()
    render_header("Presence of Categories — per Wave")
    if is_demo:
        st.info("⚠ Showing **demo data**.", icon="⚠")

    flt = sidebar_filters(df)
    filtered = apply_filters(df, **flt)

    st.caption(n_visits_caption(filtered))

    if filtered.empty or "kpi1_category_present" not in filtered.columns:
        st.warning("No data or required columns missing.")
        return

    # ── Aggregate by wave ─────────────────────────────────────────────────────
    grp = (
        filtered.groupby(["wave", "wave_num"])
        .agg(
            total=("submission_id", "count"),
            present=("kpi1_category_present", "sum"),
            philips=("kpi1_philips_available", "sum"),
        )
        .reset_index()
        .sort_values("wave_num")
    )
    grp["pct_present"] = (grp["present"] / grp["total"] * 100).round(1)
    grp["pct_absent"]  = (100 - grp["pct_present"]).round(1)
    grp["pct_philips"] = (grp["philips"] / grp["total"] * 100).round(1)

    fig = go.Figure()

    fig.add_trace(go.Bar(
        name="Category present (Yes)",
        x=grp["wave"],
        y=grp["pct_present"],
        marker_color=VERSUNI_BLUE,
        text=grp["pct_present"].apply(lambda v: f"{v:.1f}%"),
        textposition="inside",
        textfont=dict(color="white", size=11),
    ))
    fig.add_trace(go.Bar(
        name="Category absent (No)",
        x=grp["wave"],
        y=grp["pct_absent"],
        marker_color=ABSENT_COLOR,
        text=grp["pct_absent"].apply(lambda v: f"{v:.1f}%" if v >= 3 else ""),
        textposition="inside",
        textfont=dict(color="white", size=11),
    ))
    fig.add_trace(go.Scatter(
        name="% Philips available",
        x=grp["wave"],
        y=grp["pct_philips"],
        mode="lines+markers+text",
        line=dict(color=PHILIPS_LINE, width=2, dash="dash"),
        marker=dict(size=10),
        text=grp["pct_philips"].apply(lambda v: f"{v:.1f}%"),
        textposition="top center",
        textfont=dict(color=PHILIPS_LINE, size=11),
        yaxis="y2",
    ))

    fig.update_layout(
        title="% Presence Category by Wave",
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
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=360,
        margin=dict(t=40, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Country breakdown per wave ─────────────────────────────────────────────
    st.subheader("Presence by Country & Wave")
    grp2 = (
        filtered.groupby(["market_name", "wave", "wave_num"])
        .agg(
            total=("submission_id", "count"),
            present=("kpi1_category_present", "sum"),
            philips=("kpi1_philips_available", "sum"),
        )
        .reset_index()
    )
    grp2["pct_present"] = (grp2["present"] / grp2["total"] * 100).round(1)
    grp2["pct_philips"] = (grp2["philips"] / grp2["total"] * 100).round(1)

    pivot_p = grp2.pivot_table(
        index="market_name", columns="wave", values="pct_present"
    ).round(1)
    pivot_ph = grp2.pivot_table(
        index="market_name", columns="wave", values="pct_philips"
    ).round(1)

    tab1, tab2 = st.tabs(["Category Present %", "Philips Available %"])
    with tab1:
        st.dataframe(
            pivot_p.style.format("{:.1f}%", na_rep="—")
                         .background_gradient(cmap="RdYlGn", vmin=0, vmax=100),
            use_container_width=True,
        )
    with tab2:
        st.dataframe(
            pivot_ph.style.format("{:.1f}%", na_rep="—")
                          .background_gradient(cmap="RdYlGn", vmin=0, vmax=100),
            use_container_width=True,
        )


main()
