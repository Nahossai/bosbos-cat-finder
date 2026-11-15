# Project: bosbos-cat-finder (Comprehensive Shelter Scraping & Animal Discovery)

## Architecture
- **Data Ingestion (`scraper/`)**: Modular scrapers for each Calgary & area shelter adhering to a unified schema contract.
  - Existing audited scrapers: `meow_scraper.py`, `chs_scraper.py`, `cochrane_scraper.py`.
  - New shelter scrapers: `calgary_scraper.py`, `pawsitive_scraper.py`, `arf_scraper.py`, `frfa_scraper.py`, `aarcs_scraper.py`.
- **Ranking Engine (`scraper/ranker.py`)**: Parses ages, applies Bosbos candidate filters (female kittens <= 20 weeks), and computes Bosbos score (0-100) based on youth, coat/palette, and temperament traits.
- **Persistence & Export (`scraper/database.py`)**: SQLite storage (`data/bosbos.db`) tracking all scraped adoptable cats with first-seen/last-seen/status metadata, and exporting active candidates to `public/data/cats.json`.
- **Master Pipeline (`scrape_and_update.py`)**: Orchestrates parallel/sequential scraping across all shelters, deduplication, ranking, database updates, and stats reporting.
- **Frontend (`public/`)**: Single-page application (`index.html`, `app.js`, `styles.css`, `shelters.html`) dynamically displaying cats, shelter dropdowns, age/score filters, and voting.

## Code Layout
```
/home/antigravity/bosbos-cat-finder/
├── scrape_and_update.py        # Master ingestion & pipeline orchestrator
├── scraper/
│   ├── __init__.py
│   ├── base.py                 # (Optional shared utils / constants)
│   ├── meow_scraper.py         # MEOW Foundation + Regal Cat Cafe
│   ├── chs_scraper.py          # Calgary Humane Society (PetPress paginated)
│   ├── cochrane_scraper.py     # Cochrane & Area Humane Society (Webflow paginated)
│   ├── calgary_scraper.py      # City of Calgary Animal Services (24Petconnect)
│   ├── pawsitive_scraper.py    # Pawsitive Match Rescue Foundation (Wix CMS)
│   ├── arf_scraper.py          # ARF Alberta (WordPress REST API)
│   ├── frfa_scraper.py         # FRFA (WordPress & FooGallery)
│   ├── aarcs_scraper.py        # AARCS (Rescue syndication / PetPoint)
│   ├── ranker.py               # Age parsing & Bosbos scoring logic
│   └── database.py             # SQLite storage & JSON exporter
├── data/
│   └── bosbos.db               # SQLite database
├── public/
│   ├── data/
│   │   └── cats.json           # JSON export consumed by UI
│   ├── index.html              # Main web dashboard
│   ├── app.js                  # Frontend client logic
│   └── shelters.html           # Calgary shelter directory
└── tests/
    ├── test_ranker.py          # Unit tests for scoring & parsing
    ├── test_scrapers.py        # Integration tests for scrapers
    └── test_e2e_pipeline.py    # E2E pipeline integration tests
```

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Cochrane Pagination | Dynamic multi-page scraping of Webflow CMS (`?929163d6_page=1..6`) to capture 100% of cats | M1 | Survey (Explorer 1 & 2) |
| 2 | Cochrane Adoption Filter & Bio | Comprehensive "we've been adopted" detection and multi-photo/bio extraction | M1 | Survey (Explorer 2) |
| 3 | CHS PetPress Pagination | Iterative `?pg=` query handling to prevent 20-animal cutoff | M1 | Survey (Explorer 2) |
| 4 | CHS Cache-Busting & Status | Prevent stale Cloudflare/WP Engine responses (`?pg=1`) and detect "adoption in progress" | M1 | Survey (Explorer 2) |
| 5 | MEOW Regal Cat Cafe Satellite | Ingest off-site adoptable MEOW cats from Regal Cat Cafe (`regalcatcafe.com/meet-our-cats`) | M1 | Survey (Explorer 2) |
| 6 | City of Calgary Animal Services Scraper | 24Petconnect scraper (`CalgaryAdopt?at=cat`) capturing Apple Crumble and all city cats | M2 | Survey (Explorer 1 & 3) |
| 7 | Pawsitive Match Scraper | Wix CMS JSON extraction (`AdoptableCats`) capturing 42+ cats with multi-photo arrays | M2 | Survey (Explorer 1 & 3) |
| 8 | ARF Alberta Scraper | WordPress REST API (`/wp-json/wp/v2/arf_animal?animal_type=20`) parser | M3 | Survey (Explorer 1 & 3) |
| 9 | FRFA Scraper | Feline Rescue Foundation of Alberta WordPress / FooGallery scraper | M3 | Survey (Explorer 1 & 3) |
| 10 | AARCS / Aggregator Scraper | AARCS / regional PetPoint/Petfinder ingestion | M3 | Survey (Explorer 1 & 3) |
| 11 | Database Adoption Status Fix | Fix query bug in `database.py` (lines 124-127) so non-Bosbos cats are not marked adopted | M4 | Survey (Explorer 1) |
| 12 | Master Pipeline Integration | Update `scrape_and_update.py` to run all scrapers with error isolation and unified reporting | M4 | Survey (Explorer 1) |
| 13 | Frontend Shelter & Cat Sync | Verify `public/app.js` and `shelters.html` display all new shelters and their adoptable cats | M4 | Survey (Explorer 1) |
| 14 | E2E Testing Suite (Tiers 1-4) | Comprehensive opaque-box test suite for all scrapers, parsing, pipeline, and JSON output | E2E Track | Project Pattern |
| 15 | Adversarial Hardening (Tier 5) | White-box edge cases, malformed feeds, network error resilience, schema invariants | M5 | Project Pattern |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| E2E | E2E Testing Track | Requirement-driven test suite (Tiers 1-4), harness, validation | none | DONE |
| 1 | Existing Scrapers Audit & Fixes | Cochrane pagination, CHS cache/pagination/status, MEOW satellite | none | DONE |
| 2 | New Shelters - Tier 1 | City of Calgary Animal Services (24Petconnect), Pawsitive Match | none | DONE |
| 3 | New Shelters - Tier 2 | ARF Alberta, FRFA, AARCS / Aggregators | none | DONE |
| 4 | Pipeline & Storage Integration | Database adoption bug fix, `scrape_and_update.py` integration, frontend sync | M1, M2, M3 | DONE |
| 5 | E2E Verification & Hardening | Pass 100% of E2E tests + Tier 5 adversarial hardening | M4, E2E | DONE |

## Interface Contracts
### Scraper Module Contract
Every scraper module must expose:
```python
def scrape_<shelter_key>_cats() -> list[dict]:
    """
    Returns list of dicts with keys:
    - id: str (shelter_prefix + lowercase_id)
    - name: str
    - shelter: str
    - shelter_location: str
    - shelter_phone: str
    - sex: str ('Female', 'Male', 'Unknown')
    - age_str: str
    - breed: str
    - personality: str
    - image_url: str
    - images: list[str]
    - photos_count: int
    - bio: str
    - adoption_url: str
    - source_type: str
    """
```
- Must never raise an unhandled exception to caller; return `[]` or partial list on error.
- All HTTP requests must use descriptive desktop User-Agent and timeout (15-20s).
