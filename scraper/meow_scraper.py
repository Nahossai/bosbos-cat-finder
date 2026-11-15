import requests
from bs4 import BeautifulSoup
import re
import logging

logger = logging.getLogger(__name__)

MEOW_URL = "https://meowfoundation.com/adoptable-cats/"

def scrape_meow_cats():
    """
    Scrapes adoptable cats from MEOW Foundation.
    Returns a list of standardized cat dictionaries.
    """
    cats = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        resp = requests.get(MEOW_URL, headers=headers, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        blocks = soup.select("div.cat-block")
        for b in blocks:
            cat_id = b.get("data-cat-id", "")
            personality = b.get("data-personality", "")
            
            name_el = b.select_one(".cat-name")
            name = name_el.get_text(strip=True) if name_el else "Unknown"
            
            img_el = b.select_one(".cat-thumbnail img")
            img_url = img_el.get("src", "") if img_el else ""
            
            details_el = b.select_one(".cat-details p")
            details_text = details_el.get_text(separator=" ", strip=True) if details_el else ""
            
            sex_match = re.search(r"Sex:\s*([A-Za-z]+)", details_text)
            sex = sex_match.group(1).strip() if sex_match else "Unknown"
            
            age_match = re.search(r"Age:\s*([^.]+)", details_text)
            age = age_match.group(1).strip() if age_match else "Unknown"
            
            bio_el = b.select_one(".cat-bio")
            bio = bio_el.get_text(separator=" ", strip=True) if bio_el else ""
            
            cats.append({
                "id": f"meow_{cat_id}" if cat_id else f"meow_{name.lower().replace(' ', '_')}",
                "name": name,
                "shelter": "MEOW Foundation",
                "shelter_location": "Calgary, AB (35 Skyline Cres NE)",
                "shelter_phone": "(403) 230-6033",
                "sex": sex,
                "age_str": age,
                "breed": "Domestic Shorthair / Rescue Mix",
                "personality": personality,
                "image_url": img_url,
                "bio": bio,
                "adoption_url": MEOW_URL,
                "source_type": "Cat-Only Rescue Shelter"
            })
    except Exception as e:
        logger.error(f"Error scraping MEOW Foundation: {e}")
        
    return cats
