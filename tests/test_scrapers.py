import unittest
from scraper.meow_scraper import scrape_meow_cats
from scraper.chs_scraper import scrape_chs_cats
from scraper.cochrane_scraper import scrape_cochrane_cats

class TestScrapers(unittest.TestCase):
    def test_meow_scraper_returns_data(self):
        cats = scrape_meow_cats()
        self.assertIsInstance(cats, list)
        self.assertGreater(len(cats), 0, "MEOW scraper should return at least one cat")
        sample = cats[0]
        self.assertIn("name", sample)
        self.assertIn("sex", sample)
        self.assertIn("age_str", sample)
        self.assertIn("image_url", sample)

    def test_chs_scraper_returns_data(self):
        cats = scrape_chs_cats()
        self.assertIsInstance(cats, list)
        self.assertGreater(len(cats), 0, "Calgary Humane scraper should return at least one cat")
        sample = cats[0]
        self.assertIn("name", sample)
        self.assertIn("sex", sample)

    def test_cochrane_scraper_returns_data(self):
        cats = scrape_cochrane_cats()
        self.assertIsInstance(cats, list)
        # Even if 0 cats are currently listed as kittens, it must return a valid list
        for c in cats:
            self.assertIn("name", c)
            self.assertIn("adoption_url", c)

if __name__ == "__main__":
    unittest.main()
