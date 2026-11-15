"""
Adversarial Stress Test Suite for bosbos-cat-finder (Tier 5 Hardening)
Empirical verification of scrapers, ranker, database persistence, and JSON exporter
under extreme, malformed, and adversarial inputs.
"""

import unittest
from unittest.mock import patch, MagicMock
import requests
import json
import os
import tempfile
import shutil

from scraper.ranker import parse_age_to_weeks, calculate_bosbos_score
from scraper.database import init_db, save_and_update_cats, export_to_json
from scraper.meow_scraper import scrape_meow_cats
from scraper.chs_scraper import scrape_chs_cats
from scraper.cochrane_scraper import scrape_cochrane_cats
from scraper.calgary_scraper import scrape_calgary_cats
from scraper.pawsitive_scraper import scrape_pawsitive_cats
from scraper.arf_scraper import scrape_arf_cats
from scraper.frfa_scraper import scrape_frfa_cats
from scraper.aarcs_scraper import scrape_aarcs_cats


class TestAdversarialAgeParsing(unittest.TestCase):
    """Stress tests for parse_age_to_weeks under malformed and boundary inputs."""

    def test_explicit_valid_ages(self):
        """Standard valid age strings."""
        self.assertEqual(parse_age_to_weeks("8 weeks"), 8.0)
        self.assertEqual(parse_age_to_weeks("18 wks"), 18.0)
        self.assertEqual(parse_age_to_weeks("2 months"), round(2 * 4.33, 1))
        self.assertEqual(parse_age_to_weeks("15 days"), round(15 / 7.0, 1))

    def test_adult_and_years(self):
        """Adult strings and year designations must return >= 999.0."""
        for yr_str in ["1 year", "10 years", "2 yrs", "under 1 year", "1.5 years old", "approx 3 yr"]:
            res = parse_age_to_weeks(yr_str)
            self.assertIsNotNone(res, f"'{yr_str}' should return a numeric age indicator")
            self.assertGreaterEqual(res, 999.0, f"'{yr_str}' should be >= 999.0")

    def test_malformed_and_unparseable_strings(self):
        """Malformed, gibberish, or future birth strings should return None without crashing."""
        malformed_inputs = [
            "born approx Dec 2026",
            "Dec 2026",
            "unknown",
            "??!@#$",
            "NaN",
            "inf",
            "-inf",
            "null",
            "None",
            "undefined",
            "N/A",
            "adult cat",
            "senior",
            "pending",
            "",
            "   ",
            "\t\n",
        ]
        for s in malformed_inputs:
            res = parse_age_to_weeks(s)
            self.assertIsNone(res, f"Input '{s}' should return None, got {res}")

    def test_none_input(self):
        """None age string must return None without raising TypeError."""
        self.assertIsNone(parse_age_to_weeks(None))

    def test_zero_ages(self):
        """Zero days or weeks should return 0.0 without errors."""
        self.assertEqual(parse_age_to_weeks("0 weeks"), 0.0)
        self.assertEqual(parse_age_to_weeks("0 days"), 0.0)

    def test_compound_durations(self):
        """Compound durations: months + days, months + weeks."""
        # 4 months (~17.32) + 3 days (~0.43) -> ~17.8
        res = parse_age_to_weeks("4 months 3 days")
        self.assertIsNotNone(res)
        self.assertAlmostEqual(res, 17.8, delta=0.5)

        # 2 months + 2 weeks -> 2*4.33 + 2 = 10.66 -> 10.7
        res2 = parse_age_to_weeks("2 months 2 weeks")
        self.assertIsNotNone(res2)
        self.assertAlmostEqual(res2, 10.7, delta=0.5)


class TestAdversarialSexFiltering(unittest.TestCase):
    """Stress tests for calculate_bosbos_score under unusual, malformed, or ambiguous sexes."""

    def test_female_variants(self):
        """Strict female variants that must qualify."""
        qualifying = [
            "Female",
            "female",
            "FEMALE",
            "  female  ",
            "F",
            "f",
            "  F  ",
        ]
        for s in qualifying:
            cat = {"id": "c1", "name": "Lily", "sex": s, "age_str": "8 weeks"}
            res = calculate_bosbos_score(cat)
            self.assertTrue(res["is_match"], f"Sex '{s}' should qualify as female")

    def test_non_female_variants(self):
        """Non-female variants that must NOT qualify."""
        non_female = [
            "Male",
            "male",
            "MALE",
            "M",
            "m",
            "Neutered Male",
            "Unknown",
            "unknown",
            "Dog",
            "Rabbit",
            "Other",
            "",
            "   ",
            None,
        ]
        for s in non_female:
            cat = {"id": "c2", "name": "Max", "sex": s, "age_str": "8 weeks"}
            res = calculate_bosbos_score(cat)
            self.assertFalse(res["is_match"], f"Sex '{s}' must NOT qualify as female")
            self.assertEqual(res["score"], 0)


class TestScraperNetworkFailureInjection(unittest.TestCase):
    """Network failure injection across all 8 shelter scrapers: 404, 500, ConnectionError, ReadTimeout."""

    SCRAPER_FUNCS = [
        ("meow_scraper", scrape_meow_cats),
        ("chs_scraper", scrape_chs_cats),
        ("cochrane_scraper", scrape_cochrane_cats),
        ("calgary_scraper", scrape_calgary_cats),
        ("pawsitive_scraper", scrape_pawsitive_cats),
        ("arf_scraper", scrape_arf_cats),
        ("frfa_scraper", scrape_frfa_cats),
        ("aarcs_scraper", scrape_aarcs_cats),
    ]

    def _mock_http_error(self, status_code):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(f"HTTP {status_code}")
        return mock_resp

    def test_all_scrapers_handle_404_not_found(self):
        """All 8 scrapers must handle HTTP 404 gracefully without raising exceptions."""
        for name, fn in self.SCRAPER_FUNCS:
            with patch("requests.get", return_value=self._mock_http_error(404)), \
                 patch("requests.post", return_value=self._mock_http_error(404)):
                try:
                    result = fn()
                    self.assertIsInstance(result, list, f"{name} must return list on 404, got {type(result)}")
                except Exception as e:
                    self.fail(f"{name} raised unhandled exception on HTTP 404: {e}")

    def test_all_scrapers_handle_500_server_error(self):
        """All 8 scrapers must handle HTTP 500 gracefully without raising exceptions."""
        for name, fn in self.SCRAPER_FUNCS:
            with patch("requests.get", return_value=self._mock_http_error(500)), \
                 patch("requests.post", return_value=self._mock_http_error(500)):
                try:
                    result = fn()
                    self.assertIsInstance(result, list, f"{name} must return list on 500, got {type(result)}")
                except Exception as e:
                    self.fail(f"{name} raised unhandled exception on HTTP 500: {e}")

    def test_all_scrapers_handle_connection_error(self):
        """All 8 scrapers must handle requests.exceptions.ConnectionError gracefully."""
        for name, fn in self.SCRAPER_FUNCS:
            with patch("requests.get", side_effect=requests.exceptions.ConnectionError("Failed to resolve host")), \
                 patch("requests.post", side_effect=requests.exceptions.ConnectionError("Failed to resolve host")):
                try:
                    result = fn()
                    self.assertIsInstance(result, list, f"{name} must return list on ConnectionError, got {type(result)}")
                except Exception as e:
                    self.fail(f"{name} raised unhandled exception on ConnectionError: {e}")

    def test_all_scrapers_handle_read_timeout(self):
        """All 8 scrapers must handle requests.exceptions.ReadTimeout gracefully."""
        for name, fn in self.SCRAPER_FUNCS:
            with patch("requests.get", side_effect=requests.exceptions.ReadTimeout("Read timed out")), \
                 patch("requests.post", side_effect=requests.exceptions.ReadTimeout("Read timed out")):
                try:
                    result = fn()
                    self.assertIsInstance(result, list, f"{name} must return list on ReadTimeout, got {type(result)}")
                except Exception as e:
                    self.fail(f"{name} raised unhandled exception on ReadTimeout: {e}")


class TestAdversarialDataRobustness(unittest.TestCase):
    """Stress tests with Unicode characters, extreme photo URLs, missing fields, and SQL injection payloads."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_adversarial.db")
        self.json_path = os.path.join(self.temp_dir, "cats.json")
        init_db(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_unicode_and_emojis_in_cat_record(self):
        """Records with multi-lingual Unicode, emojis, and special symbols persist and export cleanly."""
        cat = {
            "id": "unicode_01",
            "name": "🐾 Snowball ❄️ / 子猫 / قطة",
            "shelter": "MEOW Foundation",
            "shelter_location": "3511 19 St NE, Calgary, AB",
            "shelter_phone": "(403) 230-6033",
            "sex": "Female",
            "age_str": "8 weeks",
            "breed": "Domestic Shorthair • Blanc Pure",
            "personality": "Very cuddly, sweet, playful baby kitten! 💖 Purrs loudly.",
            "image_url": "https://example.com/cat_🐱.jpg",
            "images": ["https://example.com/cat_🐱.jpg", "https://example.com/cat2_🌸.png"],
            "photos_count": 2,
            "bio": "Adversarial bio: 🐈 🐾 éèçà ñ 日本語 العربية Russian: Кошечка! 🌟",
            "adoption_url": "https://meowfoundation.com/adopt/unicode_01",
            "source_type": "Private Rescue"
        }

        # Step 1: Bosbos scoring
        score_res = calculate_bosbos_score(cat)
        self.assertTrue(score_res["is_match"])
        cat["bosbos_score"] = score_res["score"]
        cat["age_weeks"] = score_res["age_weeks"]
        cat["color_category"] = score_res["color_category"]
        cat["cute_tags"] = score_res["cute_tags"]
        cat["score_breakdown"] = score_res["score_breakdown"]

        # Step 2: Database persistence & JSON export
        exported = save_and_update_cats([cat], all_raw_cats=[cat], db_path=self.db_path, json_path=self.json_path)
        self.assertEqual(len(exported), 1)
        self.assertEqual(exported[0]["name"], "🐾 Snowball ❄️ / 子猫 / قطة")

        # Step 3: Verify exported JSON is valid and readable
        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["total_candidates"], 1)
        self.assertEqual(data["cats"][0]["id"], "unicode_01")
        self.assertIn("子猫", data["cats"][0]["name"])

    def test_sql_injection_payload_resilience(self):
        """Cat records containing SQL injection syntax must be safely parameterized without schema corruption."""
        malicious_cat = {
            "id": "sqli_01'; DROP TABLE cats; --",
            "name": "Little Bob'); DROP TABLE cats; SELECT ('",
            "shelter": "Cochrane Humane' OR '1'='1",
            "shelter_location": "Calgary",
            "shelter_phone": "123",
            "sex": "Female",
            "age_str": "9 weeks",
            "breed": "Tabby'; DELETE FROM cats; --",
            "personality": "Friendly",
            "image_url": "https://example.com/img.jpg",
            "images": ["https://example.com/img.jpg"],
            "photos_count": 1,
            "bio": "Innocent bio with SQL quotes: '''' or 1=1;",
            "adoption_url": "https://example.com/adopt",
            "source_type": "Humane Society"
        }

        score_res = calculate_bosbos_score(malicious_cat)
        self.assertTrue(score_res["is_match"])
        malicious_cat["bosbos_score"] = score_res["score"]
        malicious_cat["age_weeks"] = score_res["age_weeks"]
        malicious_cat["color_category"] = score_res["color_category"]
        malicious_cat["cute_tags"] = score_res["cute_tags"]

        exported = save_and_update_cats([malicious_cat], all_raw_cats=[malicious_cat], db_path=self.db_path, json_path=self.json_path)
        self.assertEqual(len(exported), 1)

        # Table must still exist and contain the record intact
        conn = init_db(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM cats")
        count = cur.fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_extreme_photo_urls_and_large_fields(self):
        """Handle very large bio (50KB), 5,000-character URL, empty images list, and data URIs."""
        long_url = "https://example.com/images/" + ("a" * 5000) + ".jpg"
        large_bio = "Very sweet fluffy kitten. " * 2000 # ~54KB
        data_uri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        cat = {
            "id": "extreme_01",
            "name": "GiantDataCat",
            "shelter": "City of Calgary Animal Services",
            "shelter_location": "Calgary",
            "shelter_phone": "403-268-2489",
            "sex": "Female",
            "age_str": "6 weeks",
            "breed": "Domestic Shorthair",
            "personality": "Sweet",
            "image_url": long_url,
            "images": [long_url, data_uri, ""],
            "photos_count": 3,
            "bio": large_bio,
            "adoption_url": "https://24petconnect.com/DetailsMain/CLGR/123",
            "source_type": "Municipal Animal Services"
        }

        score_res = calculate_bosbos_score(cat)
        self.assertTrue(score_res["is_match"])
        cat["bosbos_score"] = score_res["score"]
        cat["age_weeks"] = score_res["age_weeks"]
        cat["color_category"] = score_res["color_category"]
        cat["cute_tags"] = score_res["cute_tags"]

        exported = save_and_update_cats([cat], all_raw_cats=[cat], db_path=self.db_path, json_path=self.json_path)
        self.assertEqual(len(exported), 1)
        self.assertEqual(len(exported[0]["images"]), 3)
        self.assertTrue(exported[0]["bio"].startswith("Very sweet fluffy kitten."))


class TestEmpiricallyDiscoveredVulnerabilities(unittest.TestCase):
    """
    Empirical tests demonstrating that all 6 edge-case vulnerabilities identified
    by Challenger 1 are properly defended against and verified.
    """

    def test_vuln_none_fields_cause_type_error(self):
        """
        VULNERABILITY 1 (FIXED): When any string field ('name', 'breed', 'bio', 'colors') is None,
        calculate_bosbos_score handles it safely without raising TypeError.
        """
        cat_with_none_bio = {
            "name": "Snowflake",
            "sex": "Female",
            "age_str": "8 weeks",
            "breed": "DSH",
            "bio": None  # Common from REST APIs or scraped pages with missing bio
        }
        res = calculate_bosbos_score(cat_with_none_bio)
        self.assertTrue(res["is_match"], "calculate_bosbos_score should handle None bio safely")
        self.assertEqual(res["age_weeks"], 8.0)

    def test_vuln_none_bio_crashes_fallback_kitten_check(self):
        """
        VULNERABILITY 2 (FIXED): When age is unparseable and bio is None,
        calculate_bosbos_score does not crash with TypeError and returns is_match=False.
        """
        cat_unparseable_none_bio = {
            "name": "LittleOne",
            "sex": "Female",
            "age_str": "unknown",
            "breed": "DSH",
            "bio": None
        }
        res = calculate_bosbos_score(cat_unparseable_none_bio)
        self.assertFalse(res["is_match"])
        self.assertEqual(res["reason"], "Unknown or unparseable age")

    def test_vuln_non_string_types_cause_attribute_error(self):
        """
        VULNERABILITY 3 (FIXED): When 'sex' or 'age_str' is an integer/bool (from raw API responses),
        ranker handles it safely without raising AttributeError.
        """
        res_sex = calculate_bosbos_score({"sex": 1, "age_str": "8 weeks"})
        self.assertFalse(res_sex["is_match"])

        res_age = calculate_bosbos_score({"sex": "Female", "age_str": 12})
        self.assertFalse(res_age["is_match"])

    def test_vuln_spayed_female_rejected(self):
        """
        VULNERABILITY 4 (FIXED): 'Spayed Female', 'Female (Spayed)', and 'Intact Female'
        are properly accepted as qualifying female candidates.
        """
        cat = {"name": "Molly", "sex": "Spayed Female", "age_str": "8 weeks"}
        res = calculate_bosbos_score(cat)
        self.assertTrue(res["is_match"], "Spayed Female must qualify as female")

        cat_parens = {"name": "Luna", "sex": "Female (Spayed)", "age_str": "8 weeks"}
        res_parens = calculate_bosbos_score(cat_parens)
        self.assertTrue(res_parens["is_match"], "Female (Spayed) must qualify as female")

        cat_intact = {"name": "Bella", "sex": "Intact Female", "age_str": "8 weeks"}
        res_intact = calculate_bosbos_score(cat_intact)
        self.assertTrue(res_intact["is_match"], "Intact Female must qualify as female")

    def test_vuln_negative_age_parses_as_positive(self):
        """
        VULNERABILITY 5 (FIXED): Negative age string '-5 weeks' is rejected/returns None,
        preventing false maximum youth scores.
        """
        parsed = parse_age_to_weeks("-5 weeks")
        self.assertIsNone(parsed, "-5 weeks must return None")
        score_res = calculate_bosbos_score({"sex": "Female", "age_str": "-5 weeks"})
        self.assertFalse(score_res["is_match"], "Negative age cat must not match")

    def test_vuln_adult_cat_false_positive_with_year_and_kitten_bio(self):
        """
        VULNERABILITY 6 (FIXED): Adult cat born in past 4-digit year (1990..2025) whose bio
        mentions 'kittens' is correctly identified as adult (999.0 wks) and excluded.
        """
        mama_cat = {
            "name": "Mama Cat",
            "sex": "Female",
            "age_str": "born in May 2020",
            "bio": "Sweet adult mother who had kittens in 2020. Pure white coat, very cuddly and loving."
        }
        res = calculate_bosbos_score(mama_cat)
        self.assertFalse(res["is_match"], "Adult cat born in 2020 must be excluded")
        self.assertEqual(res["age_weeks"], 999.0)
        self.assertIn("Older than 20 weeks", res["reason"])


if __name__ == "__main__":
    unittest.main()
