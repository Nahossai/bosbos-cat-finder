# Test Infrastructure & Test Design Specification
**Project**: `bosbos-cat-finder` (Comprehensive Calgary Shelter Scraping & Animal Discovery)  
**Document**: `TEST_INFRA.md`  
**Author**: E2E Test Writer  
**Target Runner**: `/home/antigravity/.venv/bin/python -m unittest tests/test_e2e_pipeline.py`  

---

## 1. Overview & Architectural Testing Strategy

`bosbos-cat-finder` aggregates adoptable cats across Calgary & area humane societies, municipal shelters, and private rescues to identify and rank candidate kittens for "Bosbos" (female, $\le 20$ weeks, bright/white/cream color palette, cute personality traits), while preserving all adoptable shelter animals in storage and presenting an accurate, deduplicated catalog.

The test infrastructure employs **requirement-driven opaque-box testing** structured across four progressively rigorous tiers:
- **Tier 1: Feature Coverage & Interface Contracts** — Validates adherence to the Standard Cat Record schema across all 8 shelter scraper modules (CHS, Cochrane, MEOW, Calgary Animal Services, Pawsitive Match, ARF, FRFA, AARCS), the Bosbos ranker engine, and the SQLite persistence/export layer.
- **Tier 2: Boundary & Corner Cases** — Exercises edge conditions including age boundaries (0 to 20.5 weeks), empty/missing fields, malformed ages, extreme ages, non-female gender exclusion, missing images, and date parsing failures.
- **Tier 3: Cross-Feature Interactions** — Verifies multi-stage pipeline flow: Raw Scraper Extraction $\to$ Ranker Filtering & Scoring $\to$ SQLite Persistence $\to$ `public/data/cats.json` Export.
- **Tier 4: Real-World Scenarios** — End-to-end multi-shelter ingestion simulations verifying candidate ranking prioritization, adoption lifecycle transitions, and shelter data preservation.

---

## 2. Testing Methodologies & Test Design Techniques

### 2.1 Category-Partition Method (TSL)
Each functional component is partitioned into operational parameters, environmental variables, and discrete choice classes:

| Component | Parameter / Category | Choices / Partitions |
| :--- | :--- | :--- |
| **Scraper Ingestion** | Network Response Status | 200 OK, 403 Forbidden, 404 Not Found, 500 Server Error, Timeout |
| | Payload Content | Valid HTML/JSON, Empty body, Malformed markup, Missing container classes |
| | Listing Status | Active adoptable, "I've Been Adopted", Foster care, Pending adoption |
| | Image Availability | Single image, Multi-image carousel ($\ge 2$), Zero images, Malformed image URL |
| **Ranker Filtering** | Sex | `"Female"`, `"F"`, `"Male"`, `"M"`, `"Unknown"`, `""`, None, Case variations (`"female"`, `"FEMALE"`) |
| | Age Representation | Weeks (`"8 weeks"`), Months (`"2 Months"`), Compound (`"4 months 3 days"`), Years (`"1 year 2 months"`), Textual (`"Adult"`, `"Kitten"`), Malformed |
| | Age Threshold | $\le 9.0$ wks, $9.1-12.0$ wks, $12.1-15.0$ wks, $15.1-18.0$ wks, $18.1-20.5$ wks, $>20.5$ wks |
| **Ranker Scoring** | Coat / Palette | Bright White / Cream / Point (40 pts), Pastel / Calico / Accent (30 pts), Standard (10 pts) |
| | Personality / Bio | Cute traits detected ($10 + 2 \times \text{tags}$, max 20 pts), Zero cute traits (10 pts) |
| **Database & Export**| Existing Record Status | New animal (`first_seen = now`, `is_new_today = 1`), Existing animal (`is_new_today = 0`) |
| | Adoption State | Retained in current scrape (`active`), Missing from current scrape (`adopted`) |
| | JSON File Invariant | Valid JSON syntax, ISO-8601 timestamps, sorted by `bosbos_score DESC, age_weeks ASC` |

### 2.2 Boundary Value Analysis (BVA)
Precise boundaries targeted for numeric and structural parameters:

- **Age Boundaries (Weeks)**:
  - Minimum: `0.0` weeks (newborn), `0.1` weeks.
  - Youth Tier 1: `9.0` weeks (40 points) vs `9.1` weeks (36 points).
  - Youth Tier 2: `12.0` weeks (36 points) vs `12.1` weeks (30 points).
  - Youth Tier 3: `15.0` weeks (30 points) vs `15.1` weeks (25 points).
  - Youth Tier 4: `18.0` weeks (25 points) vs `18.1` weeks (20 points).
  - Hard Filter Cutoff: `20.5` weeks (`is_match = True`) vs `20.6` weeks (`is_match = False`, Older than 20 weeks).
  - Adult Ceiling: `52.0` weeks (1 year $\to$ `999.0`), `104.0` weeks.
- **Score Boundaries**:
  - Minimum possible score for match: $20 \text{ (youth)} + 10 \text{ (color)} + 10 \text{ (cute)} = 40$.
  - Maximum possible score for match: $40 \text{ (youth)} + 40 \text{ (white)} + 20 \text{ (cute)} = 100$.
- **Image Count Boundaries**:
  - `0` images $\to$ fallback to empty list and empty string `image_url = ""`.
  - `1` image $\to$ `image_url == images[0]`, `photos_count == 1`.
  - `N > 1` images $\to$ `image_url == images[0]`, `photos_count == N`.

### 2.3 Pairwise Combinatorial Test Matrix
Combinatorial interactions between Sex, Age, Color, and Cute Traits:

| Test Case ID | Sex | Age Group | Color Palette | Cute Traits | Expected Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TC-COMB-01** | Female | 8 wks ($\le 9$) | Pure White (40) | 5+ traits (20) | Match = True, Score = 100 |
| **TC-COMB-02** | Female | 11 wks (10-12) | Flame Point (40) | 2 traits (14) | Match = True, Score = 90 |
| **TC-COMB-03** | Female | 14 wks (13-15) | Calico / Pastel (30) | 0 traits (10) | Match = True, Score = 70 |
| **TC-COMB-04** | Female | 17 wks (16-18) | Brown Tabby (10) | 3 traits (16) | Match = True, Score = 51 |
| **TC-COMB-05** | Female | 20 wks (19-20.5) | Cream (40) | 1 trait (12) | Match = True, Score = 72 |
| **TC-COMB-06** | Female | 21 wks (> 20.5) | Snow White (40) | 5 traits (20) | Match = False (Older than 20 wks) |
| **TC-COMB-07** | Male | 8 wks ($\le 9$) | Pure White (40) | 5 traits (20) | Match = False (Not female) |
| **TC-COMB-08** | Unknown | 8 wks ($\le 9$) | Ivory (40) | 5 traits (20) | Match = False (Not female) |
| **TC-COMB-09** | Female | Adult / 2 yrs | Lilac Point (40) | 5 traits (20) | Match = False (Older than 20 wks) |
| **TC-COMB-10** | Female | Unparseable ("?") | Standard (10) | 0 traits (10) | Match = False (Unparseable age) |
| **TC-COMB-11** | Female | "Kitten" (implicit) | White (40) | 2 traits (14) | Match = True (Default 12 wks $\to$ Score 90) |

---

## 3. Standard Cat Record Schema Contract

Every scraper module must produce a list of dictionaries strictly adhering to the schema below:

```python
STANDARD_CAT_RECORD_SCHEMA = {
    "id": str,               # Required: Non-empty, lowercase shelter prefix (e.g. 'chs_123', 'calgary_a0963248')
    "name": str,             # Required: Non-empty string
    "shelter": str,          # Required: Standardized shelter name
    "shelter_location": str, # Optional/Recommended: City / Street address
    "shelter_phone": str,    # Optional: Contact phone number
    "sex": str,              # Required: 'Female', 'Male', or 'Unknown'
    "age_str": str,          # Required: Raw or formatted age text
    "breed": str,            # Optional/Recommended: Breed name
    "personality": str,      # Optional: Behavioral / adoption status
    "image_url": str,        # Required: Primary photo URL or empty string
    "images": list,          # Required: list of URL strings
    "photos_count": int,     # Required: len(images)
    "bio": str,              # Optional/Recommended: Bio description
    "adoption_url": str,     # Required: Valid HTTP/HTTPS adoption link
    "source_type": str       # Optional/Recommended: Shelter type classification
}
```

### Safety & Resilience Invariant
- Scrapers must never raise uncaught exceptions to the orchestrator; if network fails or parsing errors occur, the scraper must catch the error, log it, and return `[]` or partial valid records.

---

## 4. Test Suite Structure (`tests/test_e2e_pipeline.py`)

The test suite is organized into modular `TestCase` classes:

1. **`TestTier1ScraperContracts`**:
   - Tests contract validation on all 8 shelter scraper identifiers:
     - `chs_scraper` (Calgary Humane Society)
     - `cochrane_scraper` (Cochrane & Area Humane Society)
     - `meow_scraper` (MEOW Foundation)
     - `calgary_scraper` (City of Calgary Animal Services)
     - `pawsitive_scraper` (Pawsitive Match Rescue Foundation)
     - `arf_scraper` (Animal Rescue Foundation Alberta)
     - `frfa_scraper` (Feline Rescue Foundation of Alberta)
     - `aarcs_scraper` (AARCS / Aggregators)
   - Verifies that available modules export `scrape_<key>_cats()` callable returning `list[dict]`.
   - Uses `unittest.skipIf` for progressive testability on shelters planned for future milestones.
   - Rigorously validates mock shelter payloads against the Standard Schema Contract.

2. **`TestTier1RankerAndDatabaseContracts`**:
   - Tests `parse_age_to_weeks()` against explicit time units (weeks, months, days, years, compound, implicit kitten).
   - Tests `calculate_bosbos_score()` return contract (`is_match`, `score`, `age_weeks`, `color_category`, `cute_tags`, `score_breakdown`).
   - Tests `init_db()` and `save_and_update_cats()` persistence invariants in temporary SQLite databases.

3. **`TestTier2BoundaryAndCornerCases`**:
   - Tests age boundary step-downs: $\le 9$ (40), $\le 12$ (36), $\le 15$ (30), $\le 18$ (25), $\le 20.5$ (20), $> 20.5$ (0/excluded).
   - Tests gender boundaries: missing sex, empty sex, whitespace, `female` (lowercase), `FEMALE` (uppercase), `F`, `male`, `neutered male`, `spayed female`.
   - Tests missing attributes: `None` bio, empty string bio, missing images, empty array images.
   - Tests malformed age strings: gibberish text, negative values, extreme large numbers.
   - Tests adopted text detection: "I've Been Adopted", "adopted! 🥳", "status: adopted".

4. **`TestTier3CrossFeatureInteractions`**:
   - Tests the complete data pipeline with isolated mock sources:
     - Synthetic multi-shelter scrape output $\to$ Ranker execution $\to$ Database persistence $\to$ `cats.json` generation.
   - Validates JSON output formatting, key structures, candidate ordering, and timestamp adherence.
   - Validates that non-matching cats are excluded from `cats.json` while matching candidates are ordered strictly by score descending, then age ascending.

5. **`TestTier4RealWorldScenarios`**:
   - Multi-shelter ingestion simulation featuring live-like payloads from MEOW, CHS, Cochrane, Calgary Animal Services (Apple Crumble), Pawsitive Match, ARF, FRFA, and AARCS.
   - Tests pipeline idempotency: running the pipeline twice with identical data preserves `first_seen` timestamps and maintains correct `is_new_today` flags.
   - Tests adoption lifecycle: when an active cat disappears from a shelter's feed in a subsequent run, it transitions to `status = 'adopted'`.
   - Tests shelter isolation: a failure in one shelter must not corrupt or wipe candidates from other shelters.

---

## 5. Test Runner & Verification Command

To execute the test suite:
```bash
/home/antigravity/.venv/bin/python -m unittest tests/test_e2e_pipeline.py -v
```

All tests are designed to be fast ($< 2$ seconds total), deterministic, independent, and free of live network side effects.
