"""
View: Score Table — store-level drill-down
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
import streamlit as st

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
from dashboard.branding import inject_css, render_header, theme_selector
from dashboard.auth import require_password
from dashboard.data_loader import (
    load_master, apply_filters, sidebar_filters,
    n_visits_caption, score_color,
)

st.set_page_config(page_title="Score Table", page_icon="📋", layout="wide", initial_sidebar_state="collapsed")
require_password()


def _fmt_pct(v):
    try:
        return f"{float(v):.1f}%"
    except Exception:
        return "—"


def main():
    df, is_demo = load_master()
    inject_css()
    render_header("Table with All Scores")
    if is_demo:
        st.info("⚠ Showing **demo data**.", icon="⚠")

    flt = sidebar_filters(df)
    filtered = apply_filters(df, **flt)

    st.caption(n_visits_caption(filtered))

    if filtered.empty:
        st.warning("No data matches the selected filters.")
        return

    # ── Summary table (store-level) ────────────────────────────────────────────
    # Group by store — aggregate scores and count visits
    id_cols = [c for c in ["store_name", "retailer", "market_name", "category", "wave"] if c in filtered.columns]
    kpi_cols = [c for c in ["kpi1_score", "kpi2_score", "kpi3_score", "total_score"] if c in filtered.columns]

    grp = (
        filtered
        .groupby(id_cols, dropna=False)[kpi_cols]
        .agg(["mean", "count"])
    )
    grp.columns = [f"{col}_{stat}" for col, stat in grp.columns]
    grp = grp.reset_index()

    # Rename for display
    rename = {
        "store_name":      "Store",
        "retailer":        "Retailer",
        "market_name":     "Country",
        "category":        "Category",
        "wave":            "Wave",
        "total_score_mean":  "Total %",
        "kpi1_score_mean":   "Availability %",
        "kpi2_score_mean":   "Visibility %",
        "kpi3_score_mean":   "Recommendation %",
        "total_score_count": "# Visits",
    }
    display_cols = [c for c in rename if c in grp.columns]
    tbl = grp[display_cols].rename(columns=rename)

    # Sort by total desc
    sort_col = "Total %" if "Total %" in tbl.columns else tbl.columns[0]
    tbl = tbl.sort_values(sort_col, ascending=False)

    # Style score columns
    pct_cols = [c for c in ["Total %", "Availability %", "Visibility %", "Recommendation %"] if c in tbl.columns]
    styled = tbl.style.format({c: _fmt_pct for c in pct_cols})

    def _bg(val):
        try:
            v = float(val)
            if v >= 70: return "background-color: #C8E6C9"
            if v >= 40: return "background-color: #FFF9C4"
            return "background-color: #FFCDD2"
        except Exception:
            return ""

    styled = styled.applymap(_bg, subset=pct_cols)

    st.dataframe(styled, use_container_width=True, hide_index=True, height=600)

    # Totals row
    totals = {
        "Total %":           filtered["total_score"].mean() if "total_score" in filtered.columns else None,
        "Availability %":    filtered["kpi1_score"].mean()  if "kpi1_score"  in filtered.columns else None,
        "Visibility %":      filtered["kpi2_score"].mean()  if "kpi2_score"  in filtered.columns else None,
        "Recommendation %":  filtered["kpi3_score"].mean()  if "kpi3_score"  in filtered.columns else None,
    }
    tot_str = "  |  ".join(
        f"**{k}:** {v:.1f}%" for k, v in totals.items() if v is not None
    )
    st.markdown(f"**Totals (all filtered):** {tot_str}")


main()
