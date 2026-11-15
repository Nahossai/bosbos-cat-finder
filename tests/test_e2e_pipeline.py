"""
End-to-End Pipeline & Integration Test Suite for bosbos-cat-finder.

Tiers:
- Tier 1: Feature coverage for every shelter scraper module contract, ranker, and database.
- Tier 2: Boundary & Corner Cases (age thresholds, sex filters, malformed data, empty fields).
- Tier 3: Cross-Feature Interactions (Scraper -> Ranker -> DB -> JSON export).
- Tier 4: Real-World Scenarios (multi-shelter execution, candidate prioritization, adoption lifecycle, idempotency).
"""

import unittest
from unittest.mock import patch, MagicMock
import tempfile
import os
import json
import sqlite3
import importlib
import requests

from scraper.ranker import parse_age_to_weeks, calculate_bosbos_score
from scraper.database import init_db, save_and_update_cats

# Schema definition for all scraper outputs
REQUIRED_CAT_FIELDS = {
    "id": str,
    "name": str,
    "shelter": str,
    "sex": str,
    "age_str": str,
    "image_url": str,
    "images": list,
    "photos_count": int,
    "adoption_url": str,
}

RECOMMENDED_CAT_FIELDS = {
    "shelter_location": str,
    "shelter_phone": str,
    "breed": str,
    "personality": str,
    "bio": str,
    "source_type": str,
}

ALL_SHELTER_SPECS = [
    ("chs", "scraper.chs_scraper", "scrape_chs_cats", "Calgary Humane Society"),
    ("cochrane", "scraper.cochrane_scraper", "scrape_cochrane_cats", "Cochrane & Area Humane Society"),
    ("meow", "scraper.meow_scraper", "scrape_meow_cats", "MEOW Foundation"),
    ("calgary", "scraper.calgary_scraper", "scrape_calgary_cats", "City of Calgary Animal Services"),
    ("pawsitive", "scraper.pawsitive_scraper", "scrape_pawsitive_cats", "Pawsitive Match Rescue Foundation"),
    ("arf", "scraper.arf_scraper", "scrape_arf_cats", "Animal Rescue Foundation (ARF)"),
    ("frfa", "scraper.frfa_scraper", "scrape_frfa_cats", "Feline Rescue Foundation of Alberta"),
    ("aarcs", "scraper.aarcs_scraper", "scrape_aarcs_cats", "AARCS"),
]


def validate_cat_record_contract(test_case: unittest.TestCase, cat: dict):
    """Validates that a cat dictionary adheres strictly to the Standard Cat Record schema."""
    test_case.assertIsInstance(cat, dict, "Cat record must be a dict")
    for field, expected_type in REQUIRED_CAT_FIELDS.items():
        test_case.assertIn(field, cat, f"Missing required field: '{field}' in cat record: {cat}")
        test_case.assertIsInstance(
            cat[field],
            expected_type,
            f"Field '{field}' should be of type {expected_type.__name__}, got {type(cat[field]).__name__}"
        )
        if expected_type == str and field in ["id", "name", "shelter", "adoption_url"]:
            test_case.assertTrue(len(cat[field].strip()) > 0, f"Field '{field}' must not be empty string")

    # Invariants
    test_case.assertIn(cat["sex"], ["Female", "Male", "Unknown"], f"Invalid sex: {cat['sex']}")
    test_case.assertEqual(
        cat["photos_count"],
        len(cat["images"]),
        f"photos_count ({cat['photos_count']}) must match len(images) ({len(cat['images'])})"
    )
    if cat["images"]:
        test_case.assertEqual(cat["image_url"], cat["images"][0], "image_url should match images[0] when images exist")
    else:
        test_case.assertEqual(cat["image_url"], "", "image_url should be empty string when images is empty")

    test_case.assertTrue(
        cat["id"].islower() or "_" in cat["id"],
        f"Cat id '{cat['id']}' should be standardized lowercase with prefix"
    )


# ==============================================================================
# Tier 1: Feature Coverage & Interface Contracts
# ==============================================================================

class TestTier1ScraperContracts(unittest.TestCase):
    """Verifies that all 8 shelter scraper contracts conform to specification."""

    def test_standard_contract_validator_with_synthetic_shelter_records(self):
        """Tests that synthetic conforming records for all 8 shelters pass contract validation."""
        sample_shelter_records = [
            {
                "id": "chs_12345",
                "name": "Kepler",
                "shelter": "Calgary Humane Society",
                "shelter_location": "Calgary, AB (4455 110 Ave SE)",
                "shelter_phone": "(403) 205-4455",
                "sex": "Female",
                "age_str": "12 weeks",
                "breed": "Domestic Shorthair",
                "personality": "Available for Adoption",
                "image_url": "https://example.com/chs1.jpg",
                "images": ["https://example.com/chs1.jpg", "https://example.com/chs2.jpg"],
                "photos_count": 2,
                "bio": "Sweet kitten",
                "adoption_url": "https://calgaryhumane.ca/adopt/cats/?id=12345",
                "source_type": "Humane Society Shelter"
            },
            {
                "id": "cochrane_shorty",
                "name": "Shorty",
                "shelter": "Cochrane & Area Humane Society",
                "shelter_location": "Cochrane, AB",
                "shelter_phone": "(403) 932-2072",
                "sex": "Female",
                "age_str": "3 Months",
                "breed": "Domestic Shorthair",
                "personality": "Available for Adoption",
                "image_url": "https://example.com/cochrane.jpg",
                "images": ["https://example.com/cochrane.jpg"],
                "photos_count": 1,
                "bio": "Playful and cuddly",
                "adoption_url": "https://cochranehumane.ca/adopt/shorty",
                "source_type": "Humane Society"
            },
            {
                "id": "meow_14645",
                "name": "Snowdrop",
                "shelter": "MEOW Foundation",
                "shelter_location": "Calgary, AB",
                "shelter_phone": "(403) 230-6033",
                "sex": "Female",
                "age_str": "9 weeks",
                "breed": "Domestic Shorthair / Rescue Mix",
                "personality": "Affectionate",
                "image_url": "https://example.com/snowdrop.jpg",
                "images": ["https://example.com/snowdrop.jpg"],
                "photos_count": 1,
                "bio": "Loves purring and cuddling",
                "adoption_url": "https://meowfoundation.com/adoptable-cats/",
                "source_type": "Cat-Only Rescue Shelter"
            },
            {
                "id": "calgary_a0963248",
                "name": "Apple Crumble",
                "shelter": "City of Calgary Animal Services",
                "shelter_location": "Calgary, AB (2201 Portland St SE)",
                "shelter_phone": "(403) 268-2489",
                "sex": "Female",
                "age_str": "15 weeks old",
                "breed": "Domestic Shorthair",
                "personality": "Available for Adoption",
                "image_url": "https://24petconnect.com/img1.jpg",
                "images": ["https://24petconnect.com/img1.jpg", "https://24petconnect.com/img2.jpg"],
                "photos_count": 2,
                "bio": "Sweet and affectionate female kitten",
                "adoption_url": "https://24petconnect.com/CalgaryAdopt",
                "source_type": "Municipal Shelter"
            },
            {
                "id": "pm_azul",
                "name": "Azul",
                "shelter": "Pawsitive Match Rescue Foundation",
                "shelter_location": "Calgary, AB",
                "shelter_phone": "",
                "sex": "Female",
                "age_str": "4 months",
                "breed": "Domestic Longhair",
                "personality": "Playful",
                "image_url": "https://pawsitivematch.org/azul.jpg",
                "images": ["https://pawsitivematch.org/azul.jpg"],
                "photos_count": 1,
                "bio": "Gentle baby",
                "adoption_url": "https://pawsitivematch.org/adoptable-cats-item/azul",
                "source_type": "Foster Rescue"
            },
            {
                "id": "arf_c4569f",
                "name": "Bella",
                "shelter": "Animal Rescue Foundation (ARF)",
                "shelter_location": "Calgary, AB",
                "shelter_phone": "",
                "sex": "Female",
                "age_str": "10 weeks",
                "breed": "Domestic Shorthair",
                "personality": "Available",
                "image_url": "https://arf.ab.ca/c4569f.jpg",
                "images": ["https://arf.ab.ca/c4569f.jpg"],
                "photos_count": 1,
                "bio": "Cuddle bug",
                "adoption_url": "https://arf.ab.ca/adopt/bella",
                "source_type": "Rescue Foundation"
            },
            {
                "id": "frfa_ace",
                "name": "Ace",
                "shelter": "Feline Rescue Foundation of Alberta",
                "shelter_location": "Calgary, AB",
                "shelter_phone": "",
                "sex": "Male",
                "age_str": "8 weeks",
                "breed": "Domestic Shorthair",
                "personality": "Curious",
                "image_url": "https://frfa.ca/ace.jpg",
                "images": ["https://frfa.ca/ace.jpg"],
                "photos_count": 1,
                "bio": "Active kitten",
                "adoption_url": "https://frfa.ca/adopt/ace",
                "source_type": "Cat Rescue"
            },
            {
                "id": "aarcs_misty",
                "name": "Misty",
                "shelter": "AARCS",
                "shelter_location": "Calgary, AB",
                "shelter_phone": "",
                "sex": "Female",
                "age_str": "14 weeks",
                "breed": "Siamese Mix",
                "personality": "Vocal and friendly",
                "image_url": "https://aarcs.ca/misty.jpg",
                "images": ["https://aarcs.ca/misty.jpg"],
                "photos_count": 1,
                "bio": "Beautiful point kitten",
                "adoption_url": "https://aarcs.ca/adoptable-cats/misty",
                "source_type": "Rescue Organization"
            }
        ]
        for record in sample_shelter_records:
            validate_cat_record_contract(self, record)

    def test_scraper_module_contract_and_error_handling(self):
        """Verifies each shelter scraper module: existence, signature, and graceful error handling."""
        for key, module_path, func_name, shelter_name in ALL_SHELTER_SPECS:
            with self.subTest(shelter=key, module=module_path):
                try:
                    mod = importlib.import_module(module_path)
                except ImportError:
                    # Honor Progressive Testability: future milestone scrapers skipped if not yet created
                    self.skipTest(f"{module_path} not yet created in codebase (planned for upcoming milestone)")
                    continue

                self.assertTrue(hasattr(mod, func_name), f"Module {module_path} missing function {func_name}")
                scraper_func = getattr(mod, func_name)
                self.assertTrue(callable(scraper_func), f"{func_name} in {module_path} is not callable")

                # Test resilience: network error must NOT raise uncaught exception
                with patch("requests.get", side_effect=requests.exceptions.ConnectionError("Simulated DNS failure")):
                    try:
                        res = scraper_func()
                        self.assertIsInstance(res, list, f"{func_name} must return list on network error")
                        self.assertEqual(len(res), 0, f"{func_name} should return empty list on fatal network error")
                    except Exception as e:
                        self.fail(f"{func_name} raised uncaught exception on network failure: {e}")

    def test_existing_scrapers_mocked_contract_compliance(self):
        """Tests that CHS, Cochrane, and MEOW scraper parsing produces schema-compliant cat records."""
        # 1. Test CHS parsing with sample HTML
        from scraper.chs_scraper import scrape_chs_cats
        chs_html = """
        <div class="pp_listitem pp_Female">
            <span class="pp_inlinename">Snowy</span>
            <img class="pp_heroimage" src="https://example.com/snowy.jpg" />
            <a href="?id=998877">View Details</a>
            Sex: Female Breed: Domestic Shorthair Age: 10 weeks
        </div>
        """
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = chs_html
            mock_get.return_value = mock_resp
            cats = scrape_chs_cats()
            self.assertEqual(len(cats), 1)
            validate_cat_record_contract(self, cats[0])
            self.assertEqual(cats[0]["name"], "Snowy")
            self.assertEqual(cats[0]["sex"], "Female")

        # 2. Test Cochrane parsing with sample HTML
        from scraper.cochrane_scraper import scrape_cochrane_cats
        cochrane_html = """
        <div class="w-dyn-item">
            <h2>Shorty</h2>
            <img src="https://example.com/shorty.jpg" />
            <a href="/adopt/shorty">Profile</a>
            Type: Cat | Sex: Female | Age: 3 Months | Breed: Domestic Shorthair
        </div>
        """
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = cochrane_html
            mock_get.return_value = mock_resp
            cats = scrape_cochrane_cats()
            self.assertEqual(len(cats), 1)
            validate_cat_record_contract(self, cats[0])
            self.assertEqual(cats[0]["name"], "Shorty")
            self.assertEqual(cats[0]["sex"], "Female")

        # 3. Test MEOW parsing with sample HTML
        from scraper.meow_scraper import scrape_meow_cats
        meow_html = """
        <div class="cat-block" data-cat-id="5544" data-personality="Sweet">
            <div class="cat-name">Frosty</div>
            <div class="cat-thumbnail"><img src="https://example.com/frosty.jpg" /></div>
            <div class="cat-details"><p>Sex: Female. Age: 8 weeks.</p></div>
            <div class="cat-bio"><p>Super friendly kitten</p></div>
        </div>
        """
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = meow_html
            mock_get.return_value = mock_resp
            cats = scrape_meow_cats()
            self.assertEqual(len(cats), 1)
            validate_cat_record_contract(self, cats[0])
            self.assertEqual(cats[0]["name"], "Frosty")
            self.assertEqual(cats[0]["sex"], "Female")


class TestTier1RankerAndDatabaseContracts(unittest.TestCase):
    """Verifies interface contracts and basic behavior of Ranker and Database modules."""

    def test_ranker_contract(self):
        cat = {
            "name": "Luna",
            "sex": "Female",
            "age_str": "8 weeks",
            "breed": "White Short Hair",
            "bio": "Sweet and cuddly baby purring loudly."
        }
        res = calculate_bosbos_score(cat)
        self.assertIsInstance(res, dict)
        self.assertIn("is_match", res)
        self.assertIn("score", res)
        self.assertIn("age_weeks", res)
        self.assertIn("color_category", res)
        self.assertIn("cute_tags", res)
        self.assertIn("score_breakdown", res)
        self.assertTrue(res["is_match"])
        self.assertIsInstance(res["score"], int)
        self.assertGreaterEqual(res["score"], 0)
        self.assertLessEqual(res["score"], 100)

    def test_database_persistence_and_schema_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_db = os.path.join(tmpdir, "test_bosbos.db")
            test_json = os.path.join(tmpdir, "cats.json")

            conn = init_db(test_db)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cats'")
            self.assertIsNotNone(cur.fetchone())
            conn.close()

            test_cat = {
                "id": "meow_123",
                "name": "Cloud",
                "shelter": "MEOW Foundation",
                "sex": "Female",
                "age_str": "10 weeks",
                "age_weeks": 10.0,
                "breed": "Domestic Shorthair",
                "image_url": "https://example.com/c1.jpg",
                "images": ["https://example.com/c1.jpg"],
                "photos_count": 1,
                "adoption_url": "https://example.com/adopt/123",
                "bosbos_score": 85,
                "color_category": "Bright White / Cream / Point",
                "cute_tags": ["cuddle", "purr"],
                "bio": "Fluffy cuddly angel"
            }

            exported = save_and_update_cats([test_cat], all_raw_cats=[test_cat], db_path=test_db, json_path=test_json)
            self.assertEqual(len(exported), 1)
            self.assertEqual(exported[0]["id"], "meow_123")
            self.assertTrue(os.path.exists(test_json))

            with open(test_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.assertIn("cats", data)
                self.assertEqual(data["total_candidates"], 1)


# ==============================================================================
# Tier 2: Boundary & Corner Cases
# ==============================================================================

class TestTier2BoundaryAndCornerCases(unittest.TestCase):
    """Exhaustive boundary testing for age parsing, youth brackets, gender exclusion, and malformed fields."""

    def test_age_parsing_boundaries(self):
        # Explicit weeks
        self.assertEqual(parse_age_to_weeks("0 weeks"), 0.0)
        self.assertEqual(parse_age_to_weeks("1 week"), 1.0)
        self.assertEqual(parse_age_to_weeks("8.5 wks"), 8.5)
        self.assertEqual(parse_age_to_weeks("20 weeks"), 20.0)

        # Months (multiplied by 4.33)
        self.assertAlmostEqual(parse_age_to_weeks("1 month"), 4.3, places=1)
        self.assertAlmostEqual(parse_age_to_weeks("2 Months"), 8.7, places=1)
        self.assertAlmostEqual(parse_age_to_weeks("4.5 months"), 19.5, places=1)

        # Compound: months + days
        self.assertAlmostEqual(parse_age_to_weeks("3 months 7 days"), 14.0, places=1)
        self.assertAlmostEqual(parse_age_to_weeks("4 months 3 days"), 17.7, places=1)

        # Adult & Years ceiling
        self.assertEqual(parse_age_to_weeks("1 year"), 999.0)
        self.assertEqual(parse_age_to_weeks("1 yr 6 mo"), 999.0)
        self.assertEqual(parse_age_to_weeks("5 years"), 999.0)

        # Unparseable / Non-age text
        self.assertIsNone(parse_age_to_weeks("Adult"))
        self.assertIsNone(parse_age_to_weeks("Senior"))
        self.assertIsNone(parse_age_to_weeks(""))
        self.assertIsNone(parse_age_to_weeks(None))
        self.assertIsNone(parse_age_to_weeks("Unknown age"))

        # Implicit kitten fallback
        self.assertEqual(parse_age_to_weeks("8 kitten"), 8.0)
        self.assertIsNone(parse_age_to_weeks("25 kitten"))  # >20 weeks

    def test_ranker_age_boundary_scoring_tiers(self):
        """Verifies exact youth score step-downs across all age boundaries."""
        base_cat = {
            "name": "Test",
            "sex": "Female",
            "breed": "Domestic",
            "bio": ""
        }

        # Boundary 1: <= 9.0 wks -> 40 points
        c9_0 = dict(base_cat, age_str="9 weeks")
        res9_0 = calculate_bosbos_score(c9_0)
        self.assertEqual(res9_0["score_breakdown"]["age_points"], 40)

        # Boundary 2: 9.1 to 12.0 wks -> 36 points
        c9_1 = dict(base_cat, age_str="9.1 weeks")
        res9_1 = calculate_bosbos_score(c9_1)
        self.assertEqual(res9_1["score_breakdown"]["age_points"], 36)

        c12_0 = dict(base_cat, age_str="12 weeks")
        res12_0 = calculate_bosbos_score(c12_0)
        self.assertEqual(res12_0["score_breakdown"]["age_points"], 36)

        # Boundary 3: 12.1 to 15.0 wks -> 30 points
        c12_1 = dict(base_cat, age_str="12.1 weeks")
        res12_1 = calculate_bosbos_score(c12_1)
        self.assertEqual(res12_1["score_breakdown"]["age_points"], 30)

        c15_0 = dict(base_cat, age_str="15 weeks")
        res15_0 = calculate_bosbos_score(c15_0)
        self.assertEqual(res15_0["score_breakdown"]["age_points"], 30)

        # Boundary 4: 15.1 to 18.0 wks -> 25 points
        c15_1 = dict(base_cat, age_str="15.1 weeks")
        res15_1 = calculate_bosbos_score(c15_1)
        self.assertEqual(res15_1["score_breakdown"]["age_points"], 25)

        c18_0 = dict(base_cat, age_str="18 weeks")
        res18_0 = calculate_bosbos_score(c18_0)
        self.assertEqual(res18_0["score_breakdown"]["age_points"], 25)

        # Boundary 5: 18.1 to 20.5 wks -> 20 points
        c18_1 = dict(base_cat, age_str="18.1 weeks")
        res18_1 = calculate_bosbos_score(c18_1)
        self.assertEqual(res18_1["score_breakdown"]["age_points"], 20)

        c20_5 = dict(base_cat, age_str="20.5 weeks")
        res20_5 = calculate_bosbos_score(c20_5)
        self.assertTrue(res20_5["is_match"])
        self.assertEqual(res20_5["score_breakdown"]["age_points"], 20)

        # Boundary 6: > 20.5 wks -> Cutoff / is_match False
        c20_6 = dict(base_cat, age_str="20.6 weeks")
        res20_6 = calculate_bosbos_score(c20_6)
        self.assertFalse(res20_6["is_match"])
        self.assertIn("Older than 20 weeks", res20_6["reason"])

    def test_sex_filtering_boundary_and_permutations(self):
        """Ensures non-female cats are strictly excluded while female variants pass."""
        qualifying_age = "10 weeks"

        # Valid female permutations
        for s in ["Female", "female", "FEMALE", "  female  ", "F", "f"]:
            cat = {"name": "Girl", "sex": s, "age_str": qualifying_age}
            res = calculate_bosbos_score(cat)
            self.assertTrue(res["is_match"], f"Sex '{s}' should qualify as female")

        # Invalid / non-female permutations
        for s in ["Male", "male", "M", "m", "Unknown", "", None, "Neutered Male", "Dog", "Other"]:
            cat = {"name": "Boy", "sex": s, "age_str": qualifying_age}
            res = calculate_bosbos_score(cat)
            self.assertFalse(res["is_match"], f"Sex '{s}' must NOT qualify as female")
            self.assertIn("Not female", res["reason"])

    def test_coat_color_palette_scoring_boundaries(self):
        """Verifies color scoring: Top Tier (40 pts), Accent Tier (30 pts), Standard (10 pts)."""
        # Top tier
        for kw in ["pure white", "cream point", "flame point", "lynx point", "ivory", "pearl coat"]:
            cat = {"name": "ColorTest", "sex": "Female", "age_str": "8 weeks", "breed": kw, "bio": ""}
            res = calculate_bosbos_score(cat)
            self.assertEqual(res["score_breakdown"]["color_points"], 40, f"Keyword '{kw}' should score 40 color pts")
            self.assertEqual(res["color_category"], "Bright White / Cream / Point")

        # Accent tier
        for kw in ["calico", "silver tabby", "light gray", "pastel mix", "tuxedo cat"]:
            cat = {"name": "ColorTest", "sex": "Female", "age_str": "8 weeks", "breed": kw, "bio": ""}
            res = calculate_bosbos_score(cat)
            self.assertEqual(res["score_breakdown"]["color_points"], 30, f"Keyword '{kw}' should score 30 color pts")
            self.assertEqual(res["color_category"], "Pastel / Calico / Light Mix")

        # Standard tier
        cat = {"name": "ColorTest", "sex": "Female", "age_str": "8 weeks", "breed": "Brown Tabby", "bio": "Normal cat"}
        res = calculate_bosbos_score(cat)
        self.assertEqual(res["score_breakdown"]["color_points"], 10)
        self.assertEqual(res["color_category"], "Standard")

    def test_cute_tags_capping_and_scoring(self):
        """Verifies cute personality score: 10 base + min(2 * tags, 10), capped at 20 points."""
        cat_no_tags = {"name": "Test", "sex": "Female", "age_str": "8 weeks", "bio": "Friendly feline."}
        # "friendly" is in CUTE_KEYWORDS! Let's check a bio without any cute keywords:
        cat_zero = {"name": "Test", "sex": "Female", "age_str": "8 weeks", "bio": "Intake ID 1234."}
        res_zero = calculate_bosbos_score(cat_zero)
        self.assertEqual(res_zero["score_breakdown"]["cute_points"], 10)
        self.assertEqual(len(res_zero["cute_tags"]), 0)

        # 2 tags -> 10 + 2*2 = 14 pts
        cat_two = {"name": "Test", "sex": "Female", "age_str": "8 weeks", "bio": "Very sweet baby."}
        res_two = calculate_bosbos_score(cat_two)
        self.assertEqual(res_two["score_breakdown"]["cute_points"], 14)

        # 10 tags -> capped at 20 pts (max 10 added)
        cat_max = {
            "name": "Test",
            "sex": "Female",
            "age_str": "8 weeks",
            "bio": "cuddle cuddly sweet tiny little purr big eyes playful adorable gentle fluffy soft snuggle baby cute"
        }
        res_max = calculate_bosbos_score(cat_max)
        self.assertEqual(res_max["score_breakdown"]["cute_points"], 20)
        self.assertLessEqual(len(res_max["cute_tags"]), 6)  # capped at 6 tags in output

    def test_missing_or_empty_attributes(self):
        """Tests ranker resilience with empty strings, None, or absent fields."""
        cat_sparse = {
            "name": "Minimal",
            "sex": "Female",
            "age_str": "8 weeks"
        }
        res = calculate_bosbos_score(cat_sparse)
        self.assertTrue(res["is_match"])
        self.assertEqual(res["score_breakdown"]["color_points"], 10)
        self.assertEqual(res["score_breakdown"]["cute_points"], 10)

        # Bio mentions 'kitten' when age is missing -> defaults to 12.0 weeks
        cat_implicit = {
            "name": "Mystery",
            "sex": "Female",
            "bio": "A tiny white kitten found recently."
        }
        res_implicit = calculate_bosbos_score(cat_implicit)
        self.assertTrue(res_implicit["is_match"])
        self.assertEqual(res_implicit["age_weeks"], 12.0)
        self.assertEqual(res_implicit["score_breakdown"]["age_points"], 36)


# ==============================================================================
# Tier 3: Cross-Feature Interactions
# ==============================================================================

class TestTier3CrossFeatureInteractions(unittest.TestCase):
    """Verifies complete component interaction: Scraper Output -> Ranker -> DB -> JSON Export."""

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.test_dir.name, "test_bosbos.db")
        self.json_path = os.path.join(self.test_dir.name, "public", "data", "cats.json")

    def tearDown(self):
        self.test_dir.cleanup()

    def test_pipeline_integration_mock_to_json(self):
        raw_scraped_cats = [
            # Candidate 1: High scoring white kitten (Score: 40 age + 40 color + 20 cute = 100)
            {
                "id": "meow_snow",
                "name": "Snowflake",
                "shelter": "MEOW Foundation",
                "shelter_location": "Calgary, AB",
                "shelter_phone": "(403) 230-6033",
                "sex": "Female",
                "age_str": "8 weeks",
                "breed": "Domestic Shorthair - Pure White",
                "personality": "Playful",
                "image_url": "https://example.com/snow.jpg",
                "images": ["https://example.com/snow.jpg"],
                "photos_count": 1,
                "bio": "A sweet, tiny, adorable kitten who loves to cuddle, purr, and snuggle!",
                "adoption_url": "https://example.com/snow",
                "source_type": "Cat Shelter"
            },
            # Candidate 2: Medium scoring calico kitten (Score: 36 age + 30 color + 12 cute = 78)
            {
                "id": "cochrane_cali",
                "name": "Cali",
                "shelter": "Cochrane & Area Humane Society",
                "shelter_location": "Cochrane, AB",
                "shelter_phone": "(403) 932-2072",
                "sex": "Female",
                "age_str": "11 weeks",
                "breed": "Calico Mix",
                "personality": "Gentle",
                "image_url": "https://example.com/cali.jpg",
                "images": ["https://example.com/cali.jpg"],
                "photos_count": 1,
                "bio": "Gentle sweet kitten looking for a warm home.",
                "adoption_url": "https://example.com/cali",
                "source_type": "Humane Society"
            },
            # Non-candidate 1: Male kitten (must be excluded)
            {
                "id": "chs_simba",
                "name": "Simba",
                "shelter": "Calgary Humane Society",
                "shelter_location": "Calgary, AB",
                "shelter_phone": "(403) 205-4455",
                "sex": "Male",
                "age_str": "8 weeks",
                "breed": "Orange Tabby",
                "personality": "Feisty",
                "image_url": "https://example.com/simba.jpg",
                "images": ["https://example.com/simba.jpg"],
                "photos_count": 1,
                "bio": "Playful boy",
                "adoption_url": "https://example.com/simba",
                "source_type": "Humane Society"
            },
            # Non-candidate 2: Older cat (6 months / 26 weeks -> must be excluded)
            {
                "id": "chs_miso",
                "name": "Miso",
                "shelter": "Calgary Humane Society",
                "shelter_location": "Calgary, AB",
                "shelter_phone": "(403) 205-4455",
                "sex": "Female",
                "age_str": "6 months",
                "breed": "Siamese Mix",
                "personality": "Quiet",
                "image_url": "https://example.com/miso.jpg",
                "images": ["https://example.com/miso.jpg"],
                "photos_count": 1,
                "bio": "Quiet companion",
                "adoption_url": "https://example.com/miso",
                "source_type": "Humane Society"
            }
        ]

        # 1. Filter and score
        matched_candidates = []
        for cat in raw_scraped_cats:
            res = calculate_bosbos_score(cat)
            if res.get("is_match"):
                cat["bosbos_score"] = res["score"]
                cat["age_weeks"] = res["age_weeks"]
                cat["color_category"] = res["color_category"]
                cat["cute_tags"] = res["cute_tags"]
                cat["score_breakdown"] = res["score_breakdown"]
                matched_candidates.append(cat)

        self.assertEqual(len(matched_candidates), 2, "Only 2 female kittens <= 20 weeks should qualify")
        self.assertEqual(matched_candidates[0]["name"], "Snowflake")
        self.assertEqual(matched_candidates[1]["name"], "Cali")

        # 2. Persist to DB and Export to JSON
        exported_cats = save_and_update_cats(
            matched_candidates,
            all_raw_cats=raw_scraped_cats,
            db_path=self.db_path,
            json_path=self.json_path
        )

        self.assertEqual(len(exported_cats), 2)
        # Snowflake has score 100, Cali has score 80 -> Snowflake must be first
        self.assertEqual(exported_cats[0]["name"], "Snowflake")
        self.assertEqual(exported_cats[0]["bosbos_score"], 100)
        self.assertEqual(exported_cats[1]["name"], "Cali")
        self.assertEqual(exported_cats[1]["bosbos_score"], 80)

        # 3. Verify JSON file integrity
        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["total_candidates"], 2)
        self.assertIn("updated_at", data)
        self.assertIn("target_criteria", data)
        self.assertEqual(len(data["cats"]), 2)
        self.assertEqual(data["cats"][0]["id"], "meow_snow")
        self.assertEqual(data["cats"][1]["id"], "cochrane_cali")

        # 4. Verify SQLite database status
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT id, status, is_new_today FROM cats")
        rows = cur.fetchall()
        conn.close()

        id_status_map = {r[0]: (r[1], r[2]) for r in rows}
        self.assertIn("meow_snow", id_status_map)
        self.assertEqual(id_status_map["meow_snow"], ("active", 1))
        self.assertIn("cochrane_cali", id_status_map)
        self.assertEqual(id_status_map["cochrane_cali"], ("active", 1))


# ==============================================================================
# Tier 4: Real-World Scenarios
# ==============================================================================

class TestTier4RealWorldScenarios(unittest.TestCase):
    """Real-world end-to-end multi-shelter scenarios, adoption transitions, and idempotency."""

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.test_dir.name, "test_bosbos.db")
        self.json_path = os.path.join(self.test_dir.name, "cats.json")

    def tearDown(self):
        self.test_dir.cleanup()

    def test_real_world_multi_shelter_kitten_discovery(self):
        """Simulates full Calgary shelter ecosystem with real-world cats (Apple Crumble, Shorty, etc.)."""
        calgary_scraped_dataset = [
            # City of Calgary Animal Services: Apple Crumble (15 weeks old kitten)
            {
                "id": "calgary_a0963248",
                "name": "Apple Crumble",
                "shelter": "City of Calgary Animal Services",
                "shelter_location": "Calgary, AB (2201 Portland St SE)",
                "shelter_phone": "(403) 268-2489",
                "sex": "Female",
                "age_str": "15 weeks old",
                "breed": "Domestic Shorthair",
                "personality": "Available for Adoption",
                "image_url": "https://24petconnect.com/img1.jpg",
                "images": ["https://24petconnect.com/img1.jpg", "https://24petconnect.com/img2.jpg"],
                "photos_count": 2,
                "bio": "Sweet and affectionate female kitten looking for a family.",
                "adoption_url": "https://24petconnect.com/CalgaryAdopt",
                "source_type": "Municipal Shelter"
            },
            # Cochrane & Area Humane Society: Shorty (3 Months / 13 weeks old kitten)
            {
                "id": "cochrane_shorty",
                "name": "Shorty",
                "shelter": "Cochrane & Area Humane Society",
                "shelter_location": "Cochrane, AB",
                "shelter_phone": "(403) 932-2072",
                "sex": "Female",
                "age_str": "3 Months",
                "breed": "Domestic Shorthair",
                "personality": "Available for Adoption",
                "image_url": "https://cochranehumane.ca/shorty1.jpg",
                "images": ["https://cochranehumane.ca/shorty1.jpg"],
                "photos_count": 1,
                "bio": "A sweet, playful kitten.",
                "adoption_url": "https://cochranehumane.ca/adopt",
                "source_type": "Humane Society"
            },
            # MEOW Foundation: White kitten Marshmallow (8 weeks old)
            {
                "id": "meow_marshmallow",
                "name": "Marshmallow",
                "shelter": "MEOW Foundation",
                "shelter_location": "Calgary, AB",
                "shelter_phone": "(403) 230-6033",
                "sex": "Female",
                "age_str": "8 weeks",
                "breed": "Domestic Shorthair - Pure White",
                "personality": "Cuddly",
                "image_url": "https://meowfoundation.com/marshmallow.jpg",
                "images": ["https://meowfoundation.com/marshmallow.jpg"],
                "photos_count": 1,
                "bio": "Tiny white baby who purrs non-stop.",
                "adoption_url": "https://meowfoundation.com/adoptable-cats/",
                "source_type": "Cat Shelter"
            },
            # Calgary Humane Society: Adult Cat Miso (5 years old -> excluded)
            {
                "id": "chs_miso_adult",
                "name": "Miso",
                "shelter": "Calgary Humane Society",
                "shelter_location": "Calgary, AB",
                "shelter_phone": "(403) 205-4455",
                "sex": "Female",
                "age_str": "5 years",
                "breed": "Domestic Shorthair",
                "personality": "Available for Adoption",
                "image_url": "https://calgaryhumane.ca/miso.jpg",
                "images": ["https://calgaryhumane.ca/miso.jpg"],
                "photos_count": 1,
                "bio": "Lovely adult cat",
                "adoption_url": "https://calgaryhumane.ca/adopt/cats/",
                "source_type": "Humane Society Shelter"
            }
        ]

        candidates = []
        for cat in calgary_scraped_dataset:
            res = calculate_bosbos_score(cat)
            if res.get("is_match"):
                cat["bosbos_score"] = res["score"]
                cat["age_weeks"] = res["age_weeks"]
                cat["color_category"] = res["color_category"]
                cat["cute_tags"] = res["cute_tags"]
                cat["score_breakdown"] = res["score_breakdown"]
                candidates.append(cat)

        saved = save_and_update_cats(
            candidates,
            all_raw_cats=calgary_scraped_dataset,
            db_path=self.db_path,
            json_path=self.json_path
        )

        # Candidates must include Marshmallow (8w), Shorty (13w), Apple Crumble (15w)
        self.assertEqual(len(saved), 3)
        candidate_names = [c["name"] for c in saved]
        self.assertIn("Marshmallow", candidate_names)
        self.assertIn("Shorty", candidate_names)
        self.assertIn("Apple Crumble", candidate_names)
        self.assertNotIn("Miso", candidate_names)

        # Marshmallow (8w, white) must be rank #1
        self.assertEqual(saved[0]["name"], "Marshmallow")
        self.assertGreaterEqual(saved[0]["bosbos_score"], 80)

    def test_pipeline_idempotency_and_new_today_flag(self):
        """Running the pipeline twice with identical data preserves first_seen and updates status."""
        test_kitten = {
            "id": "meow_cloud",
            "name": "Cloud",
            "shelter": "MEOW Foundation",
            "sex": "Female",
            "age_str": "8 weeks",
            "age_weeks": 8.0,
            "breed": "White",
            "image_url": "https://example.com/cloud.jpg",
            "images": ["https://example.com/cloud.jpg"],
            "photos_count": 1,
            "adoption_url": "https://example.com/cloud",
            "bosbos_score": 90,
            "color_category": "Bright White / Cream / Point",
            "cute_tags": ["cuddle"],
            "bio": "Sweet angel"
        }

        # Run 1
        res1 = save_and_update_cats([test_kitten], all_raw_cats=[test_kitten], db_path=self.db_path, json_path=self.json_path)
        self.assertEqual(len(res1), 1)
        self.assertTrue(res1[0]["is_new_today"])

        # Check DB first_seen
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT first_seen, last_seen FROM cats WHERE id = 'meow_cloud'")
        first_seen_run1, last_seen_run1 = cur.fetchone()
        conn.close()

        # Run 2
        res2 = save_and_update_cats([test_kitten], all_raw_cats=[test_kitten], db_path=self.db_path, json_path=self.json_path)
        self.assertEqual(len(res2), 1)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT first_seen, last_seen, is_new_today FROM cats WHERE id = 'meow_cloud'")
        first_seen_run2, last_seen_run2, is_new_run2 = cur.fetchone()
        conn.close()

        # first_seen MUST remain identical
        self.assertEqual(first_seen_run1, first_seen_run2)
        # on the same day, is_new_today remains 1
        self.assertEqual(is_new_run2, 1)

    def test_adoption_lifecycle_transition(self):
        """When a cat disappears from a shelter's active scrape, it transitions to 'adopted'."""
        cat_a = {
            "id": "meow_cat_a",
            "name": "Cat A",
            "shelter": "MEOW Foundation",
            "sex": "Female",
            "age_str": "8 weeks",
            "age_weeks": 8.0,
            "breed": "White",
            "image_url": "https://example.com/a.jpg",
            "images": ["https://example.com/a.jpg"],
            "photos_count": 1,
            "adoption_url": "https://example.com/a",
            "bosbos_score": 90,
            "color_category": "Bright White / Cream / Point",
            "cute_tags": [],
            "bio": "Cat A"
        }
        cat_b = {
            "id": "meow_cat_b",
            "name": "Cat B",
            "shelter": "MEOW Foundation",
            "sex": "Female",
            "age_str": "9 weeks",
            "age_weeks": 9.0,
            "breed": "White",
            "image_url": "https://example.com/b.jpg",
            "images": ["https://example.com/b.jpg"],
            "photos_count": 1,
            "adoption_url": "https://example.com/b",
            "bosbos_score": 90,
            "color_category": "Bright White / Cream / Point",
            "cute_tags": [],
            "bio": "Cat B"
        }

        # Day 1: Both cats are active
        save_and_update_cats([cat_a, cat_b], all_raw_cats=[cat_a, cat_b], db_path=self.db_path, json_path=self.json_path)

        # Day 2: Cat A was adopted, only Cat B is present in shelter scrape
        res_day2 = save_and_update_cats([cat_b], all_raw_cats=[cat_b], db_path=self.db_path, json_path=self.json_path)

        # Only Cat B in exported list
        self.assertEqual(len(res_day2), 1)
        self.assertEqual(res_day2[0]["id"], "meow_cat_b")

        # Cat A in DB should now have status = 'adopted'
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT status FROM cats WHERE id = 'meow_cat_a'")
        status_a = cur.fetchone()[0]
        cur.execute("SELECT status FROM cats WHERE id = 'meow_cat_b'")
        status_b = cur.fetchone()[0]
        conn.close()

        self.assertEqual(status_a, "adopted")
        self.assertEqual(status_b, "active")


if __name__ == "__main__":
    unittest.main()
