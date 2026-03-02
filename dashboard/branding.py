"""
Versuni × Roamler — Shared Branding
=====================================
Sticky branded header, multi-theme CSS, and logo loading.
Shared by progress/tracker.py and dashboard/app.py.

Themes: light · dark · roamler · versuni
"""

from __future__ import annotations
from pathlib import Path
import base64

import streamlit as st

# ─── Brand colors ─────────────────────────────────────────────────────────────
ROAMLER_ORANGE = "#FF6738"
ROAMLER_DARK   = "#1A1A1A"
VERSUNI_BLUE   = "#003087"

# Status → color (shared across both apps)
STATUS_COLORS = {
    "complete":  "#2ECC71",
    "on_track":  "#3498DB",
    "at_risk":   ROAMLER_ORANGE,
    "critical":  "#E74C3C",
    "pending":   "#BDC3C7",
}

# ─── Themes ───────────────────────────────────────────────────────────────────
THEMES: dict[str, dict] = {
    "light": {
        "label":        "☀️ Light",
        "page_bg":      "#F8F8F8",
        "card_bg":      "#FFFFFF",
        "card_border":  "#EBEBEB",
        "text":         "#1A1A1A",
        "text_muted":   "#888888",
        "header_bg":    "#1A1A1A",        # dark header on light page
        "header_anim":  False,
        "sidebar_bg":   "#FAFAFA",
        "sidebar_border": "#EBEBEB",
        "input_border": "#DDDDDD",
    },
    "dark": {
        "label":        "🌙 Dark",
        "page_bg":      "#111111",
        "card_bg":      "#1E1E1E",
        "card_border":  "#2E2E2E",
        "text":         "#F0F0F0",
        "text_muted":   "#888888",
        "header_bg":    "#0A0A0A",
        "header_anim":  False,
        "sidebar_bg":   "#161616",
        "sidebar_border": "#2A2A2A",
        "input_border": "#3A3A3A",
    },
    "roamler": {
        "label":        "🟠 Roamler",
        "page_bg":      "#FFF5F1",
        "card_bg":      "#FFFFFF",
        "card_border":  "#FFD5C8",
        "text":         "#1A1A1A",
        "text_muted":   "#777777",
        "header_bg":    "linear-gradient(-45deg,#FF6738,#FF3D00,#FF8A50,#FF6738)",
        "header_anim":  True,             # animated gradient
        "sidebar_bg":   "#FFF5F1",
        "sidebar_border": "#FFD5C8",
        "input_border": "#FFBAA8",
    },
    "versuni": {
        "label":        "🔵 Versuni",
        "page_bg":      "#F0F4FF",
        "card_bg":      "#FFFFFF",
        "card_border":  "#C8D8F8",
        "text":         "#1A1A1A",
        "text_muted":   "#666688",
        "header_bg":    "linear-gradient(-45deg,#003087,#0056C8,#001F5A,#003087)",
        "header_anim":  True,
        "sidebar_bg":   "#F0F4FF",
        "sidebar_border": "#C8D8F8",
        "input_border": "#A8C0F0",
    },
}

HEADER_HEIGHT_PX = 68   # our branded header height
ST_HEADER_PX     = 56   # Streamlit's built-in top bar height


# ─── CSS builder ──────────────────────────────────────────────────────────────
def _build_css(theme_key: str) -> str:
    t = THEMES.get(theme_key, THEMES["light"])
    anim_css = """
@keyframes header-gradient {
    0%   { background-position: 0%   50%; }
    50%  { background-position: 100% 50%; }
    100% { background-position: 0%   50%; }
}
""" if t["header_anim"] else ""

    header_bg_css = (
        f"background: {t['header_bg']}; background-size: 400% 400%;"
        f"animation: header-gradient 8s ease infinite;"
        if t["header_anim"] else
        f"background: {t['header_bg']};"
    )

    return f"""
<style>
{anim_css}

/* ── Google font ─────────────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}}

/* ── Page background ─────────────────────────────────────────────────────── */
.stApp, [data-testid="stAppViewContainer"] {{
    background-color: {t['page_bg']} !important;
}}

/* ── Hide Streamlit's own thin header bar to avoid double-bar look ───────── */
header[data-testid="stHeader"] {{
    background: transparent !important;
    height: {ST_HEADER_PX}px !important;
}}
/* Keep the hamburger menu button visible */
header[data-testid="stHeader"] button {{
    visibility: visible !important;
}}

/* ── Our sticky branded header ───────────────────────────────────────────── */
.versuni-header {{
    position: fixed !important;
    top: {ST_HEADER_PX}px !important;
    left: 0 !important;
    right: 0 !important;
    z-index: 999 !important;
    height: {HEADER_HEIGHT_PX}px;
    {header_bg_css}
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    padding: 0 1.75rem !important;
    box-shadow: 0 3px 16px rgba(0,0,0,0.18) !important;
    transition: left 0.3s ease !important;
}}

/* ── Shift header right when sidebar is open ─────────────────────────────── */
[data-testid="stSidebar"][aria-expanded="true"] ~ * .versuni-header {{
    left: 17rem !important;
}}

/* ── Push main content below both headers ────────────────────────────────── */
[data-testid="block-container"] {{
    padding-top: {ST_HEADER_PX + HEADER_HEIGHT_PX + 16}px !important;
}}

/* ── Metric cards ────────────────────────────────────────────────────────── */
[data-testid="metric-container"] {{
    background: {t['card_bg']} !important;
    border: 1px solid {t['card_border']} !important;
    border-top: 4px solid {ROAMLER_ORANGE} !important;
    border-radius: 8px !important;
    padding: 1rem 1.25rem 0.75rem !important;
    box-shadow: 0 2px 10px rgba(0,0,0,0.06) !important;
}}
[data-testid="stMetricValue"] {{
    color: {t['text']} !important;
    font-weight: 700 !important;
    font-size: 1.8rem !important;
}}
[data-testid="stMetricLabel"] {{
    color: {t['text_muted']} !important;
    font-size: 0.75rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.07em !important;
    font-weight: 500 !important;
}}
[data-testid="stMetricDelta"] {{
    color: {t['text_muted']} !important;
    font-size: 0.8rem !important;
}}

/* ── Buttons ─────────────────────────────────────────────────────────────── */
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

/* ── Dividers ────────────────────────────────────────────────────────────── */
hr {{
    border: none !important;
    border-top: 2px solid {ROAMLER_ORANGE} !important;
    opacity: 0.2 !important;
    margin: 1rem 0 !important;
}}

/* ── Section subheadings ─────────────────────────────────────────────────── */
h2 {{
    border-left: 4px solid {ROAMLER_ORANGE} !important;
    padding-left: 0.7rem !important;
    color: {t['text']} !important;
    font-weight: 700 !important;
    font-size: 1.05rem !important;
    margin-top: 1.5rem !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}}

/* ── Chart wrappers ──────────────────────────────────────────────────────── */
[data-testid="stPlotlyChart"] {{
    background: {t['card_bg']} !important;
    border-radius: 8px !important;
    padding: 0.5rem !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.05) !important;
    border: 1px solid {t['card_border']} !important;
}}

/* ── Expanders ───────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {{
    border: 1px solid {t['card_border']} !important;
    border-radius: 6px !important;
    background: {t['card_bg']} !important;
}}

/* ── Dataframes ──────────────────────────────────────────────────────────── */
[data-testid="stDataFrame"],
[data-testid="stDataEditor"] {{
    border-radius: 8px !important;
    border: 1px solid {t['card_border']} !important;
}}

/* ── Selectboxes / inputs ────────────────────────────────────────────────── */
[data-testid="stSelectbox"] > div > div {{
    border-color: {t['input_border']} !important;
    border-radius: 6px !important;
    background: {t['card_bg']} !important;
    color: {t['text']} !important;
}}

/* ── Caption / small text ────────────────────────────────────────────────── */
.stCaption, [data-testid="stCaptionContainer"] {{
    color: {t['text_muted']} !important;
}}

/* ── General text ────────────────────────────────────────────────────────── */
p, li, label, .stMarkdown {{
    color: {t['text']} !important;
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
    for folder in _LOGO_SEARCH:
        if not folder.exists():
            continue
        for ext in (".jfif", ".png", ".jpg", ".jpeg", ".svg", ".webp"):
            p = folder / f"{stem}{ext}"
            if p.exists():
                return p
    return None


def _img_b64(path: Path) -> str:
    mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg", ".jfif") else "image/png"
    data = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{data}"


# ─── Public API ───────────────────────────────────────────────────────────────

def inject_css(theme: str = "light") -> None:
    """Inject the full themed CSS (call once per page, before any content)."""
    st.markdown(_build_css(theme), unsafe_allow_html=True)


def theme_selector(sidebar: bool = True) -> str:
    """Deprecated — always returns 'light'."""
    return "light"


def render_header(subtitle: str = "Wave III — Fieldwork Progress",
                  theme: str = "light") -> None:
    """Render the sticky branded header. Call AFTER inject_css()."""
    versuni_path = _find_logo("Logo Versuni")
    roamler_path = _find_logo("Logo Roamler")

    versuni_html = (
        f'<img src="{_img_b64(versuni_path)}" '
        f'style="max-height:42px;width:auto;max-width:130px;display:block;">'
        if versuni_path else
        f'<span style="font-size:1.3rem;font-weight:800;color:#003087;">VERSUNI</span>'
    )
    roamler_html = (
        f'<img src="{_img_b64(roamler_path)}" '
        f'style="max-height:38px;max-width:160px;width:auto;display:block;object-fit:contain;">'
        if roamler_path else
        f'<span style="font-size:1rem;font-weight:700;color:{ROAMLER_ORANGE};">ROAMLER</span>'
    )

    html = (
        f'<div class="versuni-header">'
        f'<div style="display:flex;align-items:center;gap:1rem;">'
        f'<div style="background:white;padding:7px 11px;border-radius:6px;'
        f'display:flex;align-items:center;justify-content:center;'
        f'box-shadow:0 1px 4px rgba(0,0,0,0.15);">{versuni_html}</div>'
        f'<div>'
        f'<div style="color:white;font-size:1.05rem;font-weight:700;'
        f'letter-spacing:0.02em;line-height:1.25;'
        f'text-shadow:0 1px 3px rgba(0,0,0,0.3);">Mystery Shopping</div>'
        f'<div style="color:rgba(255,255,255,0.65);font-size:0.75rem;'
        f'font-weight:400;letter-spacing:0.04em;">{subtitle}</div>'
        f'</div></div>'
        f'<div style="display:flex;align-items:center;gap:0.7rem;">'
        f'<span style="color:rgba(255,255,255,0.5);font-size:0.7rem;'
        f'font-weight:500;letter-spacing:0.06em;text-transform:uppercase;">powered by</span>'
        f'<div style="background:white;padding:7px 13px;border-radius:6px;'
        f'display:flex;align-items:center;justify-content:center;'
        f'box-shadow:0 1px 4px rgba(0,0,0,0.15);">{roamler_html}</div>'
        f'</div></div>'
    )
    st.html(html)
