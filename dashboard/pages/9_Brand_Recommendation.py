"""
View: Brand Recommendation (1st recommended brand)
  - 100% stacked bar: X = price range (Low/Medium/High), stacked = brands
  - Side table: price range breakdown
  - Also shows wave comparison toggle
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

st.set_page_config(page_title="Brand Recommendation", page_icon="💬", layout="wide", initial_sidebar_state="collapsed")
require_password()

PHILIPS_COLOR  = "#003087"
PRICE_ORDER    = ["Low", "Medium", "High"]


def _build_chart(
    df: pd.DataFrame,
    brand_col: str,
    title: str,
    x_col: str = "price_range",
    x_order: list[str] | None = None,
    top_n_brands: int = 12,
) -> go.Figure | None:
    """Build a 100% stacked bar: X = x_col, stacked = brands."""
    if brand_col not in df.columns:
        return None

    sub = df[[x_col, brand_col]].dropna()
    sub = sub[sub[x_col].isin(x_order or sub[x_col].unique())]
    sub = sub[sub[brand_col] != ""]

    if sub.empty:
        return None

    pivot = (
        sub.groupby([x_col, brand_col])
        .size()
        .unstack(fill_value=0)
    )
    # Reorder x axis
    if x_order:
        pivot = pivot.reindex([o for o in x_order if o in pivot.index])

    # Keep top N brands by total count
    top_brands = pivot.sum().sort_values(ascending=False).head(top_n_brands).index.tolist()
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
        yaxis=dict(range=[0, 105], title="% of Recommendations", ticksuffix="%"),
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
    render_header("Brand Recommendation")
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
        key="rec_xby",
    )

    x_col_map = {
        "Price Range": ("price_range",  PRICE_ORDER),
        "Wave":        ("wave",         None),
        "Country":     ("market_name",  None),
        "Retailer":    ("retailer",     None),
    }
    x_col, x_order = x_col_map[view_by]

    top_n = st.slider("Max brands shown", 5, 20, 12, key="rec_topn")

    st.subheader("1st Recommended Brand")
    fig1 = _build_chart(
        filtered, "kpi3_1st_recommended_brand",
        f"% Brand Recommendation by {view_by} — 1st Choice",
        x_col=x_col, x_order=x_order, top_n_brands=top_n,
    )
    if fig1:
        st.plotly_chart(fig1, use_container_width=True)
    else:
        st.info("No recommendation data available.")

    # Price range visits table (only for Price Range view)
    if view_by == "Price Range" and "price_range" in filtered.columns:
        pr_visits = (
            filtered.groupby("price_range")
            .size()
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

    # Reason breakdown for 1st recommendation
    if "kpi3_1st_recommendation_reason" in filtered.columns:
        st.subheader("Recommendation Reasons (1st choice)")
        reasons = (
            filtered["kpi3_1st_recommendation_reason"]
            .dropna()
            .str.split("|")
            .explode()
            .str.strip()
        )
        reasons = reasons[reasons != ""]
        reason_counts = (
            reasons.value_counts()
            .reset_index()
        )
        reason_counts.columns = ["Reason", "Count"]
        reason_counts["% Total"] = (reason_counts["Count"] / len(filtered) * 100).round(1)

        fig_r = go.Figure(go.Bar(
            x=reason_counts["% Total"].values,
            y=reason_counts["Reason"].values,
            orientation="h",
            marker_color="#0075BE",
            text=reason_counts["% Total"].apply(lambda v: f"{v:.1f}%"),
            textposition="outside",
        ))
        fig_r.update_layout(
            title="Reason for Recommendation",
            xaxis_title="% of Stores",
            yaxis=dict(autorange="reversed"),
            height=max(230, len(reason_counts) * 21 + 45),
            margin=dict(t=35, b=30, r=80),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_r, use_container_width=True)


main()
