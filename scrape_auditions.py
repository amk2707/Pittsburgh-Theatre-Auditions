"""
Pittsburgh Theatre Auditions Scraper
Scrapes audition listings from major Pittsburgh theatre company websites
and outputs a JSON file consumed by index.html.

Run locally:  python scrape_auditions.py
GitHub Actions runs this on a schedule (see .github/workflows/scrape.yml)
"""

import json
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; PghTheatreBot/1.0; "
        "+https://github.com/YOUR_USERNAME/pittsburgh-auditions)"
    )
}

OUTPUT_FILE = Path(__file__).parent / "auditions.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fetch(url: str) -> BeautifulSoup | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"  ⚠  Could not fetch {url}: {e}")
        return None


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


# ---------------------------------------------------------------------------
# Per-site scrapers  (each returns a list of dicts)
# ---------------------------------------------------------------------------

def scrape_pittsburgh_clo() -> list[dict]:
    """https://www.pittsburghclo.org/about/clo-auditions/"""
    results = []
    soup = fetch("https://www.pittsburghclo.org/about/clo-auditions/")
    if not soup:
        return results

    # CLO lists auditions in article cards / content blocks
    for block in soup.select("article, .audition-item, .entry, .post"):
        title_el = block.select_one("h1,h2,h3,h4")
        if not title_el:
            continue
        title = clean(title_el.get_text())
        if not title:
            continue

        body = clean(block.get_text(" ", strip=True))
        link_el = block.select_one("a[href]")
        url = link_el["href"] if link_el else "https://www.pittsburghclo.org/about/clo-auditions/"
        if url.startswith("/"):
            url = "https://www.pittsburghclo.org" + url

        results.append({
            "show": title,
            "company": "Pittsburgh CLO",
            "type": "musical",
            "dates": extract_dates(body),
            "location": extract_location(body) or "Pittsburgh, PA",
            "details": body[:220],
            "url": url,
            "source": "pittsburghclo.org",
        })

    return results


def scrape_pittsburgh_musical_theater() -> list[dict]:
    """https://pittsburghmusicals.com/work/audition/"""
    results = []
    soup = fetch("https://pittsburghmusicals.com/work/audition/")
    if not soup:
        return results

    for block in soup.select(".audition, article, .entry-content > *"):
        title_el = block.select_one("h1,h2,h3,h4,strong")
        if not title_el:
            continue
        title = clean(title_el.get_text())
        if len(title) < 4:
            continue

        body = clean(block.get_text(" ", strip=True))
        link_el = block.select_one("a[href]")
        url = link_el["href"] if link_el else "https://pittsburghmusicals.com/work/audition/"
        if url.startswith("/"):
            url = "https://pittsburghmusicals.com" + url

        results.append({
            "show": title,
            "company": "Pittsburgh Musical Theater",
            "type": "musical",
            "dates": extract_dates(body),
            "location": extract_location(body) or "327 S Main St, Pittsburgh, PA",
            "details": body[:220],
            "url": url,
            "source": "pittsburghmusicals.com",
        })

    return results


def scrape_pittsburgh_public_theater() -> list[dict]:
    """https://ppt.org/about/work-with-us/auditions/"""
    results = []
    soup = fetch("https://ppt.org/about/work-with-us/auditions/")
    if not soup:
        return results

    for block in soup.select(".audition-item, article, .wysiwyg > p, section"):
        title_el = block.select_one("h1,h2,h3,h4,strong")
        if not title_el:
            continue
        title = clean(title_el.get_text())
        if len(title) < 4:
            continue

        body = clean(block.get_text(" ", strip=True))
        link_el = block.select_one("a[href]")
        url = link_el["href"] if link_el else "https://ppt.org/about/work-with-us/auditions/"
        if url.startswith("/"):
            url = "https://ppt.org" + url

        results.append({
            "show": title,
            "company": "Pittsburgh Public Theater",
            "type": "play",
            "dates": extract_dates(body),
            "location": extract_location(body) or "O'Reilly Theater, Pittsburgh",
            "details": body[:220],
            "url": url,
            "source": "ppt.org",
        })

    return results


def scrape_prime_stage() -> list[dict]:
    """https://primestage.com/about-2/auditions/"""
    results = []
    soup = fetch("https://primestage.com/about-2/auditions/")
    if not soup:
        return results

    content = soup.select_one(".entry-content, main, article")
    if not content:
        return results

    body = clean(content.get_text(" ", strip=True))
    if len(body) > 10:
        results.append({
            "show": "Upcoming Season Auditions",
            "company": "Prime Stage Theatre",
            "type": "play",
            "dates": extract_dates(body) or "Check website",
            "location": "840 W. Saw Mill Run Blvd, Pittsburgh, PA",
            "details": body[:220],
            "url": "https://primestage.com/about-2/auditions/",
            "source": "primestage.com",
        })

    return results


def scrape_pittsburgh_ballet() -> list[dict]:
    """https://pbt.org/company-auditions/"""
    results = []
    soup = fetch("https://pbt.org/company-auditions/")
    if not soup:
        return results

    content = soup.select_one(".entry-content, main, article, .page-content")
    if not content:
        return results

    body = clean(content.get_text(" ", strip=True))
    if len(body) > 10:
        results.append({
            "show": "Company Auditions",
            "company": "Pittsburgh Ballet Theatre",
            "type": "ballet",
            "dates": extract_dates(body) or "Check website",
            "location": "Pittsburgh, PA",
            "details": body[:220],
            "url": "https://pbt.org/company-auditions/",
            "source": "pbt.org",
        })

    return results


def scrape_front_porch() -> list[dict]:
    """https://www.frontporchpgh.com/auditions"""
    results = []
    soup = fetch("https://www.frontporchpgh.com/auditions")
    if not soup:
        return results

    content = soup.select_one("main, article, .page-content, #content")
    if not content:
        return results

    body = clean(content.get_text(" ", strip=True))
    if len(body) > 10:
        results.append({
            "show": "Season Auditions",
            "company": "Front Porch Theatricals",
            "type": "musical",
            "dates": extract_dates(body) or "Check website",
            "location": "Pittsburgh, PA",
            "details": body[:220],
            "url": "https://www.frontporchpgh.com/auditions",
            "source": "frontporchpgh.com",
        })

    return results


def scrape_pittsburgh_unifieds() -> list[dict]:
    """https://www.pittsburghunifiedsauditions.com/"""
    results = []
    soup = fetch("https://www.pittsburghunifiedsauditions.com/")
    if not soup:
        return results

    content = soup.select_one("main, #main, .content, article")
    if not content:
        return results

    body = clean(content.get_text(" ", strip=True))
    results.append({
        "show": "Pittsburgh Unifieds — Open Auditions",
        "company": "Pittsburgh Unifieds",
        "type": "open",
        "dates": extract_dates(body) or "Rolling — check website",
        "location": "Pittsburgh, PA (in-person & virtual)",
        "details": body[:220],
        "url": "https://www.pittsburghunifiedsauditions.com/",
        "source": "pittsburghunifiedsauditions.com",
    })

    return results


# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------

DATE_PATTERNS = [
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"[\s\.]+\d{1,2}(?:[–\-]\d{1,2})?(?:,?\s*\d{4})?",
    r"\d{1,2}/\d{1,2}(?:/\d{2,4})?",
]

LOCATION_KEYWORDS = [
    "theater", "theatre", "hall", "studio", "center", "centre",
    "auditorium", "stage", "building", "room", "pittsburgh",
]


def extract_dates(text: str) -> str:
    for pat in DATE_PATTERNS:
        matches = re.findall(pat, text, re.IGNORECASE)
        if matches:
            if isinstance(matches[0], tuple):
                matches = [" ".join(m) for m in matches]
            return ", ".join(dict.fromkeys(matches[:3]))
    return "Check website for dates"


def extract_location(text: str) -> str:
    sentences = re.split(r"[.\n]", text)
    for s in sentences:
        sl = s.lower()
        if any(kw in sl for kw in LOCATION_KEYWORDS):
            loc = clean(s)
            if 5 < len(loc) < 120:
                return loc
    return ""


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def deduplicate(auditions: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for a in auditions:
        key = (a["company"].lower(), a["show"].lower()[:30])
        if key not in seen:
            seen.add(key)
            out.append(a)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

SCRAPERS = [
    scrape_pittsburgh_clo,
    scrape_pittsburgh_musical_theater,
    scrape_pittsburgh_public_theater,
    scrape_prime_stage,
    scrape_pittsburgh_ballet,
    scrape_front_porch,
    scrape_pittsburgh_unifieds,
]

# Fallback data used when a site can't be scraped
FALLBACK_DATA = [
    {
        "show": "2026 Season Auditions",
        "company": "Pittsburgh CLO",
        "type": "musical",
        "dates": "Check website",
        "location": "Pittsburgh, PA",
        "details": "Visit pittsburghclo.org for the latest audition announcements.",
        "url": "https://www.pittsburghclo.org/about/clo-auditions/",
        "source": "fallback",
    },
    {
        "show": "Open Auditions",
        "company": "Pittsburgh Musical Theater",
        "type": "musical",
        "dates": "Check website",
        "location": "327 S Main St, Pittsburgh, PA",
        "details": "Visit pittsburghmusicals.com for current audition info.",
        "url": "https://pittsburghmusicals.com/work/audition/",
        "source": "fallback",
    },
    {
        "show": "Season Auditions",
        "company": "Pittsburgh Public Theater",
        "type": "play",
        "dates": "Check website",
        "location": "O'Reilly Theater, Pittsburgh",
        "details": "Visit ppt.org for current audition announcements.",
        "url": "https://ppt.org/about/work-with-us/auditions/",
        "source": "fallback",
    },
    {
        "show": "Pittsburgh Unifieds",
        "company": "Pittsburgh Unifieds",
        "type": "open",
        "dates": "Rolling — check website",
        "location": "Pittsburgh, PA",
        "details": "In-person and virtual auditions for AEA and non-AEA performers.",
        "url": "https://www.pittsburghunifiedsauditions.com/",
        "source": "fallback",
    },
]


def main():
    print(f"\n🎭  Pittsburgh Auditions Scraper — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    all_auditions = []

    for scraper in SCRAPERS:
        name = scraper.__name__.replace("scrape_", "").replace("_", " ").title()
        print(f"  Scraping {name}...")
        try:
            results = scraper()
            print(f"    → {len(results)} listing(s) found")
            all_auditions.extend(results)
        except Exception:
            print(f"    → ERROR scraping {name}:")
            traceback.print_exc()

    all_auditions = deduplicate(all_auditions)

    # If scraping yielded nothing useful, use fallback so the site isn't empty
    if not all_auditions:
        print("\n  ⚠  No results scraped — using fallback data.")
        all_auditions = FALLBACK_DATA

    payload = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "count": len(all_auditions),
        "auditions": all_auditions,
    }

    OUTPUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"\n✅  Saved {len(all_auditions)} listing(s) → {OUTPUT_FILE}\n")


if __name__ == "__main__":
    main()
