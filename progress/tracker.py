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
import yaml
from datetime import date, datetime

from progress.connectors import roamler, wiser, pinion
from dashboard.auth import require_password
from dashboard.branding import render_header, STATUS_COLORS, ROAMLER_ORANGE

# ─── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Versuni MS Wave III — Progress",
    page_icon="📊",
    layout="wide",
)
require_password()

FIELDWORK_START = "2026-03-09"
CONFIG_DIR = Path(__file__).parent.parent / "config"

MARKET_NAMES = {
    "DE": "Germany", "FR": "France", "NL": "Netherlands",
    "UK": "United Kingdom", "TR": "Turkey",
    "AU": "Australia", "BR": "Brazil", "US": "United States",
}


# ─── Targets ─────────────────────────────────────────────────────────────────

def load_targets_from_file() -> pd.DataFrame:
    """Load targets from config/targets.yaml, return as DataFrame."""
    targets_file = CONFIG_DIR / "targets.yaml"
    if not targets_file.exists():
        return pd.DataFrame(columns=["market", "category", "target"])
    with open(targets_file) as f:
        data = yaml.safe_load(f)
    rows = []
    for market, cats in (data.get("targets") or {}).items():
        for cat, tgt in cats.items():
            rows.append({"market": market, "category": cat, "target": int(tgt or 0)})
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["market", "category", "target"])


# ─── Data loading ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)  # refresh every 5 minutes
def load_all_progress(date_from: str, date_to: str) -> pd.DataFrame:
    rows = []
    rows += roamler.get_progress(date_from, date_to)
    rows += wiser.get_progress(date_from, date_to)
    rows += pinion.get_progress(date_from, date_to)
    df = pd.DataFrame(rows)
    df["market_name"] = df["market"].map(MARKET_NAMES).fillna(df["market"])
    return df


# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        f"<div style='color:#FF6738;font-weight:700;font-size:0.85rem;"
        f"text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px'>"
        f"⚙️ Controls</div>",
        unsafe_allow_html=True,
    )

    # Date range
    st.subheader("📅 Date Range")
    d_from = st.date_input("From", value=date(2025, 1, 1),  key="date_from")
    d_to   = st.date_input("To",   value=date(2025, 12, 31), key="date_to")
    date_from_str = d_from.strftime("%Y-%m-%d")
    date_to_str   = d_to.strftime("%Y-%m-%d")
    st.caption("Switch to 2026-03-09 → 2026-06-30 for live Wave III data.")

    st.divider()

    # Targets editor
    st.subheader("🎯 Visit Targets")
    st.caption("Edit below or update `config/targets.yaml`. Changes apply this session only.")
    default_targets = load_targets_from_file()
    targets_df = st.data_editor(
        default_targets,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "market":   st.column_config.TextColumn("Market", width="small"),
            "category": st.column_config.TextColumn("Category"),
            "target":   st.column_config.NumberColumn("Target", min_value=0, step=1),
        },
        key="targets_editor",
    )

    st.divider()

    # API status
    st.subheader("🔌 API Status")
    roamler_ok = roamler.is_configured()
    wiser_ok   = wiser.is_configured()
    pinion_ok  = pinion.is_configured()

    def _status_badge(ok: bool) -> str:
        if ok:
            return "🟢"
        return "🔴"

    st.markdown(
        f"{_status_badge(roamler_ok)} **Roamler** — EU/TR  \n"
        f"{_status_badge(wiser_ok)}   **Wiser** — AU/US  \n"
        f"{_status_badge(pinion_ok)}  **Pinion** — BR"
    )
    if not roamler_ok:
        st.warning("Add ROAMLER_API_KEY to Streamlit secrets.", icon="⚠️")


# ─── Header ───────────────────────────────────────────────────────────────────
render_header(f"Wave III · {date_from_str} → {date_to_str}")

col_refresh, col_ts = st.columns([1, 6])
with col_refresh:
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()
with col_ts:
    st.caption(
        f"Fieldwork starts: {FIELDWORK_START} · "
        f"Last refreshed: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC"
    )

df = load_all_progress(date_from_str, date_to_str)

# ─── Merge targets ────────────────────────────────────────────────────────────
if not targets_df.empty and "target" in targets_df.columns:
    df = df.drop(columns=["target"], errors="ignore")
    df = df.merge(
        targets_df[["market", "category", "target"]],
        on=["market", "category"],
        how="left",
    )
df["target"] = df.get("target", pd.Series(0, index=df.index)).fillna(0).astype(int)

# Recompute pct + status
df["pct"] = (
    (df["completed"] / df["target"] * 100)
    .where(df["target"] > 0, other=0)
    .round(1)
    .fillna(0)
)
df["status"] = df["pct"].apply(
    lambda p: "complete" if p >= 100 else "on_track" if p >= 60 else
              "at_risk" if p >= 30 else "critical" if p > 0 else "pending"
)

# ─── KPI Summary ──────────────────────────────────────────────────────────────
total_target     = int(df["target"].sum())
total_completed  = int(df["completed"].sum())
overall_pct      = round(total_completed / total_target * 100, 1) if total_target > 0 else None
markets_active   = df[df["completed"] > 0]["market"].nunique()
markets_complete = df[df["status"] == "complete"]["market"].nunique()

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric(
    "Overall Progress",
    f"{overall_pct}%" if overall_pct is not None else "—",
    help="Requires targets to be set",
)
k2.metric(
    "Completed Visits",
    f"{total_completed:,}",
    f"of {total_target:,}" if total_target > 0 else "target not set",
)
k3.metric("Markets Active",   markets_active,   f"of {df['market'].nunique()}")
k4.metric("Markets Complete", markets_complete)
k5.metric("Platforms",        df["platform"].nunique())

st.divider()

# ─── Filters ──────────────────────────────────────────────────────────────────
col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    sel_market   = st.selectbox("Market",   ["All"] + sorted(df["market"].unique().tolist()))
with col_f2:
    sel_category = st.selectbox("Category", ["All"] + sorted(df["category"].unique().tolist()))
with col_f3:
    sel_platform = st.selectbox("Platform", ["All"] + sorted(df["platform"].unique().tolist()))

filtered = df.copy()
if sel_market   != "All": filtered = filtered[filtered["market"]   == sel_market]
if sel_category != "All": filtered = filtered[filtered["category"] == sel_category]
if sel_platform != "All": filtered = filtered[filtered["platform"] == sel_platform]

# ─── Chart helpers ─────────────────────────────────────────────────────────────
_targets_set = total_target > 0

def _chart_layout(fig, height: int = 360):
    fig.update_layout(
        height=height,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Inter, sans-serif", color="#333"),
        margin=dict(l=8, r=8, t=8, b=8),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            font=dict(size=11),
        ),
        xaxis=dict(gridcolor="#F0F0F0", zerolinecolor="#E0E0E0"),
        yaxis=dict(gridcolor="#F0F0F0", zerolinecolor="#E0E0E0"),
    )
    return fig


# ─── Progress by Market ───────────────────────────────────────────────────────
st.subheader("Progress by Market")

market_df = (
    filtered.groupby(["market", "market_name"])
    .agg(target=("target", "sum"), completed=("completed", "sum"))
    .reset_index()
)
market_df["pct"] = (market_df["completed"] / market_df["target"] * 100).where(
    market_df["target"] > 0, 0).round(1).fillna(0)
market_df["status"] = market_df["pct"].apply(
    lambda p: "complete" if p >= 100 else "on_track" if p >= 60 else
              "at_risk" if p >= 30 else "critical" if p > 0 else "pending"
)
market_df["label"] = market_df.apply(
    lambda r: f"{r['pct']:.0f}%  ({int(r['completed'])} visits)" if r["target"] > 0
              else f"{int(r['completed'])} visits",
    axis=1,
)

x_col = "pct" if _targets_set else "completed"
x_max = max((market_df[x_col].max() if not market_df.empty else 10) * 1.25, 10)

fig_market = px.bar(
    market_df.sort_values("completed", ascending=True),
    x=x_col, y="market_name",
    orientation="h",
    text="label",
    color="status",
    color_discrete_map=STATUS_COLORS,
    labels={
        "pct": "Completion %", "completed": "Completed visits", "market_name": "",
    },
)
fig_market.update_traces(textposition="outside", marker_line_width=0)
fig_market = _chart_layout(fig_market, height=max(280, len(market_df) * 52))
fig_market.update_layout(xaxis_range=[0, x_max], showlegend=True)
st.plotly_chart(fig_market, use_container_width=True)

# ─── Progress by Category ─────────────────────────────────────────────────────
st.subheader("Progress by Category")

cat_df = (
    filtered.groupby("category")
    .agg(target=("target", "sum"), completed=("completed", "sum"))
    .reset_index()
)
cat_df["pct"] = (cat_df["completed"] / cat_df["target"] * 100).where(
    cat_df["target"] > 0, 0).round(1).fillna(0)
cat_df["label"] = cat_df.apply(
    lambda r: f"{r['pct']:.0f}%  ({int(r['completed'])})" if r["target"] > 0
              else f"{int(r['completed'])} visits",
    axis=1,
)

y_col = "pct" if _targets_set else "completed"
y_max = max((cat_df[y_col].max() if not cat_df.empty else 10) * 1.25, 10)

fig_cat = px.bar(
    cat_df.sort_values("completed"),
    x="category", y=y_col,
    text="label",
    color=y_col,
    color_continuous_scale=[
        [0.0, "#E74C3C"],
        [0.3, ROAMLER_ORANGE],
        [0.6, "#3498DB"],
        [1.0, "#2ECC71"],
    ],
    labels={"pct": "Completion %", "completed": "Completed visits", "category": ""},
)
fig_cat.update_traces(textposition="outside", marker_line_width=0)
fig_cat = _chart_layout(fig_cat, height=360)
fig_cat.update_layout(
    yaxis_range=[0, y_max],
    coloraxis_showscale=False,
)
st.plotly_chart(fig_cat, use_container_width=True)

# ─── Detail table ─────────────────────────────────────────────────────────────
st.subheader("Detail")

display_df = filtered[
    ["market_name", "category", "platform", "completed", "target", "pct", "status"]
].copy()
display_df.columns = ["Market", "Category", "Platform", "Completed", "Target", "%", "Status"]
display_df = display_df.sort_values(["Market", "Category"])

st.dataframe(
    display_df.style.background_gradient(subset=["%"], cmap="RdYlGn", vmin=0, vmax=100),
    use_container_width=True,
    hide_index=True,
)

# ─── Manual upload fallback ───────────────────────────────────────────────────
with st.expander("📁 Manual data upload  (Wiser / Pinion CSV)"):
    st.markdown(
        "If Wiser or Pinion doesn't have an API yet, upload their progress export here.  \n"
        "Expected columns: `market, category, target, completed`"
    )
    uploaded = st.file_uploader("Upload CSV", type="csv")
    if uploaded:
        manual_df = pd.read_csv(uploaded)
        st.dataframe(manual_df)
        st.success(f"Loaded {len(manual_df)} rows from manual upload.")

# ─── Footer ───────────────────────────────────────────────────────────────────
st.markdown(
    f"<div style='text-align:center;color:#aaa;font-size:0.75rem;margin-top:2rem;'>"
    f"Versuni Mystery Shopping Wave III &nbsp;·&nbsp; "
    f"Roamler + Wiser + Pinion &nbsp;·&nbsp; "
    f"Internal use only</div>",
    unsafe_allow_html=True,
)
