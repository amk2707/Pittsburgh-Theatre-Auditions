# Pittsburgh Stage Calls 🎭

Pittsburgh Stage Calls is a self-updating site that runs a **daily agentic crawl**
across major Pittsburgh performing arts organizations and publishes audition listings
to `auditions.json`, which powers the website.

## How the agentic loop works

The scraper (`scrape_auditions.py`) now runs as a crawl loop per source:

1. Start from configured seed URLs (auditions/casting/work pages).
2. Follow same-domain links that appear audition-relevant.
3. Parse candidate content blocks for audition listings.
4. Normalize and deduplicate records.
5. Write `auditions.json` for the frontend.

This approach is more resilient than scraping a single hard-coded page per company.

## Automated daily updates

Automation is in:

```
.github/workflows/scrape.yml
```

The workflow runs **daily** and:

- installs Python dependencies
- runs `python scrape_auditions.py`
- commits updated `auditions.json` when content changes

## Current source coverage

The default source list includes:

- Pittsburgh CLO
- Pittsburgh Musical Theater
- Pittsburgh Public Theater
- Prime Stage Theatre
- Pittsburgh Ballet Theatre
- Front Porch Theatricals
- Pittsburgh Unifieds
- City Theatre
- Pittsburgh Opera
- Pittsburgh Cultural Trust

## Local usage

```bash
pip install requests beautifulsoup4
python scrape_auditions.py
```

Then serve locally:

```bash
python -m http.server
```

Open `http://localhost:8000` and the site will load `auditions.json`.

## Adding more organizations

Edit the `SOURCES` tuple in `scrape_auditions.py` and add another `SourceConfig`
entry with:

- `company`
- `base_url`
- `source`
- `default_type`
- `seeds`

The crawl loop will automatically include it in daily runs.
