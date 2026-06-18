import base64
import json
import os
import re
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageChops
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from openai import OpenAI
from pypdf import PdfReader

from page_finder import find_likely_donor_pages

# ============================================================
# Page setup
# ============================================================
st.set_page_config(
    page_title="Climate Cardinals Donor/Funder Extraction Tool",
    page_icon="🌱",
    layout="wide"
)

# ============================================================
# Brand assets
# ============================================================
APP_DIR = Path(__file__).parent if "__file__" in globals() else Path.cwd()
ASSETS_DIR = APP_DIR / "assets"

LOGO_PATHS = [
    ASSETS_DIR / "climate-cardinals-logo.png",
    ASSETS_DIR / "logo.png",
    APP_DIR / "climate-cardinals-logo.png",
]

ICON_PATHS = [
    ASSETS_DIR / "climate-cardinals-icon.png",
    ASSETS_DIR / "icon.png",
    APP_DIR / "climate-cardinals-icon.png",
]


def first_existing_path(paths):
    for path in paths:
        try:
            if path.exists():
                return path
        except Exception:
            continue
    return None


def trim_logo_whitespace(image_path, padding=14, white_threshold=245):
    """
    Crops extra transparent or white whitespace around the logo before displaying it.
    Handles transparent PNGs and white-background PNGs.
    Saves the cropped image to assets/_trimmed_climate_cardinals_logo.png.
    Falls back to the original image if trimming fails.
    """
    try:
        if image_path is None:
            return None
        image_path = Path(image_path)
        image = Image.open(image_path).convert("RGBA")
        alpha = image.getchannel("A")
        alpha_min, alpha_max = alpha.getextrema()
        bbox = None
        if alpha_min < 255:
            alpha_mask = alpha.point(lambda p: 255 if p > 0 else 0)
            bbox = alpha_mask.getbbox()
        else:
            rgb_image = image.convert("RGB")
            white_background = Image.new("RGB", rgb_image.size, (255, 255, 255))
            diff = ImageChops.difference(rgb_image, white_background).convert("L")
            non_white_mask = diff.point(lambda p: 255 if p > (255 - white_threshold) else 0)
            bbox = non_white_mask.getbbox()
        if not bbox:
            return str(image_path)
        left, top, right, bottom = bbox
        left = max(0, left - padding)
        top = max(0, top - padding)
        right = min(image.width, right + padding)
        bottom = min(image.height, bottom + padding)
        if right <= left or bottom <= top:
            return str(image_path)
        cropped = image.crop((left, top, right, bottom))
        try:
            ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            return str(image_path)
        output_path = ASSETS_DIR / "_trimmed_climate_cardinals_logo.png"
        cropped.save(output_path)
        return str(output_path)
    except Exception:
        return str(image_path)


BRAND_LOGO_PATH = first_existing_path(LOGO_PATHS)
BRAND_ICON_PATH = first_existing_path(ICON_PATHS)
TRIMMED_BRAND_LOGO_PATH = trim_logo_whitespace(BRAND_LOGO_PATH) if BRAND_LOGO_PATH else None

# ============================================================
# Plain-English AI options
# ============================================================
AI_MODEL_OPTIONS = {
    "Balanced — recommended for most sources": {
        "model": "gpt-5.4",
        "label": "Balanced",
        "short": "Best default for donor pages, sponsor pages, and most annual reports.",
        "cost": "Balanced quality and cost"
    },
    "High accuracy — for messy websites or long reports": {
        "model": "gpt-5.5",
        "label": "High accuracy",
        "short": "Use when results look incomplete or the source formatting is difficult.",
        "cost": "Higher cost"
    },
    "Fast/low-cost — for quick testing": {
        "model": "gpt-5.4-mini",
        "label": "Fast/low-cost",
        "short": "Use for quick tests when you only need a rough pass.",
        "cost": "Lowest cost"
    }
}

AI_READING_OPTIONS = {
    "Quick scan — shortest sources, lowest cost": {
        "chunks": 2,
        "label": "Quick scan",
        "short": "Reads a smaller portion of the source. Best for short donor pages.",
        "best_for": "Short webpages and quick tests"
    },
    "Standard scan — recommended for most sources": {
        "chunks": 6,
        "label": "Standard scan",
        "short": "Reads enough text for most donor pages, sponsor pages, and regular PDFs.",
        "best_for": "Most donor/funder pages and annual reports"
    },
    "Deep scan — long reports or messy pages": {
        "chunks": 8,
        "label": "Deep scan",
        "short": "Reads more of a long source. Useful when names are spread across a long PDF or report.",
        "best_for": "Long PDFs, annual reports, and messy source pages"
    },
    "Maximum scan — only when names are being missed": {
        "chunks": 10,
        "label": "Maximum scan",
        "short": "Reads the most text. Use only when a source is very long or earlier results missed names.",
        "best_for": "Difficult sources after Standard/Deep scan is not enough"
    }
}

RESULT_COLUMNS = [
    "Source Organization",
    "Donor/Funder Name",
    "Donor Type",
    "Relationship to Source",
    "IRS/Form Context",
    "Section",
    "Year",
    "Confidence",
    "Notes",
    "Source URL",
    "Extraction Method",
]

RELATIONSHIP_FUNDER = "Likely funder/donor to source organization"
RELATIONSHIP_GRANTEE = "Likely grantee/recipient"
RELATIONSHIP_UNCLEAR = "Unclear / needs review"
IRS_CONTEXT_NONE = "Not an IRS/Form 990 source"

# ============================================================
# Styling - cleaner Climate Cardinals-branded readable UI
# ============================================================
st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

        :root {
            --cc-red: #ef4444;
            --cc-red-dark: #b91c1c;
            --cc-green: #16a34a;
            --cc-teal: #2563eb;        /* interactive accent — Climate Cardinals brand blue */
            --cc-sky: #8ecae6;         /* light sky blue from the logo disc */
            --cc-navy: #17285a;        /* deep navy from the logo */
            --cc-ink: #102033;
            --cc-muted: #475569;
            --cc-subtle: #64748b;
            --cc-bg: #f7faf9;
            --cc-card: #ffffff;
            --cc-soft: #eef7f1;
            --cc-border: #dce7e2;
            --cc-border-strong: #b9d5c8;
            --cc-warning: #92400e;
            --cc-warning-bg: #fffbeb;
        }

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif;
        }

        .stApp {
            background:
                radial-gradient(42% 38% at 17% 0%, rgba(239, 68, 68, 0.20), transparent 70%),
                radial-gradient(42% 38% at 83% 0%, rgba(37, 99, 235, 0.18), transparent 72%),
                radial-gradient(48% 44% at 88% 100%, rgba(142, 202, 230, 0.20), transparent 75%),
                radial-gradient(46% 42% at 12% 100%, rgba(23, 40, 90, 0.13), transparent 75%),
                linear-gradient(180deg, #f6fbfa 0%, #edf3f6 100%);
            background-attachment: fixed;
            color: var(--cc-ink);
        }

        /* Tighter, more focused content column */
        .block-container {
            padding-top: 1.4rem;
            padding-bottom: 3.2rem;
            max-width: 1120px;
        }

        header[data-testid="stHeader"] {
            background: rgba(248, 251, 250, 0.86);
            border-bottom: 1px solid rgba(220, 231, 226, 0.85);
        }

        h1, h2, h3, h4, h5, h6 {
            color: var(--cc-ink) !important;
            letter-spacing: -0.03em;
        }

        p, li, label, .stMarkdown, .stText {
            color: var(--cc-ink);
        }

        /* ---------- Header card ---------- */
        .brand-shell {
            background:
                linear-gradient(125deg, rgba(255, 255, 255, 0.55) 0%, rgba(255, 255, 255, 0.10) 24%, rgba(255, 255, 255, 0) 50%),
                linear-gradient(180deg, rgba(255, 255, 255, 0.52), rgba(255, 255, 255, 0.42));
            -webkit-backdrop-filter: blur(22px) saturate(165%);
            backdrop-filter: blur(22px) saturate(165%);
            border: 1px solid rgba(255, 255, 255, 0.7);
            border-radius: 24px;
            padding: 1.7rem 1.9rem 1.8rem 1.9rem;
            box-shadow:
                0 24px 56px rgba(15, 32, 51, 0.14),
                inset 0 1px 0 rgba(255, 255, 255, 0.85),
                inset 0 -1px 0 rgba(15, 32, 51, 0.05);
            margin-bottom: 1.6rem;
            position: relative;
            overflow: hidden;
        }
        .brand-shell::before {
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 6px;
            background: linear-gradient(90deg, var(--cc-red) 0%, var(--cc-red-dark) 28%, var(--cc-sky) 64%, var(--cc-navy) 100%);
        }
        .brand-grid {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1.9rem;
        }
        .brand-main {
            flex: 1 1 auto;
            min-width: 0;
        }
        .brand-eyebrow {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.36rem 0.72rem;
            border-radius: 999px;
            background: #fef2f2;
            color: var(--cc-red-dark);
            border: 1px solid #fecaca;
            font-weight: 800;
            font-size: 0.78rem;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            white-space: nowrap;
        }
        .brand-logo-inline {
            flex: 0 0 auto;
            display: flex;
            align-items: center;
            justify-content: center;
            padding-left: 0.5rem;
        }
        .brand-logo-inline img {
            max-height: 66px;
            width: auto !important;
            object-fit: contain;
            display: block;
        }
        .brand-fallback {
            font-size: 1.12rem;
            font-weight: 900;
            color: var(--cc-red-dark);
            text-align: center;
            line-height: 1.1;
        }
        .hero-title {
            font-size: clamp(1.9rem, 3vw, 2.75rem);
            font-weight: 900;
            line-height: 1.04;
            letter-spacing: -0.045em;
            margin: 0.85rem 0 0.7rem 0;
            color: var(--cc-ink);
        }
        .hero-subtitle {
            font-size: 1.02rem;
            color: var(--cc-muted);
            max-width: 640px;
            line-height: 1.6;
            font-weight: 500;
            margin: 0;
        }
        .pill-row {
            display: flex;
            gap: 0.55rem;
            flex-wrap: wrap;
            margin-top: 1.1rem;
        }
        .pill {
            border: 1px solid rgba(255, 255, 255, 0.7);
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.6), rgba(255, 255, 255, 0.32));
            -webkit-backdrop-filter: blur(8px) saturate(150%);
            backdrop-filter: blur(8px) saturate(150%);
            color: #17285a;
            border-radius: 999px;
            padding: 0.44rem 0.8rem;
            font-size: 0.82rem;
            font-weight: 800;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85), 0 2px 8px rgba(15, 32, 51, 0.08);
        }
        @media (max-width: 820px) {
            .brand-shell {
                padding: 1.4rem 1.3rem 1.5rem 1.3rem;
            }
            .brand-grid {
                flex-direction: column-reverse;
                align-items: flex-start;
                gap: 1.15rem;
            }
            .brand-logo-inline {
                justify-content: flex-start;
                padding-left: 0;
            }
            .brand-logo-inline img {
                max-height: 50px;
            }
            .hero-subtitle {
                max-width: 100%;
            }
            .hero-title {
                margin-top: 0.6rem;
            }
            .brand-eyebrow {
                white-space: normal;
            }
        }

        /* ---------- Cards ---------- */
        .step-card, .info-card, .ai-panel, .recommendation-card, .option-card, .review-note {
            background: rgba(255, 255, 255, 0.8);
            -webkit-backdrop-filter: blur(12px) saturate(135%);
            backdrop-filter: blur(12px) saturate(135%);
            border: 1px solid rgba(255, 255, 255, 0.6);
            border-radius: 18px;
            padding: 1.05rem 1.15rem;
            box-shadow: 0 10px 26px rgba(15, 32, 51, 0.06), inset 0 1px 0 rgba(255, 255, 255, 0.5);
        }
        .step-card {
            min-height: 122px;
        }
        .step-number {
            display: inline-flex;
            width: 30px;
            height: 30px;
            border-radius: 999px;
            align-items: center;
            justify-content: center;
            font-weight: 900;
            background: #fef2f2;
            border: 1px solid #fecaca;
            color: var(--cc-red-dark);
            margin-bottom: 0.45rem;
        }
        .step-title, .card-title {
            font-weight: 900;
            color: var(--cc-ink);
            margin-bottom: 0.3rem;
            font-size: 1.02rem;
        }
        .step-copy, .card-copy {
            color: var(--cc-muted);
            font-size: 0.95rem;
            line-height: 1.55;
            font-weight: 500;
        }
        .small-muted {
            color: var(--cc-muted);
            font-size: 0.93rem;
            line-height: 1.5;
            margin-top: 0.5rem;
            margin-bottom: 0;
            font-weight: 500;
        }

        /* ---------- Input containment card (st.container(border=True)) ---------- */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(255, 255, 255, 0.78);
            -webkit-backdrop-filter: blur(14px) saturate(135%);
            backdrop-filter: blur(14px) saturate(135%);
            border: 1px solid rgba(255, 255, 255, 0.6) !important;
            border-radius: 20px !important;
            padding: 1.45rem 1.6rem 1.55rem 1.6rem;
            box-shadow: 0 12px 34px rgba(15, 32, 51, 0.07), inset 0 1px 0 rgba(255, 255, 255, 0.55);
            margin-bottom: 1.5rem;
        }
        .section-eyebrow {
            text-transform: uppercase;
            letter-spacing: 0.09em;
            font-size: 0.74rem;
            font-weight: 900;
            color: var(--cc-teal);
            margin-bottom: 0.2rem;
        }
        .section-title {
            font-size: 1.2rem;
            font-weight: 900;
            color: var(--cc-ink);
            letter-spacing: -0.02em;
            margin: 0 0 0.3rem 0;
        }
        .section-sub {
            color: var(--cc-muted);
            font-size: 0.95rem;
            line-height: 1.5;
            margin: 0 0 1.15rem 0;
            font-weight: 500;
        }

        /* ---------- AI status / option panels ---------- */
        .ai-ready-badge, .ai-off-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            border-radius: 999px;
            padding: 0.38rem 0.72rem;
            font-size: 0.82rem;
            font-weight: 900;
            margin-bottom: 0.6rem;
        }
        .ai-ready-badge {
            border: 1px solid #bbf7d0;
            background: #f0fdf4;
            color: #166534;
        }
        .ai-off-badge {
            border: 1px solid #fde68a;
            background: #fffbeb;
            color: var(--cc-warning);
        }
        .ai-panel {
            border-color: var(--cc-border-strong);
            margin-top: 0;
            margin-bottom: 1.4rem;
        }
        .recommendation-card {
            border-color: #fecaca;
            background: #fff7f7;
            margin-top: 0.75rem;
        }
        .review-note {
            background: #f8fafc;
            border-color: #cbd5e1;
            margin: 0.8rem 0;
        }
        .mini-label {
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.73rem;
            font-weight: 900;
            color: var(--cc-subtle);
            margin-bottom: 0.25rem;
        }
        .mini-value {
            font-size: 1.02rem;
            font-weight: 900;
            color: var(--cc-ink);
            margin-bottom: 0.25rem;
        }

        /* ---------- Form labels and inputs ---------- */
        div[data-testid="stTextInput"] label,
        div[data-testid="stRadio"] label,
        div[data-testid="stFileUploader"] label,
        div[data-testid="stSelectbox"] label,
        div[data-testid="stCheckbox"] label {
            color: var(--cc-ink) !important;
            font-weight: 800 !important;
            font-size: 0.96rem !important;
        }
        div[data-baseweb="input"] {
            border-radius: 13px !important;
            background: #ffffff !important;
            border: 1px solid #cbd5e1 !important;
            box-shadow: 0 3px 10px rgba(15, 32, 51, 0.04);
        }
        div[data-baseweb="input"] > div {
            background: #ffffff !important;
            border-radius: 13px !important;
        }
        div[data-baseweb="input"]:focus-within {
            border-color: var(--cc-teal) !important;
            box-shadow: 0 0 0 3px rgba(37, 99, 235,0.13);
        }
        div[data-testid="stTextInput"] input {
            background: #ffffff !important;
            color: var(--cc-ink) !important;
            caret-color: var(--cc-ink) !important;
            font-weight: 600 !important;
            border-radius: 13px !important;
        }
        div[data-testid="stTextInput"] input::placeholder {
            color: #64748b !important;
            opacity: 1 !important;
            font-weight: 500 !important;
        }
        input {
            color: var(--cc-ink) !important;
            font-weight: 600 !important;
        }
        input[type="radio"], input[type="checkbox"] {
            accent-color: var(--cc-red);
        }
        div[data-testid="stRadio"] [role="radiogroup"] {
            gap: 0.1rem;
        }
        div[data-testid="stRadio"] [role="radiogroup"] > label {
            padding: 0.2rem 0;
        }
        div[data-baseweb="select"] > div {
            border-radius: 13px !important;
            background: #ffffff !important;
            border: 1px solid #cbd5e1 !important;
            color: var(--cc-ink) !important;
        }

        /* ---------- Buttons ---------- */
        .stButton > button {
            border-radius: 13px;
            border: 1px solid #cbd5e1;
            font-weight: 800;
            transition: all 0.14s ease-in-out;
            padding: 0.62rem 1.05rem;
            background: #ffffff;
            color: var(--cc-ink);
            box-shadow: 0 6px 16px rgba(15, 32, 51, 0.06);
            white-space: nowrap;
        }
        .stButton > button:hover {
            transform: translateY(-1px);
            border-color: var(--cc-teal);
            box-shadow: 0 10px 24px rgba(37, 99, 235,0.12);
        }
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, var(--cc-red), var(--cc-red-dark)) !important;
            color: white !important;
            border: 1px solid var(--cc-red-dark) !important;
            box-shadow: 0 10px 24px rgba(185, 28, 28, 0.2);
        }
        .stButton > button[kind="primary"]:hover {
            border-color: var(--cc-red-dark) !important;
            box-shadow: 0 12px 28px rgba(185, 28, 28, 0.28);
        }
        .stDownloadButton > button {
            border-radius: 13px;
            font-weight: 800;
        }

        /* ---------- Metrics / alerts / tables ---------- */
        div[data-testid="stMetric"] {
            background: var(--cc-card);
            border: 1px solid var(--cc-border);
            padding: 1rem;
            border-radius: 16px;
            box-shadow: 0 8px 22px rgba(15, 32, 51, 0.05);
        }
        div[data-testid="stMetricLabel"] {
            color: var(--cc-muted);
            font-weight: 800;
        }
        div[data-testid="stMetricValue"] {
            color: var(--cc-ink);
            font-weight: 900;
        }
        div[data-testid="stAlert"] {
            border-radius: 14px;
            border: 1px solid var(--cc-border);
        }
        div[data-testid="stDataFrame"] {
            border-radius: 14px;
            overflow: hidden;
            border: 1px solid var(--cc-border);
            box-shadow: 0 12px 32px rgba(15, 32, 51, 0.07);
        }

        /* ---------- Expanders ---------- */
        div[data-testid="stExpander"] {
            border: 1px solid var(--cc-border) !important;
            border-radius: 16px !important;
            background: var(--cc-card);
            box-shadow: 0 6px 18px rgba(15, 32, 51, 0.05);
            margin-bottom: 1.1rem;
            overflow: hidden;
        }
        div[data-testid="stExpander"] summary {
            font-weight: 800;
            color: var(--cc-ink);
            padding: 0.55rem 0.2rem;
        }
        div[data-testid="stExpander"] summary:hover {
            color: var(--cc-teal);
        }

        /* ---------- Links / rules / captions ---------- */
        a {
            color: #2563eb !important;
            text-decoration-thickness: 1px !important;
            text-underline-offset: 4px !important;
            font-weight: 700;
        }
        hr {
            border-color: var(--cc-border);
            margin-top: 1.6rem;
            margin-bottom: 1.4rem;
        }
        .stCaption, [data-testid="stCaptionContainer"] {
            color: var(--cc-muted) !important;
            font-size: 0.92rem !important;
            line-height: 1.5 !important;
        }
        .footer-note {
            color: var(--cc-muted);
            font-size: 0.9rem;
            line-height: 1.6;
            font-weight: 500;
            background: var(--cc-soft);
            border: 1px solid var(--cc-border);
            border-radius: 14px;
            padding: 0.95rem 1.15rem;
            margin-top: 0.4rem;
        }
        section[data-testid="stSidebar"] {
            background: #ffffff;
            border-right: 1px solid var(--cc-border);
        }

        /* ====================================================== */
        /* Readability hardening: keep widgets legible regardless */
        /* of the visitor's browser light/dark setting.           */
        /* ====================================================== */
        .stButton > button,
        .stDownloadButton > button {
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.62), rgba(255, 255, 255, 0.4)) !important;
            color: var(--cc-ink) !important;
            -webkit-backdrop-filter: blur(10px) saturate(150%);
            backdrop-filter: blur(10px) saturate(150%);
            border: 1px solid rgba(255, 255, 255, 0.7) !important;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85), 0 6px 16px rgba(15, 32, 51, 0.10) !important;
        }
        .stButton > button:hover,
        .stDownloadButton > button:hover {
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.8), rgba(255, 255, 255, 0.56)) !important;
            color: var(--cc-ink) !important;
            border-color: rgba(255, 255, 255, 0.9) !important;
        }
        .stButton > button[kind="primary"],
        .stButton > button[kind="primary"]:hover {
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.94), rgba(185, 28, 28, 0.94)) !important;
            color: #ffffff !important;
            border: 1px solid rgba(255, 255, 255, 0.4) !important;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.5), 0 12px 26px rgba(185, 28, 28, 0.3) !important;
        }
        .stButton > button:disabled,
        .stButton > button[disabled] {
            background: #eef2f6 !important;
            color: #94a3b8 !important;
        }

        /* Selectbox: closed control + open dropdown popover */
        div[data-baseweb="select"] > div {
            background: #ffffff !important;
            color: var(--cc-ink) !important;
        }
        div[data-baseweb="select"] span,
        div[data-baseweb="select"] div {
            color: var(--cc-ink) !important;
        }
        div[data-baseweb="popover"] [role="listbox"],
        ul[role="listbox"] {
            background: #ffffff !important;
            border: 1px solid var(--cc-border) !important;
            border-radius: 12px !important;
            box-shadow: 0 16px 40px rgba(15, 32, 51, 0.16) !important;
        }
        li[role="option"] {
            background: #ffffff !important;
            color: var(--cc-ink) !important;
        }
        li[role="option"]:hover,
        li[role="option"][aria-selected="true"] {
            background: var(--cc-soft) !important;
            color: var(--cc-ink) !important;
        }

        /* Expander header stays light, never black-on-black */
        div[data-testid="stExpander"] summary {
            background: transparent !important;
            color: var(--cc-ink) !important;
        }

        /* Dataframe surface stays light */
        div[data-testid="stDataFrame"] {
            background: #ffffff !important;
        }

        /* Glass fallbacks: solid surfaces when blur is unsupported */
        /* or the visitor has reduced-transparency turned on.       */
        @supports not ((-webkit-backdrop-filter: blur(1px)) or (backdrop-filter: blur(1px))) {
            .brand-shell,
            .step-card, .info-card, .ai-panel, .option-card,
            div[data-testid="stVerticalBlockBorderWrapper"] {
                background: #ffffff !important;
            }
        }
        @media (prefers-reduced-transparency: reduce) {
            .brand-shell,
            .step-card, .info-card, .ai-panel, .option-card,
            div[data-testid="stVerticalBlockBorderWrapper"] {
                -webkit-backdrop-filter: none !important;
                backdrop-filter: none !important;
                background: #ffffff !important;
            }
        }
    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# Header
# ============================================================
def image_to_base64_data_uri(image_path):
    try:
        if not image_path:
            return ""
        with open(image_path, "rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode("utf-8")
        return f"data:image/png;base64,{encoded}"
    except Exception:
        return ""


logo_data_uri = image_to_base64_data_uri(TRIMMED_BRAND_LOGO_PATH)

if logo_data_uri:
    logo_html = (
        '<div class="brand-logo-inline">'
        f'<img src="{logo_data_uri}" alt="Climate Cardinals logo">'
        '</div>'
    )
else:
    logo_html = (
        '<div class="brand-logo-inline">'
        '<div class="brand-fallback">Climate<br>Cardinals</div>'
        '</div>'
    )

# Header is built as one compact HTML string and rendered with unsafe_allow_html=True
# so Streamlit never renders it as visible text or a Markdown code block.
header_html = (
    '<div class="brand-shell">'
    '<div class="brand-grid">'
    '<div class="brand-main">'
    '<div class="brand-eyebrow">Climate Cardinals research tool</div>'
    '<div class="hero-title">Climate Cardinals Donor/Funder Extraction Tool</div>'
    '<div class="hero-subtitle">'
    'Built for Climate Cardinals donor and funder research. Find public donor, funder, '
    'sponsor, supporter, annual report, PDF, and Form 990 sources, then export a clean '
    'reviewable CSV for research and outreach workflows.'
    '</div>'
    '<div class="pill-row">'
    '<span class="pill">AI-assisted discovery</span>'
    '<span class="pill">AI extraction</span>'
    '<span class="pill">PDF + Form 990 review</span>'
    '<span class="pill">Accessible CSV export</span>'
    '</div>'
    '</div>'
    f'{logo_html}'
    '</div>'
    '</div>'
)
st.markdown(header_html, unsafe_allow_html=True)

# ============================================================
# Session state
# ============================================================
if "candidate_pages" not in st.session_state:
    st.session_state.candidate_pages = []
if "last_homepage_url" not in st.session_state:
    st.session_state.last_homepage_url = ""
if "last_source_org" not in st.session_state:
    st.session_state.last_source_org = ""
if "skipped_pages" not in st.session_state:
    st.session_state.skipped_pages = []


# ============================================================
# OpenAI helpers
# ============================================================
def get_secret_value(name, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return os.getenv(name, default)


def get_openai_api_key():
    return get_secret_value("OPENAI_API_KEY", "")


def has_openai_key():
    return bool(get_openai_api_key())


def get_openai_client():
    api_key = get_openai_api_key()
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def safe_json_loads(raw_text):
    if not raw_text:
        return None
    try:
        return json.loads(raw_text)
    except Exception:
        pass
    match = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return None
    return None


def donor_extraction_schema():
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "source_assessment": {
                "type": "string",
                "description": "Brief assessment of whether the page/report appears to contain donor/funder/supporter/sponsor names, including IRS/Form 990 direction-of-funding concerns when relevant."
            },
            "donors": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "donor_type": {"type": "string"},
                        "relationship_to_source": {
                            "type": "string",
                            "enum": [RELATIONSHIP_FUNDER, RELATIONSHIP_GRANTEE, RELATIONSHIP_UNCLEAR]
                        },
                        "irs_form_context": {"type": "string"},
                        "section": {"type": "string"},
                        "year": {"type": "string"},
                        "confidence": {"type": "string", "enum": ["High", "Medium", "Low"]},
                        "notes": {"type": "string"}
                    },
                    "required": [
                        "name", "donor_type", "relationship_to_source", "irs_form_context",
                        "section", "year", "confidence", "notes"
                    ]
                }
            }
        },
        "required": ["source_assessment", "donors"]
    }


def page_discovery_schema():
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "pages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "url": {"type": "string"},
                        "title": {"type": "string"},
                        "page_type": {"type": "string"},
                        "year": {"type": "string"},
                        "reason": {"type": "string"},
                        "confidence": {"type": "string", "enum": ["High", "Medium", "Low"]}
                    },
                    "required": ["url", "title", "page_type", "year", "reason", "confidence"]
                }
            }
        },
        "required": ["summary", "pages"]
    }


def build_structured_text_format(name, schema):
    return {
        "format": {
            "type": "json_schema",
            "name": name,
            "schema": schema,
            "strict": True
        }
    }


def chunk_text(text, max_chars=42000, overlap=1200, max_chunks=6):
    text = text or ""
    if len(text) <= max_chars:
        return [text]
    chunks = []
    start = 0
    while start < len(text) and len(chunks) < max_chunks:
        end = min(start + max_chars, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def normalize_money_dash(line):
    return line.replace("–", "-").replace("—", "-")


def normalize_name_for_dedupe(name):
    name = str(name).strip().lower()
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"[^\w\s&.'-]", "", name)
    return name


def extract_year_from_url(url):
    years = re.findall(r"20\d{2}", (url or "").lower())
    if not years:
        return None
    return max(int(year) for year in years)


def clean_lines(text):
    return [line.strip() for line in text.split("\n") if line.strip()]


# ============================================================
# IRS/Form 990 helpers
# ============================================================
def detect_irs_form_context(source_url="", text=""):
    lower_url = str(source_url or "").lower()
    lower_text = str(text or "").lower()
    combined = f"{lower_url} {lower_text[:20000]}"
    irs_url_signals = [
        "irs", "form-990", "form990", "990-pf", "990pf", "990_pf",
        "propublica", "nonprofitexplorer", "taxexemptworld", "causeiq",
        "guidestar", "candid", "990finder"
    ]
    irs_text_signals = [
        "form 990", "form990", "990-pf", "990 pf", "return of private foundation",
        "department of the treasury", "internal revenue service", "schedule i",
        "schedule of contributors", "grants and other assistance",
        "grants paid", "contributions, gifts, grants paid", "recipient organization",
        "recipient's name", "grantee", "recipient"
    ]
    is_irs_like = any(signal in lower_url for signal in irs_url_signals) or any(signal in lower_text for signal in irs_text_signals)
    if not is_irs_like:
        return {
            "is_irs": False,
            "label": IRS_CONTEXT_NONE,
            "default_relationship": RELATIONSHIP_FUNDER,
            "warning": ""
        }
    grants_paid_signals = [
        "grants and other assistance", "grants paid", "contributions, gifts, grants paid",
        "schedule i", "part ii grants", "part xv", "recipient organization",
        "recipient's name", "name and address of recipient", "paid during the year"
    ]
    foundation_signals = [
        "990-pf", "990 pf", "return of private foundation", "private foundation",
        "form 990-pf", "part xv"
    ]
    if any(signal in combined for signal in foundation_signals) and any(signal in combined for signal in grants_paid_signals):
        return {
            "is_irs": True,
            "label": "Form 990-PF / foundation grants paid context",
            "default_relationship": RELATIONSHIP_GRANTEE,
            "warning": "This appears to be a foundation filing where listed organizations may be grant recipients, not donors to the source organization."
        }
    if any(signal in combined for signal in grants_paid_signals):
        return {
            "is_irs": True,
            "label": "Form 990 / grants paid or Schedule I context",
            "default_relationship": RELATIONSHIP_GRANTEE,
            "warning": "This appears to be a grants-paid section. Listed organizations may be grantees/recipients, not funders."
        }
    if "schedule b" in combined or "schedule of contributors" in combined:
        return {
            "is_irs": True,
            "label": "Form 990 contributor schedule context",
            "default_relationship": RELATIONSHIP_FUNDER,
            "warning": "This appears to involve contributors, but entries still need review because public filings can be incomplete or context-specific."
        }
    return {
        "is_irs": True,
        "label": "Possible IRS/Form 990 source — funding direction unclear",
        "default_relationship": RELATIONSHIP_UNCLEAR,
        "warning": "This appears to be an IRS/Form 990 source. Review whether each entry is a funder, grantee, or unclear."
    }


def normalize_relationship(value, fallback=RELATIONSHIP_FUNDER):
    value = str(value or "").strip()
    allowed = {RELATIONSHIP_FUNDER, RELATIONSHIP_GRANTEE, RELATIONSHIP_UNCLEAR}
    if value in allowed:
        return value
    lower = value.lower()
    if "grantee" in lower or "recipient" in lower:
        return RELATIONSHIP_GRANTEE
    if "unclear" in lower or "review" in lower:
        return RELATIONSHIP_UNCLEAR
    if "funder" in lower or "donor" in lower or "sponsor" in lower:
        return RELATIONSHIP_FUNDER
    return fallback


def is_irs_candidate_source(candidate):
    text = candidate_text_blob(candidate)
    path = url_path_lower(candidate.get("url", ""))
    return any(signal in text or signal in path for signal in [
        "form 990", "form-990", "form990", "990-pf", "990pf",
        "irs", "schedule i", "propublica", "nonprofit explorer",
        "grants paid", "foundation filing"
    ])


# ============================================================
# AI extraction
# ============================================================
def ai_extract_possible_donors(text, source_org, source_url, model_name, max_chunks=6):
    client = get_openai_client()
    if client is None:
        raise RuntimeError("OpenAI API key is missing. Add OPENAI_API_KEY in Streamlit Secrets.")
    chunks = chunk_text(text, max_chars=42000, overlap=1200, max_chunks=max_chunks)
    all_rows = []
    assessments = []
    irs_context = detect_irs_form_context(source_url, text)
    for idx, chunk in enumerate(chunks, start=1):
        prompt = f"""
You are helping Climate Cardinals review public nonprofit donor/funder sources.

Task:
Extract donor, funder, sponsor, supporter, contributor, foundation, corporate partner, agency donor, annual fund donor, named sponsor, named grantor, or IRS/Form 990 grant-related entries from the source text.

Important precision rules:
- Only include names that clearly appear to be donors/funders/sponsors/supporters/contributors/grantors OR names that appear in IRS/Form 990 grant-related tables and need relationship review.
- Include corporate/foundation partners only if the source describes them as donating, funding, granting, sponsoring, contributing, underwriting, or providing financial/product support.
- Do NOT include staff names, board members, advisory councils, youth councils, program participants, ordinary program partners, media features, press outlets, article names, program names, event names, social links, addresses, emails, navigation items, menu items, generic headings, or award/recognition lists.
- Do NOT include media outlets such as Forbes, The Guardian, Vice, Washington Post, Read It, etc. unless the text explicitly says they donated/funded/sponsored.
- Do NOT include program partners such as UNICEF, Yale, Google, etc. unless the text explicitly says they donated/funded/sponsored.
- If a line is just a tier heading, use it as the Section, but do not include it as a donor name.
- If the source does not clearly contain a donor/funder/sponsor list or IRS/Form 990 grant-related list, return an empty donors list.
- Prefer precision over quantity. It is better to return fewer clean names than many noisy names.
- Keep names exactly as written when possible.

IRS/Form 990 relationship rules:
- Detect whether the source appears to be an IRS/Form 990/Form 990-PF/Foundation filing/Schedule I/grants paid source.
- IRS/Form 990 sources can show money flowing OUT of an organization to grantees/recipients, not money coming IN as donors.
- Do NOT label grantees/recipients as donors/funders.
- If the source is a foundation filing or 990-PF and names are listed under grants paid, contributions paid, grants and other assistance, recipient organization, or grantee sections, classify those names as "{RELATIONSHIP_GRANTEE}".
- If the source is for the researched source organization and the text clearly shows a foundation/company/government agency giving money TO that source organization, classify as "{RELATIONSHIP_FUNDER}".
- If the direction of funding is unclear, classify as "{RELATIONSHIP_UNCLEAR}".
- Always fill IRS/Form Context. If not IRS-related, use "{IRS_CONTEXT_NONE}".

Detected source context before AI review:
- IRS/Form context label: {irs_context['label']}
- Suggested default relationship if unclear: {irs_context['default_relationship']}
- Warning: {irs_context.get('warning', '')}

Use confidence:
High = clearly a donor/funder/sponsor/supporter/contributor name or clearly a grantee/recipient in an IRS grants-paid context.
Medium = likely but context is not perfect.
Low = uncertain but possibly relevant.

Source organization:
{source_org}

Source URL:
{source_url}

Part of source being reviewed:
{idx} of {len(chunks)}

Source text:
\"\"\"
{chunk}
\"\"\"
"""
        response = client.responses.create(
            model=model_name,
            input=[
                {
                    "role": "system",
                    "content": "You extract clean nonprofit donor/funder and IRS/Form 990 relationship data into strict structured JSON. You prioritize precision and avoid staff/media/program/recognition false positives."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            text=build_structured_text_format("donor_extraction_result", donor_extraction_schema())
        )
        parsed = safe_json_loads(response.output_text)
        if not parsed:
            continue
        assessments.append(parsed.get("source_assessment", ""))
        for donor in parsed.get("donors", []):
            name = str(donor.get("name", "")).strip()
            if not name:
                continue
            relationship = normalize_relationship(
                donor.get("relationship_to_source", ""),
                fallback=irs_context.get("default_relationship", RELATIONSHIP_FUNDER)
            )
            irs_form_context = str(donor.get("irs_form_context", "")).strip() or irs_context.get("label", IRS_CONTEXT_NONE)
            all_rows.append({
                "Source Organization": source_org or "Unknown organization",
                "Donor/Funder Name": name,
                "Donor Type": donor.get("donor_type", "Unknown"),
                "Relationship to Source": relationship,
                "IRS/Form Context": irs_form_context,
                "Section": donor.get("section", "AI-extracted donor/funder names"),
                "Year": donor.get("year", "Unknown"),
                "Confidence": donor.get("confidence", "Medium"),
                "Notes": donor.get("notes", ""),
                "Source URL": source_url or "Uploaded PDF",
                "Extraction Method": "AI-assisted"
            })
    df = pd.DataFrame(all_rows)
    df = clean_extracted_results(df, source_url=source_url)
    return df, " ".join([a for a in assessments if a])


def ai_find_likely_pages(source_org, homepage_url, model_name):
    client = get_openai_client()
    if client is None:
        raise RuntimeError("OpenAI API key is missing. Add OPENAI_API_KEY in Streamlit Secrets.")
    prompt = f"""
Find likely public donor/funder/supporter/sponsor pages for this nonprofit.

Organization:
{source_org}

Homepage:
{homepage_url}

Look for:
- donor pages
- funder pages
- supporter pages
- sponsor pages
- contributor pages
- annual reports
- impact reports
- donor impact PDFs
- gratitude reports
- IRS/Form 990 sources when useful for funder research
- pages with donor tiers, corporate partners, foundations, agency donors, or individual donors

Return direct URLs where possible.
Prefer pages that are likely to contain actual donor/funder names, not broad homepage pages, generic recognition pages, program pages, press/media pages, or staff/advisory pages.
If recommending IRS/Form 990 sources, note that the source may require grantee/funder relationship review.
"""
    response = client.responses.create(
        model=model_name,
        tools=[{"type": "web_search"}],
        input=[
            {
                "role": "system",
                "content": "You find likely donor/funder/source pages for nonprofit research. Return structured JSON only."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        text=build_structured_text_format("donor_page_discovery_result", page_discovery_schema())
    )
    parsed = safe_json_loads(response.output_text)
    if not parsed:
        return [], "AI did not return usable page results."
    pages = []
    for page in parsed.get("pages", []):
        page_url = str(page.get("url", "")).strip()
        if not page_url.startswith("http"):
            continue
        confidence = page.get("confidence", "Medium")
        score = 95 if confidence == "High" else 82 if confidence == "Medium" else 65
        pages.append({
            "score": score,
            "url": page_url,
            "title": page.get("title", "AI-found page"),
            "reason": page.get("reason", ""),
            "page_type": page.get("page_type", "Unknown"),
            "year": page.get("year", "Unknown"),
            "method": "AI web search"
        })
    return pages, parsed.get("summary", "")


# ============================================================
# Inputs and AI UX
# ============================================================
homepage_url = ""
url = ""
uploaded_file = None

with st.container(border=True):
    st.markdown(
        '<div class="section-eyebrow">Get started</div>'
        '<div class="section-title">Choose your source</div>'
        '<div class="section-sub">Tell the tool which organization you’re researching and where it should start looking.</div>',
        unsafe_allow_html=True
    )

    source_org = st.text_input("Source organization name", placeholder="Example: The Climate Center")

    input_mode = st.radio(
        "What source do you want to start with?",
        [
            "Find pages from an organization homepage",
            "Use an exact webpage or PDF URL",
            "Upload a PDF report"
        ],
        help="Most users should start with the homepage option. Use the direct URL option only when you already know the exact donor page, annual report, Form 990 source, or PDF."
    )

    if input_mode == "Find pages from an organization homepage":
        homepage_url = st.text_input(
            "Organization homepage URL",
            placeholder="Example: https://theclimatecenter.org"
        )
        st.markdown(
            '<div class="small-muted">Best starting point: paste the organization’s main website. The app will look for likely donor, funder, sponsor, supporter, annual report, PDF, and IRS/Form 990 sources.</div>',
            unsafe_allow_html=True
        )
    elif input_mode == "Use an exact webpage or PDF URL":
        url = st.text_input(
            "Exact webpage or PDF URL",
            placeholder="Paste a direct donor page, supporter page, annual report page, Form 990 source, or PDF link here"
        )
        st.markdown(
            '<div class="small-muted">Use this when you already have the exact source page, IRS/Form 990 page, or PDF you want the app to read.</div>',
            unsafe_allow_html=True
        )
    elif input_mode == "Upload a PDF report":
        uploaded_file = st.file_uploader("Upload a PDF report", type=["pdf"])
        st.markdown(
            '<div class="small-muted">Use this for annual reports, impact reports, donor PDFs, IRS/Form 990 PDFs, or saved reports on your computer.</div>',
            unsafe_allow_html=True
        )

api_ready = has_openai_key()
use_ai = api_ready

if api_ready:
    st.markdown(
        '<div class="ai-panel">'
        '<span class="ai-ready-badge">● AI is ready</span>'
        '<div class="card-title">Smart extraction is turned on automatically</div>'
        '<div class="card-copy">'
        'The app will use AI first to find likely donor/funder pages and clean results from messy webpages, PDFs, and IRS/Form 990 sources. '
        'If AI is unavailable for a source, the app will quietly fall back to standard extraction only when the page looks donor-related.'
        '</div>'
        '</div>',
        unsafe_allow_html=True
    )
else:
    st.markdown(
        '<div class="ai-panel">'
        '<span class="ai-off-badge">● AI not connected in this version</span>'
        '<div class="card-title">Standard extraction is available as a backup</div>'
        '<div class="card-copy">'
        'This version does not currently see an OpenAI API key. The app will still try conservative standard extraction. '
        'AI discovery, IRS/Form 990 relationship review, and extraction will turn on once OPENAI_API_KEY is added in Streamlit Secrets or local secrets.'
        '</div>'
        '</div>',
        unsafe_allow_html=True
    )

with st.expander("Smart AI options", expanded=False):
    st.markdown(
        '<div class="info-card">'
        '<div class="card-title">What does AI do here?</div>'
        '<div class="card-copy">'
        'AI helps the app understand messy donor pages, sponsor lists, annual reports, PDFs, and IRS/Form 990 sources more intelligently than basic keyword rules. '
        'It can help find better source pages and return cleaner donor/funder names with confidence and relationship notes.'
        '</div>'
        '</div>',
        unsafe_allow_html=True
    )

    if api_ready:
        st.markdown(
            '<div class="recommendation-card">'
            '<div class="card-title">Recommended default</div>'
            '<div class="card-copy">'
            'For most work, leave this on <strong>Balanced</strong> and <strong>Standard scan</strong>. '
            'These settings are designed to give strong results without using more API credits than necessary.'
            '</div>'
            '</div>',
            unsafe_allow_html=True
        )
    else:
        st.info(
            "AI options are shown below, but they only turn on once the OpenAI API key is available. "
            "For local testing, add the key to `.streamlit/secrets.toml`. For the public app, keep it in Streamlit Secrets."
        )

    model_choice = st.selectbox(
        "AI quality level",
        list(AI_MODEL_OPTIONS.keys()),
        index=0,
        disabled=not api_ready,
        help="Choose how strong the AI should be. Balanced is recommended for most work."
    )
    model_name = AI_MODEL_OPTIONS[model_choice]["model"]
    selected_model_info = AI_MODEL_OPTIONS[model_choice]

    reading_choice = st.selectbox(
        "How deeply should AI read the source?",
        list(AI_READING_OPTIONS.keys()),
        index=1,
        disabled=not api_ready,
        help=(
            "This controls how much of a long webpage or PDF the AI is allowed to read. "
            "Deeper scans can find more names in long reports, but may take longer and use more API credits."
        )
    )
    max_ai_chunks = AI_READING_OPTIONS[reading_choice]["chunks"]
    selected_reading_info = AI_READING_OPTIONS[reading_choice]

    col_ai_1, col_ai_2 = st.columns(2, gap="small")
    with col_ai_1:
        st.markdown(
            '<div class="option-card">'
            '<div class="mini-label">Selected AI quality</div>'
            f'<div class="mini-value">{selected_model_info["label"]}</div>'
            '<div class="card-copy">'
            f'{selected_model_info["short"]}<br><br>'
            f'<strong>Cost level:</strong> {selected_model_info["cost"]}'
            '</div>'
            '</div>',
            unsafe_allow_html=True
        )
    with col_ai_2:
        st.markdown(
            '<div class="option-card">'
            '<div class="mini-label">Selected reading depth</div>'
            f'<div class="mini-value">{selected_reading_info["label"]}</div>'
            '<div class="card-copy">'
            f'{selected_reading_info["short"]}<br><br>'
            f'<strong>Best for:</strong> {selected_reading_info["best_for"]}'
            '</div>'
            '</div>',
            unsafe_allow_html=True
        )

    with st.expander("Which option should I choose?", expanded=False):
        st.write("**Balanced + Standard scan** is the best choice for most donor pages, sponsor pages, and regular annual reports.")
        st.write("**High accuracy + Deep scan** is better when a source is very messy, very long, or the first result looks incomplete.")
        st.write("**Fast/low-cost + Quick scan** is mainly for quick testing when you only need a rough first pass.")

    with st.expander("What does “reading depth” mean?", expanded=False):
        st.write(
            "Reading depth controls how much of a long webpage or PDF the AI is allowed to read. "
            "A short donor page usually only needs Standard scan. A long annual report or IRS filing may need Deep scan because relevant names could be buried far into the document. "
            "Deeper reading can improve results, but it may take longer and use more OpenAI credits."
        )

    st.caption(
        "AI is the main extraction method when connected. Standard extraction remains in the background as a backup if AI is unavailable or returns no clean results."
    )


# ============================================================
# Text extraction helpers
# ============================================================
@st.cache_data(show_spinner=False)
def extract_text_from_webpage(url):
    response = requests.get(
        url,
        timeout=25,
        headers={"User-Agent": "Mozilla/5.0 donor-funder-extraction-tool/2.3"}
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    for tag in soup([
        "script", "style", "header", "nav", "footer", "aside",
        "form", "noscript", "svg", "button"
    ]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body
    if main is None:
        return soup.get_text("\n", strip=True)
    return main.get_text("\n", strip=True)


@st.cache_data(show_spinner=False)
def extract_text_from_pdf_url(url):
    response = requests.get(
        url,
        timeout=35,
        headers={"User-Agent": "Mozilla/5.0 donor-funder-extraction-tool/2.3"}
    )
    response.raise_for_status()
    reader = PdfReader(BytesIO(response.content))
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text


def extract_text_from_uploaded_pdf(uploaded_file):
    reader = PdfReader(uploaded_file)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text


# ============================================================
# Rule-based donor extraction logic
# ============================================================
def is_exact_donor_result_page(url):
    lower = (url or "").lower()
    exact_signals = [
        "business-and-agency-donors", "business-donors", "agency-donors",
        "individual-donors", "foundation-donors", "corporate-donors",
        "annual-fund-donors", "major-donors", "donor-list", "donor-lists",
        "funders", "supporters", "sponsors", "contributors", "donor-impact",
        "gratitude-report"
    ]
    return any(signal in lower for signal in exact_signals)


def is_donor_section_heading(line, source_org=""):
    line = normalize_money_dash(line.strip())
    lower = line.lower()
    if not line:
        return False
    reject_words = [
        "donated", "surpassed", "because", "every", "we ", "our ", "their ",
        "this year", "since", "average", "funds", "grants", "participants",
        "challenge", "community", "facing", "amount granted", "miles traversed",
        "the numbers", "impact report", "annual report", "revenue", "expense",
        "financial", "read more", "learn more", "click here", "webinar",
        "legislators", "endorsements", "climate-safe", "letter of support",
        "letters of support", "media features", "advisory council", "youth council",
        "program", "programs", "translation", "translations", "recognition",
        "recognitions", "award", "awards", "press", "news"
    ]
    if any(word in lower for word in reject_words):
        return False
    exact_headings = [
        "donors", "supporters", "sponsors", "funders", "foundations",
        "contributors", "business and agency donors", "individual donors",
        "individuals and foundations", "corporate partners", "foundation partners",
        "institutional funders", "major donors", "annual fund donors",
        "our supporters", "our donors", "thank you supporters",
        "thank you to our supporters", "thank you to our donors",
        "thank you to our funders", "2025 annual fund donors", "business donors",
        "agency donors", "foundation donors", "visionary partners",
        "mission partners", "leadership partners"
    ]
    if lower in exact_headings:
        return True
    if re.fullmatch(r"\d{4}\s+annual fund donors", lower):
        return True
    if re.fullmatch(r"(individual|business|agency|foundation|corporate)\s+donors?\s+\d{4}", lower):
        return True
    if re.fullmatch(r"\d{4}\s+(individual|business|agency|foundation|corporate)\s+donors?", lower):
        return True
    tier_words = [
        "diamond members", "emerald members", "sapphire members", "ruby members",
        "platinum members", "gold members", "silver members", "bronze members",
        "visionary partners", "mission partners", "leadership partners",
        "supporter level", "partner level", "climate leaders", "climate champions",
        "climate supporters", "climate giants", "climate warriors",
        "climate heroes", "climate defenders", "climate contributors"
    ]
    if any(tier in lower for tier in tier_words):
        return True
    if re.fullmatch(r"\$[\d,]+\s*(\+|and up)", lower):
        return True
    if re.fullmatch(r"\$[\d,]+\s*(-|to)\s*\$[\d,]+", lower):
        return True
    return False


def is_stop_section(line):
    lower = line.lower()
    stop_keywords = [
        "board of directors", "staff", "leadership", "contact", "privacy policy",
        "copyright", "financial statements", "statement of activities",
        "statement of financial position", "expenses", "revenue", "assets",
        "liabilities", "from our director", "looking ahead", "financials",
        "audited financials", "subscribe", "newsletter", "follow us",
        "related posts", "recent posts", "read full bio", "meet the team",
        "media features", "advisory council", "youth council", "programs",
        "translations", "recognitions", "recognition for impact"
    ]
    return any(stop in lower for stop in stop_keywords)


def looks_like_sentence(line):
    words = line.split()
    if len(words) > 7:
        return True
    sentence_words = [
        "the", "and", "but", "because", "with", "from", "this", "that",
        "these", "those", "through", "across", "during", "for", "into",
        "while", "where", "when", "have", "has", "will", "can", "are",
        "is", "was", "were"
    ]
    lower_words = [word.strip(".,!?;:").lower() for word in words]
    if len(words) >= 5 and any(word in lower_words for word in sentence_words):
        return True
    return False


def has_name_shape(line):
    words = line.split()
    if not words:
        return False
    if line.isupper() and 2 <= len(line) <= 12:
        return True
    capitalized_words = 0
    for word in words:
        cleaned = word.strip(".,&()[]{}'\"")
        if not cleaned:
            continue
        if cleaned[0].isupper():
            capitalized_words += 1
    if capitalized_words >= 1 and len(words) <= 6:
        return True
    org_suffixes = [
        "foundation", "fund", "trust", "inc", "llc", "corp", "corporation",
        "company", "bank", "group", "partners", "association", "institute",
        "center", "centre", "council", "agency", "department", "university",
        "school", "college", "club", "society", "alliance", "network", "energy",
        "motors", "carbon", "union", "coalition"
    ]
    lower = line.lower()
    if any(suffix in lower for suffix in org_suffixes):
        return True
    return False


def is_probable_name(line):
    line = line.strip()
    lower = line.lower()
    if not line:
        return False
    if is_donor_section_heading(line):
        return False
    bad_words = [
        "donate", "contact", "privacy", "copyright", "annual report",
        "table of contents", "click", "learn more", "email", "phone", "address",
        "website", "our work", "about us", "menu", "search", "skip to content",
        "financial", "revenue", "expense", "back", "home", "news", "events",
        "careers", "login", "accessibility", "take action", "impact", "values",
        "theory of change", "people", "business network", "partners & advisors",
        "newsletter", "subscribe", "read more", "view all", "share", "facebook",
        "twitter", "linkedin", "instagram", "youtube", "cookie", "terms", "policy",
        "press", "blog", "because of you", "meaningful change", "looking ahead",
        "milestones", "growth", "what we strive for", "climate ride is",
        "every pedal stroke", "support conservation", "advance smarter", "create safe",
        "community, protecting", "the country", "annual report 2025", "from our director",
        "uniting adventure and impact", "growing participation", "participants", "grants",
        "donated", "surpassed", "non-profits", "environmental and", "active transportation",
        "we are a community", "since our founding", "conservation, climate", "amount granted",
        "miles traversed", "the numbers", "facing the challenge", "mission", "vision",
        "page", "report", "total", "subtotal", "the cause", "outreach", "advocacy",
        "movement", "ride bridges", "at the forefront", "resilience", "recognizing",
        "beneficiary", "citizen philanthropists", "california coast", "conversations",
        "personal journeys", "result", "surge", "positive", "anonymous donations",
        "anonymous donation", "all rights reserved", "webinar", "webinars", "letters of support",
        "letter of support", "legislators", "senator", "assemblymember", "committee",
        "program", "campaign", "policies", "chapter", "initiative", "endorsement",
        "endorsements", "climate-safe", "read full bio", "full bio", "bio", "biography",
        "profile", "read bio", "view bio", "meet the team", "speaker", "speakers", "watch",
        "register", "registration", "join us", "sign up", "volunteer", "petition", "download",
        "resource", "resources", "media features", "advisory councils", "young changemakers",
        "young explorers", "read it"
    ]
    if len(line) < 2:
        return False
    if len(line) > 90:
        return False
    if any(word in lower for word in bad_words):
        return False
    if "@" in line:
        return False
    if lower.startswith("http"):
        return False
    if line.replace(" ", "").replace(",", "").replace(".", "").replace("$", "").isdigit():
        return False
    letters = re.findall(r"[A-Za-z]", line)
    if len(letters) < 2:
        return False
    if looks_like_sentence(line):
        return False
    if line.endswith(".") and not line.isupper():
        return False
    if len(line) >= 5:
        no_spaces = line.replace(" ", "")
        if line.count(" ") >= len(no_spaces) - 1 and line.isupper():
            return False
    if not has_name_shape(line):
        return False
    return True


def source_looks_like_strong_donor_page(source_url):
    lower = (source_url or "").lower()
    strong_signals = [
        "donor", "donors", "funder", "funders", "sponsor", "sponsors",
        "supporter", "supporters", "contributors", "annual-report",
        "impact-report", "gratitude-report", "partners"
    ]
    weak_signals_to_avoid_for_fallback = [
        "thank-you", "gratitude", "advisors", "program", "programs",
        "recognition", "recognitions", "press", "media", "news"
    ]
    if any(signal in lower for signal in strong_signals) and not any(signal in lower for signal in weak_signals_to_avoid_for_fallback):
        return True
    if any(signal in lower for signal in weak_signals_to_avoid_for_fallback):
        return False
    return False


def source_is_broad_report_page(source_url):
    lower = (source_url or "").lower()
    broad_signals = [
        "annual-report", "annual-reports", "impact-report", "impact-reports",
        "/impact", "/about/annual-report", "/about/impact"
    ]
    strong_signals = [
        "donor", "donors", "supporter", "supporters", "funder", "funders",
        "sponsor", "sponsors", "contributors"
    ]
    has_broad_signal = any(signal in lower for signal in broad_signals)
    has_strong_signal = any(signal in lower for signal in strong_signals)
    return has_broad_signal and not has_strong_signal


def extract_possible_donors_rule_based(text, source_org, source_url):
    lines = clean_lines(text)
    irs_context = detect_irs_form_context(source_url, text)
    relationship = normalize_relationship(irs_context.get("default_relationship"), fallback=RELATIONSHIP_FUNDER)
    irs_label = irs_context.get("label", IRS_CONTEXT_NONE)
    rows = []
    collecting = False
    current_section = "Possible donor/funder names"
    for line in lines:
        if is_donor_section_heading(line, source_org):
            collecting = True
            current_section = line
            continue
        if collecting and is_stop_section(line):
            collecting = False
            continue
        if collecting and is_probable_name(line):
            rows.append({
                "Source Organization": source_org or "Unknown organization",
                "Donor/Funder Name": line,
                "Donor Type": "Unknown",
                "Relationship to Source": relationship,
                "IRS/Form Context": irs_label,
                "Section": current_section,
                "Year": str(extract_year_from_url(source_url) or "Unknown"),
                "Confidence": "Medium",
                "Notes": "Standard extraction",
                "Source URL": source_url or "Uploaded PDF",
                "Extraction Method": "Standard extraction"
            })
    if (
        not rows
        and source_looks_like_strong_donor_page(source_url)
        and not source_is_broad_report_page(source_url)
    ):
        for line in lines:
            if is_probable_name(line):
                rows.append({
                    "Source Organization": source_org or "Unknown organization",
                    "Donor/Funder Name": line,
                    "Donor Type": "Unknown",
                    "Relationship to Source": relationship,
                    "IRS/Form Context": irs_label,
                    "Section": "Possible donor/funder names - fallback scan",
                    "Year": str(extract_year_from_url(source_url) or "Unknown"),
                    "Confidence": "Low",
                    "Notes": "Fallback standard scan",
                    "Source URL": source_url or "Uploaded PDF",
                    "Extraction Method": "Standard extraction"
                })
    df = pd.DataFrame(rows)
    df = clean_extracted_results(df, source_url=source_url)
    return df


# ============================================================
# Result cleaning / false-positive control
# ============================================================
def clean_extracted_results(df, source_url=""):
    if df is None or df.empty:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    df = df.copy()
    for col in RESULT_COLUMNS:
        if col not in df.columns:
            if col == "Relationship to Source":
                df[col] = RELATIONSHIP_FUNDER
            elif col == "IRS/Form Context":
                df[col] = IRS_CONTEXT_NONE
            else:
                df[col] = ""
    for col in [
        "Donor/Funder Name", "Donor Type", "Relationship to Source", "IRS/Form Context",
        "Section", "Notes", "Source URL", "Extraction Method"
    ]:
        df[col] = df[col].astype(str)
    source_lower = str(source_url or "").lower()
    false_positive_contexts = [
        "media feature", "media features", "press", "news", "article",
        "advisory council", "youth council", "young changemaker", "young changemakers",
        "young explorers", "speaker", "staff", "board", "program", "programs",
        "translation", "translations", "recognition", "recognitions",
        "climate and justice leader"
    ]
    false_positive_names = {
        "media features", "the guardian", "read it", "forbes", "vice",
        "the washington post", "young changemakers", "young explorers",
        "advisory councils", "who youth council"
    }
    donor_context_words = [
        "donor", "donors", "funder", "funders", "sponsor", "sponsors",
        "supporter", "supporters", "contributor", "contributors", "grant",
        "grants", "funding", "donation", "donating", "donated", "sponsored",
        "sponsoring", "underwrite", "underwriting", "annual fund", "grantee", "recipient"
    ]

    def keep_row(row):
        name = normalize_name_for_dedupe(row.get("Donor/Funder Name", ""))
        section = str(row.get("Section", "")).lower()
        notes = str(row.get("Notes", "")).lower()
        donor_type = str(row.get("Donor Type", "")).lower()
        relationship = str(row.get("Relationship to Source", "")).lower()
        irs_context = str(row.get("IRS/Form Context", "")).lower()
        method = str(row.get("Extraction Method", "")).lower()
        combined = " ".join([name, section, notes, donor_type, relationship, irs_context, source_lower])
        if not name or len(name) < 2:
            return False
        if name in false_positive_names:
            return False
        if any(bad in combined for bad in false_positive_contexts):
            if not any(good in combined for good in donor_context_words):
                return False
        if "program partner" in donor_type or "program partner" in combined:
            if not any(good in combined for good in donor_context_words):
                return False
        if "standard" in method:
            if any(bad in source_lower for bad in ["recognition", "recognitions", "/program", "/programs", "media", "press", "news"]):
                return False
        return True

    df = df[df.apply(keep_row, axis=1)]
    if not df.empty:
        df["Relationship to Source"] = df["Relationship to Source"].apply(lambda value: normalize_relationship(value, fallback=RELATIONSHIP_FUNDER))
        df.loc[df["IRS/Form Context"].str.strip().eq(""), "IRS/Form Context"] = IRS_CONTEXT_NONE
        df["Dedupe Key"] = df["Donor/Funder Name"].apply(normalize_name_for_dedupe)
        df = df.drop_duplicates(subset=["Dedupe Key", "Source URL"])
        df = df.drop(columns=["Dedupe Key"])
        df = df.reset_index(drop=True)
    for col in RESULT_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[RESULT_COLUMNS]
    return df


# ============================================================
# Extraction and display helpers
# ============================================================
def extract_text_from_source(target_url, uploaded_file):
    if uploaded_file is not None:
        return extract_text_from_uploaded_pdf(uploaded_file), "Uploaded PDF"
    if target_url:
        source = target_url
        if target_url.lower().endswith(".pdf"):
            return extract_text_from_pdf_url(target_url), source
        return extract_text_from_webpage(target_url), source
    return None, None


def extract_from_source(target_url, uploaded_file, source_org, use_ai_flag, model_name, max_ai_chunks):
    text, source = extract_text_from_source(target_url, uploaded_file)
    if not text:
        return None, source, ""
    ai_note = ""
    if use_ai_flag and has_openai_key():
        try:
            ai_df, ai_note = ai_extract_possible_donors(
                text=text,
                source_org=source_org,
                source_url=source,
                model_name=model_name,
                max_chunks=max_ai_chunks
            )
            if ai_df is not None and not ai_df.empty:
                return ai_df, source, ai_note
        except Exception as ai_error:
            st.warning(
                f"AI extraction was unavailable for this source, so the app used standard extraction if this page looked donor-related. Details: {ai_error}"
            )
    if source and source_looks_like_strong_donor_page(source):
        rule_df = extract_possible_donors_rule_based(text, source_org, source)
        return rule_df, source, ai_note
    return pd.DataFrame(columns=RESULT_COLUMNS), source, ai_note


@st.cache_data(show_spinner=False)
def cached_find_pages(homepage_url, top_n):
    return find_likely_donor_pages(homepage_url, top_n=top_n)


def normalize_candidate_url(url):
    url = str(url or "").strip()
    if not url:
        return ""
    parsed = urlparse(url)
    cleaned = parsed._replace(fragment="").geturl()
    if cleaned.endswith("/"):
        cleaned = cleaned[:-1]
    return cleaned.lower()


def get_domain_label(url):
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain or "source site"
    except Exception:
        return "source site"


def candidate_text_blob(candidate):
    return " ".join([
        str(candidate.get("page_type", "")),
        str(candidate.get("title", "")),
        str(candidate.get("url", "")),
        str(candidate.get("reason", "")),
        str(candidate.get("method", "")),
    ]).lower()


def url_path_lower(url):
    try:
        return urlparse(url).path.lower()
    except Exception:
        return str(url or "").lower()


def friendly_page_type(candidate):
    text = candidate_text_blob(candidate)
    path = url_path_lower(candidate.get("url", ""))
    if any(signal in text or signal in path for signal in [
        "form 990", "form-990", "form990", "990-pf", "990pf",
        "irs", "schedule i", "nonprofit explorer", "propublica", "grants paid"
    ]):
        if "990-pf" in text or "990pf" in text or "990-pf" in path or "990pf" in path:
            return "IRS/Form 990-PF source"
        if "grants paid" in text or "schedule i" in text:
            return "IRS/Form 990 grants-paid source"
        return "IRS/Form 990 source"
    direct_partner_list_phrases = [
        "visionary partners", "mission partners", "leadership partners",
        "corporate partners", "foundation partners", "our partners",
        "partner list", "donor list", "supporter list", "sponsor list"
    ]
    if any(phrase in text for phrase in direct_partner_list_phrases):
        return "Direct partner/donor list page"
    if ".pdf" in path or "pdf" in text:
        if "donor" in text and "impact" in text:
            return "Donor impact PDF"
        if "gratitude" in text:
            return "Donor gratitude PDF"
        return "PDF report"
    if "annual" in text and "report" in text:
        return "Annual report page"
    if "foundation" in text and ("partner" in text or "partners" in text or "corporate" in text):
        return "Corporate/foundation partners page"
    if "corporate" in text and ("partner" in text or "partners" in text or "sponsor" in text):
        return "Corporate partners page"
    if "foundation" in text or "/foundations" in path:
        return "Foundation/funder page"
    if "partner" in text or "partners" in text or "/partners" in path:
        return "Partner page"
    if "sponsor" in text:
        return "Sponsor page"
    if "supporter" in text or "supporters" in text:
        return "Supporter page"
    if "funder" in text or "funders" in text:
        return "Funder page"
    if "donor" in text or "donors" in text:
        return "Donor page"
    if "contributor" in text or "contributors" in text:
        return "Contributor page"
    if "financial" in text or "financials" in path:
        return "Financials/report page"
    return "Possible donor-related page"


def is_low_quality_discovery_page(candidate):
    text = candidate_text_blob(candidate)
    path = url_path_lower(candidate.get("url", ""))
    title = str(candidate.get("title", "")).lower()
    if is_irs_candidate_source(candidate):
        return False
    hard_bad_path_bits = [
        "/node/", "/en-espanol/", "/espanol", "/es/", "/fr/", "/de/",
        "/blog", "/blogs", "/news", "/newsroom", "/press", "/media",
        "/article", "/articles", "/story", "/stories", "/events", "/event",
        "/careers", "/jobs", "/volunteer", "/recipes", "/recipe",
        "/programs", "/program", "/recognitions", "/recognition"
    ]
    if any(bit in path for bit in hard_bad_path_bits):
        if not any(good in text for good in ["donor", "fund", "sponsor", "supporter", "contributor", "annual report", "donor impact", "gratitude"]):
            return True
    weak_title_bits = [
        "en español", "español", "blog", "news", "press", "recipe",
        "volunteer", "careers", "event", "homepage", "programs",
        "recognitions", "recognition", "media features"
    ]
    if any(bit in title for bit in weak_title_bits):
        if not any(good in text for good in ["donor", "funder", "sponsor", "supporter", "annual report", "donor impact"]):
            return True
    page_type = friendly_page_type(candidate).lower()
    if page_type == "possible donor-related page" and not any(
        good in text for good in [
            "annual report", "donor", "donors", "partner", "partners",
            "foundation", "foundations", "supporter", "supporters",
            "sponsor", "sponsors", "funder", "funders", "form 990", "990-pf"
        ]
    ):
        return True
    return False


def page_specificity_score(candidate):
    text = candidate_text_blob(candidate)
    path = url_path_lower(candidate.get("url", ""))
    title = str(candidate.get("title", "")).lower()
    try:
        score = int(candidate.get("score", 60))
    except Exception:
        score = 60
    if "/node/" in path or "/en-espanol/" in path or "/espanol" in path:
        score -= 300
    if is_irs_candidate_source(candidate):
        score += 35
        if "grants paid" in text or "schedule i" in text or "990-pf" in text or "990pf" in text:
            score += 20
    best_path_bits = [
        "/partners", "/about/partners", "/corporate-and-foundation",
        "/foundations", "/foundation", "/donors", "/supporters",
        "/sponsors", "/funders", "/contributors"
    ]
    for bit in best_path_bits:
        if bit in path:
            score += 160
    report_path_bits = [
        "/annual-report", "/annual-reports", "/financials",
        "/impact-report", "/impact-reports", "/donor-impact"
    ]
    for bit in report_path_bits:
        if bit in path:
            score += 65
    strong_title_phrases = [
        "visionary partners", "mission partners", "leadership partners",
        "corporate partners", "foundation partners", "our partners",
        "partner list", "donor list", "supporter list", "sponsor list",
        "donors", "our donors", "supporters", "our supporters",
        "partners", "foundations", "corporate and foundation", "sponsors",
        "funders", "donor impact", "gratitude report", "annual report",
        "form 990", "990-pf", "schedule i", "grants paid"
    ]
    for phrase in strong_title_phrases:
        if phrase in title or phrase in text:
            score += 42
    page_type = friendly_page_type(candidate).lower()
    if page_type in [
        "direct partner/donor list page",
        "corporate/foundation partners page", "corporate partners page",
        "foundation/funder page", "partner page", "donor page",
        "supporter page", "sponsor page", "funder page", "contributor page"
    ]:
        score += 165
    elif page_type in ["annual report page", "donor impact pdf", "donor gratitude pdf"]:
        score += 55
    elif page_type in ["irs/form 990 source", "irs/form 990-pf source", "irs/form 990 grants-paid source"]:
        score += 30
    elif page_type == "pdf report":
        score += 25
    elif page_type == "possible donor-related page":
        score -= 110
    informational_phrases = [
        "how foundations partner", "why i partner", "ways to give",
        "how to partner", "become a partner", "partner with us",
        "corporate and foundations/foundations"
    ]
    for phrase in informational_phrases:
        if phrase in title or phrase in text or phrase in path:
            score -= 130
    bad_context_bits = [
        "/blog", "/blogs", "/news", "/newsroom", "/press", "/media",
        "/article", "/articles", "/story", "/stories", "/events", "/event",
        "/careers", "/jobs", "/volunteer", "/recipes", "/recipe",
        "/about-us/our-work", "/programs", "/program", "/recognitions", "/recognition"
    ]
    for bit in bad_context_bits:
        if bit in path:
            score -= 160
    weak_title_bits = [
        "blog", "news", "press", "recipe", "volunteer", "careers",
        "event", "en español", "español", "homepage", "about us", "our work",
        "programs", "recognition", "recognitions", "media features"
    ]
    for bit in weak_title_bits:
        if bit in title:
            score -= 80
    found_year = extract_year_from_url(candidate.get("url", ""))
    if found_year:
        score += max(0, min(60, (found_year - 2010) * 4))
    if page_type == "possible donor-related page" and not any(bit in path for bit in best_path_bits + report_path_bits):
        score -= 140
    return score


def rerank_candidate_pages(candidates):
    reranked = []
    for candidate in candidates or []:
        candidate = dict(candidate)
        candidate["display_score"] = page_specificity_score(candidate)
        reranked.append(candidate)
    return sorted(reranked, key=lambda item: item.get("display_score", 0), reverse=True)


def match_strength_label(score):
    try:
        score = int(score)
    except Exception:
        score = 0
    if score >= 120:
        return "Best match"
    if score >= 75:
        return "Good match"
    return "Possible match"


def readable_candidate_label(candidate):
    display_score = candidate.get("display_score", page_specificity_score(candidate))
    strength = match_strength_label(display_score)
    page_type = friendly_page_type(candidate)
    domain = get_domain_label(candidate.get("url", ""))
    title = str(candidate.get("title", "")).strip()
    if not title or title.lower() in ["found page", "ai-found page", "page", "unknown"]:
        return f"{strength} — {page_type} — {domain}"
    if len(title) > 58:
        title = title[:55].rstrip() + "..."
    return f"{strength} — {page_type} — {domain} — {title}"


@st.cache_data(show_spinner=False, ttl=3600)
def check_url_status(url):
    url = str(url or "").strip()
    if not url.startswith("http"):
        return {
            "url": url,
            "final_url": url,
            "status": "Broken link",
            "status_code": None,
            "is_usable": False,
            "message": "This does not look like a valid web link."
        }
    headers = {
        "User-Agent": "Mozilla/5.0 donor-funder-extraction-tool/2.3",
        "Accept": "text/html,application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        response = requests.get(
            url,
            timeout=12,
            headers=headers,
            allow_redirects=True,
            stream=True
        )
        status_code = response.status_code
        final_url = response.url
        response.close()
        if 200 <= status_code < 400:
            return {
                "url": url,
                "final_url": final_url,
                "status": "Available",
                "status_code": status_code,
                "is_usable": True,
                "message": "This page opened successfully."
            }
        if status_code == 404:
            return {
                "url": url,
                "final_url": final_url,
                "status": "Broken link",
                "status_code": status_code,
                "is_usable": False,
                "message": "This page no longer exists or could not be found."
            }
        if status_code in [401, 403]:
            return {
                "url": url,
                "final_url": final_url,
                "status": "Website blocked access",
                "status_code": status_code,
                "is_usable": False,
                "message": "The website blocked automated access to this page."
            }
        return {
            "url": url,
            "final_url": final_url,
            "status": "Could not verify",
            "status_code": status_code,
            "is_usable": False,
            "message": f"The page returned HTTP status {status_code}."
        }
    except requests.exceptions.Timeout:
        return {
            "url": url,
            "final_url": url,
            "status": "Could not verify",
            "status_code": None,
            "is_usable": False,
            "message": "The page took too long to respond."
        }
    except requests.exceptions.RequestException as exc:
        return {
            "url": url,
            "final_url": url,
            "status": "Could not verify",
            "status_code": None,
            "is_usable": False,
            "message": str(exc)
        }


def filter_usable_candidate_pages(candidates):
    usable = []
    skipped = []
    for candidate in candidates or []:
        status = check_url_status(candidate.get("url", ""))
        candidate = dict(candidate)
        candidate["page_status"] = status["status"]
        candidate["status_code"] = status["status_code"]
        candidate["status_message"] = status["message"]
        candidate["final_url"] = status["final_url"]
        if status["is_usable"]:
            if status.get("final_url") and status["final_url"] != candidate.get("url"):
                candidate["url"] = status["final_url"]
            if is_low_quality_discovery_page(candidate):
                candidate["page_status"] = "Skipped as low-quality match"
                candidate["status_message"] = "This page opens, but looks like a translated, generic, program, recognition, news/blog, or CMS page rather than a clean donor/funder source."
                skipped.append(candidate)
            else:
                usable.append(candidate)
        else:
            skipped.append(candidate)
    usable = rerank_candidate_pages(usable)
    return usable, skipped


def merge_candidate_pages(rule_candidates, ai_candidates):
    merged = {}
    for candidate in rule_candidates or []:
        url = candidate.get("url", "")
        key = normalize_candidate_url(url)
        if not key:
            continue
        merged[key] = {
            "score": int(candidate.get("score", 60)),
            "url": url,
            "title": candidate.get("title", "Found page"),
            "reason": candidate.get("reason", "Found by website link scan."),
            "page_type": candidate.get("page_type", "Unknown"),
            "year": str(extract_year_from_url(url) or "Unknown"),
            "method": "Website scan"
        }
    for candidate in ai_candidates or []:
        url = candidate.get("url", "")
        key = normalize_candidate_url(url)
        if not key:
            continue
        if key in merged:
            merged[key]["score"] = max(merged[key]["score"], int(candidate.get("score", 90)))
            merged[key]["method"] = "Website scan + AI"
            merged[key]["reason"] = candidate.get("reason", merged[key]["reason"])
            merged[key]["title"] = candidate.get("title", merged[key]["title"])
            merged[key]["page_type"] = candidate.get("page_type", merged[key]["page_type"])
            if candidate.get("year") and candidate.get("year") != "Unknown":
                merged[key]["year"] = candidate.get("year")
        else:
            merged[key] = candidate
    results = list(merged.values())
    results = rerank_candidate_pages(results)
    return results


def candidate_year(candidate):
    year_value = str(candidate.get("year", "") or "")
    match = re.search(r"20\d{2}", year_value)
    if match:
        return int(match.group(0))
    return extract_year_from_url(candidate.get("url", ""))


def is_actual_list_source(candidate):
    text = candidate_text_blob(candidate)
    path = url_path_lower(candidate.get("url", ""))
    page_type = friendly_page_type(candidate).lower()
    if page_type not in [
        "direct partner/donor list page", "donor page", "supporter page", "sponsor page",
        "funder page", "contributor page", "partner page", "corporate partners page",
        "corporate/foundation partners page", "foundation/funder page"
    ]:
        return False
    weak_info = [
        "how foundations partner", "why i partner", "ways to give", "how to partner",
        "become a partner", "partner with us", "/ways-to-give/corporate-and-foundations/foundations"
    ]
    if any(bit in text or bit in path for bit in weak_info):
        if not any(strong in text for strong in ["visionary partners", "mission partners", "leadership partners", "our partners", "donor list", "supporter list"]):
            return False
    bad_context = ["/program", "/programs", "/recognition", "/recognitions", "/press", "/media", "/news"]
    if any(bit in path for bit in bad_context):
        return False
    return True


def is_report_or_pdf_source(candidate):
    page_type = friendly_page_type(candidate).lower()
    text = candidate_text_blob(candidate)
    return page_type in [
        "annual report page", "donor impact pdf", "donor gratitude pdf", "pdf report",
        "financials/report page", "irs/form 990 source", "irs/form 990-pf source", "irs/form 990 grants-paid source"
    ] or "pdf" in text


def is_useful_extraction_candidate(candidate):
    return (
        is_actual_list_source(candidate)
        or is_report_or_pdf_source(candidate)
        or is_exact_donor_result_page(candidate.get("url", ""))
        or is_irs_candidate_source(candidate)
    )


def get_current_latest_candidate_urls(manual_url=""):
    manual_url = (manual_url or "").strip()
    if manual_url:
        return [manual_url]
    candidates = [c for c in st.session_state.candidate_pages if is_useful_extraction_candidate(c)]
    if not candidates:
        return []
    direct_pages = [c for c in candidates if is_actual_list_source(c)]
    report_pages = [c for c in candidates if is_report_or_pdf_source(c) or is_exact_donor_result_page(c.get("url", ""))]
    direct_pages = sorted(direct_pages, key=lambda c: c.get("display_score", page_specificity_score(c)), reverse=True)
    dated_reports = [(candidate_year(c), c) for c in report_pages if candidate_year(c)]
    newest_report_pages = []
    if dated_reports:
        newest_year = max(year for year, _ in dated_reports)
        newest_report_pages = [c for year, c in dated_reports if year == newest_year]
        newest_report_pages = sorted(newest_report_pages, key=lambda c: c.get("display_score", page_specificity_score(c)), reverse=True)
    selected = []
    for c in direct_pages[:2] + newest_report_pages[:2]:
        url = c.get("url", "")
        if url and url not in selected:
            selected.append(url)
    if not selected and st.session_state.candidate_pages:
        selected.append(st.session_state.candidate_pages[0].get("url", ""))
    return [url for url in selected if url]


def get_candidate_urls_for_extraction(mode="all", manual_url=""):
    if mode in ["current", "newest"]:
        return get_current_latest_candidate_urls(manual_url=manual_url)
    candidate_urls = []
    for candidate in st.session_state.candidate_pages:
        candidate_url = candidate.get("url", "")
        if not is_useful_extraction_candidate(candidate):
            continue
        candidate_urls.append(candidate_url)
    candidate_urls = list(dict.fromkeys([url for url in candidate_urls if url]))
    return candidate_urls


def combine_and_clean_results(all_results, dedupe_across_pages=False):
    combined_df = pd.concat(all_results, ignore_index=True)
    combined_df = clean_extracted_results(combined_df)
    if combined_df.empty:
        return combined_df
    combined_df["Dedupe Key"] = combined_df["Donor/Funder Name"].apply(normalize_name_for_dedupe)
    if dedupe_across_pages:
        combined_df = combined_df.drop_duplicates(subset=["Dedupe Key"])
    else:
        combined_df = combined_df.drop_duplicates(subset=["Dedupe Key", "Source URL"])
    combined_df = combined_df.drop(columns=["Dedupe Key"])
    combined_df = combined_df.reset_index(drop=True)
    for col in RESULT_COLUMNS:
        if col not in combined_df.columns:
            combined_df[col] = ""
    combined_df = combined_df[RESULT_COLUMNS]
    return combined_df


def show_extraction_summary(result_df, years_display_override=None):
    if result_df is None or result_df.empty:
        return
    temp_df = result_df.copy()
    if "Year" not in temp_df.columns:
        temp_df["Year"] = temp_df["Source URL"].apply(extract_year_from_url)
    if "Relationship to Source" not in temp_df.columns:
        temp_df["Relationship to Source"] = RELATIONSHIP_FUNDER
    temp_df["Dedupe Key"] = temp_df["Donor/Funder Name"].apply(normalize_name_for_dedupe)
    total_rows = len(temp_df)
    unique_names = temp_df["Dedupe Key"].nunique()
    pages_used = temp_df["Source URL"].nunique()
    grantee_review_count = int(temp_df["Relationship to Source"].eq(RELATIONSHIP_GRANTEE).sum())
    unclear_review_count = int(temp_df["Relationship to Source"].eq(RELATIONSHIP_UNCLEAR).sum())
    raw_years = [
        str(year).strip() for year in temp_df["Year"].dropna().unique()
        if str(year).strip().lower() not in ["", "unknown", "none", "nan"]
    ]
    numeric_years = sorted({
        int(year) for year in raw_years
        if re.fullmatch(r"20\d{2}", year)
    })
    if years_display_override:
        years_display = years_display_override
    elif not numeric_years:
        years_display = "Unknown"
    elif len(numeric_years) == 1:
        years_display = str(numeric_years[0])
    elif len(numeric_years) <= 4:
        years_display = ", ".join(str(year) for year in numeric_years)
    else:
        years_display = f"Multiple years ({numeric_years[0]}–{numeric_years[-1]})"
    st.subheader("Extraction summary")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total rows", total_rows)
    col2.metric("Unique names", unique_names)
    col3.metric("Pages used", pages_used)
    col4.metric("Years included", years_display)
    col5.metric("Grantee/recipient review", grantee_review_count)
    if total_rows != unique_names:
        st.info(
            "Some names may appear on multiple pages or across multiple years. "
            "The CSV keeps Source URL and Section so those appearances can be reviewed."
        )
    if grantee_review_count:
        st.warning(
            f"{grantee_review_count} row(s) are flagged as likely grantees/recipients (shown in amber in the table below). "
            "On IRS/Form 990 sources these are often organizations receiving money from the filing organization, not donors to the source organization. "
            "Check the direction of funding before treating any of them as a funder."
        )
    if unclear_review_count:
        st.info(
            f"{unclear_review_count} row(s) are marked 'Unclear / needs review' because the funding direction was not certain. Confirm these before use."
        )


def style_results_dataframe(result_df):
    """
    Display-only: color-codes the Relationship to Source column so funders,
    grantees/recipients, and unclear rows are easy to tell apart at a glance.
    Falls back to the plain dataframe if styling is unavailable. Does not change
    the underlying data or the exported CSV.
    """
    relationship_styles = {
        RELATIONSHIP_FUNDER: "background-color: #e0f2fe; color: #075985; font-weight: 600;",
        RELATIONSHIP_GRANTEE: "background-color: #fef3c7; color: #92400e; font-weight: 600;",
        RELATIONSHIP_UNCLEAR: "background-color: #f1f5f9; color: #334155; font-weight: 600;",
    }
    try:
        def color_relationship_column(column):
            return [relationship_styles.get(str(value).strip(), "") for value in column]
        return result_df.style.apply(color_relationship_column, subset=["Relationship to Source"])
    except Exception:
        return result_df


def show_results(result_df, source_org, ai_note="", years_display_override=None):
    if result_df is None:
        st.warning("Please provide a valid source.")
        return
    if result_df.empty:
        st.warning(
            "No clear donor/funder names were extracted from this source. "
            "Try a more specific donor, supporter, sponsor, funder, contributor, annual report, IRS/Form 990, or donor PDF page."
        )
        return
    if ai_note:
        with st.expander("AI source assessment", expanded=False):
            st.write(ai_note)
    show_extraction_summary(result_df, years_display_override=years_display_override)
    st.success(f"Extracted {len(result_df)} possible donor/funder or IRS/Form 990 relationship rows.")
    st.info("Please review results before using them. Pay special attention to Relationship to Source, IRS/Form Context, confidence, and notes.")
    st.markdown(
        '<div style="display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:0.1rem 0 0.6rem;">'
        '<span style="font-weight:800; color:#475569; font-size:0.85rem; margin-right:4px;">Relationship key:</span>'
        '<span style="background:#e0f2fe; color:#075985; border:1px solid #bae6fd; border-radius:999px; padding:3px 10px; font-size:0.8rem; font-weight:700;">Likely funder/donor — gave to the source org</span>'
        '<span style="background:#fef3c7; color:#92400e; border:1px solid #fde68a; border-radius:999px; padding:3px 10px; font-size:0.8rem; font-weight:700;">Likely grantee/recipient — may be receiving money; review</span>'
        '<span style="background:#f1f5f9; color:#334155; border:1px solid #cbd5e1; border-radius:999px; padding:3px 10px; font-size:0.8rem; font-weight:700;">Unclear — needs review</span>'
        '</div>',
        unsafe_allow_html=True
    )
    st.dataframe(style_results_dataframe(result_df), use_container_width=True)
    csv = result_df.to_csv(index=False).encode("utf-8")
    safe_org = re.sub(r"[^a-zA-Z0-9]+", "_", source_org.lower()).strip("_") or "organization"
    st.download_button(
        label="Download results as CSV",
        data=csv,
        file_name=f"{safe_org}_donors.csv",
        mime="text/csv"
    )


def run_multi_page_extraction(mode="all", manual_url=""):
    urls_to_extract = get_candidate_urls_for_extraction(mode=mode, manual_url=manual_url)
    if not urls_to_extract:
        st.warning(
            "No usable donor/funder source pages were found for this extraction mode. "
            "Try pasting a specific donor, supporter, partner, annual report, IRS/Form 990, or PDF URL into the override box."
        )
        return
    all_results = []
    is_current_mode = mode in ["current", "newest"]
    label = "current/latest donors" if is_current_mode else "all years found"
    years_display_override = "Current / latest available" if is_current_mode else None
    st.caption(f"Reading {len(urls_to_extract)} source page(s).")
    with st.spinner(f"Extracting names from {label}..."):
        for candidate_url in urls_to_extract:
            result_df, selected_source, ai_note = extract_from_source(
                target_url=candidate_url,
                uploaded_file=None,
                source_org=source_org,
                use_ai_flag=use_ai,
                model_name=model_name,
                max_ai_chunks=max_ai_chunks
            )
            if result_df is not None and not result_df.empty:
                all_results.append(result_df)
    if not all_results:
        st.warning(
            "No clear donor/funder names were extracted from the found pages. "
            "Try choosing another dropdown page, pasting a direct donor/funder/supporter page, or uploading a PDF."
        )
        return
    combined_df = combine_and_clean_results(
        all_results,
        dedupe_across_pages=False
    )
    show_results(combined_df, source_org, years_display_override=years_display_override)


# ============================================================
# Main app actions
# ============================================================
if input_mode == "Find pages from an organization homepage":
    col1, col2, col3 = st.columns([0.18, 0.18, 0.64], gap="small")
    with col1:
        find_clicked = st.button("Find likely pages", type="primary", use_container_width=True)
    with col2:
        clear_clicked = st.button("Clear found pages", use_container_width=True)

    if clear_clicked:
        st.session_state.candidate_pages = []
        st.session_state.last_homepage_url = ""
        st.session_state.last_source_org = ""
        st.session_state.skipped_pages = []
        st.success("Cleared found pages.")

    if find_clicked:
        if not source_org:
            st.warning("Please enter the source organization name first.")
        elif not homepage_url:
            st.warning("Please enter an organization homepage URL.")
        else:
            try:
                rule_candidates = []
                ai_candidates = []
                ai_summary = ""
                with st.status("Finding usable donor/funder pages...", expanded=True) as status:
                    st.write("Scanning the organization website for donor, sponsor, supporter, annual report, IRS/Form 990, and PDF links...")
                    rule_candidates = cached_find_pages(homepage_url, top_n=10)
                    if use_ai and has_openai_key():
                        st.write("Asking AI to look for stronger public donor/funder page matches...")
                        try:
                            ai_candidates, ai_summary = ai_find_likely_pages(
                                source_org=source_org,
                                homepage_url=homepage_url,
                                model_name=model_name
                            )
                        except Exception as ai_error:
                            st.warning(
                                f"AI page discovery was unavailable, so the app used regular website scanning only. Details: {ai_error}"
                            )
                    st.write("Combining duplicate suggestions...")
                    candidates = merge_candidate_pages(rule_candidates, ai_candidates)
                    st.write("Checking which suggested pages actually open...")
                    usable_candidates, skipped_candidates = filter_usable_candidate_pages(candidates)
                    st.session_state.skipped_pages = skipped_candidates
                    status.update(label="Page discovery complete", state="complete", expanded=False)
                if not usable_candidates:
                    st.warning(
                        "No usable donor/funder pages were found. The app may have found broken, blocked, or low-quality links only. "
                        "Try using the manual URL option with a direct donor, funder, annual report, IRS/Form 990, or PDF link."
                    )
                    st.session_state.candidate_pages = []
                else:
                    st.session_state.candidate_pages = usable_candidates
                    st.session_state.last_homepage_url = homepage_url
                    st.session_state.last_source_org = source_org
                    st.success(f"Found {len(usable_candidates)} usable page(s).")
                    if skipped_candidates:
                        st.info(f"Skipped {len(skipped_candidates)} broken, blocked, unavailable, or low-quality page(s).")
                    if ai_summary:
                        st.info(ai_summary)
            except Exception as e:
                st.error(f"Something went wrong while finding pages: {e}")

    if st.session_state.candidate_pages:
        st.subheader("Found usable pages")
        st.caption("The app checked the suggested links and only shows pages that appear to open successfully and look relevant.")
        if st.session_state.get("skipped_pages"):
            with st.expander(f"Skipped {len(st.session_state.skipped_pages)} broken, blocked, unavailable, or low-quality page(s)", expanded=False):
                for skipped in st.session_state.skipped_pages:
                    status = skipped.get("page_status", "Unavailable")
                    code = skipped.get("status_code")
                    message = skipped.get("status_message", "This page could not be used.")
                    code_text = f"HTTP {code}" if code else "No status code"
                    st.write(f"**{status}** ({code_text}) — {skipped.get('url', '')}")
                    st.caption(message)
        candidate_options = []
        seen_labels = {}
        for idx, candidate in enumerate(st.session_state.candidate_pages, start=1):
            base_label = readable_candidate_label(candidate)
            label_count = seen_labels.get(base_label, 0) + 1
            seen_labels[base_label] = label_count
            if label_count > 1:
                label = f"{base_label} ({label_count})"
            else:
                label = base_label
            candidate_options.append(label)
        selected_option = st.selectbox(
            "Review a suggested source page",
            candidate_options,
            key="candidate_page_selectbox",
            help="Best match means the app thinks this page is highly likely to contain donor/funder information. IRS/Form 990 sources should be reviewed carefully for funder vs grantee direction."
        )
        selected_index = candidate_options.index(selected_option)
        selected_candidate = st.session_state.candidate_pages[selected_index]
        selected_url = selected_candidate["url"]
        with st.expander("Why this page was suggested", expanded=False):
            st.write(selected_candidate.get("reason", "No reason provided."))
            st.write(f"Page type: {friendly_page_type(selected_candidate)}")
            st.write(f"Page status: {selected_candidate.get('page_status', 'Available')}")
            st.write(f"Year: {selected_candidate.get('year', 'Unknown')}")
            st.write(f"Source method: {selected_candidate.get('method', 'Website scan')}")
            if is_irs_candidate_source(selected_candidate):
                st.warning("This looks like an IRS/Form 990-related source. Review Relationship to Source and IRS/Form Context carefully after extraction.")
            st.caption("The app ranks cleaner donor, partner, supporter, annual report, PDF, and IRS/Form 990 sources higher than generic, translated, program, recognition, newsroom, or broken pages.")
        manual_candidate_url = st.text_input(
            "Optional: paste a more specific page URL to extract from instead",
            placeholder="Example: exact individual donors, business donors, annual report, IRS/Form 990, or PDF page"
        )
        final_selected_url = manual_candidate_url.strip() if manual_candidate_url.strip() else selected_url
        st.caption("Recommended starting source")
        st.write(final_selected_url)
        st.caption("Use the dropdown above to review suggested sources. The buttons below keep the workflow simple: current/latest donors or all years found.")
        col_b, col_c = st.columns(2, gap="small")
        with col_b:
            extract_newest = st.button(
                "Extract current/latest donors",
                type="primary",
                use_container_width=True,
                help="Recommended. Uses the best current direct donor/partner pages and the newest dated sources found."
            )
        with col_c:
            extract_all = st.button(
                "Extract all years found (slower)",
                use_container_width=True,
                help="Scans current pages plus older annual reports, donor impact PDFs, IRS/Form 990 sources, and historical sources. This may take longer and use more API credits."
            )
        if extract_newest:
            try:
                run_multi_page_extraction(mode="current", manual_url=manual_candidate_url.strip())
            except requests.exceptions.HTTPError as e:
                status_code = getattr(e.response, "status_code", None)
                if status_code == 404:
                    st.error("One of the selected source pages no longer exists. Try another source or paste a direct URL.")
                elif status_code in [401, 403]:
                    st.error("One of the selected source pages blocked automated access. Try a different source or upload a PDF.")
                else:
                    st.error("One of the selected source pages could not be opened. Try another source or upload a PDF.")
                st.caption(str(e))
            except Exception as e:
                st.error(f"Something went wrong during current/latest extraction: {e}")
        if extract_all:
            try:
                run_multi_page_extraction(mode="all", manual_url=manual_candidate_url.strip())
            except Exception as e:
                st.error(f"Something went wrong during all-years extraction: {e}")

elif input_mode == "Use an exact webpage or PDF URL":
    st.divider()
    if st.button("Extract names", type="primary"):
        if not source_org:
            st.warning("Please enter the source organization name first.")
        elif not url:
            st.warning("Please paste a webpage or PDF URL.")
        else:
            try:
                with st.spinner("Extracting names from URL..."):
                    result_df, selected_source, ai_note = extract_from_source(
                        target_url=url,
                        uploaded_file=None,
                        source_org=source_org,
                        use_ai_flag=use_ai,
                        model_name=model_name,
                        max_ai_chunks=max_ai_chunks
                    )
                show_results(result_df, source_org, ai_note=ai_note)
            except requests.exceptions.HTTPError as e:
                status_code = getattr(e.response, "status_code", None)
                if status_code == 404:
                    st.error(
                        "This page no longer exists or could not be found. Try a different direct source page, "
                        "an annual report/PDF, or manual review for this organization."
                    )
                elif status_code in [401, 403]:
                    st.error(
                        "This website blocked the app from reading the page. Try uploading a PDF version, "
                        "using a different source page, or manually reviewing this site."
                    )
                else:
                    st.error(
                        "This page could not be opened. Try a different source page, upload a PDF, or manually review this site."
                    )
                st.caption(str(e))
            except Exception as e:
                st.error(f"Something went wrong: {e}")

elif input_mode == "Upload a PDF report":
    st.divider()
    if st.button("Extract names", type="primary"):
        if not source_org:
            st.warning("Please enter the source organization name first.")
        elif uploaded_file is None:
            st.warning("Please upload a PDF report.")
        else:
            try:
                with st.spinner("Extracting names from uploaded PDF..."):
                    result_df, selected_source, ai_note = extract_from_source(
                        target_url="",
                        uploaded_file=uploaded_file,
                        source_org=source_org,
                        use_ai_flag=use_ai,
                        model_name=model_name,
                        max_ai_chunks=max_ai_chunks
                    )
                show_results(result_df, source_org, ai_note=ai_note)
            except Exception as e:
                st.error(f"Something went wrong: {e}")

st.divider()
st.markdown(
    '<div class="footer-note">'
    'Note: AI improves discovery and extraction, but some websites may block automated access. '
    'For blocked websites, upload a PDF report or use manual review. Always review results before using them. '
    'For IRS/Form 990 sources, review Relationship to Source carefully because grant tables may list grantees/recipients rather than donors.'
    '</div>',
    unsafe_allow_html=True
)
