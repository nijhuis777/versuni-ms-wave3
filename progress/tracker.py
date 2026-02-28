"""
Versuni MS Wave III — Project Hub
==================================
Central Streamlit dashboard for the Wave III fieldwork project.

Tabs:
  📊 Progress       — live fieldwork completion across all platforms
  📋 Questionnaires — upload & compare questionnaire JSON files
  📁 Data Hub       — upload, merge and commit Excel/CSV market data

Run:  streamlit run progress/tracker.py
Share: deploy to Streamlit Cloud for team access (Daniel, Paula, etc.)
"""

import sys
from pathlib import Path
_repo_root = str(Path(__file__).parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import streamlit as st
import pandas as pd
import plotly.express as px
import yaml
from datetime import date, datetime

# ─── Page config (must be first st call) ─────────────────────────────────────
st.set_page_config(
    page_title="Versuni MS Wave III — Project Hub",
    page_icon="📊",
    layout="wide",
)

from progress.connectors import roamler, wiser, pinion
from dashboard.auth import require_password

try:
    from dashboard.branding import (
        render_header, inject_css, theme_selector,
        STATUS_COLORS, ROAMLER_ORANGE,
    )
except Exception as _branding_err:
    import traceback as _tb
    st.error(
        f"**Import error — dashboard.branding:**\n\n"
        f"```\n{_branding_err}\n```\n\n"
        f"**Full traceback:**\n```\n{_tb.format_exc()}\n```\n\n"
        f"**sys.path:** `{sys.path}`"
    )
    st.stop()

require_password()

_theme = st.session_state.get("theme", "light")
inject_css(_theme)

FIELDWORK_START = "2026-03-09"
CONFIG_DIR = Path(__file__).parent.parent / "config"

MARKET_NAMES = {
    "DE": "Germany", "FR": "France", "NL": "Netherlands",
    "UK": "United Kingdom", "TR": "Turkey",
    "AU": "Australia", "BR": "Brazil", "US": "United States",
    "POL": "Poland",   # 2025 Wave II scope; not in Wave III
}


# ─── Targets ──────────────────────────────────────────────────────────────────

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


# ─── Data loading ──────────────────────────────────────────────────────────────
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
    st.subheader("🎨 Theme")
    _theme = theme_selector(sidebar=True)
    inject_css(_theme)

    st.divider()

    st.subheader("📅 Date Range")
    d_from = st.date_input("From", value=date(2025, 1, 1),  key="date_from")
    d_to   = st.date_input("To",   value=date(2025, 12, 31), key="date_to")
    date_from_str = d_from.strftime("%Y-%m-%d")
    date_to_str   = d_to.strftime("%Y-%m-%d")
    st.caption("Switch to 2026-03-09 → 2026-06-30 for live Wave III data.")

    st.divider()

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

    st.subheader("🔌 API Status")
    roamler_ok = roamler.is_configured()
    wiser_ok   = wiser.is_configured()
    pinion_ok  = pinion.is_configured()

    def _badge(ok: bool) -> str:
        return "🟢" if ok else "🔴"

    st.markdown(
        f"{_badge(roamler_ok)} **Roamler** — EU/TR  \n"
        f"{_badge(wiser_ok)}   **Wiser** — AU/US  \n"
        f"{_badge(pinion_ok)}  **Pinion** — BR"
    )
    if not roamler_ok:
        st.warning("Add ROAMLER_API_KEY to Streamlit secrets.", icon="⚠️")


# ─── Header ───────────────────────────────────────────────────────────────────
render_header(f"Wave III · {date_from_str} → {date_to_str}", theme=_theme)

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

try:
    df = load_all_progress(date_from_str, date_to_str)
except Exception as _load_err:
    st.error(f"⚠️ Error loading progress data: {_load_err}")
    import traceback as _tb
    with st.expander("Error details"):
        st.code(_tb.format_exc())
    df = pd.DataFrame(columns=[
        "market", "market_name", "category", "platform",
        "completed", "target", "pct", "status",
    ])

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

# ─── Top-level tabs ────────────────────────────────────────────────────────────
tab_progress, tab_questionnaires, tab_datahub = st.tabs([
    "📊 Fieldwork Progress",
    "📋 Questionnaires",
    "📁 Data Hub",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Fieldwork Progress
# ══════════════════════════════════════════════════════════════════════════════
with tab_progress:

    # ─── KPI Summary ──────────────────────────────────────────────────────────
    total_target     = int(df["target"].sum())
    total_completed  = int(df["completed"].sum())
    overall_pct      = round(total_completed / total_target * 100, 1) if total_target > 0 else None
    markets_active   = df[df["completed"] > 0]["market"].nunique()
    markets_complete = df[df["status"] == "complete"]["market"].nunique()

    k1, k2, k3, k4, k5, k6, k7, k8 = st.columns(8)
    k1.metric("Progress",         f"{overall_pct}%" if overall_pct is not None else "—")
    k2.metric("Completed",        f"{total_completed:,}")
    k3.metric("Target",           f"{total_target:,}" if total_target > 0 else "—")
    k4.metric("Markets Active",   markets_active)
    k5.metric("Markets Complete", markets_complete)
    k6.metric("Platforms",        df["platform"].nunique())

    # ─── Data-quality notice ───────────────────────────────────────────────────
    _rm_df = df[df["platform"] == "roamler"] if not df.empty else df
    if not _rm_df.empty:
        _stub = "note" in _rm_df.columns and _rm_df["note"].notna().any()
        _err  = "error" in _rm_df.columns and _rm_df["error"].notna().any()
        _zero = int(_rm_df["completed"].sum()) == 0
        if _err:
            st.error(f"Roamler API error: {_rm_df['error'].dropna().iloc[0]}")
        elif _stub:
            st.warning("⚠️ Roamler is using **stub data** (API not configured or failed). "
                       "Check the 🔍 debug expander below for details.")
        elif _zero and roamler_ok:
            st.info(f"ℹ️ Roamler returned **0 completed visits** for "
                    f"{date_from_str} → {date_to_str}. "
                    "Either no approved submissions exist for this date range, "
                    "or all jobs are being skipped (unknown market). "
                    "Check the 🔍 debug expander below.")

    with k7:
        sel_market = st.selectbox(
            "Market", ["All"] + sorted(df["market"].unique().tolist()),
            key="prog_market", label_visibility="collapsed",
        )
        st.caption("Market")
    with k8:
        sel_platform = st.selectbox(
            "Platform", ["All"] + sorted(df["platform"].unique().tolist()),
            key="prog_platform", label_visibility="collapsed",
        )
        st.caption("Platform")

    filtered = df.copy()
    if sel_market   != "All": filtered = filtered[filtered["market"]   == sel_market]
    if sel_platform != "All": filtered = filtered[filtered["platform"] == sel_platform]

    _targets_set = total_target > 0

    # ─── Chart helpers ────────────────────────────────────────────────────────
    def _chart_layout(fig, height: int = 260):
        fig.update_layout(
            height=height,
            plot_bgcolor="white",
            paper_bgcolor="white",
            font=dict(family="Inter, sans-serif", color="#444", size=11),
            margin=dict(l=4, r=110, t=4, b=4),
            legend=dict(
                orientation="h",
                yanchor="bottom", y=1.01,
                xanchor="right", x=1,
                font=dict(size=10),
                bgcolor="rgba(0,0,0,0)",
            ),
            xaxis=dict(gridcolor="#F4F4F4", zerolinecolor="#E8E8E8", tickfont=dict(size=10)),
            yaxis=dict(gridcolor="#F4F4F4", zerolinecolor="#E8E8E8", tickfont=dict(size=10)),
        )
        return fig

    # ─── Bar chart: drill-down ────────────────────────────────────────────────
    # No market selected → progress by market
    # Market selected    → progress by category within that market
    def _make_label(cdf: pd.DataFrame) -> pd.Series:
        """Vectorised label — avoids pandas ValueError from apply() on certain dtypes."""
        compl = cdf["completed"].fillna(0).astype(int)
        pct   = cdf["pct"].fillna(0).round(0).astype(int)
        with_target    = pct.astype(str) + "%  (" + compl.astype(str) + " visits)"
        without_target = compl.astype(str) + " visits"
        return with_target.where(cdf["target"] > 0, without_target)

    def _status_vec(pct_series: pd.Series) -> pd.Series:
        s = pd.Series("pending", index=pct_series.index)
        s = s.where(pct_series <= 0,   "critical")
        s = s.where(pct_series < 30,   "at_risk")
        s = s.where(pct_series < 60,   "on_track")
        s = s.where(pct_series < 100,  "complete")
        return s

    if sel_market == "All":
        st.subheader("Progress by Market")
        chart_df = (
            filtered.groupby(["market", "market_name"])
            .agg(target=("target", "sum"), completed=("completed", "sum"))
            .reset_index()
        )
        chart_df["completed"] = chart_df["completed"].fillna(0).astype(int)
        chart_df["pct"] = (chart_df["completed"] / chart_df["target"] * 100).where(
            chart_df["target"] > 0, 0).round(1).fillna(0)
        chart_df["status"] = _status_vec(chart_df["pct"])
        chart_df["label"]  = _make_label(chart_df)
        y_col = "market_name"

    else:
        st.subheader(f"Progress by Category — {MARKET_NAMES.get(sel_market, sel_market)}")
        chart_df = (
            filtered.groupby("category")
            .agg(target=("target", "sum"), completed=("completed", "sum"))
            .reset_index()
        )
        chart_df["completed"] = chart_df["completed"].fillna(0).astype(int)
        chart_df["pct"] = (chart_df["completed"] / chart_df["target"] * 100).where(
            chart_df["target"] > 0, 0).round(1).fillna(0)
        chart_df["status"] = _status_vec(chart_df["pct"])
        chart_df["label"]  = _make_label(chart_df)
        y_col = "category"

    if not chart_df.empty:
        x_col = "pct" if _targets_set else "completed"
        x_max = max(chart_df[x_col].max() * 1.35, 10)
        fig_bar = px.bar(
            chart_df.sort_values("completed", ascending=True),
            x=x_col, y=y_col,
            orientation="h",
            text="label",
            color="status",
            color_discrete_map=STATUS_COLORS,
            labels={"pct": "Completion %", "completed": "Completed visits",
                    "market_name": "", "category": ""},
        )
        fig_bar.update_traces(
            textposition="outside",
            marker_line_width=0,
            textfont=dict(size=10),
        )
        fig_bar = _chart_layout(fig_bar, height=max(180, len(chart_df) * 36))
        fig_bar.update_layout(xaxis_range=[0, x_max], showlegend=True)
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("No data for the selected filters.")

    # ─── Detail table ──────────────────────────────────────────────────────────
    with st.expander(f"📋 Detail table  ({len(filtered)} rows)", expanded=False):
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

    # ─── Roamler job diagnostics ───────────────────────────────────────────────
    with st.expander("🔍 Roamler job diagnostics (debug)", expanded=False):
        st.caption(
            "Shows every job the Roamler API returns and how its name was parsed. "
            "Use this to spot jobs assigned to the wrong market / category."
        )
        if roamler_ok:
            debug_rows, meta = roamler.debug_jobs()
            if "error" in meta:
                st.error(meta["error"])
            else:
                st.caption(
                    f"**{meta['total_fetched']} jobs fetched** — "
                    f"markets: {', '.join(meta['markets_found'])} — "
                    f"skipped (unknown market): {meta['skipped_unknown_market']}"
                )
                if debug_rows:
                    import pandas as _pd
                    dbg = _pd.DataFrame(debug_rows)
                    st.dataframe(
                        dbg[["id", "market", "category", "workingTitle", "title"]],
                        use_container_width=True,
                        hide_index=True,
                    )

                    # ── Raw get_progress() diagnostic ─────────────────────
                    st.divider()
                    st.caption("**Raw get_progress() output** — bypass the cache and call "
                               "the full pipeline directly to see exactly what data is returned.")
                    if st.button("🧪 Run get_progress() now", key="run_get_progress"):
                        with st.spinner("Running get_progress()…"):
                            try:
                                _prog = roamler.get_progress(date_from_str, date_to_str)
                            except Exception as _pe:
                                st.error(f"get_progress() raised: {_pe}")
                                _prog = []
                        if _prog:
                            _prog_df = _pd.DataFrame(_prog)
                            total_c  = int(_prog_df["completed"].sum())
                            st.success(
                                f"get_progress() returned **{len(_prog)} rows** · "
                                f"**{total_c} total completed** for {date_from_str} → {date_to_str}"
                            )
                            for _col in ["error", "note", "skipped_job_ids"]:
                                if _col in _prog_df.columns:
                                    _v = _prog_df[_col].dropna()
                                    if not _v.empty:
                                        st.warning(f"{_col}: {_v.iloc[0]}")
                            _show_cols = [c for c in
                                          ["market","category","completed","skipped_jobs","date_from","date_to"]
                                          if c in _prog_df.columns]
                            st.dataframe(_prog_df[_show_cols], use_container_width=True, hide_index=True)
                        else:
                            st.warning("get_progress() returned an empty list.")

                    # ── Per-job submission count (on demand) ───────────────
                    st.divider()
                    st.caption(
                        "**Load submission counts** — fetches submissions for every job in "
                        "the selected date range. Takes ~1–2 min for 77 jobs."
                    )
                    if st.button("📊 Load submission counts per job", key="load_sub_counts"):
                        prog_bar = st.progress(0, text="Fetching submissions…")

                        def _cb(done: int, total: int):
                            pct = done / total if total else 1
                            prog_bar.progress(pct, text=f"Fetching submissions… {done}/{total}")

                        with st.spinner("Querying Roamler API for each job…"):
                            subs_rows, _ = roamler.debug_jobs_with_submissions(
                                date_from_str, date_to_str, progress_cb=_cb
                            )

                        prog_bar.empty()

                        if subs_rows:
                            sdf = _pd.DataFrame(subs_rows)
                            # Human-readable submission label
                            def _sub_label(row):
                                s = row.get("submissions", -2)
                                if s == -1:  return "skipped (??)"
                                if s == -2:  return f"error: {row.get('sub_error','?')}"
                                return str(s)
                            sdf["subs"] = sdf.apply(_sub_label, axis=1)
                            cols = ["id", "market", "category", "subs", "workingTitle", "title"]
                            st.dataframe(
                                sdf[[c for c in cols if c in sdf.columns]],
                                use_container_width=True,
                                hide_index=True,
                            )
                            total_subs = sdf["submissions"].clip(lower=0).sum()
                            st.success(
                                f"Total submissions in {date_from_str} → {date_to_str}: "
                                f"**{total_subs}** across {len(subs_rows)} jobs"
                            )
                else:
                    st.info("No jobs returned.")
        else:
            st.warning("Roamler API not configured — no data to show.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Questionnaires
# ══════════════════════════════════════════════════════════════════════════════
with tab_questionnaires:
    from progress.questionnaire_manager import render_questionnaire_tab
    render_questionnaire_tab()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Data Hub
# ══════════════════════════════════════════════════════════════════════════════
with tab_datahub:
    from progress.data_hub import render_data_hub_tab
    render_data_hub_tab()


# ─── Footer ───────────────────────────────────────────────────────────────────
st.markdown(
    "<div style='text-align:center;color:#aaa;font-size:0.75rem;margin-top:2rem;'>"
    "Versuni Mystery Shopping Wave III &nbsp;·&nbsp; "
    "Roamler + Wiser + Pinion &nbsp;·&nbsp; "
    "Internal use only</div>",
    unsafe_allow_html=True,
)
