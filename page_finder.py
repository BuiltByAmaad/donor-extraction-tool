import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urldefrag
import xml.etree.ElementTree as ET
from urllib.robotparser import RobotFileParser


USER_AGENT = "Mozilla/5.0 donor-page-finder/3.0"

BAD_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".mp4", ".mov", ".avi", ".zip", ".css", ".js",
    ".ico", ".woff", ".woff2", ".ttf", ".mp3", ".wav"
)

BAD_URL_PARTS = [
    "/contact",
    "/privacy",
    "/terms",
    "/careers",
    "/jobs",
    "/events",
    "/event/",
    "/calendar",
    "/news/",
    "/blog/",
    "/press",
    "/staff",
    "/team",
    "/board",
    "/login",
    "/cart",
    "/donate",
    "/wp-json",
    "/feed",
    "/tag/",
    "/category/",
    "/author/",
]


VERY_STRONG_PATTERNS = [
    "business-and-agency-donors",
    "business-agency-donors",
    "individual-donors",
    "business-donors",
    "agency-donors",
    "foundation-donors",
    "corporate-donors",
    "annual-fund-donors",
    "major-donors",
    "donor-list",
    "donor-lists",
    "our-donors",
]

STRONG_KEYWORDS = {
    "donor": 45,
    "donors": 45,
    "funder": 40,
    "funders": 40,
    "supporter": 32,
    "supporters": 32,
    "sponsor": 30,
    "sponsors": 30,
    "contributor": 28,
    "contributors": 28,
}

REPORT_KEYWORDS = {
    "annual-report": 25,
    "annual-reports": 25,
    "annual report": 25,
    "annual reports": 25,
    "impact-report": 20,
    "impact-reports": 20,
    "impact report": 20,
    "impact reports": 20,
    "impact": 8,
    "report": 8,
}

WEAK_KEYWORDS = {
    "partner": 6,
    "partners": 6,
    "recognition": 10,
    "gratitude": 8,
    "thank-you": 8,
    "thank you": 8,
    "giving": 8,
}


def normalize_homepage(url):
    url = url.strip()

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def normalize_url(url):
    url, _fragment = urldefrag(url)
    return url.rstrip("/")


def get_domain(url):
    return urlparse(url).netloc.replace("www.", "").lower()


def same_domain(url, domain):
    return get_domain(url) == domain.replace("www.", "").lower()


def is_good_url(url):
    lower = url.lower()

    if any(skip in lower for skip in ["mailto:", "tel:", "javascript:"]):
        return False

    if lower.endswith(BAD_EXTENSIONS):
        return False

    if any(bad in lower for bad in BAD_URL_PARTS):
        return False

    return True


def extract_newest_year(text):
    years = re.findall(r"20\d{2}", text.lower())

    if not years:
        return 0

    return max(int(year) for year in years)


def year_bonus(text):
    newest_year = extract_newest_year(text)

    if newest_year == 0:
        return 0

    # Strongly prefer newer donor/report pages.
    # 2025 beats 2024, 2024 beats 2023, etc.
    return max(0, newest_year - 2020) * 60


def exact_donor_page_bonus(url):
    lower = url.lower()
    bonus = 0

    if "business-and-agency-donors" in lower:
        bonus += 250

    if "individual-donors" in lower:
        bonus += 240

    if "business-donors" in lower:
        bonus += 220

    if "agency-donors" in lower:
        bonus += 220

    if "foundation-donors" in lower:
        bonus += 210

    if "corporate-donors" in lower:
        bonus += 210

    if "annual-fund-donors" in lower:
        bonus += 200

    if "major-donors" in lower:
        bonus += 190

    if "donors" in lower:
        bonus += 120

    if "funders" in lower:
        bonus += 100

    if "supporters" in lower:
        bonus += 80

    if "sponsors" in lower:
        bonus += 80

    return bonus


def is_exact_donor_page(url):
    lower = url.lower()

    exact_signals = [
        "business-and-agency-donors",
        "business-agency-donors",
        "individual-donors",
        "business-donors",
        "agency-donors",
        "foundation-donors",
        "corporate-donors",
        "annual-fund-donors",
        "major-donors",
        "donor-list",
        "donor-lists",
        "our-donors",
    ]

    return any(signal in lower for signal in exact_signals)


def is_broad_landing_page(url):
    lower = url.lower()

    broad_landing = (
        lower.endswith("/about/annual-report")
        or lower.endswith("/about/annual-reports")
        or lower.endswith("/about/impact")
        or lower.endswith("/impact")
        or lower.endswith("/annual-report")
        or lower.endswith("/annual-reports")
    )

    has_strong = any(word in lower for word in [
        "donor", "donors", "funder", "funders",
        "supporter", "supporters", "sponsor", "sponsors",
        "contributors"
    ])

    return broad_landing and not has_strong


def fetch_url(url, timeout=12):
    headers = {"User-Agent": USER_AGENT}

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=(5, timeout)
        )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "").lower()

        if (
            "text/html" not in content_type
            and "xml" not in content_type
            and "text/plain" not in content_type
        ):
            return None

        return response.text

    except Exception:
        return None


def get_robot_parser(homepage):
    robots_url = urljoin(homepage, "/robots.txt")
    parser = RobotFileParser()
    parser.set_url(robots_url)

    try:
        parser.read()
        return parser
    except Exception:
        return None


def can_fetch(robot_parser, url):
    if robot_parser is None:
        return True

    try:
        return robot_parser.can_fetch(USER_AGENT, url)
    except Exception:
        return True


def get_sitemap_urls_from_robots(homepage):
    robots_url = urljoin(homepage, "/robots.txt")
    text = fetch_url(robots_url)

    if not text:
        return []

    sitemap_urls = []

    for line in text.splitlines():
        line = line.strip()

        if line.lower().startswith("sitemap:"):
            sitemap_url = line.split(":", 1)[1].strip()
            if sitemap_url:
                sitemap_urls.append(sitemap_url)

    return sitemap_urls


def parse_sitemap_xml(xml_text):
    urls = []

    try:
        root = ET.fromstring(xml_text)

        for loc in root.iter():
            if loc.tag.endswith("loc") and loc.text:
                urls.append(loc.text.strip())

    except Exception:
        return []

    return urls


def get_sitemap_urls(homepage, max_urls=3000):
    sitemap_candidates = [
        urljoin(homepage, "/sitemap.xml"),
        urljoin(homepage, "/sitemap_index.xml"),
    ]

    sitemap_candidates.extend(get_sitemap_urls_from_robots(homepage))

    all_page_urls = []
    seen_sitemaps = set()
    seen_urls = set()
    domain = get_domain(homepage)

    queue = []

    for sitemap in sitemap_candidates:
        sitemap = normalize_url(sitemap)
        if sitemap not in seen_sitemaps:
            queue.append(sitemap)
            seen_sitemaps.add(sitemap)

    while queue and len(all_page_urls) < max_urls:
        sitemap_url = queue.pop(0)
        xml_text = fetch_url(sitemap_url)

        if not xml_text:
            continue

        discovered = parse_sitemap_xml(xml_text)

        for url in discovered:
            clean_url = normalize_url(url)

            # Sitemap index support: child XML sitemaps.
            if clean_url.lower().endswith(".xml") and clean_url not in seen_sitemaps:
                queue.append(clean_url)
                seen_sitemaps.add(clean_url)
                continue

            if not same_domain(clean_url, domain):
                continue

            if not is_good_url(clean_url):
                continue

            if clean_url not in seen_urls:
                all_page_urls.append(clean_url)
                seen_urls.add(clean_url)

            if len(all_page_urls) >= max_urls:
                break

    return all_page_urls


def text_from_url(url):
    lower = url.lower()
    parsed = urlparse(lower)
    path = parsed.path.replace("/", " ").replace("-", " ").replace("_", " ")
    return path


def score_text(text):
    lower = text.lower()
    lower_hyphen = lower.replace("_", "-")
    score = 0

    for pattern in VERY_STRONG_PATTERNS:
        if pattern in lower_hyphen:
            score += 160

    for keyword, points in STRONG_KEYWORDS.items():
        if keyword in lower:
            score += points

    for keyword, points in REPORT_KEYWORDS.items():
        if keyword in lower or keyword in lower_hyphen:
            score += points

    for keyword, points in WEAK_KEYWORDS.items():
        if keyword in lower or keyword in lower_hyphen:
            score += points

    if extract_newest_year(lower):
        score += 12
        score += year_bonus(lower)

    return score


def score_url(url, link_text="", page_title="", source_page=""):
    lower = url.lower()
    combined = f"{url} {text_from_url(url)} {link_text} {page_title} {source_page}"
    score = score_text(combined)

    # Exact donor pages should beat broad annual report pages.
    if "donor" in lower and re.search(r"20\d{2}", lower):
        score += 120

    if "supporter" in lower and re.search(r"20\d{2}", lower):
        score += 70

    if "funder" in lower and re.search(r"20\d{2}", lower):
        score += 70

    if "annual-report" in lower and "donor" in lower:
        score += 100

    if "annual-reports" in lower and "donor" in lower:
        score += 100

    if "impact" in lower and "donor" in lower:
        score += 60

    score += exact_donor_page_bonus(url)

    # Prefer the newest year in the URL itself even more strongly than link/page text.
    newest_year = extract_newest_year(url)
    if newest_year:
        score += max(0, newest_year - 2020) * 100

    # Penalize broad landing pages unless they also contain donor/funder/supporter.
    if is_broad_landing_page(url):
        score -= 250

    return score


def extract_page_title_and_links(page_url, homepage, robot_parser=None, limit=350):
    if not can_fetch(robot_parser, page_url):
        return "", []

    html = fetch_url(page_url)

    if not html:
        return "", []

    soup = BeautifulSoup(html, "lxml")
    domain = get_domain(homepage)

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    links = []
    seen = set()

    # Limit keeps huge pages from being too slow.
    for tag in soup.find_all("a", href=True, limit=limit):
        href = tag.get("href")
        absolute_url = urljoin(page_url, href)
        absolute_url = normalize_url(absolute_url)

        if absolute_url in seen:
            continue

        if same_domain(absolute_url, domain) and is_good_url(absolute_url):
            link_text = tag.get_text(" ", strip=True)
            links.append({
                "url": absolute_url,
                "link_text": link_text,
                "source_page": page_url,
            })
            seen.add(absolute_url)

    return title, links


def make_candidate(url, link_text="", page_title="", source_page=""):
    url = normalize_url(url)

    return {
        "url": url,
        "score": score_url(
            url,
            link_text=link_text,
            page_title=page_title,
            source_page=source_page
        ),
        "year": extract_newest_year(url),
        "exact_bonus": exact_donor_page_bonus(url),
        "is_exact": is_exact_donor_page(url),
        "link_text": link_text,
        "source_page": source_page,
    }


def dedupe_candidates(candidates):
    best_by_url = {}

    for candidate in candidates:
        url = normalize_url(candidate["url"])

        if url not in best_by_url:
            best_by_url[url] = candidate
        else:
            old = best_by_url[url]
            if ranking_tuple(candidate) > ranking_tuple(old):
                best_by_url[url] = candidate

    return list(best_by_url.values())


def ranking_tuple(candidate):
    # This is the main fix.
    # It breaks score ties by:
    # 1. Exact donor page
    # 2. Newest year
    # 3. Exact donor-page bonus
    # 4. Overall score
    url = candidate["url"]

    return (
        1 if candidate.get("is_exact") else 0,
        candidate.get("year", 0),
        candidate.get("exact_bonus", 0),
        candidate.get("score", 0),
        -1 if is_broad_landing_page(url) else 0,
    )


def should_crawl_candidate(candidate):
    url = candidate["url"]

    if is_exact_donor_page(url):
        return True

    if is_broad_landing_page(url):
        return True

    if candidate["score"] >= 40:
        return True

    lower = url.lower()

    useful_terms = [
        "annual-report",
        "annual-reports",
        "impact",
        "donor",
        "donors",
        "funder",
        "funders",
        "supporter",
        "supporters",
        "sponsor",
        "sponsors",
        "contributors",
    ]

    return any(term in lower for term in useful_terms)


def find_likely_donor_pages(homepage_url, top_n=10):
    homepage = normalize_homepage(homepage_url)
    domain = get_domain(homepage)
    robot_parser = get_robot_parser(homepage)

    candidates = []

    # 1. Sitemap discovery.
    sitemap_urls = get_sitemap_urls(homepage, max_urls=3000)

    for url in sitemap_urls:
        candidates.append(make_candidate(url))

    # 2. Add common likely paths.
    common_paths = [
        "/donors",
        "/supporters",
        "/funders",
        "/sponsors",
        "/contributors",
        "/annual-report",
        "/annual-reports",
        "/impact",
        "/impact-report",
        "/impact-reports",
        "/about/impact",
        "/about/annual-report",
        "/about/annual-reports",
        "/about/impact/annual-reports",
    ]

    for path in common_paths:
        guessed_url = normalize_url(urljoin(homepage, path))
        if same_domain(guessed_url, domain) and is_good_url(guessed_url):
            candidates.append(make_candidate(guessed_url))

    # 3. Deep internal crawl.
    # We seed the crawl with homepage + strongest sitemap URLs.
    seed_urls = [homepage]

    scored_sitemap = sorted(
        [make_candidate(url) for url in sitemap_urls],
        key=ranking_tuple,
        reverse=True
    )

    for item in scored_sitemap[:80]:
        seed_urls.append(item["url"])

    queue = []
    seen_queue = set()

    for url in seed_urls:
        clean_url = normalize_url(url)

        if clean_url not in seen_queue and same_domain(clean_url, domain) and is_good_url(clean_url):
            queue.append({
                "url": clean_url,
                "depth": 0,
                "link_text": "",
                "source_page": "",
            })
            seen_queue.add(clean_url)

    crawled = set()
    max_pages_to_crawl = 120
    max_depth = 5

    while queue and len(crawled) < max_pages_to_crawl:
        current = queue.pop(0)
        current_url = current["url"]
        current_depth = current["depth"]

        if current_url in crawled:
            continue

        if current_depth > max_depth:
            continue

        crawled.add(current_url)

        time.sleep(0.08)

        page_title, links = extract_page_title_and_links(
            current_url,
            homepage,
            robot_parser=robot_parser,
            limit=350
        )

        current_candidate = make_candidate(
            current_url,
            link_text=current.get("link_text", ""),
            page_title=page_title,
            source_page=current.get("source_page", "")
        )

        candidates.append(current_candidate)

        link_candidates = []

        for link in links:
            linked_url = link["url"]
            link_text = link.get("link_text", "")

            candidate = make_candidate(
                linked_url,
                link_text=link_text,
                page_title=page_title,
                source_page=current_url
            )

            candidates.append(candidate)
            link_candidates.append(candidate)

        # Crawl most promising links first.
        link_candidates.sort(key=ranking_tuple, reverse=True)

        for candidate in link_candidates[:35]:
            next_url = candidate["url"]

            if next_url in seen_queue:
                continue

            if not same_domain(next_url, domain):
                continue

            if not is_good_url(next_url):
                continue

            if should_crawl_candidate(candidate):
                queue.append({
                    "url": next_url,
                    "depth": current_depth + 1,
                    "link_text": candidate.get("link_text", ""),
                    "source_page": current_url,
                })
                seen_queue.add(next_url)

    # 4. Final ranking.
    candidates = dedupe_candidates(candidates)

    # Remove very low scoring pages.
    candidates = [c for c in candidates if c["score"] > 0]

    # Main corrected ranking.
    candidates.sort(key=ranking_tuple, reverse=True)

    # Prefer exact donor pages in the output when we have them.
    exact_candidates = [c for c in candidates if c.get("is_exact")]
    other_candidates = [c for c in candidates if not c.get("is_exact")]

    final_candidates = exact_candidates + other_candidates

    clean_results = []

    for candidate in final_candidates:
        clean_results.append({
            "url": candidate["url"],
            "score": candidate["score"],
        })

    return clean_results[:top_n]