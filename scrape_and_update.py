#!/usr/bin/env python3
import sys
import logging
from scraper.meow_scraper import scrape_meow_cats
from scraper.chs_scraper import scrape_chs_cats
from scraper.cochrane_scraper import scrape_cochrane_cats
from scraper.calgary_scraper import scrape_calgary_cats
from scraper.pawsitive_scraper import scrape_pawsitive_cats
from scraper.arf_scraper import scrape_arf_cats
from scraper.frfa_scraper import scrape_frfa_cats
from scraper.aarcs_scraper import scrape_aarcs_cats
from scraper.ranker import calculate_bosbos_score
from scraper.database import save_and_update_cats

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bosbos_runner")

def run_pipeline():
    logger.info("Starting Calgary Bosbos Cat Scraper Pipeline across all 8 shelters...")
    
    # 1. Fetch from all 8 shelter sources with try/except isolation
    scrapers = [
        ("MEOW Foundation", scrape_meow_cats),
        ("Calgary Humane Society", scrape_chs_cats),
        ("Cochrane & Area Humane Society", scrape_cochrane_cats),
        ("City of Calgary Animal Services", scrape_calgary_cats),
        ("Pawsitive Match Rescue Foundation", scrape_pawsitive_cats),
        ("ARF Alberta", scrape_arf_cats),
        ("FRFA", scrape_frfa_cats),
        ("AARCS", scrape_aarcs_cats),
    ]
    
    all_raw_cats = []
    shelter_stats = {}
    
    for shelter_name, scraper_fn in scrapers:
        logger.info(f"Fetching from {shelter_name}...")
        try:
            cats = scraper_fn()
            if not isinstance(cats, list):
                logger.warning(f"{shelter_name} returned non-list data: {type(cats)}")
                cats = []
            logger.info(f"Retrieved {len(cats)} cats from {shelter_name}.")
            shelter_stats[shelter_name] = len(cats)
            all_raw_cats.extend(cats)
        except Exception as e:
            logger.error(f"Error scraping {shelter_name}: {e}", exc_info=True)
            shelter_stats[shelter_name] = 0
            
    logger.info(f"Total raw cats retrieved across all shelters: {len(all_raw_cats)}")
    
    # 2. Deduplicate cats by id
    unique_cats = []
    seen_ids = set()
    for cat in all_raw_cats:
        cat_id = cat.get("id")
        if cat_id:
            if cat_id not in seen_ids:
                seen_ids.add(cat_id)
                unique_cats.append(cat)
        else:
            unique_cats.append(cat)
            
    logger.info(f"Unique cats after deduplication: {len(unique_cats)}")
    
    # 3. Filter and score against Bosbos criteria
    bosbos_candidates = []
    for cat in unique_cats:
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
    bosbos_candidates.sort(key=lambda c: (-c.get("bosbos_score", 0), c.get("age_weeks", 99)))
    
    # 4. Save to database and export JSON
    saved_cats = save_and_update_cats(bosbos_candidates, all_raw_cats=unique_cats)
    logger.info(f"Saved {len(saved_cats)} active candidates to database and public/data/cats.json.")
    
    # 5. Clean summary reporting
    print("\n" + "="*80)
    print("🐾 CALGARY & AREA SHELTER INGESTION SUMMARY 🐾")
    print("="*80)
    for shelter_name, count in shelter_stats.items():
        print(f"  • {shelter_name:<38}: {count:>4} cats scraped")
    print("-" * 80)
    print(f"  Total Scraped Cats                    : {len(all_raw_cats):>4}")
    print(f"  Total Unique Cats                     : {len(unique_cats):>4}")
    print(f"  Qualifying Bosbos Candidates (<=20w F): {len(saved_cats):>4}")
    print("="*80)
    
    print("\n" + "="*80)
    print("🐾 BOSBOS CALGARY DAILY SHORTLIST CANDIDATES 🐾")
    print("Target: Female Kittens <= 20 weeks | Bright/White Color Palette | Cute Features")
    print("="*80)
    if not saved_cats:
        print("  No qualifying Bosbos candidates currently listed across scraped shelters.")
    for idx, c in enumerate(saved_cats, 1):
        star = "🌟 [NEW TODAY] " if c.get("is_new_today") else ""
        print(f"{idx}. {star}{c['name']} (Score: {c.get('bosbos_score')}/100)")
        print(f"   • Shelter: {c.get('shelter')} ({c.get('shelter_location', 'Calgary')})")
        print(f"   • Age: {c.get('age_str')} (~{c.get('age_weeks')} wks) | Sex: {c.get('sex')}")
        print(f"   • Palette: {c.get('color_category')}")
        if c.get("cute_tags"):
            print(f"   • Cute Traits: {', '.join(c.get('cute_tags'))}")
        photos_num = c.get("photos_count", len(c.get("images", [])))
        print(f"   • Photos: {photos_num} photos available")
        print(f"   • Adoption Link: {c.get('adoption_url')}")
        print("-" * 80)
        
    return saved_cats

if __name__ == "__main__":
    run_pipeline()
