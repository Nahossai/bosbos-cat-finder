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

    def test_inclusive_female_matching(self):
        # Spayed female, Female (Spayed), Intact Female, and F variants
        for sex in ["Spayed Female", "Female (Spayed)", "Intact Female", "f", "FEMALE"]:
            cat = {"name": "Lilly", "sex": sex, "age_str": "8 weeks"}
            res = calculate_bosbos_score(cat)
            self.assertTrue(res["is_match"], f"Expected {sex} to match as female")

        # Strictly reject males
        for sex in ["Male", "Neutered Male", "m", "M", "intact male"]:
            cat = {"name": "Simba", "sex": sex, "age_str": "8 weeks"}
            res = calculate_bosbos_score(cat)
            self.assertFalse(res["is_match"], f"Expected {sex} to be rejected")
            self.assertIn("Not female", res["reason"])

    def test_negative_age_and_ranges(self):
        # Negative ages rejected
        self.assertIsNone(parse_age_to_weeks("-5 weeks"))
        self.assertIsNone(parse_age_to_weeks("-2 months"))
        cat_neg = {"name": "Test", "sex": "female", "age_str": "-5 weeks"}
        res_neg = calculate_bosbos_score(cat_neg)
        self.assertFalse(res_neg["is_match"])

        # Legitimate ranges preserved
        self.assertEqual(parse_age_to_weeks("6-8 weeks"), 8.0)
        self.assertEqual(parse_age_to_weeks("6 - 8 weeks"), 8.0)

    def test_four_digit_birth_year_detection(self):
        self.assertEqual(parse_age_to_weeks("born in May 2020"), 999.0)
        self.assertEqual(parse_age_to_weeks("2018"), 999.0)
        # Adult mother cat with kittens in bio should be rejected
        cat = {
            "name": "Mama Cat",
            "sex": "Female",
            "age_str": "born in May 2020",
            "bio": "Adult mother who had kittens in 2020. Pure white."
        }
        res = calculate_bosbos_score(cat)
        self.assertFalse(res["is_match"])
        self.assertEqual(res["age_weeks"], 999.0)

    def test_robust_handling_of_none_and_non_string_types(self):
        # None fields must not trigger TypeError
        cat_nones = {
            "name": None,
            "sex": "Female",
            "age_str": "8 weeks",
            "breed": None,
            "colors": None,
            "bio": None
        }
        res = calculate_bosbos_score(cat_nones)
        self.assertTrue(res["is_match"])

        # Non-string sex and age_str must not trigger AttributeError
        self.assertFalse(calculate_bosbos_score({"sex": 1, "age_str": "8 weeks"})["is_match"])
        self.assertFalse(calculate_bosbos_score({"sex": "Female", "age_str": 12})["is_match"])

if __name__ == "__main__":
    unittest.main()
