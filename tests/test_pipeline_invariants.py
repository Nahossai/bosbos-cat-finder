"""
Empirical Verification Test Suite for Pipeline Invariants & Data Integrity.
Tested by Challenger 2 for Milestone 5.

Invariants verified:
1. Pipeline idempotency, deduplication, first_seen immutability, date rollover, and likes preservation.
2. Adoption lifecycle transitions: disappearance -> adopted, temporary scrape failure -> active preserved.
3. Sorting and ranking invariants: bosbos_score DESC, age_weeks ASC, tiebreaking, and contract adherence.
4. End-to-end master pipeline execution under fault injection.
"""

import unittest
from unittest.mock import patch, MagicMock
import tempfile
import os
import json
import sqlite3
import random
from datetime import datetime, timedelta

from scraper.database import init_db, save_and_update_cats, export_to_json
from scraper.ranker import calculate_bosbos_score, parse_age_to_weeks
import scrape_and_update


class TestPipelineIdempotencyAndIntegrity(unittest.TestCase):
    """Verifies that multiple sequential executions never duplicate records, preserve first_seen,
    and update is_new_today and last_seen accurately."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_bosbos.db")
        self.json_path = os.path.join(self.temp_dir.name, "cats.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_sample_cat(self, cat_id="meow_snowball", name="Snowball", shelter="MEOW Foundation",
                            sex="Female", age_str="8 weeks", age_weeks=8.0, bosbos_score=95):
        return {
            "id": cat_id,
            "name": name,
            "shelter": shelter,
            "shelter_location": "Calgary, AB",
            "shelter_phone": "(403) 230-6033",
            "sex": sex,
            "age_str": age_str,
            "age_weeks": age_weeks,
            "breed": "Domestic Shorthair - Pure White",
            "personality": "Playful and cuddly",
            "image_url": "https://example.com/snowball1.jpg",
            "images": ["https://example.com/snowball1.jpg"],
            "photos_count": 1,
            "bio": "Sweet cuddly white kitten.",
            "adoption_url": f"https://example.com/adopt/{cat_id}",
            "bosbos_score": bosbos_score,
            "color_category": "Bright White / Cream / Point",
            "cute_tags": ["cuddle", "sweet", "playful"],
            "is_bosbos_match": 1
        }

    def test_idempotent_multiple_sequential_runs_same_day(self):
        """Sequential runs on the same calendar day must produce identical record counts,
        preserve first_seen timestamps, and keep is_new_today as 1 (True)."""
        cat1 = self._create_sample_cat("meow_snowball", "Snowball")
        cat2 = self._create_sample_cat("chs_whiskers", "Whiskers", shelter="Calgary Humane Society",
                                       age_str="12 weeks", age_weeks=12.0, bosbos_score=85)
        raw_pool = [cat1, cat2]

        # Execution 1
        res1 = save_and_update_cats(raw_pool, all_raw_cats=raw_pool, db_path=self.db_path, json_path=self.json_path)
        self.assertEqual(len(res1), 2)
        self.assertTrue(res1[0]["is_new_today"])
        self.assertTrue(res1[1]["is_new_today"])

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT id, first_seen, last_seen, is_new_today, status FROM cats ORDER BY id")
        rows1 = cur.fetchall()
        self.assertEqual(len(rows1), 2)
        cat_ids1 = [r[0] for r in rows1]
        self.assertEqual(cat_ids1, ["chs_whiskers", "meow_snowball"])
        first_seen_snowball_1 = [r[1] for r in rows1 if r[0] == "meow_snowball"][0]
        first_seen_whiskers_1 = [r[1] for r in rows1 if r[0] == "chs_whiskers"][0]
        conn.close()

        # Execution 2 (identical data, subsequent moment)
        res2 = save_and_update_cats(raw_pool, all_raw_cats=raw_pool, db_path=self.db_path, json_path=self.json_path)
        self.assertEqual(len(res2), 2)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT id, first_seen, last_seen, is_new_today, status FROM cats ORDER BY id")
        rows2 = cur.fetchall()
        self.assertEqual(len(rows2), 2, "No duplicate records should be created across runs")
        first_seen_snowball_2 = [r[1] for r in rows2 if r[0] == "meow_snowball"][0]
        first_seen_whiskers_2 = [r[1] for r in rows2 if r[0] == "chs_whiskers"][0]
        last_seen_snowball_2 = [r[2] for r in rows2 if r[0] == "meow_snowball"][0]
        is_new_snowball_2 = [r[3] for r in rows2 if r[0] == "meow_snowball"][0]
        conn.close()

        # Invariants
        self.assertEqual(first_seen_snowball_1, first_seen_snowball_2, "first_seen must remain strictly immutable")
        self.assertEqual(first_seen_whiskers_1, first_seen_whiskers_2, "first_seen must remain strictly immutable")
        self.assertGreaterEqual(last_seen_snowball_2, first_seen_snowball_1, "last_seen must be updated to current time")
        self.assertEqual(is_new_snowball_2, 1, "is_new_today remains 1 on the same calendar day")

        # Execution 3
        res3 = save_and_update_cats(raw_pool, all_raw_cats=raw_pool, db_path=self.db_path, json_path=self.json_path)
        self.assertEqual(len(res3), 2)
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM cats")
        total_cats = cur.fetchone()[0]
        conn.close()
        self.assertEqual(total_cats, 2, "DB row count remains strictly 2")

    def test_in_batch_deduplication(self):
        """If a raw scrape feed produces duplicate entries for the same cat ID within a single run,
        it must not create multiple DB rows or cause errors."""
        cat1 = self._create_sample_cat("meow_dupe", "DupeCat")
        cat1_copy = self._create_sample_cat("meow_dupe", "DupeCat Enriched")
        raw_pool = [cat1, cat1_copy]

        res = save_and_update_cats([cat1_copy], all_raw_cats=raw_pool, db_path=self.db_path, json_path=self.json_path)
        self.assertEqual(len(res), 1)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM cats WHERE id = 'meow_dupe'")
        rows = cur.fetchall()
        conn.close()
        self.assertEqual(len(rows), 1, "Duplicate cat ID collapsed into single entry")

    def test_first_seen_and_new_today_across_date_rollover(self):
        """Simulate day 1 ingestion, followed by day 2 re-scrape.
        Returning cats must have is_new_today=False and identical first_seen.
        New cats arriving on day 2 must have is_new_today=True."""
        cat_day1 = self._create_sample_cat("cat_veteran", "Veteran Cat")

        day1_time = datetime(2026, 11, 15, 10, 0, 0)
        day2_time = datetime(2026, 11, 16, 10, 0, 0)

        # Ingest on Day 1
        with patch("scraper.database.datetime") as mock_dt:
            mock_dt.utcnow.return_value = day1_time
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            res1 = save_and_update_cats([cat_day1], all_raw_cats=[cat_day1], db_path=self.db_path, json_path=self.json_path)
            self.assertEqual(len(res1), 1)
            self.assertTrue(res1[0]["is_new_today"])
            day1_first_seen = res1[0]["first_seen"]
            self.assertEqual(day1_first_seen, day1_time.isoformat())

        # Day 2: Veteran Cat returns, and a newcomer arrives
        cat_day2_new = self._create_sample_cat("cat_newcomer", "Newcomer Cat")
        with patch("scraper.database.datetime") as mock_dt:
            mock_dt.utcnow.return_value = day2_time
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            res2 = save_and_update_cats(
                [cat_day1, cat_day2_new],
                all_raw_cats=[cat_day1, cat_day2_new],
                db_path=self.db_path,
                json_path=self.json_path
            )

            self.assertEqual(len(res2), 2)
            cat_map = {c["id"]: c for c in res2}

            # Veteran Cat
            self.assertEqual(cat_map["cat_veteran"]["first_seen"], day1_first_seen, "first_seen must persist across days")
            self.assertFalse(cat_map["cat_veteran"]["is_new_today"], "Veteran cat on day 2 is NOT new today")

            # Newcomer Cat
            self.assertEqual(cat_map["cat_newcomer"]["first_seen"], day2_time.isoformat())
            self.assertTrue(cat_map["cat_newcomer"]["is_new_today"], "Newcomer cat on day 2 IS new today")

    def test_likes_count_and_user_data_preservation_across_runs(self):
        """User interactions (such as likes_count) must not be wiped when an active cat is re-scraped."""
        cat = self._create_sample_cat("meow_liked", "Liked Cat")

        # Initial run
        save_and_update_cats([cat], all_raw_cats=[cat], db_path=self.db_path, json_path=self.json_path)

        # Simulate user likes
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("UPDATE cats SET likes_count = 42 WHERE id = 'meow_liked'")
        conn.commit()
        conn.close()

        # Subsequent pipeline update with new bio text
        updated_cat = dict(cat)
        updated_cat["bio"] = "Updated bio with even more adorable kitten details!"
        res = save_and_update_cats([updated_cat], all_raw_cats=[updated_cat], db_path=self.db_path, json_path=self.json_path)

        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["likes_count"], 42, "likes_count must be preserved across pipeline runs")
        self.assertEqual(res[0]["bio"], "Updated bio with even more adorable kitten details!")


class TestAdoptionLifecycleTransitions(unittest.TestCase):
    """Verifies adoption state machine:
    - Normal disappearance transitions cat to status = 'adopted' and removes from JSON.
    - Temporary scrape failure PRESERVES active cats without marking them adopted.
    - Re-listing reactivates cats without resetting first_seen.
    - Non-Bosbos adoptable cats are tracked without false adoptions on scrape failures.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_bosbos.db")
        self.json_path = os.path.join(self.temp_dir.name, "cats.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _cat(self, cat_id, name, shelter, is_match=1, score=90, age_weeks=8.0):
        return {
            "id": cat_id,
            "name": name,
            "shelter": shelter,
            "shelter_location": "Calgary, AB",
            "shelter_phone": "(403) 000-0000",
            "sex": "Female",
            "age_str": f"{age_weeks} weeks",
            "age_weeks": age_weeks,
            "breed": "Domestic Shorthair",
            "personality": "Available",
            "image_url": f"https://example.com/{cat_id}.jpg",
            "images": [f"https://example.com/{cat_id}.jpg"],
            "photos_count": 1,
            "bio": f"Bio for {name}",
            "adoption_url": f"https://example.com/adopt/{cat_id}",
            "bosbos_score": score if is_match else 0,
            "color_category": "Standard",
            "cute_tags": [],
            "is_bosbos_match": is_match
        }

    def test_cat_disappearance_transitions_to_adopted(self):
        """When a shelter's scrape completes and a cat is missing from that shelter,
        it transitions to status = 'adopted' and is excluded from cats.json."""
        cat1 = self._cat("meow_1", "Cat One", "MEOW Foundation")
        cat2 = self._cat("meow_2", "Cat Two", "MEOW Foundation")

        # Run 1: Both cats active
        res1 = save_and_update_cats([cat1, cat2], all_raw_cats=[cat1, cat2], db_path=self.db_path, json_path=self.json_path)
        self.assertEqual(len(res1), 2)

        # Run 2: Cat 1 is adopted, only Cat 2 is returned by MEOW Foundation
        res2 = save_and_update_cats([cat2], all_raw_cats=[cat2], db_path=self.db_path, json_path=self.json_path)

        # JSON export verification
        self.assertEqual(len(res2), 1)
        self.assertEqual(res2[0]["id"], "meow_2")

        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        json_ids = [c["id"] for c in data["cats"]]
        self.assertIn("meow_2", json_ids)
        self.assertNotIn("meow_1", json_ids)

        # SQLite status verification
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT id, status FROM cats ORDER BY id")
        statuses = dict(cur.fetchall())
        conn.close()

        self.assertEqual(statuses["meow_1"], "adopted", "Missing cat must transition to 'adopted'")
        self.assertEqual(statuses["meow_2"], "active", "Remaining cat must remain 'active'")

    def test_temporary_shelter_scrape_failure_does_not_mark_adopted(self):
        """CRITICAL INVARIANT: If a shelter scraper fails (e.g. network timeout, 500 error,
        DNS failure, empty return), its active cats MUST NOT transition to 'adopted'.
        They must remain 'active' and preserved in the JSON export."""
        cat_meow = self._cat("meow_1", "MeowCat", "MEOW Foundation")
        cat_chs = self._cat("chs_1", "ChsCat", "Calgary Humane Society")
        cat_cochrane = self._cat("cochrane_1", "CochraneCat", "Cochrane & Area Humane Society")

        # Run 1: All 3 shelters scrape successfully
        initial_pool = [cat_meow, cat_chs, cat_cochrane]
        res1 = save_and_update_cats(initial_pool, all_raw_cats=initial_pool, db_path=self.db_path, json_path=self.json_path)
        self.assertEqual(len(res1), 3)

        # Run 2: Calgary Humane Society scraper fails completely (returns 0 cats).
        # MEOW and Cochrane succeed.
        partial_pool = [cat_meow, cat_cochrane]
        res2 = save_and_update_cats(partial_pool, all_raw_cats=partial_pool, db_path=self.db_path, json_path=self.json_path)

        # Verify DB statuses: chs_1 MUST still be 'active'
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT id, status FROM cats ORDER BY id")
        statuses = dict(cur.fetchall())
        conn.close()

        self.assertEqual(statuses["meow_1"], "active")
        self.assertEqual(statuses["chs_1"], "active", "Failed shelter's cats MUST NOT be marked adopted!")
        self.assertEqual(statuses["cochrane_1"], "active")

        # Verify JSON export includes all active cats
        self.assertEqual(len(res2), 3, "Export must retain active cats from the failed shelter")
        exported_ids = [c["id"] for c in res2]
        self.assertIn("chs_1", exported_ids)
        self.assertIn("meow_1", exported_ids)
        self.assertIn("cochrane_1", exported_ids)

    def test_all_shelters_failing_does_not_corrupt_database(self):
        """If all scrapers fail simultaneously (complete outage), no active cats become adopted."""
        cat1 = self._cat("meow_1", "MeowCat", "MEOW Foundation")
        cat2 = self._cat("chs_1", "ChsCat", "Calgary Humane Society")

        save_and_update_cats([cat1, cat2], all_raw_cats=[cat1, cat2], db_path=self.db_path, json_path=self.json_path)

        # Complete outage: 0 raw cats retrieved
        res_outage = save_and_update_cats([], all_raw_cats=[], db_path=self.db_path, json_path=self.json_path)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT id, status FROM cats")
        statuses = dict(cur.fetchall())
        conn.close()

        self.assertEqual(statuses["meow_1"], "active")
        self.assertEqual(statuses["chs_1"], "active")
        self.assertEqual(len(res_outage), 2, "Export still retains active cats during total outage")

    def test_relisting_adopted_cat_reactivates_with_original_first_seen(self):
        """If an adopted cat reappears in a future scrape, it must transition back to 'active'
        while preserving its original first_seen timestamp."""
        cat = self._cat("meow_relist", "RelistedCat", "MEOW Foundation")

        # 1. Ingest
        save_and_update_cats([cat], all_raw_cats=[cat], db_path=self.db_path, json_path=self.json_path)
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT first_seen FROM cats WHERE id = 'meow_relist'")
        orig_first_seen = cur.fetchone()[0]
        conn.close()

        # 2. Cat adopted (another cat scraped, meow_relist missing)
        other_cat = self._cat("meow_other", "OtherCat", "MEOW Foundation")
        save_and_update_cats([other_cat], all_raw_cats=[other_cat], db_path=self.db_path, json_path=self.json_path)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT status FROM cats WHERE id = 'meow_relist'")
        self.assertEqual(cur.fetchone()[0], "adopted")
        conn.close()

        # 3. Cat relisted (adoption fell through)
        save_and_update_cats([cat, other_cat], all_raw_cats=[cat, other_cat], db_path=self.db_path, json_path=self.json_path)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT status, first_seen FROM cats WHERE id = 'meow_relist'")
        status, first_seen_after = cur.fetchone()
        conn.close()

        self.assertEqual(status, "active", "Relisted cat must transition back to 'active'")
        self.assertEqual(first_seen_after, orig_first_seen, "first_seen must remain unchanged on relisting")

    def test_non_bosbos_cat_lifecycle_and_isolation(self):
        """Non-Bosbos matching cats (e.g. adult cats) must also transition to adopted when missing,
        and must not be marked adopted on shelter scrape failures."""
        adult_chs = self._cat("chs_adult", "Adult Cat", "Calgary Humane Society", is_match=0, score=0, age_weeks=104.0)
        kitten_meow = self._cat("meow_kitten", "Kitten", "MEOW Foundation", is_match=1, score=90, age_weeks=8.0)

        # Initial scrape
        save_and_update_cats([kitten_meow], all_raw_cats=[kitten_meow, adult_chs], db_path=self.db_path, json_path=self.json_path)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT status, is_bosbos_match FROM cats WHERE id = 'chs_adult'")
        row = cur.fetchone()
        self.assertEqual(row, ("active", 0))
        conn.close()

        # Failure at CHS -> adult_chs stays active
        save_and_update_cats([kitten_meow], all_raw_cats=[kitten_meow], db_path=self.db_path, json_path=self.json_path)
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT status FROM cats WHERE id = 'chs_adult'")
        self.assertEqual(cur.fetchone()[0], "active")
        conn.close()

        # CHS succeeds with a DIFFERENT cat -> adult_chs transitions to adopted
        chs_new_cat = self._cat("chs_new", "New Cat", "Calgary Humane Society", is_match=0, score=0)
        save_and_update_cats([kitten_meow], all_raw_cats=[kitten_meow, chs_new_cat], db_path=self.db_path, json_path=self.json_path)
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT status FROM cats WHERE id = 'chs_adult'")
        self.assertEqual(cur.fetchone()[0], "adopted")
        conn.close()


class TestSortingAndRankingInvariants(unittest.TestCase):
    """Verifies that public/data/cats.json and export_to_json strictly enforce:
    1. bosbos_score DESC
    2. age_weeks ASC (tiebreaker)
    under all permutations, boundary values, and synthetic distributions."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_bosbos.db")
        self.json_path = os.path.join(self.temp_dir.name, "cats.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _cat(self, cat_id, score, age_weeks):
        return {
            "id": cat_id,
            "name": f"Cat_{cat_id}",
            "shelter": "Test Shelter",
            "shelter_location": "Calgary, AB",
            "shelter_phone": "(403) 123-4567",
            "sex": "Female",
            "age_str": f"{age_weeks} weeks",
            "age_weeks": age_weeks,
            "breed": "Domestic Shorthair",
            "personality": "Sweet",
            "image_url": "https://example.com/img.jpg",
            "images": ["https://example.com/img.jpg"],
            "photos_count": 1,
            "bio": "Sweet kitten",
            "adoption_url": f"https://example.com/{cat_id}",
            "bosbos_score": score,
            "color_category": "Standard",
            "cute_tags": [],
            "is_bosbos_match": 1
        }

    def test_live_cats_json_sorting_and_schema_invariants(self):
        """Assert that the existing production public/data/cats.json satisfies all invariants."""
        prod_json_path = os.path.join(os.path.dirname(__file__), "..", "public", "data", "cats.json")
        self.assertTrue(os.path.exists(prod_json_path), f"{prod_json_path} must exist")

        with open(prod_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIn("cats", data)
        cats = data["cats"]
        self.assertGreater(len(cats), 0, "Production cats.json must contain candidate cats")

        for i in range(len(cats) - 1):
            c1 = cats[i]
            c2 = cats[i + 1]

            s1, a1 = c1["bosbos_score"], c1["age_weeks"]
            s2, a2 = c2["bosbos_score"], c2["age_weeks"]

            # Invariant 1: Score must be non-increasing
            self.assertGreaterEqual(
                s1, s2,
                f"Score ordering violated at indices {i} and {i+1}: {c1['name']} ({s1}) < {c2['name']} ({s2})"
            )

            # Invariant 2: Tiebreak age must be non-decreasing for equal scores
            if s1 == s2:
                self.assertLessEqual(
                    a1, a2,
                    f"Tiebreaker age violated at indices {i} and {i+1}: score {s1} == {s2}, but age {a1} > {a2}"
                )

        # Invariant 3: All exported cats must be active, female, <= 20.5 weeks
        for c in cats:
            self.assertEqual(c["status"], "active")
            self.assertIn(c["sex"], ["Female", "F"])
            self.assertLessEqual(c["age_weeks"], 20.5)
            self.assertGreaterEqual(c["bosbos_score"], 40, "Candidate matches must have a score >= 40")

    def test_synthetic_permutations_strictly_satisfy_score_desc_age_asc(self):
        """Stress-test export_to_json with a randomized dataset containing multiple tied scores,
        varied ages, and shuffled insertion order."""
        # Define test specs: (score, age_weeks)
        specs = [
            (95, 8.0),
            (95, 10.0),
            (95, 12.0),
            (90, 8.0),
            (90, 9.0),
            (90, 11.5),
            (85, 7.0),
            (85, 14.0),
            (80, 8.0),
            (80, 8.0), # identical score & age
            (70, 15.0),
            (60, 18.0),
            (50, 20.0),
        ]

        cats = [self._cat(f"cat_{i:02d}", s, a) for i, (s, a) in enumerate(specs)]

        # Shuffle insertion order multiple times to verify sort robustness
        for seed in [42, 1337, 9999]:
            random.seed(seed)
            shuffled_cats = list(cats)
            random.shuffle(shuffled_cats)

            # Save to temporary db
            temp_db = os.path.join(self.temp_dir.name, f"test_sort_{seed}.db")
            temp_json = os.path.join(self.temp_dir.name, f"cats_sort_{seed}.json")

            exported = save_and_update_cats(
                shuffled_cats,
                all_raw_cats=shuffled_cats,
                db_path=temp_db,
                json_path=temp_json
            )

            self.assertEqual(len(exported), len(specs))

            for i in range(len(exported) - 1):
                c1 = exported[i]
                c2 = exported[i + 1]
                s1, a1 = c1["bosbos_score"], c1["age_weeks"]
                s2, a2 = c2["bosbos_score"], c2["age_weeks"]

                self.assertGreaterEqual(s1, s2, f"Seed {seed}: Score violated at index {i}")
                if s1 == s2:
                    self.assertLessEqual(a1, a2, f"Seed {seed}: Tiebreak age violated at index {i}")

    def test_non_matching_cats_excluded_from_json(self):
        """Cats with is_bosbos_match=0 or score=0 or status='adopted' must be excluded from JSON."""
        match_cat = self._cat("match_1", score=90, age_weeks=8.0)
        non_match_male = self._cat("male_1", score=0, age_weeks=8.0)
        non_match_male["is_bosbos_match"] = 0
        non_match_male["sex"] = "Male"

        res = save_and_update_cats(
            [match_cat],
            all_raw_cats=[match_cat, non_match_male],
            db_path=self.db_path,
            json_path=self.json_path
        )

        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["id"], "match_1")

        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data["cats"]), 1)
        self.assertEqual(data["cats"][0]["id"], "match_1")


class TestMasterPipelineEndToEndExecution(unittest.TestCase):
    """Executes the master pipeline runner under full normal and simulated failure scenarios."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "pipeline_bosbos.db")
        self.json_path = os.path.join(self.temp_dir.name, "pipeline_cats.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("scrape_and_update.save_and_update_cats")
    def test_run_pipeline_handles_scraper_exceptions_gracefully(self, mock_save):
        """If half of the scrapers throw exceptions and others return valid data,
        run_pipeline must continue and pass valid unique cats to save_and_update_cats."""
        mock_save.return_value = []

        valid_cat = {
            "id": "meow_test",
            "name": "Test Kitten",
            "shelter": "MEOW Foundation",
            "shelter_location": "Calgary, AB",
            "shelter_phone": "(403) 230-6033",
            "sex": "Female",
            "age_str": "8 weeks",
            "breed": "Domestic Shorthair - Pure White",
            "personality": "Sweet",
            "image_url": "https://example.com/test.jpg",
            "images": ["https://example.com/test.jpg"],
            "photos_count": 1,
            "bio": "Sweet white baby kitten.",
            "adoption_url": "https://example.com/adopt/test",
            "source_type": "Cat Shelter"
        }

        with patch("scrape_and_update.scrape_meow_cats", return_value=[valid_cat]), \
             patch("scrape_and_update.scrape_chs_cats", side_effect=ConnectionError("Simulated CHS failure")), \
             patch("scrape_and_update.scrape_cochrane_cats", side_effect=TimeoutError("Simulated Cochrane timeout")), \
             patch("scrape_and_update.scrape_calgary_cats", return_value=[]), \
             patch("scrape_and_update.scrape_pawsitive_cats", side_effect=Exception("Simulated Pawsitive 500")), \
             patch("scrape_and_update.scrape_arf_cats", return_value=[]), \
             patch("scrape_and_update.scrape_frfa_cats", side_effect=RuntimeError("Simulated FRFA failure")), \
             patch("scrape_and_update.scrape_aarcs_cats", return_value=[]):

            res = scrape_and_update.run_pipeline()

            # Pipeline must complete without raising uncaught exceptions
            self.assertTrue(mock_save.called)
            called_candidates = mock_save.call_args[0][0]
            called_raw = mock_save.call_args[1]["all_raw_cats"]

            self.assertEqual(len(called_raw), 1)
            self.assertEqual(called_raw[0]["id"], "meow_test")
            self.assertEqual(len(called_candidates), 1)
            self.assertEqual(called_candidates[0]["id"], "meow_test")
            self.assertGreaterEqual(called_candidates[0]["bosbos_score"], 80)


if __name__ == "__main__":
    unittest.main()
