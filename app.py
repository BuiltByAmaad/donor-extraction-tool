import json
import os
import re
from io import BytesIO
from urllib.parse import urlparse

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
    page_title="Donor/Funder Extraction Tool",
    page_icon="🌱",
    layout="wide"
)


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


# ============================================================
# Styling
# ============================================================

st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

        :root {
            --bg: #050816;
            --panel: rgba(15, 23, 42, 0.68);
            --panel-strong: rgba(15, 23, 42, 0.88);
            --border: rgba(148, 163, 184, 0.22);
            --border-strong: rgba(45, 212, 191, 0.42);
            --text: #f8fafc;
            --muted: #a8b3c7;
            --accent: #ff5f57;
            --accent-2: #ff3b52;
            --cyan: #38bdf8;
            --green: #22c55e;
            --teal: #2dd4bf;
            --gold: #fbbf24;
            --purple: #a78bfa;
        }

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif;
        }

        .stApp {
            background:
                radial-gradient(circle at 8% 6%, rgba(56, 189, 248, 0.24), transparent 30%),
                radial-gradient(circle at 92% 12%, rgba(34, 197, 94, 0.18), transparent 30%),
                radial-gradient(circle at 40% 65%, rgba(167, 139, 250, 0.10), transparent 33%),
                radial-gradient(circle at 60% 105%, rgba(45, 212, 191, 0.15), transparent 38%),
                linear-gradient(135deg, #050816 0%, #07111c 52%, #071b16 100%);
            background-attachment: fixed;
            color: var(--text);
        }

        .stApp::before {
            content: "";
            position: fixed;
            inset: 0;
            pointer-events: none;
            background:
                linear-gradient(115deg, transparent 0%, rgba(255,255,255,0.025) 45%, transparent 70%),
                radial-gradient(circle at 20% 20%, rgba(56,189,248,0.10), transparent 22%);
            animation: backgroundFloat 14s ease-in-out infinite alternate;
            z-index: 0;
        }

        @keyframes backgroundFloat {
            0% { opacity: 0.45; transform: translateY(0) scale(1); }
            100% { opacity: 0.8; transform: translateY(-14px) scale(1.03); }
        }

        .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
            max-width: 1500px;
            position: relative;
            z-index: 1;
        }

        header[data-testid="stHeader"] {
            background: rgba(5, 8, 22, 0.34);
            backdrop-filter: blur(18px);
            -webkit-backdrop-filter: blur(18px);
        }

        .hero-card {
            position: relative;
            overflow: hidden;
            padding: 2.7rem 2.85rem;
            border-radius: 32px;
            background:
                linear-gradient(135deg, rgba(15, 23, 42, 0.93), rgba(15, 23, 42, 0.58)),
                linear-gradient(135deg, rgba(56, 189, 248, 0.18), rgba(34, 197, 94, 0.10));
            border: 1px solid rgba(148, 163, 184, 0.24);
            box-shadow:
                0 34px 110px rgba(0, 0, 0, 0.45),
                0 0 80px rgba(45, 212, 191, 0.08),
                inset 0 1px 0 rgba(255, 255, 255, 0.10);
            backdrop-filter: blur(26px) saturate(155%);
            -webkit-backdrop-filter: blur(26px) saturate(155%);
            margin-bottom: 1.4rem;
        }

        .hero-card::before {
            content: "";
            position: absolute;
            top: -50%;
            left: -25%;
            width: 78%;
            height: 130%;
            background: linear-gradient(
                120deg,
                transparent 0%,
                rgba(255, 255, 255, 0.16) 45%,
                transparent 70%
            );
            transform: rotate(14deg);
            animation: glassSweep 9s ease-in-out infinite;
            pointer-events: none;
        }

        .hero-card::after {
            content: "";
            position: absolute;
            inset: 0;
            background:
                radial-gradient(circle at 18% 12%, rgba(56,189,248,0.18), transparent 24%),
                radial-gradient(circle at 84% 80%, rgba(45,212,191,0.14), transparent 28%);
            pointer-events: none;
            animation: heroPulse 7s ease-in-out infinite alternate;
        }

        @keyframes glassSweep {
            0%, 72%, 100% { transform: translateX(-35%) rotate(14deg); opacity: 0; }
            18% { opacity: 1; }
            38% { transform: translateX(150%) rotate(14deg); opacity: 0; }
        }

        @keyframes heroPulse {
            from { opacity: 0.35; }
            to { opacity: 0.72; }
        }

        .hero-title {
            position: relative;
            z-index: 1;
            font-size: clamp(2.25rem, 4vw, 3.7rem);
            font-weight: 900;
            letter-spacing: -0.065em;
            margin-bottom: 0.68rem;
            color: #ffffff;
            text-shadow: 0 12px 46px rgba(56, 189, 248, 0.22);
        }

        .hero-subtitle {
            position: relative;
            z-index: 1;
            font-size: 1.06rem;
            color: #d7e2f3;
            max-width: 980px;
            line-height: 1.65;
        }

        .pill-row {
            position: relative;
            z-index: 1;
            display: flex;
            gap: 0.65rem;
            flex-wrap: wrap;
            margin-top: 1.45rem;
        }

        .pill {
            border: 1px solid rgba(45, 212, 191, 0.38);
            background: rgba(20, 184, 166, 0.16);
            color: #d7fffb;
            border-radius: 999px;
            padding: 0.46rem 0.86rem;
            font-size: 0.8rem;
            font-weight: 850;
            box-shadow:
                0 0 26px rgba(45, 212, 191, 0.08),
                inset 0 1px 0 rgba(255, 255, 255, 0.07);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
        }

        .step-card, .info-card, .ai-panel, .recommendation-card, .option-card {
            background:
                linear-gradient(135deg, rgba(15, 23, 42, 0.76), rgba(15, 23, 42, 0.46));
            border: 1px solid rgba(148, 163, 184, 0.20);
            border-radius: 22px;
            padding: 1rem 1.1rem;
            box-shadow:
                0 18px 54px rgba(0,0,0,0.24),
                inset 0 1px 0 rgba(255,255,255,0.05);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
        }

        .step-card { min-height: 122px; }

        .step-number {
            display: inline-flex;
            width: 28px;
            height: 28px;
            border-radius: 999px;
            align-items: center;
            justify-content: center;
            font-weight: 900;
            background: rgba(56, 189, 248, 0.16);
            border: 1px solid rgba(56, 189, 248, 0.38);
            color: #e0f2fe;
            margin-bottom: 0.45rem;
        }

        .step-title, .card-title {
            font-weight: 900;
            color: #f8fafc;
            margin-bottom: 0.26rem;
        }

        .step-copy, .card-copy {
            color: #a8b3c7;
            font-size: 0.91rem;
            line-height: 1.5;
        }

        .small-muted {
            color: var(--muted);
            font-size: 0.91rem;
            line-height: 1.48;
            margin-top: 0.3rem;
            margin-bottom: 0.35rem;
        }

        .ai-badge, .ai-ready-badge, .ai-off-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            border-radius: 999px;
            padding: 0.38rem 0.75rem;
            font-size: 0.78rem;
            font-weight: 900;
            margin-bottom: 0.55rem;
        }

        .ai-ready-badge {
            border: 1px solid rgba(34, 197, 94, 0.44);
            background: rgba(34, 197, 94, 0.14);
            color: #bbf7d0;
            box-shadow: 0 0 34px rgba(34,197,94,0.09);
        }

        .ai-off-badge {
            border: 1px solid rgba(251, 191, 36, 0.38);
            background: rgba(251, 191, 36, 0.13);
            color: #fde68a;
        }

        .ai-panel {
            border-color: rgba(45, 212, 191, 0.26);
            position: relative;
            overflow: hidden;
            margin-top: 0.3rem;
            margin-bottom: 0.7rem;
        }

        .ai-panel::before {
            content: "";
            position: absolute;
            inset: -1px;
            background: linear-gradient(90deg, rgba(56,189,248,0.18), rgba(45,212,191,0.08), rgba(251,191,36,0.12));
            opacity: 0.22;
            pointer-events: none;
        }

        .ai-panel > * { position: relative; z-index: 1; }

        .recommendation-card {
            border-color: rgba(251, 191, 36, 0.26);
            background:
                linear-gradient(135deg, rgba(120, 53, 15, 0.24), rgba(15, 23, 42, 0.60));
            margin-top: 0.7rem;
        }

        .mini-label {
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.72rem;
            font-weight: 900;
            color: #94a3b8;
            margin-bottom: 0.25rem;
        }

        .mini-value {
            font-size: 1.02rem;
            font-weight: 900;
            color: #f8fafc;
            margin-bottom: 0.25rem;
        }

        div[data-testid="stTextInput"] label,
        div[data-testid="stRadio"] label,
        div[data-testid="stFileUploader"] label,
        div[data-testid="stSelectbox"] label,
        div[data-testid="stCheckbox"] label {
            color: #e2e8f0 !important;
            font-weight: 780 !important;
        }

        div[data-baseweb="input"] {
            border-radius: 16px;
            background: rgba(30, 41, 59, 0.74) !important;
            border: 1px solid rgba(148, 163, 184, 0.18);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.04),
                0 14px 34px rgba(0, 0, 0, 0.18);
        }

        div[data-baseweb="input"]:focus-within {
            border-color: rgba(56, 189, 248, 0.50);
            box-shadow:
                0 0 0 3px rgba(56, 189, 248, 0.10),
                0 16px 42px rgba(56, 189, 248, 0.08);
        }

        input { color: #f8fafc !important; font-weight: 590 !important; }

        div[data-baseweb="select"] > div {
            border-radius: 16px !important;
            background: rgba(30, 41, 59, 0.74) !important;
            border: 1px solid rgba(148, 163, 184, 0.18) !important;
        }

        .stButton > button {
            border-radius: 16px;
            border: 1px solid rgba(148, 163, 184, 0.22);
            font-weight: 870;
            transition: all 0.17s ease-in-out;
            padding: 0.72rem 1.08rem;
            background: rgba(15, 23, 42, 0.78);
            color: #f8fafc;
            box-shadow:
                0 12px 30px rgba(0, 0, 0, 0.22),
                inset 0 1px 0 rgba(255, 255, 255, 0.06);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
        }

        .stButton > button:hover {
            transform: translateY(-2px);
            border-color: rgba(45, 212, 191, 0.64);
            box-shadow:
                0 18px 42px rgba(20, 184, 166, 0.15),
                inset 0 1px 0 rgba(255, 255, 255, 0.09);
        }

        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #ff6b5f, #ff3555) !important;
            color: white !important;
            border: 1px solid rgba(255, 255, 255, 0.16) !important;
            box-shadow:
                0 18px 42px rgba(255, 95, 87, 0.28),
                0 0 52px rgba(255, 59, 82, 0.12),
                inset 0 1px 0 rgba(255, 255, 255, 0.20);
        }

        div[data-testid="stMetric"] {
            background:
                linear-gradient(135deg, rgba(15, 23, 42, 0.86), rgba(15, 23, 42, 0.60));
            border: 1px solid rgba(148, 163, 184, 0.22);
            padding: 1rem;
            border-radius: 20px;
            box-shadow: 0 16px 44px rgba(0, 0, 0, 0.24);
            backdrop-filter: blur(18px);
            -webkit-backdrop-filter: blur(18px);
        }

        div[data-testid="stMetricLabel"] { color: #94a3b8; font-weight: 760; }
        div[data-testid="stMetricValue"] { color: #f8fafc; font-weight: 900; }

        div[data-testid="stAlert"] {
            border-radius: 18px;
            border: 1px solid rgba(148, 163, 184, 0.16);
            backdrop-filter: blur(14px);
            -webkit-backdrop-filter: blur(14px);
        }

        div[data-testid="stDataFrame"] {
            border-radius: 18px;
            overflow: hidden;
            border: 1px solid rgba(148, 163, 184, 0.18);
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.26);
        }

        a {
            color: #38bdf8 !important;
            text-decoration-thickness: 1px !important;
            text-underline-offset: 4px !important;
        }

        hr {
            border-color: rgba(148, 163, 184, 0.16);
            margin-top: 2rem;
            margin-bottom: 1.6rem;
        }

        h2, h3 { letter-spacing: -0.035em; color: #f8fafc; }
    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# Header
# ============================================================

st.markdown(
    """
    <div class="hero-card">
        <div class="hero-title">Donor/Funder Extraction Tool</div>
        <div class="hero-subtitle">
            Find donor, funder, sponsor, supporter, and contributor pages from a homepage,
            then extract names into a clean reviewable table and downloadable CSV.
        </div>
        <div class="pill-row">
            <span class="pill">AI-assisted discovery</span>
            <span class="pill">AI extraction</span>
            <span class="pill">PDF support</span>
            <span class="pill">Reviewable CSV export</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

with st.expander("How to use this tool", expanded=False):
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(
            """
            <div class="step-card">
                <div class="step-number">1</div>
                <div class="step-title">Enter the organization</div>
                <div class="step-copy">Type the nonprofit name. Then paste a homepage, paste a direct donor page, or upload a PDF report.</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with c2:
        st.markdown(
            """
            <div class="step-card">
                <div class="step-number">2</div>
                <div class="step-title">Let the app find or read pages</div>
                <div class="step-copy">The tool can search for likely donor/funder pages and use AI to read messy source text more intelligently.</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with c3:
        st.markdown(
            """
            <div class="step-card">
                <div class="step-number">3</div>
                <div class="step-title">Review and download</div>
                <div class="step-copy">Check the table, review confidence and notes, then download a CSV for your tracker.</div>
            </div>
            """,
            unsafe_allow_html=True
        )


# ============================================================
# Session state
# ============================================================

if "candidate_pages" not in st.session_state:
    st.session_state.candidate_pages = []

if "last_homepage_url" not in st.session_state:
    st.session_state.last_homepage_url = ""

if "last_source_org" not in st.session_state:
    st.session_state.last_source_org = ""


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
                "description": "Brief assessment of whether the page/report appears to contain donor/funder/supporter/sponsor names."
            },
            "donors": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "donor_type": {"type": "string"},
                        "section": {"type": "string"},
                        "year": {"type": "string"},
                        "confidence": {"type": "string", "enum": ["High", "Medium", "Low"]},
                        "notes": {"type": "string"}
                    },
                    "required": ["name", "donor_type", "section", "year", "confidence", "notes"]
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


def ai_extract_possible_donors(text, source_org, source_url, model_name, max_chunks=6):
    client = get_openai_client()

    if client is None:
        raise RuntimeError("OpenAI API key is missing. Add OPENAI_API_KEY in Streamlit Secrets.")

    chunks = chunk_text(text, max_chars=42000, overlap=1200, max_chunks=max_chunks)
    all_rows = []
    assessments = []

    for idx, chunk in enumerate(chunks, start=1):
        prompt = f"""
You are helping Climate Cardinals review public nonprofit donor/funder sources.

Task:
Extract donor, funder, sponsor, supporter, contributor, foundation, corporate partner, agency donor, or annual fund names from the source text.

Important rules:
- Only include names that appear to be donors/funders/sponsors/supporters/contributors.
- Do not include navigation items, menu items, staff names, board members, article paragraphs, program names, event names, social links, addresses, emails, or generic headings.
- If a line is just a tier heading, use it as the Section, but do not include it as a donor name.
- If the source does not clearly contain a donor/funder list, return an empty donors list.
- Prefer precision over quantity. It is better to return fewer clean names than many noisy names.
- Keep names exactly as written when possible.
- Use confidence:
  High = clearly a donor/funder/sponsor/supporter name.
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
                    "content": "You extract clean nonprofit donor/funder data into strict structured JSON."
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

            all_rows.append({
                "Source Organization": source_org or "Unknown organization",
                "Donor/Funder Name": name,
                "Donor Type": donor.get("donor_type", "Unknown"),
                "Section": donor.get("section", "AI-extracted donor/funder names"),
                "Year": donor.get("year", "Unknown"),
                "Confidence": donor.get("confidence", "Medium"),
                "Notes": donor.get("notes", ""),
                "Source URL": source_url or "Uploaded PDF",
                "Extraction Method": "AI-assisted"
            })

    df = pd.DataFrame(all_rows)

    if not df.empty:
        df["Dedupe Key"] = df["Donor/Funder Name"].apply(normalize_name_for_dedupe)
        df = df.drop_duplicates(subset=["Dedupe Key", "Source URL"])
        df = df.drop(columns=["Dedupe Key"])
        df = df.reset_index(drop=True)

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
- PDFs
- pages with donor tiers, corporate partners, foundations, agency donors, or individual donors

Return direct URLs where possible.
Prefer pages that are likely to contain actual donor/funder names, not broad homepage pages.
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

source_org = st.text_input("Source organization name", placeholder="Example: The Climate Center")

api_ready = has_openai_key()

# AI is now automatic when connected.
# If AI fails or is unavailable, the app still falls back to standard extraction in the background.
use_ai = api_ready

if api_ready:
    st.markdown(
        """
        <div class="ai-panel">
            <span class="ai-ready-badge">● AI is ready</span>
            <div class="card-title">Smart extraction is turned on automatically</div>
            <div class="card-copy">
                The app will use AI first to find likely donor/funder pages and clean results from messy webpages or PDFs.
                If AI is unavailable for a source, the app will quietly fall back to standard extraction so the workflow does not break.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
else:
    st.markdown(
        """
        <div class="ai-panel">
            <span class="ai-off-badge">● AI not connected in this version</span>
            <div class="card-title">Standard extraction is available as a backup</div>
            <div class="card-copy">
                This local version does not currently see an OpenAI API key. The public Streamlit app can use AI once OPENAI_API_KEY is saved in Streamlit Secrets.
                Until then, the app will still try standard extraction.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

with st.expander("Smart AI options", expanded=True):
    st.markdown(
        """
        <div class="info-card">
            <div class="card-title">What does AI do here?</div>
            <div class="card-copy">
                AI helps the app understand messy donor pages, sponsor lists, annual reports, and PDFs more intelligently than basic keyword rules.
                It can help find better source pages and return cleaner donor/funder names with confidence notes.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if api_ready:
        st.markdown(
            """
            <div class="recommendation-card">
                <div class="card-title">Recommended default</div>
                <div class="card-copy">
                    For most work, leave this on <strong>Balanced</strong> and <strong>Standard scan</strong>.
                    These settings are designed to give strong results without using more API credits than necessary.
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.info(
            "AI options are shown below, but they will only turn on once the OpenAI API key is available. "
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

    col_ai_1, col_ai_2 = st.columns(2)

    with col_ai_1:
        st.markdown(
            f"""
            <div class="option-card">
                <div class="mini-label">Selected AI quality</div>
                <div class="mini-value">{selected_model_info['label']}</div>
                <div class="card-copy">
                    {selected_model_info['short']}<br><br>
                    <strong>Cost level:</strong> {selected_model_info['cost']}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col_ai_2:
        st.markdown(
            f"""
            <div class="option-card">
                <div class="mini-label">Selected reading depth</div>
                <div class="mini-value">{selected_reading_info['label']}</div>
                <div class="card-copy">
                    {selected_reading_info['short']}<br><br>
                    <strong>Best for:</strong> {selected_reading_info['best_for']}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with st.expander("Which option should I choose?", expanded=False):
        st.write(
            "**Balanced + Standard scan** is the best choice for most donor pages, sponsor pages, and regular annual reports."
        )
        st.write(
            "**High accuracy + Deep scan** is better when a source is very messy, very long, or the first result looks incomplete."
        )
        st.write(
            "**Fast/low-cost + Quick scan** is mainly for quick testing when you only need a rough first pass."
        )

    with st.expander("What does “reading depth” mean?", expanded=False):
        st.write(
            "Reading depth controls how much of a long webpage or PDF the AI is allowed to read. "
            "A short donor page usually only needs Standard scan. A long annual report may need Deep scan because the donor list could be buried far into the document. "
            "Deeper reading can improve results, but it may take longer and use more OpenAI credits."
        )

    st.caption(
        "AI is the main extraction method when connected. Standard extraction remains in the background as a backup if AI is unavailable or returns no clean results."
    )

input_mode = st.radio(
    "Choose input method",
    [
        "Automatically find donor/funder page from homepage",
        "Paste exact webpage or PDF URL",
        "Upload PDF report"
    ]
)

homepage_url = ""
url = ""
uploaded_file = None

if input_mode == "Automatically find donor/funder page from homepage":
    st.markdown(
        '<div class="small-muted">Recommended workflow: paste only the organization homepage and let the tool discover likely donor/funder pages.</div>',
        unsafe_allow_html=True
    )
    homepage_url = st.text_input(
        "Organization homepage URL",
        placeholder="Example: https://theclimatecenter.org"
    )

elif input_mode == "Paste exact webpage or PDF URL":
    st.markdown(
        '<div class="small-muted">Use this when you already have the exact donor page, annual report page, or PDF link.</div>',
        unsafe_allow_html=True
    )
    url = st.text_input(
        "Webpage or PDF URL",
        placeholder="Paste a donor page, annual report page, or PDF link here"
    )

elif input_mode == "Upload PDF report":
    st.markdown(
        '<div class="small-muted">Use this for PDF reports saved on your computer.</div>',
        unsafe_allow_html=True
    )
    uploaded_file = st.file_uploader("Upload a PDF report", type=["pdf"])


# ============================================================
# Text extraction helpers
# ============================================================

def clean_lines(text):
    return [line.strip() for line in text.split("\n") if line.strip()]


@st.cache_data(show_spinner=False)
def extract_text_from_webpage(url):
    response = requests.get(
        url,
        timeout=25,
        headers={"User-Agent": "Mozilla/5.0 donor-funder-extraction-tool/2.0"}
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
        headers={"User-Agent": "Mozilla/5.0 donor-funder-extraction-tool/2.0"}
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


def is_exact_donor_result_page(url):
    lower = (url or "").lower()

    exact_signals = [
        "business-and-agency-donors", "business-donors", "agency-donors",
        "individual-donors", "foundation-donors", "corporate-donors",
        "annual-fund-donors", "major-donors", "donor-list", "donor-lists",
        "funders", "supporters", "sponsors", "contributors"
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
        "letters of support"
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
        "agency donors", "foundation donors"
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
        "visionary", "champion", "leader", "supporter level", "partner level",
        "climate leaders", "climate champions", "climate supporters", "climate giants",
        "climate warriors", "climate heroes", "climate defenders", "climate contributors"
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
        "related posts", "recent posts", "read full bio", "meet the team"
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
        "resource", "resources"
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
        "supporter", "supporters", "contributors"
    ]

    weak_signals_to_avoid_for_fallback = [
        "thank-you", "gratitude", "partners", "advisors", "impact",
        "annual-report", "annual-reports"
    ]

    if any(signal in lower for signal in strong_signals):
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
                    "Section": "Possible donor/funder names - fallback scan",
                    "Year": str(extract_year_from_url(source_url) or "Unknown"),
                    "Confidence": "Low",
                    "Notes": "Fallback standard scan",
                    "Source URL": source_url or "Uploaded PDF",
                    "Extraction Method": "Standard extraction"
                })

    df = pd.DataFrame(rows)

    if not df.empty:
        df["Dedupe Key"] = df["Donor/Funder Name"].apply(normalize_name_for_dedupe)
        df = df.drop_duplicates(subset=["Dedupe Key", "Source URL"])
        df = df.drop(columns=["Dedupe Key"])
        df = df.reset_index(drop=True)

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
                f"AI extraction was unavailable for this source, so the app used standard extraction instead. Details: {ai_error}"
            )

    rule_df = extract_possible_donors_rule_based(text, source_org, source)
    return rule_df, source, ai_note


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
        else:
            merged[key] = candidate

    results = list(merged.values())
    results = sorted(results, key=lambda item: item.get("score", 0), reverse=True)

    return results


def get_candidate_urls_for_extraction(mode="all"):
    candidate_urls = []

    for candidate in st.session_state.candidate_pages:
        candidate_url = candidate["url"]

        if mode in ["newest", "all"]:
            if source_is_broad_report_page(candidate_url):
                continue

            if not is_exact_donor_result_page(candidate_url):
                continue

        candidate_urls.append(candidate_url)

    candidate_urls = list(dict.fromkeys(candidate_urls))

    if mode == "newest":
        years = [extract_year_from_url(url) for url in candidate_urls]
        years = [year for year in years if year is not None]

        if years:
            newest_year = max(years)
            candidate_urls = [
                url for url in candidate_urls
                if extract_year_from_url(url) == newest_year
            ]

    return candidate_urls


def combine_and_clean_results(all_results, dedupe_across_pages=False):
    combined_df = pd.concat(all_results, ignore_index=True)

    combined_df["Dedupe Key"] = combined_df["Donor/Funder Name"].apply(normalize_name_for_dedupe)

    if dedupe_across_pages:
        combined_df = combined_df.drop_duplicates(subset=["Dedupe Key"])
    else:
        combined_df = combined_df.drop_duplicates(subset=["Dedupe Key", "Source URL"])

    combined_df = combined_df.drop(columns=["Dedupe Key"])
    combined_df = combined_df.reset_index(drop=True)

    return combined_df


def show_extraction_summary(result_df):
    if result_df is None or result_df.empty:
        return

    temp_df = result_df.copy()

    if "Year" not in temp_df.columns:
        temp_df["Year"] = temp_df["Source URL"].apply(extract_year_from_url)

    temp_df["Dedupe Key"] = temp_df["Donor/Funder Name"].apply(normalize_name_for_dedupe)

    total_rows = len(temp_df)
    unique_names = temp_df["Dedupe Key"].nunique()
    pages_used = temp_df["Source URL"].nunique()
    years = sorted([
        str(year) for year in temp_df["Year"].dropna().unique()
        if str(year).lower() not in ["unknown", "none", "nan"]
    ])

    st.subheader("Extraction summary")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total rows", total_rows)
    col2.metric("Unique names", unique_names)
    col3.metric("Pages used", pages_used)
    col4.metric("Years included", ", ".join(years[:5]) + ("..." if len(years) > 5 else "") if years else "Unknown")

    if total_rows != unique_names:
        st.info(
            "Some names may appear on multiple pages or across multiple years. "
            "The CSV keeps Source URL and Section so those appearances can be reviewed."
        )


def show_results(result_df, source_org, ai_note=""):
    if result_df is None:
        st.warning("Please provide a valid source.")
        return

    if result_df.empty:
        st.warning(
            "No clear donor/funder names were extracted from this source. "
            "Try a more specific donor, supporter, sponsor, funder, contributor, or annual report page."
        )
        return

    if ai_note:
        with st.expander("AI source assessment", expanded=False):
            st.write(ai_note)

    show_extraction_summary(result_df)

    st.success(f"Extracted {len(result_df)} possible donor/funder names.")
    st.info("Please review results before using them. AI and standard extraction can still miss names or include uncertain entries.")
    st.dataframe(result_df, use_container_width=True)

    csv = result_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        label="Download results as CSV",
        data=csv,
        file_name=f"{source_org.lower().replace(' ', '_')}_donors.csv",
        mime="text/csv"
    )


def run_multi_page_extraction(mode="all"):
    urls_to_extract = get_candidate_urls_for_extraction(mode=mode)

    if not urls_to_extract:
        st.warning(
            "No exact donor/funder pages were found for this extraction mode. "
            "Try selecting a specific page from the dropdown or pasting one into the override box."
        )
        return

    all_results = []
    label = "current-year donor pages" if mode == "newest" else "historical donor database"

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
            "Try pasting a specific donor/funder/supporter page into the manual override box."
        )
        return

    combined_df = combine_and_clean_results(
        all_results,
        dedupe_across_pages=False
    )

    show_results(combined_df, source_org)


# ============================================================
# Main app actions
# ============================================================

if input_mode == "Automatically find donor/funder page from homepage":
    st.divider()

    col1, col2 = st.columns([1, 1])

    with col1:
        find_clicked = st.button("Find likely pages", type="primary")

    with col2:
        clear_clicked = st.button("Clear found pages")

    if clear_clicked:
        st.session_state.candidate_pages = []
        st.session_state.last_homepage_url = ""
        st.session_state.last_source_org = ""
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

                with st.spinner("Scanning the website for likely donor/funder pages..."):
                    rule_candidates = cached_find_pages(homepage_url, top_n=10)

                if use_ai and has_openai_key():
                    with st.spinner("AI is checking the web for stronger donor/funder page matches..."):
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

                candidates = merge_candidate_pages(rule_candidates, ai_candidates)

                if not candidates:
                    st.warning(
                        "No likely donor/funder pages were found. "
                        "Try using the manual URL option with a direct donor, funder, annual report, or PDF link."
                    )
                    st.session_state.candidate_pages = []
                else:
                    st.session_state.candidate_pages = candidates
                    st.session_state.last_homepage_url = homepage_url
                    st.session_state.last_source_org = source_org
                    st.success(f"Found {len(candidates)} likely page(s).")

                    if ai_summary:
                        st.info(ai_summary)

            except Exception as e:
                st.error(f"Something went wrong while finding pages: {e}")

    if st.session_state.candidate_pages:
        st.subheader("Found pages")

        candidate_options = []

        for candidate in st.session_state.candidate_pages:
            label = (
                f"Score {candidate.get('score', 0)} | "
                f"{candidate.get('method', 'Found')} | "
                f"{candidate.get('title', 'Page')} | "
                f"{candidate.get('url', '')}"
            )
            candidate_options.append(label)

        selected_option = st.selectbox(
            "Choose which page to extract from",
            candidate_options,
            key="candidate_page_selectbox"
        )

        selected_index = candidate_options.index(selected_option)
        selected_candidate = st.session_state.candidate_pages[selected_index]
        selected_url = selected_candidate["url"]

        with st.expander("Why this page was suggested", expanded=False):
            st.write(selected_candidate.get("reason", "No reason provided."))
            st.write(f"Page type: {selected_candidate.get('page_type', 'Unknown')}")
            st.write(f"Year: {selected_candidate.get('year', 'Unknown')}")

        manual_candidate_url = st.text_input(
            "Optional: paste a more specific page URL to extract from instead",
            placeholder="Example: exact individual donors or business donors page"
        )

        final_selected_url = manual_candidate_url.strip() if manual_candidate_url.strip() else selected_url

        st.caption("Selected extraction page")
        st.write(final_selected_url)

        col_a, col_b, col_c = st.columns([1, 1, 1])

        with col_a:
            extract_selected = st.button("Extract selected page", type="primary")

        with col_b:
            extract_newest = st.button("Extract current-year donor pages")

        with col_c:
            extract_all = st.button("Extract historical donor database")

        if extract_selected:
            try:
                with st.spinner("Extracting names from selected page..."):
                    result_df, selected_source, ai_note = extract_from_source(
                        target_url=final_selected_url,
                        uploaded_file=None,
                        source_org=source_org,
                        use_ai_flag=use_ai,
                        model_name=model_name,
                        max_ai_chunks=max_ai_chunks
                    )

                show_results(result_df, source_org, ai_note=ai_note)

                if result_df is not None and result_df.empty:
                    st.info(
                        "Try another page from the dropdown or paste a more specific page URL. "
                        "Broad annual report, impact, and thank-you pages often do not contain the actual donor list."
                    )

            except Exception as e:
                st.error(f"Something went wrong during extraction: {e}")

        if extract_newest:
            try:
                run_multi_page_extraction(mode="newest")
            except Exception as e:
                st.error(f"Something went wrong during current-year extraction: {e}")

        if extract_all:
            try:
                run_multi_page_extraction(mode="all")
            except Exception as e:
                st.error(f"Something went wrong during historical extraction: {e}")


elif input_mode == "Paste exact webpage or PDF URL":
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
                st.error(
                    "This website blocked the app from reading the page. "
                    "Try uploading a PDF version, using a different source page, or manually reviewing this site."
                )
                st.caption(str(e))
            except Exception as e:
                st.error(f"Something went wrong: {e}")


elif input_mode == "Upload PDF report":
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

st.caption(
    "Note: AI improves discovery and extraction, but some websites may block automated access. "
    "For blocked websites, upload a PDF report or use manual review. Always review results before using them."
)
