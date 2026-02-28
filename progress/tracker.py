"""
Versuni MS Wave III — Fieldwork Progress Tracker
=================================================
Streamlit dashboard showing live fieldwork completion across all platforms.
Run:  streamlit run progress/tracker.py
Share: deploy to Streamlit Cloud for team access (Daniel, Paula, etc.)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

from progress.connectors import roamler, wiser, pinion

# ─── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Versuni MS Wave III — Progress",
    page_icon="📊",
    layout="wide",
)

FIELDWORK_START = "2026-03-09"
STATUS_COLORS = {
    "complete":  "#2ECC71",
    "on_track":  "#3498DB",
    "at_risk":   "#F39C12",
    "critical":  "#E74C3C",
    "pending":   "#BDC3C7",
}

MARKET_NAMES = {
    "DE": "Germany", "FR": "France", "NL": "Netherlands",
    "UK": "United Kingdom", "TR": "Turkey",
    "AU": "Australia", "BR": "Brazil", "US": "United States",
}

# ─── Data loading ────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)  # refresh every 5 minutes
def load_all_progress() -> pd.DataFrame:
    rows = []
    rows += roamler.get_progress()
    rows += wiser.get_progress()
    rows += pinion.get_progress()
    df = pd.DataFrame(rows)
    df["market_name"] = df["market"].map(MARKET_NAMES).fillna(df["market"])
    return df


# ─── Header ─────────────────────────────────────────────────────────────────
st.title("📊 Versuni Mystery Shopping — Wave III")
st.caption(f"Fieldwork start: {FIELDWORK_START} · Last refreshed: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")

col_refresh, col_spacer = st.columns([1, 8])
with col_refresh:
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()

df = load_all_progress()

# ─── KPI summary row ─────────────────────────────────────────────────────────
total_target    = df["target"].sum()
total_completed = df["completed"].sum()
overall_pct     = round(total_completed / total_target * 100, 1) if total_target > 0 else 0
markets_active  = df[df["pct"] > 0]["market"].nunique()
markets_complete = df[df["status"] == "complete"]["market"].nunique()

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Overall Progress", f"{overall_pct}%")
k2.metric("Completed Visits", f"{total_completed:,}", f"of {total_target:,}")
k3.metric("Markets Active", markets_active, f"of {df['market'].nunique()}")
k4.metric("Markets Complete", markets_complete)
k5.metric("Platforms", df["platform"].nunique())

st.divider()

# ─── Filters ─────────────────────────────────────────────────────────────────
col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    markets = ["All"] + sorted(df["market"].unique().tolist())
    sel_market = st.selectbox("Market", markets)
with col_f2:
    categories = ["All"] + sorted(df["category"].unique().tolist())
    sel_category = st.selectbox("Category", categories)
with col_f3:
    platforms = ["All"] + sorted(df["platform"].unique().tolist())
    sel_platform = st.selectbox("Platform", platforms)

filtered = df.copy()
if sel_market != "All":    filtered = filtered[filtered["market"] == sel_market]
if sel_category != "All":  filtered = filtered[filtered["category"] == sel_category]
if sel_platform != "All":  filtered = filtered[filtered["platform"] == sel_platform]

# ─── Progress by Market ───────────────────────────────────────────────────────
st.subheader("Progress by Market")

market_df = (
    filtered.groupby(["market", "market_name"])
    .agg(target=("target", "sum"), completed=("completed", "sum"))
    .reset_index()
)
market_df["pct"] = (market_df["completed"] / market_df["target"] * 100).round(1).fillna(0)
market_df["status"] = market_df["pct"].apply(
    lambda p: "complete" if p >= 100 else "on_track" if p >= 60 else "at_risk" if p >= 30 else "critical" if p > 0 else "pending"
)
market_df["color"] = market_df["status"].map(STATUS_COLORS)

fig_market = px.bar(
    market_df.sort_values("pct", ascending=True),
    x="pct", y="market_name",
    orientation="h",
    text="pct",
    color="status",
    color_discrete_map=STATUS_COLORS,
    labels={"pct": "Completion %", "market_name": "Market"},
)
fig_market.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
fig_market.update_layout(height=350, showlegend=True, xaxis_range=[0, 110])
st.plotly_chart(fig_market, use_container_width=True)

# ─── Progress by Category ─────────────────────────────────────────────────────
st.subheader("Progress by Category")

cat_df = (
    filtered.groupby("category")
    .agg(target=("target", "sum"), completed=("completed", "sum"))
    .reset_index()
)
cat_df["pct"] = (cat_df["completed"] / cat_df["target"] * 100).round(1).fillna(0)

fig_cat = px.bar(
    cat_df.sort_values("pct"),
    x="category", y="pct",
    color="pct",
    color_continuous_scale=["#E74C3C", "#F39C12", "#3498DB", "#2ECC71"],
    labels={"pct": "Completion %", "category": "Category"},
    text="pct",
)
fig_cat.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
fig_cat.update_layout(height=350, coloraxis_showscale=False, yaxis_range=[0, 110])
st.plotly_chart(fig_cat, use_container_width=True)

# ─── Detail table ─────────────────────────────────────────────────────────────
st.subheader("Detail")
display_df = filtered[["market_name", "category", "platform", "completed", "target", "pct", "status"]].copy()
display_df.columns = ["Market", "Category", "Platform", "Completed", "Target", "%", "Status"]
display_df = display_df.sort_values(["Market", "Category"])

st.dataframe(
    display_df.style.background_gradient(subset=["%"], cmap="RdYlGn", vmin=0, vmax=100),
    use_container_width=True,
    hide_index=True,
)

# ─── Manual upload fallback ───────────────────────────────────────────────────
with st.expander("📁 Manual data upload (Wiser / Pinion CSV)"):
    st.markdown(
        "If Wiser or Pinion doesn't have an API yet, upload their progress export here. "
        "Expected columns: `market, category, target, completed`"
    )
    uploaded = st.file_uploader("Upload CSV", type="csv")
    if uploaded:
        manual_df = pd.read_csv(uploaded)
        st.dataframe(manual_df)
        st.success(f"Loaded {len(manual_df)} rows from manual upload.")

st.caption("Versuni MS Wave III · Roamler + Wiser + Pinion · Internal use only")
