"""
Data Hub
=========
Central file management for Wave III market data.

Handles:
  • Upload of per-market Excel / CSV exports from Roamler, Wiser, Pinion
  • In-session preview and column mapping
  • Merge into one master dataset
  • Auto-commit merged master to GitHub (→ BI dashboard picks it up)
  • File history via GitHub repo listing

Usage (from tracker.py):
    from progress.data_hub import render_data_hub_tab
    render_data_hub_tab()
"""

from __future__ import annotations
import io
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from progress.github_storage import (
    is_configured, commit_file, list_files, read_file
)

_CONFIG_DIR = Path(__file__).parent.parent / "config"
_DATA_UPLOAD_PATH = "data/uploads"
_MASTER_PATH      = "data/processed/master_wave3.xlsx"

# Master schema: what columns the BI dashboard expects
MASTER_COLUMNS = [
    "market", "category", "platform", "retailer",
    "visit_date", "kpi1_score", "kpi2_score", "kpi3_score",
    "kpi1_category_present", "kpi1_versuni_brand_present",
    "kpi1_versuni_models_count", "kpi2_most_standout",
    "kpi2_versuni_grouped", "kpi3_recommended_brand",
]


# ─── Scope helpers ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def _load_scope() -> dict:
    p = _CONFIG_DIR / "scope.yaml"
    if p.exists():
        with open(p) as f:
            return yaml.safe_load(f)
    return {}


def _all_markets() -> list[str]:
    return sorted(_load_scope().get("markets", {}).keys())


def _all_categories() -> list[str]:
    return sorted(_load_scope().get("categories", {}).keys())


# ─── Upload section ────────────────────────────────────────────────────────────

def _render_upload() -> None:
    st.markdown(
        "Upload a platform data export (Excel or CSV) per market. "
        "Each file is tagged and added to the merge queue."
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        market = st.selectbox("Market", _all_markets(), key="hub_market")
    with c2:
        category = st.selectbox("Category", _all_categories(), key="hub_cat")
    with c3:
        platform = st.selectbox("Platform", ["roamler", "wiser", "pinion"], key="hub_platform")

    up_file = st.file_uploader(
        "Upload Excel or CSV", type=["xlsx", "xls", "csv"], key="hub_uploader"
    )

    if up_file:
        try:
            raw_bytes = up_file.read()
            up_file.seek(0)
            if up_file.name.lower().endswith(".csv"):
                df = pd.read_csv(io.BytesIO(raw_bytes))
            else:
                df = pd.read_excel(io.BytesIO(raw_bytes))

            st.success(f"File loaded: **{len(df):,} rows × {len(df.columns)} columns**")
            st.dataframe(df.head(20), use_container_width=True, hide_index=True)

            if st.button("✅ Add to merge queue", type="primary", key="hub_add_btn"):
                if "hub_queue" not in st.session_state:
                    st.session_state["hub_queue"] = []

                ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                entry = {
                    "market":   market,
                    "category": category,
                    "platform": platform,
                    "filename": up_file.name,
                    "rows":     len(df),
                    "added_at": ts,
                    "df":       df,
                }
                st.session_state["hub_queue"].append(entry)

                # Persist raw file to GitHub for team access
                if is_configured():
                    ts_safe = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
                    repo_path = (
                        f"{_DATA_UPLOAD_PATH}/"
                        f"{market}_{category}_{ts_safe}_{up_file.name}"
                    )
                    if commit_file(repo_path, raw_bytes,
                                   f"Upload: {market}/{category} ({platform}) {ts}"):
                        st.success(f"✅ Raw file saved to `{repo_path}` in GitHub.")
                    else:
                        st.warning("File added to queue but GitHub commit failed.")
                else:
                    st.info("File added to queue (session only — add GITHUB_TOKEN to persist).")

        except Exception as exc:
            st.error(f"Could not read file: {exc}")

    # Queue overview
    queue = st.session_state.get("hub_queue", [])
    if queue:
        st.divider()
        st.markdown(f"**Merge queue — {len(queue)} file(s)**")
        queue_meta = [{k: v for k, v in e.items() if k != "df"} for e in queue]
        st.dataframe(pd.DataFrame(queue_meta), use_container_width=True, hide_index=True)
        if st.button("🗑️ Clear queue", key="hub_clear_btn"):
            st.session_state["hub_queue"] = []
            st.rerun()


# ─── Merge section ─────────────────────────────────────────────────────────────

def _render_merge() -> None:
    queue = st.session_state.get("hub_queue", [])
    if not queue:
        st.info("Upload files in the '⬆️ Upload' tab first — they'll appear here.")
        return

    st.markdown(f"**{len(queue)} file(s) in queue** — map columns then merge.")

    # Collect all unique columns across all queued files
    all_cols = set()
    for entry in queue:
        all_cols.update(entry["df"].columns.tolist())
    sorted_cols = sorted(all_cols)

    def _best_guess(target: str) -> int:
        for i, c in enumerate(sorted_cols):
            if c.lower() == target.lower() or c.lower().replace(" ", "_") == target.lower():
                return i + 1  # +1 because index 0 = "(skip)"
        return 0

    with st.expander("⚙️ Column mapping  (map platform columns → master schema)", expanded=True):
        st.caption(
            "For each master column, pick the matching column from your uploaded files. "
            "Leave as '(skip)' if the column doesn't exist."
        )
        col_map: dict[str, str] = {}
        opts = ["(skip)"] + sorted_cols
        for master_col in MASTER_COLUMNS:
            col_map[master_col] = st.selectbox(
                f"→ **{master_col}**",
                opts,
                index=_best_guess(master_col),
                key=f"colmap_{master_col}",
            )

    if st.button("🔀 Merge all files into master", type="primary", key="hub_merge_btn"):
        dfs: list[pd.DataFrame] = []
        for entry in queue:
            df = entry["df"].copy()

            # Apply column mapping (rename platform cols → master cols)
            rename = {v: k for k, v in col_map.items() if v and v != "(skip)" and v in df.columns}
            df = df.rename(columns=rename)

            # Inject metadata for columns that aren't in the file
            if "market"   not in df.columns: df["market"]   = entry["market"]
            if "category" not in df.columns: df["category"] = entry["category"]
            if "platform" not in df.columns: df["platform"] = entry["platform"]

            dfs.append(df)

        master = pd.concat(dfs, ignore_index=True)

        # Keep only master columns that exist + any extras
        keep = [c for c in MASTER_COLUMNS if c in master.columns]
        extras = [c for c in master.columns if c not in MASTER_COLUMNS]
        master = master[keep + extras]

        st.session_state["hub_master"] = master
        st.success(
            f"✅ Merged **{len(master):,} rows** from {len(dfs)} file(s) · "
            f"{master['market'].nunique()} markets · {master['category'].nunique()} categories"
        )

    master = st.session_state.get("hub_master")
    if master is not None:
        st.dataframe(master.head(50), use_container_width=True, hide_index=True)

        dl_col, push_col = st.columns(2)

        # Download
        with dl_col:
            csv = master.to_csv(index=False).encode()
            st.download_button(
                "⬇️ Download master CSV", data=csv,
                file_name="master_wave3.csv", mime="text/csv",
                key="hub_dl_csv",
            )

        # Push to GitHub as master_wave3.xlsx (BI dashboard reads this)
        with push_col:
            if is_configured():
                if st.button("🚀 Save to GitHub as master_wave3.xlsx", key="hub_push_btn"):
                    buf = io.BytesIO()
                    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                        master.to_excel(writer, sheet_name="Master", index=False)
                    buf.seek(0)
                    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                    ok = commit_file(
                        _MASTER_PATH, buf.read(),
                        f"Update master dataset — {len(master):,} rows ({ts})"
                    )
                    if ok:
                        st.success(
                            "✅ `data/processed/master_wave3.xlsx` updated. "
                            "The BI dashboard will pick it up on next refresh."
                        )
                    else:
                        st.error("GitHub commit failed. Check GITHUB_TOKEN permissions.")
            else:
                st.info("Add GITHUB_TOKEN to push master to GitHub.")


# ─── History section ───────────────────────────────────────────────────────────

def _render_history() -> None:
    st.markdown(
        "Files that have been uploaded and committed to the GitHub repo. "
        "Click a filename to preview."
    )

    if not is_configured():
        st.warning("GITHUB_TOKEN required to browse the file history.", icon="⚠️")
        return

    with st.spinner("Loading file list from GitHub…"):
        files = list_files(_DATA_UPLOAD_PATH)

    if not files:
        st.info(f"No files yet under `{_DATA_UPLOAD_PATH}/` in the repo.")
        return

    file_rows = [
        {
            "name":     f["name"],
            "path":     f["path"],
            "size_kb":  round(f.get("size", 0) / 1024, 1),
        }
        for f in files if f.get("type") == "file"
    ]
    df_files = pd.DataFrame(file_rows)
    st.dataframe(df_files, use_container_width=True, hide_index=True)

    # Preview selected file
    st.divider()
    selected = st.selectbox(
        "Preview a file", ["—"] + [f["name"] for f in file_rows],  # type: ignore[index]
        key="hub_history_select"
    )
    if selected and selected != "—":
        path = next(f["path"] for f in file_rows if f["name"] == selected)  # type: ignore[index]
        raw = read_file(path)
        if raw:
            try:
                if selected.lower().endswith(".csv"):
                    df_prev = pd.read_csv(io.BytesIO(raw))
                else:
                    df_prev = pd.read_excel(io.BytesIO(raw))
                st.write(f"**{selected}** — {len(df_prev):,} rows × {len(df_prev.columns)} columns")
                st.dataframe(df_prev.head(50), use_container_width=True, hide_index=True)
            except Exception as exc:
                st.error(f"Could not preview: {exc}")


# ─── Public tab renderer ───────────────────────────────────────────────────────

def render_data_hub_tab() -> None:
    st.subheader("📁 Data Hub")
    st.caption(
        "Central hub for all market data files. Upload platform exports, "
        "map columns to the master schema, and merge into one dataset "
        "that feeds the BI dashboard."
    )

    upload_tab, merge_tab, history_tab = st.tabs(
        ["⬆️ Upload", "🔀 Merge to master", "📜 File history"]
    )

    with upload_tab:
        _render_upload()

    with merge_tab:
        _render_merge()

    with history_tab:
        _render_history()
