import unittest
from scraper.meow_scraper import scrape_meow_cats
from scraper.chs_scraper import scrape_chs_cats
from scraper.cochrane_scraper import scrape_cochrane_cats
from scraper.calgary_scraper import scrape_calgary_cats
from scraper.pawsitive_scraper import scrape_pawsitive_cats
from scraper.arf_scraper import scrape_arf_cats
from scraper.frfa_scraper import scrape_frfa_cats
from scraper.aarcs_scraper import scrape_aarcs_cats

REQUIRED_SCHEMA_KEYS = [
    "id",
    "name",
    "shelter",
    "shelter_location",
    "shelter_phone",
    "sex",
    "age_str",
    "breed",
    "personality",
    "image_url",
    "images",
    "photos_count",
    "bio",
    "adoption_url",
    "source_type",
]

class TestScrapers(unittest.TestCase):
    def _assert_valid_cat_schema(self, cat):
        for key in REQUIRED_SCHEMA_KEYS:
            self.assertIn(key, cat, f"Missing key '{key}' in cat record: {cat.get('id', cat.get('name'))}")
        self.assertIsInstance(cat["id"], str)
        self.assertIsInstance(cat["name"], str)
        self.assertIsInstance(cat["shelter"], str)
        self.assertIsInstance(cat["images"], list)
        self.assertIsInstance(cat["photos_count"], int)
        self.assertEqual(len(cat["images"]), cat["photos_count"])
        self.assertIn(cat["sex"], ["Female", "Male", "Unknown"])

    def test_meow_scraper_returns_data(self):
        cats = scrape_meow_cats()
        self.assertIsInstance(cats, list)
        self.assertGreater(len(cats), 0, "MEOW scraper should return at least one cat")
        for cat in cats:
            self._assert_valid_cat_schema(cat)

    def test_chs_scraper_returns_data(self):
        cats = scrape_chs_cats()
        self.assertIsInstance(cats, list)
        self.assertGreater(len(cats), 0, "Calgary Humane scraper should return at least one cat")
        for cat in cats:
            self._assert_valid_cat_schema(cat)

    def test_cochrane_scraper_returns_data(self):
        cats = scrape_cochrane_cats()
        self.assertIsInstance(cats, list)
        self.assertGreater(len(cats), 0, "Cochrane scraper should return at least one cat")
        for cat in cats:
            self._assert_valid_cat_schema(cat)

    def test_calgary_scraper_returns_data(self):
        cats = scrape_calgary_cats()
        self.assertIsInstance(cats, list)
        self.assertGreater(len(cats), 0, "City of Calgary scraper should return at least one cat")
        for cat in cats:
            self._assert_valid_cat_schema(cat)

    def test_pawsitive_scraper_returns_data(self):
        cats = scrape_pawsitive_cats()
        self.assertIsInstance(cats, list)
        self.assertGreater(len(cats), 0, "Pawsitive Match scraper should return at least one cat")
        for cat in cats:
            self._assert_valid_cat_schema(cat)

    def test_arf_scraper_returns_data(self):
        cats = scrape_arf_cats()
        self.assertIsInstance(cats, list)
        self.assertGreater(len(cats), 0, "ARF Alberta scraper should return at least one cat")
        for cat in cats:
            self._assert_valid_cat_schema(cat)

    def test_frfa_scraper_returns_data(self):
        cats = scrape_frfa_cats()
        self.assertIsInstance(cats, list)
        self.assertGreater(len(cats), 0, "FRFA scraper should return at least one cat")
        for cat in cats:
            self._assert_valid_cat_schema(cat)

    def test_aarcs_scraper_returns_data(self):
        cats = scrape_aarcs_cats()
        self.assertIsInstance(cats, list)
        self.assertGreater(len(cats), 0, "AARCS scraper should return at least one cat")
        for cat in cats:
            self._assert_valid_cat_schema(cat)

if __name__ == "__main__":
    unittest.main()
