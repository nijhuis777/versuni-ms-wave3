"""
View: 2nd Brand Recommendation
  - Same layout as page 9 but for kpi3_2nd_recommended_brand
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

st.set_page_config(page_title="2nd Brand Recommendation", page_icon="💬", layout="wide", initial_sidebar_state="collapsed")
require_password()

PHILIPS_COLOR = "#003087"
PRICE_ORDER   = ["Low", "Medium", "High"]


def _build_chart(df, brand_col, title, x_col="price_range", x_order=None, top_n=12):
    if brand_col not in df.columns:
        return None
    sub = df[[x_col, brand_col]].dropna()
    if x_order:
        sub = sub[sub[x_col].isin(x_order)]
    sub = sub[sub[brand_col] != ""]
    if sub.empty:
        return None

    pivot = (
        sub.groupby([x_col, brand_col]).size().unstack(fill_value=0)
    )
    if x_order:
        pivot = pivot.reindex([o for o in x_order if o in pivot.index])

    top_brands = pivot.sum().sort_values(ascending=False).head(top_n).index.tolist()
    other_brands = [b for b in pivot.columns if b not in top_brands]
    if other_brands:
        pivot["Other"] = pivot[other_brands].sum(axis=1)
        pivot = pivot.drop(columns=other_brands)
        top_brands = [b for b in top_brands if b in pivot.columns] + ["Other"]

    pivot_pct = (pivot.div(pivot.sum(axis=1), axis=0) * 100).round(1)
    pivot_pct = pivot_pct[top_brands]

    palette = px.colors.qualitative.Plotly + px.colors.qualitative.D3 + px.colors.qualitative.Set1
    fig = go.Figure()
    for i, brand in enumerate(top_brands):
        color = PHILIPS_COLOR if brand == "Philips" else palette[i % len(palette)]
        vals = pivot_pct[brand] if brand in pivot_pct.columns else [0] * len(pivot_pct)
        fig.add_trace(go.Bar(
            name=brand,
            x=pivot_pct.index,
            y=vals,
            marker_color=color,
            text=[f"{v:.1f}%" if v >= 4 else "" for v in vals],
            textposition="inside",
            textfont=dict(size=9, color="white"),
        ))

    fig.update_layout(
        title=title,
        barmode="stack",
        yaxis=dict(range=[0, 105], title="% of 2nd Recommendations", ticksuffix="%"),
        xaxis_title=x_col.replace("_", " ").title(),
        legend=dict(orientation="v", x=1.01, y=1, font=dict(size=10)),
        height=350,
        margin=dict(t=40, b=35, r=200),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def main():
    df, is_demo = load_master()
    inject_css()
    render_header("2nd Brand Recommendation")
    if is_demo:
        st.info("⚠ Showing **demo data**.", icon="⚠")

    flt = sidebar_filters(df)
    filtered = apply_filters(df, **flt)

    st.caption(n_visits_caption(filtered))

    if filtered.empty:
        st.warning("No data matches the selected filters.")
        return

    view_by = st.radio(
        "X-axis grouping",
        ["Price Range", "Wave", "Country", "Retailer"],
        horizontal=True,
        key="rec2_xby",
    )
    x_col_map = {
        "Price Range": ("price_range",  PRICE_ORDER),
        "Wave":        ("wave",         None),
        "Country":     ("market_name",  None),
        "Retailer":    ("retailer",     None),
    }
    x_col, x_order = x_col_map[view_by]

    top_n = st.slider("Max brands shown", 5, 20, 12, key="rec2_topn")

    st.subheader("2nd Recommended Brand")
    fig = _build_chart(
        filtered, "kpi3_2nd_recommended_brand",
        f"% 2nd Brand Recommendation by {view_by}",
        x_col=x_col, x_order=x_order, top_n=top_n,
    )
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No 2nd recommendation data available.")

    if view_by == "Price Range" and "price_range" in filtered.columns:
        pr_visits = (
            filtered.groupby("price_range").size()
            .reset_index(name="# Visits")
            .assign(pct=lambda d: (d["# Visits"] / d["# Visits"].sum() * 100).round(1))
            .rename(columns={"price_range": "Price Range", "pct": "% Visits"})
        )
        st.dataframe(
            pr_visits.style.format({"% Visits": "{:.1f}%"}),
            hide_index=True,
            use_container_width=True,
        )

    st.divider()

    # 1st vs 2nd brand comparison
    st.subheader("1st vs 2nd Brand Choice — Philips")
    has_both = (
        "kpi3_1st_recommended_brand" in filtered.columns
        and "kpi3_2nd_recommended_brand" in filtered.columns
    )
    if has_both:
        n = len(filtered)
        p1 = (filtered["kpi3_1st_recommended_brand"] == "Philips").sum()
        p2 = (filtered["kpi3_2nd_recommended_brand"] == "Philips").sum()
        c1, c2 = st.columns(2)
        c1.metric("Philips — 1st Choice", f"{p1/n*100:.1f}%", help=f"{p1:,} of {n:,} stores")
        c2.metric("Philips — 2nd Choice", f"{p2/n*100:.1f}%", help=f"{p2:,} of {n:,} stores")


main()
