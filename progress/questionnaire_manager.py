"""
Questionnaire Manager
=====================
Side-by-side comparison of Roamler/Wiser/Pinion questionnaire JSON files
across markets, to ensure all markets follow the master template.

Questionnaire JSON files are stored in the GitHub repo at:
    questionnaires/{category}/master.json       ← canonical template
    questionnaires/{category}/{market}.json     ← per-market version

Usage (from tracker.py):
    from progress.questionnaire_manager import render_questionnaire_tab
    render_questionnaire_tab()
"""

from __future__ import annotations
import json
from datetime import datetime, timezone

import streamlit as st

from progress.github_storage import (
    is_configured, read_file, commit_file, list_files
)
import yaml
from pathlib import Path

_CONFIG_DIR = Path(__file__).parent.parent / "config"

# ─── Scope helpers ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def _load_scope() -> dict:
    p = _CONFIG_DIR / "scope.yaml"
    if p.exists():
        with open(p) as f:
            return yaml.safe_load(f)
    return {}


def _all_markets() -> list[str]:
    scope = _load_scope()
    return sorted(scope.get("markets", {}).keys())


def _all_categories() -> list[str]:
    scope = _load_scope()
    return sorted(scope.get("categories", {}).keys())


# ─── JSON parsing ──────────────────────────────────────────────────────────────

def _extract_questions(data: dict | list) -> list[dict]:
    """
    Normalise Roamler / Wiser / Pinion JSON to a flat list of question dicts.
    Each question has at minimum: id, title, type.
    """
    if isinstance(data, list):
        raw = data
    else:
        for key in ("questions", "Questions", "items", "Items", "tasks"):
            if key in data:
                raw = data[key]
                break
        else:
            raw = []

    questions = []
    for q in raw:
        if not isinstance(q, dict):
            continue
        qid = str(q.get("id") or q.get("Id") or q.get("code") or q.get("Code") or "")
        title = str(q.get("title") or q.get("Title") or q.get("text") or q.get("question") or "")
        questions.append({
            "id": qid,
            "title": title,
            "type": q.get("type") or q.get("Type") or "",
            "answers": q.get("answers") or q.get("Answers") or [],
            "_raw": q,
        })
    return questions


def _questions_index(questions: list[dict]) -> dict[str, dict]:
    return {q["id"]: q for q in questions if q["id"]}


# ─── Diff renderer ─────────────────────────────────────────────────────────────

def _render_diff(master_questions: list[dict], market_questions: list[dict],
                 market_name: str) -> None:
    master_idx = _questions_index(master_questions)
    market_idx = _questions_index(market_questions)
    all_ids = list(dict.fromkeys(
        [q["id"] for q in master_questions] + [q["id"] for q in market_questions]
    ))  # preserve order, deduplicate

    identical = missing = extra = changed = 0

    for qid in all_ids:
        m_q  = master_idx.get(qid)
        mk_q = market_idx.get(qid)

        if m_q and mk_q:
            same_title = m_q["title"].strip() == mk_q["title"].strip()
            same_ans   = str(m_q["answers"]) == str(mk_q["answers"])
            if same_title and same_ans:
                identical += 1
                with st.expander(f"✅ {qid}  —  {m_q['title'][:70]}", expanded=False):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.caption("Master")
                        st.json(m_q["_raw"], expanded=False)
                    with c2:
                        st.caption(market_name)
                        st.json(mk_q["_raw"], expanded=False)
            else:
                changed += 1
                with st.expander(f"⚠️ {qid}  —  DIFFERS", expanded=True):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.caption("**Master**")
                        if not same_title:
                            st.markdown(
                                f"<span style='background:#FFF3CD;padding:2px 4px;"
                                f"border-radius:3px'>{m_q['title']}</span>",
                                unsafe_allow_html=True,
                            )
                        else:
                            st.write(m_q["title"])
                        st.json(m_q["_raw"], expanded=False)
                    with c2:
                        st.caption(f"**{market_name}**")
                        if not same_title:
                            st.markdown(
                                f"<span style='background:#FFE0B2;padding:2px 4px;"
                                f"border-radius:3px'>{mk_q['title']}</span>",
                                unsafe_allow_html=True,
                            )
                        else:
                            st.write(mk_q["title"])
                        st.json(mk_q["_raw"], expanded=False)

        elif m_q and not mk_q:
            missing += 1
            c1, c2 = st.columns(2)
            with c1:
                st.error(f"❌ Missing in {market_name}: **{qid}** — {m_q['title'][:60]}")
            with c2:
                st.empty()
        else:
            extra += 1
            c1, c2 = st.columns(2)
            with c1:
                st.empty()
            with c2:
                st.info(f"➕ Extra in {market_name}: **{qid}** — {mk_q['title'][:60]}")  # type: ignore[index]

    # Summary bar
    total = identical + changed + missing + extra
    st.divider()
    cols = st.columns(4)
    cols[0].metric("✅ Identical", identical, f"of {total}")
    cols[1].metric("⚠️ Changed",   changed)
    cols[2].metric("❌ Missing",   missing)
    cols[3].metric("➕ Extra",     extra)


# ─── Public tab renderer ───────────────────────────────────────────────────────

def render_questionnaire_tab() -> None:
    st.subheader("📋 Questionnaire Manager")
    st.caption(
        "Upload questionnaire JSON files per market and compare them against the "
        "master template. Core questions should match; market versions may add "
        "local brands, SKUs, or translated labels."
    )

    github_ok = is_configured()
    if not github_ok:
        st.warning(
            "Add **GITHUB_TOKEN** to Streamlit secrets to enable file storage. "
            "Without it, comparisons run on uploaded files only (in-session).",
            icon="⚠️",
        )

    upload_tab, compare_tab, library_tab = st.tabs(
        ["⬆️ Upload", "🔍 Compare", "📚 Library"]
    )

    # ── Upload ─────────────────────────────────────────────────────────────────
    with upload_tab:
        st.markdown("Upload a questionnaire JSON (exported from Roamler / Wiser / Pinion admin).")

        c1, c2 = st.columns(2)
        with c1:
            up_category = st.selectbox("Category", _all_categories(), key="q_up_cat")
        with c2:
            is_master = st.checkbox("This is the **master template** for this category",
                                    key="q_up_master")
            if not is_master:
                up_market = st.selectbox("Market", _all_markets(), key="q_up_market")
            else:
                up_market = "master"

        up_file = st.file_uploader("Upload questionnaire JSON", type=["json"],
                                   key="q_uploader")
        if up_file:
            try:
                raw_bytes = up_file.read()
                parsed = json.loads(raw_bytes)
                questions = _extract_questions(parsed)
                st.success(f"Parsed: **{len(questions)} questions** detected.")
                with st.expander("Preview questions"):
                    for q in questions[:10]:
                        st.write(f"• `{q['id']}` — {q['title'][:80]}")
                    if len(questions) > 10:
                        st.caption(f"… and {len(questions)-10} more")

                label = "master" if is_master else up_market
                if st.button(f"💾 Save  {up_category} / {label}  to repo",
                             type="primary", key="q_save_btn"):
                    # Cache in session for compare tab
                    key = f"q_json_{up_category}_{label}"
                    st.session_state[key] = parsed

                    if github_ok:
                        repo_path = f"questionnaires/{up_category}/{label}.json"
                        ts  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                        ok  = commit_file(repo_path, raw_bytes,
                                          f"Questionnaire: {up_category}/{label} ({ts})")
                        if ok:
                            st.success(f"✅ Saved to `{repo_path}` in GitHub.")
                        else:
                            st.error("GitHub commit failed — check GITHUB_TOKEN permissions.")
                    else:
                        st.info("Stored in session. Add GITHUB_TOKEN to persist across sessions.")
            except json.JSONDecodeError as e:
                st.error(f"Invalid JSON: {e}")

    # ── Compare ────────────────────────────────────────────────────────────────
    with compare_tab:
        st.markdown("Pick a category and market to compare against the master template.")

        c1, c2 = st.columns(2)
        with c1:
            cmp_cat = st.selectbox("Category", _all_categories(), key="q_cmp_cat")
        with c2:
            cmp_market = st.selectbox("Market to compare", _all_markets(), key="q_cmp_market")

        def _load_json(category: str, label: str) -> dict | None:
            """Try session cache first, then GitHub."""
            key = f"q_json_{category}_{label}"
            if key in st.session_state:
                return st.session_state[key]
            if github_ok:
                raw = read_file(f"questionnaires/{category}/{label}.json")
                if raw:
                    data = json.loads(raw)
                    st.session_state[key] = data
                    return data
            return None

        if st.button("🔍 Compare", type="primary", key="q_cmp_btn"):
            master_data = _load_json(cmp_cat, "master")
            market_data = _load_json(cmp_cat, cmp_market)

            if not master_data:
                st.warning(
                    f"No master template found for **{cmp_cat}**. "
                    "Upload one in the '⬆️ Upload' tab first.", icon="⚠️"
                )
            elif not market_data:
                st.warning(
                    f"No questionnaire found for **{cmp_market} / {cmp_cat}**. "
                    "Upload it in the '⬆️ Upload' tab first.", icon="⚠️"
                )
            else:
                master_qs = _extract_questions(master_data)
                market_qs = _extract_questions(market_data)
                st.markdown(
                    f"**Master** ({len(master_qs)} questions) vs "
                    f"**{cmp_market}** ({len(market_qs)} questions)"
                )
                st.divider()
                _render_diff(master_qs, market_qs, cmp_market)

    # ── Library ────────────────────────────────────────────────────────────────
    with library_tab:
        st.markdown("Files saved to the GitHub repo under `questionnaires/`.")
        if not github_ok:
            st.info("GITHUB_TOKEN required to browse the repo library.")
        else:
            categories = _all_categories()
            for cat in categories:
                files = list_files(f"questionnaires/{cat}")
                if files:
                    with st.expander(f"📁 {cat}  ({len(files)} files)"):
                        for f in files:
                            if f.get("type") == "file":
                                name = f["name"].replace(".json", "")
                                tag  = "🏆 master" if name == "master" else f"🌍 {name}"
                                st.write(f"• {tag}  — `{f['path']}`")
