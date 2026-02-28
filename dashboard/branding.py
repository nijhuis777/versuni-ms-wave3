"""
Versuni × Roamler — Shared Branding
=====================================
Roamler-style CSS theme, logo loading, and header rendering
shared by tracker.py and dashboard/app.py.

Logo files expected at (in priority order):
  1. <project_root>/assets/Logo Versuni.jfif   (add to git for Streamlit Cloud)
  2. <project_root>/../Operations/Logo Versuni.jfif  (local dev fallback)
"""

from __future__ import annotations
from pathlib import Path
import base64

import streamlit as st

# ─── Brand colors ─────────────────────────────────────────────────────────────
ROAMLER_ORANGE  = "#FF6738"
ROAMLER_DARK    = "#1A1A1A"
ROAMLER_GREY    = "#F5F5F5"
VERSUNI_BLUE    = "#003087"

# Status → color mapping (used by both tracker and dashboard)
STATUS_COLORS = {
    "complete":  "#2ECC71",
    "on_track":  "#3498DB",
    "at_risk":   ROAMLER_ORANGE,
    "critical":  "#E74C3C",
    "pending":   "#BDC3C7",
}

# ─── CSS ──────────────────────────────────────────────────────────────────────
CSS = f"""
<style>
/* ── Google-style clean font ─────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}}

/* ── Page background ─────────────────────────────────────────────────────── */
.stApp {{
    background-color: #F8F8F8;
}}

/* ── Metric cards ─────────────────────────────────────────────────────────── */
[data-testid="metric-container"] {{
    background: #FFFFFF;
    border: 1px solid #EBEBEB;
    border-top: 4px solid {ROAMLER_ORANGE};
    border-radius: 8px;
    padding: 1rem 1.25rem 0.75rem;
    box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}}
[data-testid="stMetricValue"] {{
    color: {ROAMLER_DARK} !important;
    font-weight: 700 !important;
    font-size: 1.8rem !important;
}}
[data-testid="stMetricLabel"] {{
    color: #888 !important;
    font-size: 0.75rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.07em !important;
    font-weight: 500 !important;
}}
[data-testid="stMetricDelta"] {{
    color: #666 !important;
    font-size: 0.8rem !important;
}}

/* ── Buttons ──────────────────────────────────────────────────────────────── */
.stButton > button {{
    background-color: {ROAMLER_ORANGE} !important;
    color: white !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    padding: 0.4rem 1.2rem !important;
    transition: background 0.15s ease;
}}
.stButton > button:hover {{
    background-color: #E55530 !important;
    color: white !important;
}}

/* ── Dividers ─────────────────────────────────────────────────────────────── */
hr {{
    border: none !important;
    border-top: 2px solid {ROAMLER_ORANGE} !important;
    opacity: 0.15 !important;
    margin: 1rem 0 !important;
}}

/* ── Subheadings ──────────────────────────────────────────────────────────── */
h2 {{
    border-left: 4px solid {ROAMLER_ORANGE};
    padding-left: 0.7rem !important;
    color: {ROAMLER_DARK} !important;
    font-weight: 700 !important;
    font-size: 1.1rem !important;
    margin-top: 1.5rem !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}}

/* ── Plotly chart wrapper ─────────────────────────────────────────────────── */
[data-testid="stPlotlyChart"] {{
    background: white;
    border-radius: 8px;
    padding: 0.5rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    border: 1px solid #EBEBEB;
}}

/* ── Sidebar ──────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {{
    background-color: #FAFAFA;
    border-right: 2px solid #EBEBEB;
}}
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {{
    border-left: 3px solid {ROAMLER_ORANGE} !important;
    padding-left: 0.5rem !important;
    font-size: 0.9rem !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: {ROAMLER_DARK} !important;
}}

/* ── Expander ─────────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {{
    border: 1px solid #EBEBEB !important;
    border-radius: 6px !important;
    background: white;
}}

/* ── Dataframe ────────────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {{
    border-radius: 8px !important;
    overflow: hidden;
    border: 1px solid #EBEBEB !important;
}}

/* ── Selectboxes ──────────────────────────────────────────────────────────── */
[data-testid="stSelectbox"] > div > div {{
    border-color: #DDDDDD !important;
    border-radius: 6px !important;
}}
</style>
"""


# ─── Logo helpers ─────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).parent.parent

_LOGO_SEARCH = [
    _PROJECT_ROOT / "assets",
    _PROJECT_ROOT.parent / "Operations",
]


def _find_logo(stem: str) -> Path | None:
    """Find a logo file by stem name (without extension)."""
    for folder in _LOGO_SEARCH:
        if not folder.exists():
            continue
        for ext in (".jfif", ".png", ".jpg", ".jpeg", ".svg", ".webp"):
            p = folder / f"{stem}{ext}"
            if p.exists():
                return p
    return None


def _img_b64(path: Path) -> str:
    """Return base64 data-URI for an image file."""
    mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg", ".jfif") else "image/png"
    data = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{data}"


def render_header(subtitle: str = "Wave III — Fieldwork Progress") -> None:
    """Render the branded page header with Versuni + Roamler logos."""
    inject_css()

    versuni_path = _find_logo("Logo Versuni")
    roamler_path = _find_logo("Logo Roamler")

    versuni_html = (
        f'<img src="{_img_b64(versuni_path)}" style="height:44px;object-fit:contain;">'
        if versuni_path else
        f'<span style="font-size:1.4rem;font-weight:800;color:{VERSUNI_BLUE};">VERSUNI</span>'
    )
    roamler_html = (
        f'<img src="{_img_b64(roamler_path)}" style="height:36px;object-fit:contain;">'
        if roamler_path else
        f'<span style="font-size:1rem;font-weight:700;color:{ROAMLER_ORANGE};">ROAMLER</span>'
    )

    st.markdown(
        f"""
        <div style="
            background: {ROAMLER_DARK};
            border-radius: 10px;
            padding: 1rem 1.5rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 1.25rem;
            box-shadow: 0 3px 12px rgba(0,0,0,0.12);
        ">
            <div style="display:flex;align-items:center;gap:1rem;">
                <div style="background:white;padding:6px 10px;border-radius:6px;">
                    {versuni_html}
                </div>
                <div>
                    <div style="color:white;font-size:1.1rem;font-weight:700;
                                letter-spacing:0.03em;line-height:1.2;">
                        Mystery Shopping
                    </div>
                    <div style="color:#aaa;font-size:0.8rem;font-weight:400;
                                letter-spacing:0.04em;">
                        {subtitle}
                    </div>
                </div>
            </div>
            <div style="display:flex;align-items:center;gap:0.6rem;">
                <span style="color:#888;font-size:0.75rem;font-weight:500;">
                    powered by
                </span>
                <div style="background:white;padding:5px 10px;border-radius:6px;">
                    {roamler_html}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def inject_css() -> None:
    """Inject the Roamler CSS theme."""
    st.markdown(CSS, unsafe_allow_html=True)
