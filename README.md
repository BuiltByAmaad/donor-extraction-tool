# Donor / Funder Extraction Tool

A Streamlit-based research tool for extracting donor, funder, foundation, and grantmaker signals from nonprofit websites, annual reports, and PDF documents.

This project was built to support nonprofit fundraising and development research by reducing the manual work required to identify potential funders from public-facing documents and web pages.

---

## Overview

Nonprofits often publish donor and funder information across scattered sources:

- annual reports
- impact reports
- donor pages
- sponsorship pages
- IRS / public filing references
- foundation acknowledgements
- partner pages
- PDF reports

Manually reviewing these sources can take significant time. This tool helps automate the first pass of that research by scanning nonprofit web pages and documents for likely donor, funder, and foundation names.

The goal is not to replace human review, but to make funder research faster, more structured, and easier to verify.

---

## What the Tool Does

The Donor / Funder Extraction Tool helps users:

- search nonprofit websites for likely donor or funder pages
- extract donor and funder names from web page text
- process annual report PDFs and other public documents
- surface likely foundations, organizations, sponsors, and grantmakers
- label results with source context
- support faster nonprofit development and fundraising research

---

## Why This Matters

Fundraising research is often repetitive and time-consuming. Development teams may need to inspect dozens of websites, reports, and filings to understand who funds similar organizations.

This tool helps by creating a faster research workflow:

1. Start with a nonprofit website or document.
2. Scan likely donor/funder-related sources.
3. Extract candidate names.
4. Review and verify the results manually.
5. Use the findings to support outreach, research, or funder mapping.

This is especially useful for small nonprofit teams that do not have large research departments or expensive prospecting tools.

---

## Current Status

This is a working prototype.

It is designed for internal research workflows and exploratory funder discovery. Results should be reviewed by a human before being used for outreach, reporting, or decision-making.

The tool may produce false positives or miss some funders depending on page structure, PDF formatting, naming conventions, and how the source document is written.

---

## Tech Stack

- **Python**
- **Streamlit** for the user interface
- **BeautifulSoup** for parsing web pages
- **Requests** for fetching web content
- **pandas** for organizing extracted results
- **pypdf** for reading PDF documents
- **OpenAI API** for language-model-assisted extraction and classification workflows
- **Pillow** for image/logo handling and interface assets

---

## Repository Structure

```text
donor-extraction-tool/
├── app.py                 # Main Streamlit application
├── page_finder.py          # Helper logic for finding likely donor/funder pages
├── test_page_finder.py     # Basic tests for page-finding logic
├── requirements.txt        # Python dependencies
├── assets/                 # Logo and visual assets
└── .streamlit/             # Streamlit configuration
```

---

## Main Files

### `app.py`

The main Streamlit application. This file contains the primary user interface and extraction workflow.

It handles:

- user inputs
- source selection
- PDF or webpage processing
- extraction display
- result organization
- interface branding

### `page_finder.py`

Helper module for finding likely donor, funder, sponsor, annual report, or giving-related pages from a nonprofit website.

This helps users avoid manually hunting through a website for the most relevant pages.

### `requirements.txt`

Contains the dependencies needed to run the tool locally.

---

## Installation

Clone the repository:

```bash
git clone https://github.com/BuiltByAmaad/donor-extraction-tool.git
cd donor-extraction-tool
```

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Environment Variables

This project may require an OpenAI API key for model-assisted extraction features.

Create a `.env` file or configure Streamlit secrets depending on your setup.

Example `.env` format:

```bash
OPENAI_API_KEY=your_api_key_here
```

Do not commit API keys or secrets to GitHub.

If using Streamlit secrets, configure them in:

```text
.streamlit/secrets.toml
```

Example:

```toml
OPENAI_API_KEY = "your_api_key_here"
```

---

## Running the App

Run the Streamlit app locally:

```bash
streamlit run app.py
```

Then open the local Streamlit URL shown in the terminal, usually:

```text
http://localhost:8501
```

---

## Basic Workflow

A typical workflow looks like this:

1. Enter a nonprofit website or provide a relevant report.
2. Let the tool identify likely donor, funder, sponsor, or annual-report pages.
3. Extract candidate funder names from the selected sources.
4. Review source labels and context.
5. Verify useful results manually against the original sources.

---

## Example Use Cases

This tool can support:

- nonprofit funder research
- donor prospecting
- grantmaker discovery
- annual report analysis
- sponsor mapping
- climate nonprofit fundraising research
- development team workflows
- research on similar organizations’ funding ecosystems

---

## Limitations

This is a prototype and has several limitations:

- It may confuse grantees, partners, sponsors, and funders depending on context.
- PDF extraction quality depends on how the PDF was created.
- Some annual reports are image-based or poorly structured, which can reduce accuracy.
- Website structures vary widely.
- Some donor lists may be hidden behind interactive elements or inaccessible pages.
- The tool may produce false positives.
- Human review is still required before using results in outreach or reporting.
- It does not guarantee a complete list of donors or funders.

---

## Human-in-the-Loop Design

This tool is intended to assist research, not fully automate judgment.

The safest workflow is:

```text
Tool extracts candidates → Human reviews sources → Human verifies names → Researcher decides what to use
```

This keeps the system useful while reducing the risk of incorrect funder identification.

---

## What I Built

I built this tool to explore how lightweight automation and AI-assisted workflows can support nonprofit fundraising research.

My work included:

- building the Streamlit interface
- developing donor/funder extraction workflows
- creating page-finding logic for likely donor and annual report pages
- integrating PDF and webpage processing
- organizing extracted results into a usable research workflow
- improving source labeling and usability
- applying Climate Cardinals-style branding and accessibility improvements

---

## Design Goals

The tool was designed to be:

- simple enough for non-technical users
- useful for fast first-pass research
- transparent about sources
- easy to run locally
- adaptable to different nonprofit websites
- supportive of human review instead of replacing it

---

## Future Improvements

Potential next steps include:

- improved funder vs. grantee classification
- confidence scoring for extracted names
- better PDF table extraction
- export to CSV or Google Sheets
- duplicate detection and entity normalization
- improved source citations
- support for IRS Form 990 workflows
- cleaner modular code structure
- stronger automated tests
- deployment as a hosted internal tool

---

## Screenshots

Screenshots or a short demo video should be added here.

Suggested screenshots:

1. Home/input screen
2. Donor/funder page discovery results
3. Extracted funder names with source context
4. Export or review workflow

```text
TODO: Add screenshots or a short Loom demo.
```

---

## Important Note

This project is a research and workflow prototype. It should not be used as the sole source of truth for donor, funder, or grantmaker identification.

All extracted results should be verified against the original source material.

---

## Author

Built by **Amaad Zaidi**

- GitHub: [BuiltByAmaad](https://github.com/BuiltByAmaad)
- LinkedIn: [Amaad Zaidi](https://www.linkedin.com/in/amaadzaidi)

---

## License

No license has been added yet.

If this project is intended to be open source, an appropriate license should be added before reuse or redistribution.
