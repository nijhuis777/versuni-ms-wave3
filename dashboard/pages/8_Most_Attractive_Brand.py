"""
View: Most Attractive Brand
  - 100% stacked bar: X = brands, stacked = attractiveness reasons
  - Side table: brand → % of stores + reason breakdown
"""
from __future__ import annotations
import sys
from pathlib import Path
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import streamlit as st

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
from dashboard.branding import inject_css, render_header, theme_selector
from dashboard.auth import require_password
from dashboard.data_loader import (
    load_master, apply_filters, sidebar_filters, n_visits_caption,
)

st.set_page_config(page_title="Most Attractive Brand", page_icon="✨", layout="wide", initial_sidebar_state="collapsed")
require_password()

PHILIPS_COLOR = "#003087"


def main():
    df, is_demo = load_master()
    inject_css()
    render_header("Most Attractive Brand")
    if is_demo:
        st.info("⚠ Showing **demo data**.", icon="⚠")

    flt = sidebar_filters(df)
    filtered = apply_filters(df, **flt)

    st.caption(n_visits_caption(filtered))

    if filtered.empty or "kpi2_standout_brand" not in filtered.columns:
        st.warning("No data or 'kpi2_standout_brand' column missing.")
        return

    n_total = len(filtered)

    # ── Brand frequency ───────────────────────────────────────────────────────
    brand_counts = (
        filtered["kpi2_standout_brand"]
        .dropna()
        .value_counts()
        .reset_index()
    )
    brand_counts.columns = ["Brand", "Count"]
    brand_counts["% Stores"] = (brand_counts["Count"] / n_total * 100).round(1)
    brand_counts = brand_counts[brand_counts["Brand"] != ""].sort_values("Count", ascending=False)

    # Top N brands filter
    top_n = st.slider("Show top N brands", min_value=3, max_value=min(20, len(brand_counts)), value=8, key="attract_topn")
    top_brands = brand_counts.head(top_n)["Brand"].tolist()

    # ── Reason × Brand cross-tab ──────────────────────────────────────────────
    # Explode reason column (pipe-separated)
    has_reason = "kpi2_standout_reason" in filtered.columns

    if has_reason:
        reason_df = filtered[["kpi2_standout_brand", "kpi2_standout_reason"]].dropna()
        reason_df = reason_df[reason_df["kpi2_standout_brand"].isin(top_brands)]
        reason_df = reason_df.copy()
        reason_df["reason"] = reason_df["kpi2_standout_reason"].str.split("|")
        reason_df = reason_df.explode("reason")
        reason_df["reason"] = reason_df["reason"].str.strip()
        reason_df = reason_df[reason_df["reason"] != ""]

        pivot = (
            reason_df.groupby(["kpi2_standout_brand", "reason"])
            .size()
            .unstack(fill_value=0)
        )
        # Reorder columns by frequency
        pivot = pivot[pivot.sum().sort_values(ascending=False).index]
        # Sort rows by total
        pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index]
        # Keep only top brands
        pivot = pivot[pivot.index.isin(top_brands)]

        # Normalize to %
        pivot_pct = (pivot.div(pivot.sum(axis=1), axis=0) * 100).round(1)

        # ── 100% stacked bar ──────────────────────────────────────────────────
        reasons_ordered = pivot.columns.tolist()
        palette = px.colors.qualitative.Set2 + px.colors.qualitative.Pastel
        reason_colors = {r: palette[i % len(palette)] for i, r in enumerate(reasons_ordered)}

        fig = go.Figure()
        for reason in reasons_ordered:
            if reason not in pivot_pct.columns:
                continue
            fig.add_trace(go.Bar(
                name=reason,
                x=pivot_pct.index,
                y=pivot_pct[reason],
                marker_color=reason_colors[reason],
                text=pivot_pct[reason].apply(lambda v: f"{v:.0f}%" if v >= 5 else ""),
                textposition="inside",
                textfont=dict(size=8),
            ))

        fig.update_layout(
            title="% Most Attractive Brand — by Reason",
            barmode="stack",
            yaxis=dict(range=[0, 105], title="% of mentions", ticksuffix="%"),
            xaxis=dict(tickangle=-30),
            legend=dict(orientation="v", x=1.01, y=1, font=dict(size=10)),
            height=360,
            margin=dict(t=40, b=60, r=260),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
    else:
        # Simple bar without reason breakdown
        fig = go.Figure(go.Bar(
            x=top_brands,
            y=brand_counts[brand_counts["Brand"].isin(top_brands)]["% Stores"].values,
            marker_color=[PHILIPS_COLOR if b == "Philips" else "#90CAF9" for b in top_brands],
            text=brand_counts[brand_counts["Brand"].isin(top_brands)]["% Stores"].apply(lambda v: f"{v:.1f}%"),
            textposition="outside",
        ))
        fig.update_layout(
            title="% Most Attractive Brand",
            yaxis=dict(range=[0, 110], ticksuffix="%"),
            height=320,
            margin=dict(t=40, b=35),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )

    # Layout: chart + side table
    col_chart, col_table = st.columns([3, 1])
    with col_chart:
        st.plotly_chart(fig, use_container_width=True)
    with col_table:
        st.subheader("Brand Summary")
        tbl = brand_counts.head(top_n)[["Brand", "Count", "% Stores"]].copy()
        tbl.columns = ["Brand", "# Answers", "% Stores"]
        st.dataframe(
            tbl.style.format({"% Stores": "{:.1f}%"}),
            hide_index=True,
            use_container_width=True,
            height=340,
        )


main()
