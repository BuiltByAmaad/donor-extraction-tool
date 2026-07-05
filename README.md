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
