"""
View: Facings — average unboxed facings per brand per retailer
Stacked bar chart (100% of brands), one bar per retailer.
Also shows wave-over-wave comparison.
"""
from __future__ import annotations
import sys
from pathlib import Path
import re
import plotly.express as px
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

st.set_page_config(page_title="Facings", page_icon="📦", layout="wide", initial_sidebar_state="collapsed")
require_password()

PHILIPS_COLOR = "#003087"  # highlight Philips bar


def _brand_label(col: str) -> str:
    """Convert 'facings_unboxed_philips' → 'Philips'."""
    name = col.replace("facings_unboxed_", "").replace("facings_boxed_", "")
    name = name.replace("_", " ").strip()
    return name.title()


def main():
    df, is_demo = load_master()
    inject_css()
    render_header("Facings — Average Unboxed Facings per Brand")
    if is_demo:
        st.info("⚠ Showing **demo data**.", icon="⚠")

    flt = sidebar_filters(df)
    filtered = apply_filters(df, **flt)

    st.caption(n_visits_caption(filtered))

    if filtered.empty:
        st.warning("No data matches the selected filters.")
        return

    # ── Identify facing columns ───────────────────────────────────────────────
    facing_type = st.radio(
        "Facing type", ["Unboxed", "Boxed", "Both (combined)"], horizontal=True
    )
    prefix_map = {
        "Unboxed":          ["facings_unboxed_"],
        "Boxed":            ["facings_boxed_"],
        "Both (combined)":  ["facings_unboxed_", "facings_boxed_"],
    }
    prefixes = prefix_map[facing_type]

    facing_cols = [c for c in filtered.columns if any(c.startswith(p) for p in prefixes)]

    if not facing_cols:
        st.info("No facings columns found in the dataset yet — run the ETL first.")
        return

    # Map column → brand label
    brand_map: dict[str, str] = {}
    for col in facing_cols:
        lbl = _brand_label(col)
        brand_map[col] = lbl

    # Aggregate avg facings per retailer
    agg = (
        filtered.groupby("retailer")[facing_cols]
        .mean()
        .round(2)
        .reset_index()
    )
    # Rename brand columns to brand labels (combine if both boxed+unboxed)
    brand_agg: dict[str, pd.Series] = {}
    for col, lbl in brand_map.items():
        if lbl in brand_agg:
            brand_agg[lbl] = brand_agg[lbl].add(agg[col].fillna(0))
        else:
            brand_agg[lbl] = agg[col].fillna(0)

    brand_df = pd.DataFrame(brand_agg)
    brand_df.insert(0, "Retailer", agg["retailer"].values)

    # Sort by Philips avg descending
    sort_brands = [b for b in ["Philips"] if b in brand_df.columns]
    if sort_brands:
        brand_df = brand_df.sort_values(sort_brands[0], ascending=False)

    # ── Brand selector (limit to top N for readability) ───────────────────────
    all_brands = [c for c in brand_df.columns if c != "Retailer"]
    top_brands_default = sorted(
        all_brands,
        key=lambda b: brand_df[b].mean(),
        reverse=True,
    )[:10]
    selected_brands = st.multiselect(
        "Brands to show",
        options=all_brands,
        default=top_brands_default,
        key="facings_brands",
    )
    if not selected_brands:
        selected_brands = top_brands_default

    plot_df = brand_df[["Retailer"] + selected_brands].copy()

    sort_by = st.radio("Sort", ["Score ↓", "A → Z"], horizontal=True, key="facings_sort")
    if sort_by == "A → Z":
        plot_df = plot_df.sort_values("Retailer")
    elif "Philips" in plot_df.columns:
        plot_df = plot_df.sort_values("Philips", ascending=False)

    # Color palette — highlight Philips
    color_map: dict[str, str] = {}
    palette = px.colors.qualitative.Plotly + px.colors.qualitative.D3
    pal_idx = 0
    for brand in selected_brands:
        if brand == "Philips":
            color_map[brand] = PHILIPS_COLOR
        else:
            color_map[brand] = palette[pal_idx % len(palette)]
            pal_idx += 1

    # ── Stacked bar chart ─────────────────────────────────────────────────────
    fig = go.Figure()
    for brand in selected_brands:
        fig.add_trace(go.Bar(
            name=brand,
            x=plot_df["Retailer"],
            y=plot_df[brand],
            marker_color=color_map[brand],
            text=plot_df[brand].apply(lambda v: f"{v:.1f}" if v >= 0.5 else ""),
            textposition="inside",
            textfont=dict(size=8),
        ))

    fig.update_layout(
        title=f"# Avg. {facing_type} Facings by Retailer and Brand",
        barmode="stack",
        yaxis_title="Avg Facings",
        xaxis=dict(tickangle=-45),
        legend=dict(orientation="v", x=1.01, y=1),
        height=370,
        margin=dict(t=40, b=80, r=150),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Philips share table ───────────────────────────────────────────────────
    st.subheader("Philips Share of Shelf")
    if "Philips" in plot_df.columns:
        total_col = plot_df[selected_brands].sum(axis=1)
        philips_share = (plot_df["Philips"] / total_col.replace(0, float("nan")) * 100).round(1)
        share_tbl = pd.DataFrame({
            "Retailer":         plot_df["Retailer"].values,
            "Philips Facings":  plot_df["Philips"].values,
            "Total Facings":    total_col.values.round(1),
            "Philips Share %":  philips_share.values,
        })
        st.dataframe(
            share_tbl.style.format({"Philips Share %": "{:.1f}%"}),
            hide_index=True,
            use_container_width=True,
        )

    # ── Raw data ──────────────────────────────────────────────────────────────
    with st.expander("Show raw facings data"):
        st.dataframe(plot_df, hide_index=True, use_container_width=True)


main()
