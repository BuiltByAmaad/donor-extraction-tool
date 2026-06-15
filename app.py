import re
import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from pypdf import PdfReader
from io import BytesIO

st.set_page_config(page_title="Donor/Funder Extraction Tool", layout="wide")

st.title("Donor/Funder Extraction Tool")
st.write(
    "Upload a nonprofit impact report PDF or paste a webpage/PDF link. "
    "The tool will extract possible donor, funder, foundation, sponsor, or supporter names into a table."
)

source_org = st.text_input("Source organization name", placeholder="Example: Climate Ride")

url = st.text_input(
    "Webpage or PDF URL",
    placeholder="Paste a donor page, annual report page, or PDF link here"
)

uploaded_file = st.file_uploader("Or upload a PDF report", type=["pdf"])


def clean_lines(text):
    return [line.strip() for line in text.split("\n") if line.strip()]


def extract_text_from_webpage(url):
    response = requests.get(
        url,
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove site navigation, scripts, buttons, and other non-content elements.
    for tag in soup([
        "script", "style", "header", "nav", "footer", "aside",
        "form", "noscript", "svg", "button"
    ]):
        tag.decompose()

    main = soup.find("main") or soup.find("article") or soup.body

    if main is None:
        return soup.get_text("\n", strip=True)

    return main.get_text("\n", strip=True)


def extract_text_from_pdf_url(url):
    response = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0"}
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


def normalize_money_dash(line):
    # Standardize long dashes in giving tiers.
    return line.replace("–", "-").replace("—", "-")


def is_donor_section_heading(line, source_org=""):
    line = normalize_money_dash(line.strip())
    lower = line.lower()

    if not line:
        return False

    # Reject paragraph/stat lines immediately.
    reject_words = [
        "donated", "surpassed", "because", "every", "we ",
        "our ", "their ", "this year", "since", "average", "funds",
        "grants", "participants", "challenge", "community", "facing",
        "amount granted", "miles traversed", "the numbers", "impact report",
        "annual report", "revenue", "expense", "financial"
    ]

    if any(word in lower for word in reject_words):
        return False

    # Exact donor/supporter list headings.
    exact_headings = [
        "donors",
        "supporters",
        "sponsors",
        "funders",
        "foundations",
        "contributors",
        "business and agency donors",
        "individuals and foundations",
        "corporate partners",
        "foundation partners",
        "institutional funders",
        "major donors",
        "annual fund donors",
        "our supporters",
        "our donors",
        "2025 annual fund donors"
    ]

    if lower in exact_headings:
        return True

    # Headings like "2025 ANNUAL FUND DONORS"
    if re.fullmatch(r"\d{4}\s+annual fund donors", lower):
        return True

    # Webpage tier headings like:
    # "Diamond Members ($20,000 and up)"
    # "Emerald Members ($10,000 - $19,999)"
    tier_words = [
        "diamond members",
        "emerald members",
        "sapphire members",
        "ruby members",
        "platinum members",
        "gold members",
        "silver members",
        "bronze members"
    ]

    if any(tier in lower for tier in tier_words):
        return True

    # Short PDF tier lines like "$150-$1,000", "$150 - $1,000", "$10,000+"
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
        "audited financials"
    ]

    return any(stop in lower for stop in stop_keywords)


def is_probable_name(line):
    line = line.strip()
    lower = line.lower()

    if not line:
        return False

    # Do not include donor-section headings as donor names.
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
        "anonymous donations", "anonymous donation"
    ]

    if len(line) < 2:
        return False

    if len(line) > 80:
        return False

    if any(word in lower for word in bad_words):
        return False

    if "@" in line:
        return False

    if lower.startswith("http"):
        return False

    # Remove pure numbers/money lines.
    if line.replace(" ", "").replace(",", "").replace(".", "").replace("$", "").isdigit():
        return False

    letters = re.findall(r"[A-Za-z]", line)
    if len(letters) < 2:
        return False

    # Avoid full sentences.
    if len(line.split()) > 7:
        return False

    # Avoid sentence endings unless likely an abbreviation/org acronym.
    if line.endswith(".") and not line.isupper():
        return False

    # Avoid spaced-out headings like "G R A N T S".
    if len(line) >= 5:
        no_spaces = line.replace(" ", "")
        if line.count(" ") >= len(no_spaces) - 1 and line.isupper():
            return False

    return True


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

    df = pd.DataFrame(rows)

    if not df.empty:
        df = df.drop_duplicates(subset=["Donor/Funder Name"])
        df = df.reset_index(drop=True)

    return df


if st.button("Extract names"):
    if not source_org:
        st.warning("Please enter the source organization name first.")
    else:
        try:
            text = ""
            source = ""

            if uploaded_file is not None:
                text = extract_text_from_uploaded_pdf(uploaded_file)
                source = "Uploaded PDF"

            elif url:
                source = url

                if url.lower().endswith(".pdf"):
                    text = extract_text_from_pdf_url(url)
                else:
                    text = extract_text_from_webpage(url)

            else:
                st.warning("Please upload a PDF or paste a URL.")
                st.stop()

            result_df = extract_possible_donors(text, source_org, source)

            if result_df.empty:
                st.warning(
                    "No clear donor/funder names were extracted. "
                    "This source may need manual review."
                )
            else:
                st.success(f"Extracted {len(result_df)} possible donor/funder names.")
                st.dataframe(result_df, use_container_width=True)

                csv = result_df.to_csv(index=False).encode("utf-8")

                st.download_button(
                    label="Download results as CSV",
                    data=csv,
                    file_name=f"{source_org.lower().replace(' ', '_')}_donors.csv",
                    mime="text/csv"
                )

        except Exception as e:
            st.error(f"Something went wrong: {e}")