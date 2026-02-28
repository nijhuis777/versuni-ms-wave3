"""
Versuni Mystery Shopping — Wave III BI Dashboard
=================================================
Primary Streamlit dashboard for internal team + Versuni stakeholders.
Run:  streamlit run dashboard/app.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from dashboard.auth import require_password
from dashboard.branding import render_header, inject_css, ROAMLER_ORANGE

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Versuni MS Wave III",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)
require_password()
inject_css()

VERSUNI_BLUE   = "#003087"
VERSUNI_LIGHT  = "#0075BE"
PHILIPS_RED    = "#E31837"
NEUTRAL_GREY   = "#F5F5F5"

DATA_PATH = Path(__file__).parent.parent / "data" / "processed" / "master_wave3.xlsx"

MARKET_NAMES = {
    "DE": "Germany", "FR": "France", "NL": "Netherlands",
    "UK": "United Kingdom", "TR": "Turkey",
    "AU": "Australia", "BR": "Brazil", "US": "United States",
}

KPI_LABELS = {
    "kpi1_score": "KPI1 — Availability",
    "kpi2_score": "KPI2 — Visibility",
    "kpi3_score": "KPI3 — Recommendation",
}

# ─── Data loading ─────────────────────────────────────────────────────────────
@st.cache_data
def load_data() -> pd.DataFrame:
    if not DATA_PATH.exists():
        return _demo_data()
    df = pd.read_excel(DATA_PATH, sheet_name="Master")
    df["market_name"] = df["market"].map(MARKET_NAMES).fillna(df["market"])
    return df


def _demo_data() -> pd.DataFrame:
    """Generate realistic demo data for development / before real data arrives."""
    import random
    random.seed(42)
    markets = ["DE", "FR", "NL", "UK", "TR", "AU", "BR", "US"]
    categories = ["FAEM", "SAEM", "Airfryer", "Blender", "Iron", "Handheld_Steamer"]
    retailers = {
        "DE": ["MediaMarkt", "Saturn", "Expert"], "FR": ["Fnac", "Boulanger", "Darty"],
        "NL": ["MediaMarkt", "BCC", "Coolblue"], "UK": ["Currys", "John Lewis", "Argos"],
        "TR": ["Teknosa", "MediaMarkt", "Bimeks"], "AU": ["Harvey Norman", "JB Hi-Fi"],
        "BR": ["Magazine Luiza", "Casas Bahia"], "US": ["Best Buy", "Walmart", "Target"],
    }
    brands = ["Philips", "Delonghi", "Siemens", "Tefal", "Bosch", "Ninja", "Other"]
    rows = []
    for market in markets:
        n_cats = {"DE":7,"FR":5,"NL":7,"UK":6,"TR":7,"AU":5,"BR":3,"US":2}.get(market, 5)
        n_stores = {"DE":300,"FR":250,"NL":150,"UK":250,"TR":250,"AU":150,"BR":400,"US":400}.get(market, 100)
        for cat in categories[:n_cats]:
            for i in range(min(n_stores // 10, 30)):  # sample
                kpi1 = random.uniform(50, 95)
                kpi2 = random.uniform(40, 90)
                kpi3 = random.uniform(30, 85)
                rows.append({
                    "market": market,
                    "market_name": MARKET_NAMES[market],
                    "category": cat,
                    "platform": "roamler" if market not in ["AU","US","BR"] else ("wiser" if market != "BR" else "pinion"),
                    "retailer": random.choice(retailers.get(market, ["Unknown"])),
                    "visit_date": f"2026-03-{random.randint(9,28):02d}",
                    "wave": "Wave III",
                    "kpi1_category_present": random.choice([True, True, True, False]),
                    "kpi1_versuni_brand_present": random.choice([True, True, False]),
                    "kpi1_versuni_models_count": random.randint(1, 8),
                    "kpi2_most_standout": random.choice(brands),
                    "kpi2_versuni_grouped": random.choice([True, False]),
                    "kpi3_recommended_brand": random.choice(["Philips", "Delonghi", "Tefal", "Other"]),
                    "kpi1_score": round(kpi1, 1),
                    "kpi2_score": round(kpi2, 1),
                    "kpi3_score": round(kpi3, 1),
                })
    return pd.DataFrame(rows)


# ─── Sidebar ──────────────────────────────────────────────────────────────────
def sidebar_filters(df: pd.DataFrame):
    st.sidebar.markdown(
        f"<div style='color:#FF6738;font-weight:700;font-size:0.85rem;"
        f"text-transform:uppercase;letter-spacing:0.05em;margin-bottom:8px'>"
        f"🔍 Filters</div>",
        unsafe_allow_html=True,
    )

    markets = st.sidebar.multiselect(
        "Market", options=sorted(df["market_name"].unique()),
        default=sorted(df["market_name"].unique())
    )
    categories = st.sidebar.multiselect(
        "Category", options=sorted(df["category"].unique()),
        default=sorted(df["category"].unique())
    )
    retailers = ["All"] + sorted(df["retailer"].dropna().unique().tolist())
    retailer = st.sidebar.selectbox("Retailer", retailers)

    st.sidebar.divider()
    st.sidebar.caption("Wave III · 2026 · Versuni Global MS Program")

    return markets, categories, retailer


# ─── Helpers ─────────────────────────────────────────────────────────────────
def kpi_gauge(value: float, label: str, color: str = VERSUNI_LIGHT) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        title={"text": label, "font": {"size": 13}},
        number={"suffix": "%", "font": {"size": 22}},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": color},
            "steps": [
                {"range": [0, 40],  "color": "#FDECEA"},
                {"range": [40, 70], "color": "#FFF3E0"},
                {"range": [70, 100],"color": "#E8F5E9"},
            ],
            "threshold": {"line": {"color": "black", "width": 2}, "thickness": 0.75, "value": 70},
        }
    ))
    fig.update_layout(height=200, margin=dict(l=10, r=10, t=30, b=10))
    return fig


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    df = load_data()
    using_demo = not DATA_PATH.exists()

    if using_demo:
        st.info("⚠ No master data file found — showing **demo data**. Run the ETL pipeline to load real data.", icon="⚠")

    markets, categories, retailer = sidebar_filters(df)

    # Apply filters
    filtered = df[df["market_name"].isin(markets) & df["category"].isin(categories)]
    if retailer != "All":
        filtered = filtered[filtered["retailer"] == retailer]

    # ─── Page header ──────────────────────────────────────────────────────────
    render_header("Wave III — Results Dashboard")
    st.caption(f"n = {len(filtered):,} visits · {filtered['market'].nunique()} markets · {filtered['category'].nunique()} categories")

    # ─── KPI summary gauges ───────────────────────────────────────────────────
    avg_kpi1 = filtered["kpi1_score"].mean() if "kpi1_score" in filtered else 0
    avg_kpi2 = filtered["kpi2_score"].mean() if "kpi2_score" in filtered else 0
    avg_kpi3 = filtered["kpi3_score"].mean() if "kpi3_score" in filtered else 0

    g1, g2, g3 = st.columns(3)
    with g1: st.plotly_chart(kpi_gauge(round(avg_kpi1, 1), "KPI1 — Availability", "#2196F3"), use_container_width=True)
    with g2: st.plotly_chart(kpi_gauge(round(avg_kpi2, 1), "KPI2 — Visibility", "#4CAF50"), use_container_width=True)
    with g3: st.plotly_chart(kpi_gauge(round(avg_kpi3, 1), "KPI3 — Recommendation", "#FF9800"), use_container_width=True)

    st.divider()

    # ─── Tabs ─────────────────────────────────────────────────────────────────
    tab_avail, tab_vis, tab_rec, tab_comp, tab_raw = st.tabs([
        "📦 KPI1 Availability", "👁 KPI2 Visibility", "💬 KPI3 Recommendation",
        "⚔ Competition", "📋 Raw Data"
    ])

    # ── KPI1: Availability ───────────────────────────────────────────────────
    with tab_avail:
        st.subheader("Brand Availability by Market")
        avail_mkt = filtered.groupby("market_name")["kpi1_score"].mean().reset_index()
        fig = px.bar(avail_mkt.sort_values("kpi1_score"),
                     x="kpi1_score", y="market_name", orientation="h",
                     color="kpi1_score", color_continuous_scale="Blues",
                     labels={"kpi1_score": "Availability %", "market_name": "Market"},
                     text="kpi1_score")
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_layout(coloraxis_showscale=False, xaxis_range=[0, 110])
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Availability by Category")
        avail_cat = filtered.groupby(["market_name", "category"])["kpi1_score"].mean().reset_index()
        fig2 = px.bar(avail_cat, x="category", y="kpi1_score", color="market_name",
                      barmode="group",
                      labels={"kpi1_score": "Availability %", "category": "Category"},
                      color_discrete_sequence=px.colors.qualitative.Set2)
        st.plotly_chart(fig2, use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            cat_present = filtered["kpi1_category_present"].value_counts()
            fig_pie = px.pie(values=cat_present.values,
                             names=["Present", "Not Present"],
                             title="Category present in store",
                             color_discrete_sequence=[VERSUNI_LIGHT, "#E0E0E0"])
            st.plotly_chart(fig_pie, use_container_width=True)
        with c2:
            brand_present = filtered["kpi1_versuni_brand_present"].value_counts()
            fig_pie2 = px.pie(values=brand_present.values,
                              names=["Philips available", "Not available"],
                              title="Philips brand availability",
                              color_discrete_sequence=[PHILIPS_RED, "#E0E0E0"])
            st.plotly_chart(fig_pie2, use_container_width=True)

    # ── KPI2: Visibility ─────────────────────────────────────────────────────
    with tab_vis:
        st.subheader("Visibility by Market")
        vis_mkt = filtered.groupby("market_name")["kpi2_score"].mean().reset_index()
        fig = px.bar(vis_mkt.sort_values("kpi2_score"),
                     x="kpi2_score", y="market_name", orientation="h",
                     color="kpi2_score", color_continuous_scale="Greens",
                     text="kpi2_score",
                     labels={"kpi2_score": "Visibility %", "market_name": "Market"})
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_layout(coloraxis_showscale=False, xaxis_range=[0, 110])
        st.plotly_chart(fig, use_container_width=True)

        if "kpi2_most_standout" in filtered.columns:
            st.subheader("Most Standout Brand")
            standout = filtered["kpi2_most_standout"].value_counts().reset_index()
            standout.columns = ["Brand", "Count"]
            fig2 = px.bar(standout, x="Count", y="Brand", orientation="h",
                          color="Brand",
                          color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig2, use_container_width=True)

    # ── KPI3: Recommendation ─────────────────────────────────────────────────
    with tab_rec:
        st.subheader("Brand Recommendation by Market")
        rec_mkt = filtered.groupby("market_name")["kpi3_score"].mean().reset_index()
        fig = px.bar(rec_mkt.sort_values("kpi3_score"),
                     x="kpi3_score", y="market_name", orientation="h",
                     color="kpi3_score", color_continuous_scale="Oranges",
                     text="kpi3_score",
                     labels={"kpi3_score": "Recommendation %", "market_name": "Market"})
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_layout(coloraxis_showscale=False, xaxis_range=[0, 110])
        st.plotly_chart(fig, use_container_width=True)

        if "kpi3_recommended_brand" in filtered.columns:
            st.subheader("Recommended Brand")
            rec_brand = filtered["kpi3_recommended_brand"].value_counts().reset_index()
            rec_brand.columns = ["Brand", "Count"]
            colors = [PHILIPS_RED if b == "Philips" else "#B0BEC5" for b in rec_brand["Brand"]]
            fig2 = go.Figure(go.Bar(x=rec_brand["Count"], y=rec_brand["Brand"],
                                     orientation="h", marker_color=colors,
                                     text=rec_brand["Count"], textposition="outside"))
            fig2.update_layout(yaxis=dict(autorange="reversed"),
                                xaxis_title="# Recommendations", yaxis_title="Brand")
            st.plotly_chart(fig2, use_container_width=True)

    # ── Competition ──────────────────────────────────────────────────────────
    with tab_comp:
        st.subheader("Competitive Landscape")
        st.info("Competitor analysis built from KPI1 brand availability + KPI2 standout data.")

        kpi_matrix = filtered.groupby("category").agg(
            kpi1=("kpi1_score", "mean"),
            kpi2=("kpi2_score", "mean"),
            kpi3=("kpi3_score", "mean"),
        ).reset_index()

        fig = go.Figure()
        for _, row in kpi_matrix.iterrows():
            fig.add_trace(go.Scatterpolar(
                r=[row["kpi1"], row["kpi2"], row["kpi3"], row["kpi1"]],
                theta=["Availability", "Visibility", "Recommendation", "Availability"],
                fill="toself",
                name=row["category"],
                opacity=0.6,
            ))
        fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100])), showlegend=True,
                          title="KPI Spider — by Category")
        st.plotly_chart(fig, use_container_width=True)

        # Market × KPI heatmap
        heatmap_df = filtered.groupby("market_name").agg(
            KPI1=("kpi1_score", "mean"),
            KPI2=("kpi2_score", "mean"),
            KPI3=("kpi3_score", "mean"),
        ).round(1)
        fig2 = px.imshow(heatmap_df, color_continuous_scale="RdYlGn",
                          zmin=0, zmax=100,
                          text_auto=True, aspect="auto",
                          title="KPI Heatmap — Market × KPI")
        st.plotly_chart(fig2, use_container_width=True)

    # ── Raw Data ─────────────────────────────────────────────────────────────
    with tab_raw:
        st.subheader("Raw Data Export")
        show_cols = [c for c in [
            "market_name", "category", "platform", "retailer", "visit_date",
            "kpi1_score", "kpi2_score", "kpi3_score",
            "kpi2_most_standout", "kpi3_recommended_brand"
        ] if c in filtered.columns]
        st.dataframe(filtered[show_cols], use_container_width=True, hide_index=True)

        csv = filtered.to_csv(index=False).encode()
        st.download_button("⬇ Download full dataset (CSV)", data=csv,
                            file_name="versuni_wave3_export.csv", mime="text/csv")


if __name__ == "__main__":
    main()
