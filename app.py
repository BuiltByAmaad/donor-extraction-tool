import re
import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from pypdf import PdfReader
from io import BytesIO

from page_finder import find_likely_donor_pages


st.set_page_config(
    page_title="Donor/Funder Extraction Tool",
    page_icon="🌱",
    layout="wide"
)


# -----------------------------
# Custom styling
# -----------------------------

st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

        :root {
            --bg: #060a12;
            --panel: rgba(15, 23, 42, 0.62);
            --panel-strong: rgba(15, 23, 42, 0.82);
            --border: rgba(148, 163, 184, 0.20);
            --border-strong: rgba(125, 211, 252, 0.34);
            --text: #f8fafc;
            --muted: #a8b3c7;
            --accent: #ff5f57;
            --cyan: #38bdf8;
            --green: #22c55e;
            --teal: #2dd4bf;
        }

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif;
        }

        .stApp {
            background:
                radial-gradient(circle at 8% 8%, rgba(56, 189, 248, 0.18), transparent 28%),
                radial-gradient(circle at 92% 12%, rgba(34, 197, 94, 0.14), transparent 28%),
                radial-gradient(circle at 60% 100%, rgba(45, 212, 191, 0.10), transparent 35%),
                linear-gradient(135deg, #050816 0%, #07111c 52%, #071b16 100%);
            color: var(--text);
        }

        .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
            max-width: 1480px;
        }

        header[data-testid="stHeader"] {
            background: rgba(5, 8, 22, 0.35);
            backdrop-filter: blur(18px);
            -webkit-backdrop-filter: blur(18px);
        }

        .hero-card {
            position: relative;
            overflow: hidden;
            padding: 2.4rem 2.6rem;
            border-radius: 30px;
            background:
                linear-gradient(135deg, rgba(15, 23, 42, 0.88), rgba(15, 23, 42, 0.54)),
                linear-gradient(135deg, rgba(56, 189, 248, 0.14), rgba(34, 197, 94, 0.08));
            border: 1px solid rgba(148, 163, 184, 0.24);
            box-shadow:
                0 28px 90px rgba(0, 0, 0, 0.38),
                inset 0 1px 0 rgba(255, 255, 255, 0.08);
            backdrop-filter: blur(24px) saturate(150%);
            -webkit-backdrop-filter: blur(24px) saturate(150%);
            margin-bottom: 2rem;
        }

        .hero-card::before {
            content: "";
            position: absolute;
            top: -45%;
            left: -20%;
            width: 70%;
            height: 120%;
            background: linear-gradient(
                120deg,
                transparent 0%,
                rgba(255, 255, 255, 0.10) 45%,
                transparent 70%
            );
            transform: rotate(14deg);
            animation: glassSweep 9s ease-in-out infinite;
            pointer-events: none;
        }

        @keyframes glassSweep {
            0%, 72%, 100% { transform: translateX(-35%) rotate(14deg); opacity: 0; }
            18% { opacity: 1; }
            38% { transform: translateX(150%) rotate(14deg); opacity: 0; }
        }

        .hero-title {
            position: relative;
            z-index: 1;
            font-size: clamp(2rem, 4vw, 3.35rem);
            font-weight: 900;
            letter-spacing: -0.06em;
            margin-bottom: 0.65rem;
            color: #ffffff;
            text-shadow: 0 10px 40px rgba(56, 189, 248, 0.18);
        }

        .hero-subtitle {
            position: relative;
            z-index: 1;
            font-size: 1.04rem;
            color: #cbd5e1;
            max-width: 940px;
            line-height: 1.62;
        }

        .pill-row {
            position: relative;
            z-index: 1;
            display: flex;
            gap: 0.6rem;
            flex-wrap: wrap;
            margin-top: 1.35rem;
        }

        .pill {
            border: 1px solid rgba(45, 212, 191, 0.34);
            background: rgba(20, 184, 166, 0.13);
            color: #d7fffb;
            border-radius: 999px;
            padding: 0.42rem 0.78rem;
            font-size: 0.8rem;
            font-weight: 750;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
        }

        .small-muted {
            color: var(--muted);
            font-size: 0.9rem;
            line-height: 1.48;
            margin-top: 0.3rem;
            margin-bottom: 0.35rem;
        }

        div[data-testid="stTextInput"] label,
        div[data-testid="stRadio"] label,
        div[data-testid="stFileUploader"] label,
        div[data-testid="stSelectbox"] label {
            color: #e2e8f0 !important;
            font-weight: 700 !important;
        }

        div[data-baseweb="input"] {
            border-radius: 16px;
            background: rgba(30, 41, 59, 0.70) !important;
            border: 1px solid rgba(148, 163, 184, 0.16);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.04),
                0 14px 34px rgba(0, 0, 0, 0.18);
        }

        div[data-baseweb="input"]:focus-within {
            border-color: rgba(56, 189, 248, 0.48);
            box-shadow:
                0 0 0 3px rgba(56, 189, 248, 0.10),
                0 16px 42px rgba(56, 189, 248, 0.08);
        }

        input {
            color: #f8fafc !important;
            font-weight: 560 !important;
        }

        div[data-baseweb="select"] > div {
            border-radius: 16px !important;
            background: rgba(30, 41, 59, 0.72) !important;
            border: 1px solid rgba(148, 163, 184, 0.16) !important;
        }

        div[role="radiogroup"] label {
            margin-bottom: 0.18rem;
        }

        .stButton > button {
            border-radius: 16px;
            border: 1px solid rgba(148, 163, 184, 0.20);
            font-weight: 800;
            transition: all 0.17s ease-in-out;
            padding: 0.68rem 1.05rem;
            background: rgba(15, 23, 42, 0.72);
            color: #f8fafc;
            box-shadow:
                0 12px 30px rgba(0, 0, 0, 0.20),
                inset 0 1px 0 rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
        }

        .stButton > button:hover {
            transform: translateY(-2px);
            border-color: rgba(45, 212, 191, 0.62);
            box-shadow:
                0 18px 34px rgba(20, 184, 166, 0.13),
                inset 0 1px 0 rgba(255, 255, 255, 0.08);
        }

        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #ff5f57, #ff3b52) !important;
            color: white !important;
            border: 1px solid rgba(255, 255, 255, 0.14) !important;
            box-shadow:
                0 16px 38px rgba(255, 95, 87, 0.22),
                inset 0 1px 0 rgba(255, 255, 255, 0.18);
        }

        .stButton > button[kind="primary"]:hover {
            box-shadow:
                0 22px 48px rgba(255, 95, 87, 0.32),
                inset 0 1px 0 rgba(255, 255, 255, 0.22);
        }

        div[data-testid="stMetric"] {
            background:
                linear-gradient(135deg, rgba(15, 23, 42, 0.82), rgba(15, 23, 42, 0.56));
            border: 1px solid rgba(148, 163, 184, 0.20);
            padding: 1rem;
            border-radius: 20px;
            box-shadow: 0 16px 44px rgba(0, 0, 0, 0.22);
            backdrop-filter: blur(18px);
            -webkit-backdrop-filter: blur(18px);
        }

        div[data-testid="stMetricLabel"] {
            color: #94a3b8;
            font-weight: 700;
        }

        div[data-testid="stMetricValue"] {
            color: #f8fafc;
            font-weight: 900;
        }

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
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.24);
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

        h2, h3 {
            letter-spacing: -0.035em;
            color: #f8fafc;
        }

        div[data-testid="stVerticalBlock"] {
            gap: 0.82rem;
        }
    </style>
    """,
    unsafe_allow_html=True
)


st.markdown(
    """
    <div class="hero-card">
        <div class="hero-title">Donor/Funder Extraction Tool</div>
        <div class="hero-subtitle">
            Find donor, funder, sponsor, supporter, and contributor pages from a homepage,
            then extract names into a clean reviewable table and downloadable CSV.
        </div>
        <div class="pill-row">
            <span class="pill">Homepage discovery</span>
            <span class="pill">Current-year extraction</span>
            <span class="pill">Historical donor database</span>
            <span class="pill">CSV export</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)


# -----------------------------
# App state
# -----------------------------

if "candidate_pages" not in st.session_state:
    st.session_state.candidate_pages = []

if "last_homepage_url" not in st.session_state:
    st.session_state.last_homepage_url = ""

if "last_source_org" not in st.session_state:
    st.session_state.last_source_org = ""


# -----------------------------
# Inputs
# -----------------------------

source_org = st.text_input("Source organization name", placeholder="Example: The Climate Center")

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
        '<div class="small-muted">Best for Carl’s requested workflow: paste only the organization homepage and let the tool discover likely donor pages.</div>',
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


# -----------------------------
# Text extraction helpers
# -----------------------------

def clean_lines(text):
    return [line.strip() for line in text.split("\n") if line.strip()]


@st.cache_data(show_spinner=False)
def extract_text_from_webpage(url):
    response = requests.get(
        url,
        timeout=25,
        headers={"User-Agent": "Mozilla/5.0 donor-funder-extraction-tool/1.0"}
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

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
        headers={"User-Agent": "Mozilla/5.0 donor-funder-extraction-tool/1.0"}
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


# -----------------------------
# Donor extraction logic
# -----------------------------

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
        "business-and-agency-donors",
        "business-donors",
        "agency-donors",
        "individual-donors",
        "foundation-donors",
        "corporate-donors",
        "annual-fund-donors",
        "major-donors",
        "donor-list",
        "donor-lists",
        "funders",
        "supporters",
        "sponsors",
        "contributors"
    ]

    return any(signal in lower for signal in exact_signals)


def is_donor_section_heading(line, source_org=""):
    line = normalize_money_dash(line.strip())
    lower = line.lower()

    if not line:
        return False

    reject_words = [
        "donated", "surpassed", "because", "every", "we ",
        "our ", "their ", "this year", "since", "average", "funds",
        "grants", "participants", "challenge", "community", "facing",
        "amount granted", "miles traversed", "the numbers", "impact report",
        "annual report", "revenue", "expense", "financial", "read more",
        "learn more", "click here", "webinar", "legislators", "endorsements",
        "climate-safe", "letter of support", "letters of support"
    ]

    if any(word in lower for word in reject_words):
        return False

    exact_headings = [
        "donors",
        "supporters",
        "sponsors",
        "funders",
        "foundations",
        "contributors",
        "business and agency donors",
        "individual donors",
        "individuals and foundations",
        "corporate partners",
        "foundation partners",
        "institutional funders",
        "major donors",
        "annual fund donors",
        "our supporters",
        "our donors",
        "thank you supporters",
        "thank you to our supporters",
        "thank you to our donors",
        "thank you to our funders",
        "2025 annual fund donors",
        "business donors",
        "agency donors",
        "foundation donors"
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
        "diamond members",
        "emerald members",
        "sapphire members",
        "ruby members",
        "platinum members",
        "gold members",
        "silver members",
        "bronze members",
        "visionary",
        "champion",
        "leader",
        "supporter level",
        "partner level",
        "climate leaders",
        "climate champions",
        "climate supporters"
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
        "board of directors",
        "staff",
        "leadership",
        "contact",
        "privacy policy",
        "copyright",
        "financial statements",
        "statement of activities",
        "statement of financial position",
        "expenses",
        "revenue",
        "assets",
        "liabilities",
        "from our director",
        "looking ahead",
        "financials",
        "audited financials",
        "subscribe",
        "newsletter",
        "follow us",
        "related posts",
        "recent posts",
        "read full bio",
        "meet the team"
    ]

    return any(stop in lower for stop in stop_keywords)


def looks_like_sentence(line):
    words = line.split()

    if len(words) > 7:
        return True

    sentence_words = [
        "the", "and", "but", "because", "with", "from", "this",
        "that", "these", "those", "through", "across", "during",
        "for", "into", "while", "where", "when", "have", "has",
        "will", "can", "are", "is", "was", "were"
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
        "school", "college", "club", "society", "alliance", "network",
        "energy", "motors", "carbon", "union", "coalition"
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
        "table of contents", "click", "learn more", "email", "phone",
        "address", "website", "our work", "about us", "menu", "search",
        "skip to content", "financial", "revenue", "expense", "back",
        "home", "news", "events", "careers", "login", "accessibility",
        "take action", "impact", "values", "theory of change", "people",
        "business network", "partners & advisors", "newsletter",
        "subscribe", "read more", "view all", "share", "facebook",
        "twitter", "linkedin", "instagram", "youtube", "cookie",
        "terms", "policy", "press", "blog", "because of you",
        "meaningful change", "looking ahead", "milestones", "growth",
        "what we strive for", "climate ride is", "every pedal stroke",
        "support conservation", "advance smarter", "create safe",
        "community, protecting", "the country", "annual report 2025",
        "from our director", "uniting adventure and impact",
        "growing participation", "participants", "events", "grants",
        "donated", "surpassed", "non-profits", "environmental and",
        "active transportation", "we are a community", "since our founding",
        "conservation, climate", "amount granted", "miles traversed",
        "the numbers", "facing the challenge", "what we strive for",
        "mission", "vision", "page", "report", "total", "subtotal",
        "the cause", "outreach", "advocacy", "movement", "ride bridges",
        "at the forefront", "resilience", "recognizing", "beneficiary",
        "citizen philanthropists", "california coast", "conversations",
        "personal journeys", "result", "surge", "positive",
        "anonymous donations", "anonymous donation", "all rights reserved",
        "webinar", "webinars", "letters of support", "letter of support",
        "legislators", "senator", "assemblymember", "committee", "program",
        "campaign", "policy", "policies", "coalition", "chapter",
        "initiative", "endorsement", "endorsements", "climate-safe",
        "read full bio", "full bio", "bio", "biography", "profile",
        "read bio", "view bio", "meet the team", "speaker", "speakers",
        "watch", "register", "registration", "join us", "sign up",
        "volunteer", "petition", "download", "resource", "resources"
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
        "donor",
        "donors",
        "funder",
        "funders",
        "sponsor",
        "sponsors",
        "supporter",
        "supporters",
        "contributors"
    ]

    weak_signals_to_avoid_for_fallback = [
        "thank-you",
        "gratitude",
        "partners",
        "advisors",
        "impact",
        "annual-report",
        "annual-reports"
    ]

    if any(signal in lower for signal in strong_signals):
        return True

    if any(signal in lower for signal in weak_signals_to_avoid_for_fallback):
        return False

    return False


def source_is_broad_report_page(source_url):
    lower = (source_url or "").lower()

    broad_signals = [
        "annual-report",
        "annual-reports",
        "impact-report",
        "impact-reports",
        "/impact",
        "/about/annual-report",
        "/about/impact"
    ]

    strong_signals = [
        "donor",
        "donors",
        "supporter",
        "supporters",
        "funder",
        "funders",
        "sponsor",
        "sponsors",
        "contributors"
    ]

    has_broad_signal = any(signal in lower for signal in broad_signals)
    has_strong_signal = any(signal in lower for signal in strong_signals)

    return has_broad_signal and not has_strong_signal


def extract_possible_donors(text, source_org, source_url):
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
                "Section": current_section,
                "Source URL": source_url or "Uploaded PDF"
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
                    "Section": "Possible donor/funder names - fallback scan",
                    "Source URL": source_url or "Uploaded PDF"
                })

    df = pd.DataFrame(rows)

    if not df.empty:
        df["Dedupe Key"] = df["Donor/Funder Name"].apply(normalize_name_for_dedupe)
        df = df.drop_duplicates(subset=["Dedupe Key", "Source URL"])
        df = df.drop(columns=["Dedupe Key"])
        df = df.reset_index(drop=True)

    return df


def extract_from_source(target_url, uploaded_file, source_org):
    if uploaded_file is not None:
        text = extract_text_from_uploaded_pdf(uploaded_file)
        source = "Uploaded PDF"

    elif target_url:
        source = target_url

        if target_url.lower().endswith(".pdf"):
            text = extract_text_from_pdf_url(target_url)
        else:
            text = extract_text_from_webpage(target_url)

    else:
        return None, None

    result_df = extract_possible_donors(text, source_org, source)
    return result_df, source


@st.cache_data(show_spinner=False)
def cached_find_pages(homepage_url, top_n):
    return find_likely_donor_pages(homepage_url, top_n=top_n)


def get_candidate_urls_for_extraction(mode="all"):
    candidate_urls = []

    for candidate in st.session_state.candidate_pages:
        candidate_url = candidate["url"]

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
    temp_df["Year"] = temp_df["Source URL"].apply(extract_year_from_url)
    temp_df["Dedupe Key"] = temp_df["Donor/Funder Name"].apply(normalize_name_for_dedupe)

    total_rows = len(temp_df)
    unique_names = temp_df["Dedupe Key"].nunique()
    pages_used = temp_df["Source URL"].nunique()
    years = sorted([int(year) for year in temp_df["Year"].dropna().unique()])

    st.subheader("Extraction summary")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total rows", total_rows)
    col2.metric("Unique names", unique_names)
    col3.metric("Pages used", pages_used)
    col4.metric("Years included", ", ".join(str(year) for year in years) if years else "Unknown")

    if total_rows != unique_names:
        st.info(
            "Some names may appear on multiple pages or across multiple years. "
            "The CSV keeps Source URL and Section so those appearances can be reviewed."
        )


def show_results(result_df, source_org):
    if result_df is None:
        st.warning("Please provide a valid source.")
        return

    if result_df.empty:
        st.warning(
            "No clear donor/funder names were extracted from this page. "
            "Try a more specific donor, supporter, sponsor, funder, contributor, or annual report subpage."
        )
        return

    show_extraction_summary(result_df)

    st.success(f"Extracted {len(result_df)} possible donor/funder names.")
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
            result_df, selected_source = extract_from_source(
                target_url=candidate_url,
                uploaded_file=None,
                source_org=source_org
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


# -----------------------------
# Main app actions
# -----------------------------

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
                with st.spinner("Searching the website for likely donor/funder pages..."):
                    candidates = cached_find_pages(homepage_url, top_n=10)

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

            except Exception as e:
                st.error(f"Something went wrong while finding pages: {e}")

    if st.session_state.candidate_pages:
        st.subheader("Found pages")

        candidate_options = [
            f"Score {candidate['score']}: {candidate['url']}"
            for candidate in st.session_state.candidate_pages
        ]

        selected_option = st.selectbox(
            "Choose which page to extract from",
            candidate_options,
            key="candidate_page_selectbox"
        )

        selected_index = candidate_options.index(selected_option)
        selected_candidate = st.session_state.candidate_pages[selected_index]
        selected_url = selected_candidate["url"]

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
                    result_df, selected_source = extract_from_source(
                        target_url=final_selected_url,
                        uploaded_file=None,
                        source_org=source_org
                    )

                show_results(result_df, source_org)

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
                    result_df, selected_source = extract_from_source(
                        target_url=url,
                        uploaded_file=None,
                        source_org=source_org
                    )

                show_results(result_df, source_org)

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
                    result_df, selected_source = extract_from_source(
                        target_url="",
                        uploaded_file=uploaded_file,
                        source_org=source_org
                    )

                show_results(result_df, source_org)

            except Exception as e:
                st.error(f"Something went wrong: {e}")