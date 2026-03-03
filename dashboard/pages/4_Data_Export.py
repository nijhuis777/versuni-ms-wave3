"""
View: Data Export — downloadable store-level score table
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
    load_master, apply_filters, sidebar_filters, n_visits_caption,
)

st.set_page_config(page_title="Data Export", page_icon="📤", layout="wide", initial_sidebar_state="collapsed")
require_password()


def main():
    df, is_demo = load_master()
    inject_css()
    render_header("Data for Export")
    if is_demo:
        st.info("⚠ Showing **demo data**.", icon="⚠")

    flt = sidebar_filters(df)
    filtered = apply_filters(df, **flt)

    st.caption(n_visits_caption(filtered))

    if filtered.empty:
        st.warning("No data matches the selected filters.")
        return

    # ── Column selector ───────────────────────────────────────────────────────
    base_cols = [
        "store_name", "retailer", "market_name", "category", "wave",
        "visit_date", "price_range",
        "kpi1_score", "kpi2_score", "kpi3_score", "total_score",
        "kpi1_category_present", "kpi1_philips_available",
        "kpi2_standout_brand", "kpi3_1st_recommended_brand", "kpi3_2nd_recommended_brand",
    ]
    available = [c for c in base_cols if c in filtered.columns]
    extra = [c for c in filtered.columns if c not in available and not c.startswith("facings_")]
    extra_facings = [c for c in filtered.columns if c.startswith("facings_")]

    show_extra  = st.checkbox("Include additional answer fields", value=False)
    show_facings = st.checkbox("Include facings columns", value=False)

    export_cols = available[:]
    if show_extra:
        export_cols += extra
    if show_facings:
        export_cols += extra_facings

    export_df = filtered[export_cols].copy()

    # Format score columns as %
    for col in [c for c in export_cols if c.endswith("_score")]:
        export_df[col] = export_df[col].apply(
            lambda v: f"{v:.1f}%" if pd.notna(v) else ""
        )

    st.dataframe(export_df, use_container_width=True, hide_index=True, height=600)

    # ── Download buttons ──────────────────────────────────────────────────────
    dl1, dl2 = st.columns(2)

    csv = filtered[export_cols].to_csv(index=False).encode("utf-8")
    dl1.download_button(
        "⬇ Download CSV",
        data=csv,
        file_name="versuni_ms_export.csv",
        mime="text/csv",
        use_container_width=True,
    )

    # Excel export
    import io
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        filtered[export_cols].to_excel(writer, index=False, sheet_name="Scores")
    dl2.download_button(
        "⬇ Download Excel",
        data=buf.getvalue(),
        file_name="versuni_ms_export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    # Summary totals
    st.divider()
    score_avgs = {
        "Brand Availability":   filtered["kpi1_score"].mean() if "kpi1_score" in filtered.columns else None,
        "Brand Visibility":     filtered["kpi2_score"].mean() if "kpi2_score" in filtered.columns else None,
        "Brand Recommendation": filtered["kpi3_score"].mean() if "kpi3_score" in filtered.columns else None,
        "Total":                filtered["total_score"].mean() if "total_score" in filtered.columns else None,
    }
    cols = st.columns(4)
    for col, (label, val) in zip(cols, score_avgs.items()):
        if val is not None:
            col.metric(label, f"{val:.1f}%")


main()
