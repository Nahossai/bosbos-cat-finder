import unittest
from scraper.ranker import parse_age_to_weeks, calculate_bosbos_score

class TestBosbosRanker(unittest.TestCase):
    def test_age_parsing(self):
        self.assertEqual(parse_age_to_weeks("18 weeks"), 18.0)
        self.assertAlmostEqual(parse_age_to_weeks("2 Months"), 8.7, places=1)
        self.assertAlmostEqual(parse_age_to_weeks("4 months 3 days"), 17.7, places=1)
        self.assertEqual(parse_age_to_weeks("1 year 2 months"), 999.0)
        self.assertIsNone(parse_age_to_weeks("Adult"))

    def test_male_exclusion(self):
        cat = {
            "name": "Bansot",
            "sex": "male",
            "age": "8 weeks",
            "breed": "White Short Hair",
            "bio": "Sweet cuddly kitten"
        }
        res = calculate_bosbos_score(cat)
        self.assertFalse(res["is_match"])
        self.assertIn("Not female", res["reason"])

    def test_older_cat_exclusion(self):
        cat = {
            "name": "Miso",
            "sex": "female",
            "age": "6 months",
            "breed": "Domestic Shorthair",
            "bio": "Gentle girl"
        }
        res = calculate_bosbos_score(cat)
        self.assertFalse(res["is_match"])
        self.assertIn("Older than 20 weeks", res["reason"])

    def test_bosbos_high_score_match(self):
        # 8-week old female white kitten with cute bio
        cat = {
            "name": "Snowflake",
            "sex": "female",
            "age": "8 weeks",
            "breed": "Domestic Shorthair - Pure White",
            "bio": "A tiny, adorable bundle of joy with big eyes who loves to cuddle and purr on your lap!"
        }
        res = calculate_bosbos_score(cat)
        self.assertTrue(res["is_match"])
        self.assertGreaterEqual(res["score"], 90)
        self.assertEqual(res["color_category"], "Bright White / Cream / Point")
        self.assertIn("cuddle", res["cute_tags"])

if __name__ == "__main__":
    unittest.main()
