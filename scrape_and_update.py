#!/usr/bin/env python3
import sys
import logging
from scraper.meow_scraper import scrape_meow_cats
from scraper.chs_scraper import scrape_chs_cats
from scraper.cochrane_scraper import scrape_cochrane_cats
from scraper.ranker import calculate_bosbos_score
from scraper.database import save_and_update_cats

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bosbos_runner")

def run_pipeline():
    logger.info("Starting Calgary Bosbos Cat Scraper Pipeline...")
    
    # 1. Fetch from all sources
    all_raw_cats = []
    
    logger.info("Fetching from MEOW Foundation...")
    meow_cats = scrape_meow_cats()
    logger.info(f"Retrieved {len(meow_cats)} cats from MEOW Foundation.")
    all_raw_cats.extend(meow_cats)
    
    logger.info("Fetching from Calgary Humane Society...")
    chs_cats = scrape_chs_cats()
    logger.info(f"Retrieved {len(chs_cats)} cats from Calgary Humane Society.")
    all_raw_cats.extend(chs_cats)
    
    logger.info("Fetching from Cochrane & Area Humane Society...")
    cochrane_cats = scrape_cochrane_cats()
    logger.info(f"Retrieved {len(cochrane_cats)} cats from Cochrane Humane Society.")
    all_raw_cats.extend(cochrane_cats)
    
    logger.info(f"Total cats retrieved across all shelters: {len(all_raw_cats)}")
    
    # 2. Filter and score against Bosbos criteria
    bosbos_candidates = []
    for cat in all_raw_cats:
        res = calculate_bosbos_score(cat)
        if res.get("is_match"):
            cat["bosbos_score"] = res["score"]
            cat["age_weeks"] = res["age_weeks"]
            cat["color_category"] = res["color_category"]
            cat["cute_tags"] = res["cute_tags"]
            cat["score_breakdown"] = res["score_breakdown"]
            bosbos_candidates.append(cat)
            
    logger.info(f"Filtered down to {len(bosbos_candidates)} qualifying Bosbos candidates (Female, <=20 weeks).")
    
    # Sort candidates by score DESC, then age ASC
    bosbos_candidates.sort(key=lambda c: (-c["bosbos_score"], c.get("age_weeks", 99)))
    
    # 3. Save to database and export JSON
    saved_cats = save_and_update_cats(bosbos_candidates)
    logger.info(f"Saved {len(saved_cats)} active candidates to database and public/data/cats.json.")
    
    # 4. Print clean summary table
    print("\n" + "="*80)
    print("🐾 BOSBOS CALGARY DAILY SHORTLIST CANDIDATES 🐾")
    print(f"Target: Female Kittens <= 20 weeks | Bright/White Color Palette | Cute Features")
    print("="*80)
    for idx, c in enumerate(saved_cats, 1):
        star = "🌟 [NEW TODAY] " if c.get("is_new_today") else ""
        print(f"{idx}. {star}{c['name']} (Score: {c['bosbos_score']}/100)")
        print(f"   • Shelter: {c['shelter']} ({c.get('shelter_location', 'Calgary')})")
        print(f"   • Age: {c['age_str']} (~{c.get('age_weeks')} wks) | Sex: {c['sex']}")
        print(f"   • Palette: {c.get('color_category')}")
        if c.get("cute_tags"):
            print(f"   • Cute Traits: {', '.join(c['cute_tags'])}")
        print(f"   • Adoption Link: {c.get('adoption_url')}")
        print("-" * 80)
        
    return saved_cats

if __name__ == "__main__":
    run_pipeline()
