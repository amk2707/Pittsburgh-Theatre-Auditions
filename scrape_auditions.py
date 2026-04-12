"""
Pittsburgh performing arts audition scraper.

The script runs an agentic crawl loop for each source:
1) start from audition/job/casting seed URLs
2) follow same-domain links that look audition-related
3) extract audition listings from candidate content blocks

Output: auditions.json consumed by index.html
"""

from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

OUTPUT_FILE = Path(__file__).parent / "auditions.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PittsburghStageCallsBot/2.0)",
}

AUDITION_TERMS = [
    "audition",
    "auditions",
    "casting",
    "open call",
    "open audition",
    "unified",
    "callback",
    "video audition",
]

PAGE_CONTENT_SELECTOR = "main, article, .entry-content, .content, #content, body"

DATE_PATTERNS = [
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\s+\d{1,2}(?:\s*[-–]\s*\d{1,2})?(?:,\s*\d{4})?",
    r"\d{1,2}/\d{1,2}(?:/\d{2,4})?",
]

LOCATION_PATTERN = re.compile(
    r"(?:in|at)\s+([A-Z0-9][A-Za-z0-9'&,\- ]{4,80}(?:Pittsburgh|PA|Pennsylvania)[A-Za-z0-9'&,\- ]*)"
)

NOISY_TITLE_TERMS = (
    "skip to content",
    "join our e-club",
    "privacy",
    "security",
    "newsletter",
    "contact/location",
    "click here",
    "learn more",
    "home",
)


@dataclass(frozen=True)
class SourceConfig:
    company: str
    base_url: str
    source: str
    default_type: str
    seeds: tuple[str, ...]
    default_location: str = "Pittsburgh, PA"


SOURCES: tuple[SourceConfig, ...] = (
    SourceConfig(
        company="Pittsburgh CLO",
        base_url="https://www.pittsburghclo.org",
        source="pittsburghclo.org",
        default_type="musical",
        default_location="Pittsburgh, PA",
        seeds=(
            "https://www.pittsburghclo.org/about/clo-auditions/",
            "https://www.pittsburghclo.org",
        ),
    ),
    SourceConfig(
        company="Pittsburgh Musical Theater",
        base_url="https://pittsburghmusicals.com",
        source="pittsburghmusicals.com",
        default_type="musical",
        default_location="327 S Main St, Pittsburgh, PA",
        seeds=(
            "https://pittsburghmusicals.com/work/audition/",
            "https://pittsburghmusicals.com",
        ),
    ),
    SourceConfig(
        company="Pittsburgh Public Theater",
        base_url="https://ppt.org",
        source="ppt.org",
        default_type="play",
        default_location="O'Reilly Theater, Pittsburgh",
        seeds=(
            "https://ppt.org/about/work-with-us/auditions/",
            "https://ppt.org",
        ),
    ),
    SourceConfig(
        company="Prime Stage Theatre",
        base_url="https://primestage.com",
        source="primestage.com",
        default_type="play",
        default_location="840 W Saw Mill Run Blvd, Pittsburgh, PA",
        seeds=(
            "https://primestage.com/about-2/auditions/",
            "https://primestage.com",
        ),
    ),
    SourceConfig(
        company="Pittsburgh Ballet Theatre",
        base_url="https://pbt.org",
        source="pbt.org",
        default_type="ballet",
        default_location="Pittsburgh, PA",
        seeds=(
            "https://pbt.org/company-auditions/",
            "https://pbt.org",
        ),
    ),
    SourceConfig(
        company="Front Porch Theatricals",
        base_url="https://www.frontporchpgh.com",
        source="frontporchpgh.com",
        default_type="musical",
        default_location="Pittsburgh, PA",
        seeds=(
            "https://www.frontporchpgh.com/auditions",
            "https://www.frontporchpgh.com",
        ),
    ),
    SourceConfig(
        company="Pittsburgh Unifieds",
        base_url="https://www.pittsburghunifiedsauditions.com",
        source="pittsburghunifiedsauditions.com",
        default_type="open",
        default_location="Pittsburgh, PA",
        seeds=(
            "https://www.pittsburghunifiedsauditions.com/",
        ),
    ),
    SourceConfig(
        company="City Theatre",
        base_url="https://citytheatrecompany.org",
        source="citytheatrecompany.org",
        default_type="play",
        default_location="Pittsburgh, PA",
        seeds=(
            "https://citytheatrecompany.org/about/employment/",
            "https://citytheatrecompany.org",
        ),
    ),
    SourceConfig(
        company="Pittsburgh Opera",
        base_url="https://www.pittsburghopera.org",
        source="pittsburghopera.org",
        default_type="open",
        default_location="Pittsburgh, PA",
        seeds=(
            "https://www.pittsburghopera.org",
        ),
    ),
    SourceConfig(
        company="Pittsburgh Cultural Trust",
        base_url="https://trustarts.org",
        source="trustarts.org",
        default_type="variety",
        default_location="Pittsburgh, PA",
        seeds=(
            "https://trustarts.org",
        ),
    ),
)


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
        backoff_factor=1,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    scheme = parsed.scheme or "https"
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path or "/"
    normalized = urlunparse((scheme, host, path, "", "", ""))
    return normalized.rstrip("/") if path != "/" else normalized


def is_http_url(url: str) -> bool:
    return urlparse(url).scheme.lower() in {"http", "https"}


def is_same_domain(url: str, base_url: str) -> bool:
    host = urlparse(url).netloc.lower()
    base_host = urlparse(base_url).netloc.lower()
    return host == base_host or host.endswith(f".{base_host}") or base_host.endswith(f".{host}")


def looks_like_audition_text(text: str) -> bool:
    text_l = text.lower()
    return any(term in text_l for term in AUDITION_TERMS)


def is_noisy_title(title: str) -> bool:
    title_l = clean(title).lower()
    return not title_l or any(term in title_l for term in NOISY_TITLE_TERMS)


def should_follow_url(url: str) -> bool:
    lower = url.lower()
    if "{" in lower or "}" in lower:
        return False
    blocked_ext = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".pdf", ".webp", ".mp4", ".mp3", ".zip")
    if lower.endswith(blocked_ext):
        return False
    return any(
        term in lower
        for term in ["audition", "casting", "open-call", "open_audition", "unified", "performer"]
    )


def fetch_soup(session: requests.Session, url: str) -> BeautifulSoup | None:
    try:
        response = session.get(url, timeout=20)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except Exception as exc:
        print(f"    ! fetch failed {url}: {exc}")
        return None


def extract_dates(text: str) -> str:
    hits: list[str] = []
    for pattern in DATE_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            candidate = clean(match.group(0))
            if candidate and candidate not in hits:
                hits.append(candidate)
            if len(hits) >= 3:
                break
        if hits:
            break
    return ", ".join(hits) if hits else "Check website for dates"


def extract_location(text: str) -> str:
    match = LOCATION_PATTERN.search(text)
    if match:
        location = clean(match.group(1))
        return location[:90]
    if "pittsburgh" in text.lower():
        return "Pittsburgh, PA"
    return ""


def classify_type(text: str, default_type: str) -> str:
    lower = text.lower()
    if "ballet" in lower or "dance" in lower:
        return "ballet"
    if "musical" in lower:
        return "musical"
    if "play" in lower or "theatre" in lower or "theater" in lower:
        return "play"
    if "opera" in lower or "symphony" in lower:
        return "variety"
    if "open call" in lower or "unified" in lower:
        return "open"
    return default_type


def choose_title(block: Tag, fallback_title: str) -> str:
    title_el = block.select_one("h1, h2, h3, h4, strong, b")
    if title_el:
        title = clean(title_el.get_text(" ", strip=True))
        if len(title) >= 5:
            return title[:120]
    return fallback_title


def make_record(source: SourceConfig, title: str, body: str, url: str) -> dict:
    return {
        "show": title,
        "company": source.company,
        "type": classify_type(f"{title} {body}", source.default_type),
        "dates": extract_dates(body),
        "location": extract_location(body) or source.default_location,
        "details": body[:260] if body else "See source website for full audition details.",
        "url": url,
        "source": source.source,
    }


def extract_records_from_page(source: SourceConfig, page_url: str, soup: BeautifulSoup) -> list[dict]:
    records: list[dict] = []
    seen_urls: set[str] = set()
    page_title = clean((soup.title.get_text(" ", strip=True) if soup.title else "") or "Audition listing")
    main = soup.select_one(PAGE_CONTENT_SELECTOR)
    body_text = clean(main.get_text(" ", strip=True) if main else "")

    heading_el = soup.select_one("h1, h2")
    heading = clean(heading_el.get_text(" ", strip=True) if heading_el else "")
    canonical_title = heading if len(heading) >= 5 else page_title

    path_signal = clean(urlparse(page_url).path.replace("-", " ").replace("_", " "))
    url_signal = looks_like_audition_text(path_signal)
    title_signal = looks_like_audition_text(canonical_title)
    if (url_signal or title_signal) and len(canonical_title) <= 140 and not is_noisy_title(canonical_title):
        record = make_record(source, canonical_title, body_text, page_url)
        seen_urls.add(record["url"])
        records.append(record)

    if main:
        for anchor in main.select("a[href]"):
            href = clean(anchor.get("href", ""))
            if not href:
                continue
            candidate_url = normalize_url(urljoin(page_url, href))
            if not is_http_url(candidate_url):
                continue
            if not is_same_domain(candidate_url, source.base_url):
                continue

            anchor_text = clean(anchor.get_text(" ", strip=True))
            if len(anchor_text) < 6 or len(anchor_text) > 140:
                continue
            if not looks_like_audition_text(anchor_text):
                continue
            if any(noisy in anchor_text.lower() for noisy in ["email", "click here", "learn more", "newsletter"]):
                continue
            if is_noisy_title(anchor_text):
                continue
            if candidate_url in seen_urls:
                continue

            context_text = clean(anchor.parent.get_text(" ", strip=True) if anchor.parent else anchor_text)
            if not context_text or len(context_text) > 280:
                context_text = f"{anchor_text} ({source.company})"
            record = make_record(source, anchor_text[:120], context_text, candidate_url)
            seen_urls.add(record["url"])
            records.append(record)
            if len(records) >= 6:
                break

    return records


def crawl_source(session: requests.Session, source: SourceConfig) -> list[dict]:
    queue: deque[tuple[str, int]] = deque((normalize_url(seed), 0) for seed in source.seeds)
    visited: set[str] = set()
    discovered: list[dict] = []

    max_pages = 6
    max_depth = 2

    print(f"  Crawling {source.company}...")
    while queue and len(visited) < max_pages:
        url, depth = queue.popleft()
        if url in visited:
            continue
        if not is_same_domain(url, source.base_url):
            continue
        visited.add(url)

        soup = fetch_soup(session, url)
        if not soup:
            continue

        page_records = extract_records_from_page(source, url, soup)
        if page_records:
            discovered.extend(page_records)

        if depth >= max_depth:
            continue

        for anchor in soup.select("a[href]"):
            href = clean(anchor.get("href", ""))
            if not href:
                continue
            next_url = normalize_url(urljoin(url, href))
            if not is_http_url(next_url):
                continue
            link_text = clean(anchor.get_text(" ", strip=True))
            if next_url in visited:
                continue
            if not is_same_domain(next_url, source.base_url):
                continue
            if should_follow_url(next_url) or looks_like_audition_text(link_text):
                queue.append((next_url, depth + 1))

    print(f"    visited {len(visited)} page(s), found {len(discovered)} listing candidate(s)")
    return discovered


def deduplicate(records: list[dict]) -> list[dict]:
    unique: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for item in records:
        key = (
            clean(item["company"]).lower(),
            normalize_url(item["url"]),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def fallback_records() -> list[dict]:
    return [
        {
            "show": "Pittsburgh Auditions and Casting Calls",
            "company": "Regional Performing Arts",
            "type": "open",
            "dates": "Check source websites",
            "location": "Pittsburgh, PA",
            "details": "No active listings were extracted. Use the source links for the latest audition information.",
            "url": "https://www.pittsburghunifiedsauditions.com/",
            "source": "fallback",
        }
    ]


def main() -> None:
    print(f"\nPittsburgh Performing Arts Agentic Scraper — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    session = build_session()

    collected: list[dict] = []
    for source in SOURCES:
        records = crawl_source(session, source)
        collected.extend(records)

    auditions = deduplicate(collected)
    if not auditions:
        print("  ! No listings extracted; using fallback record.")
        auditions = fallback_records()

    payload = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "count": len(auditions),
        "auditions": auditions,
    }
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"\nSaved {len(auditions)} listing(s) -> {OUTPUT_FILE}\n")


if __name__ == "__main__":
    main()
