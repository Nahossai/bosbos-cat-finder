import requests
from bs4 import BeautifulSoup
import re
import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

MEOW_URL = "https://meowfoundation.com/adoptable-cats/"

def _get_extra_photos_for_cat(cat_id, base_img):
    photos = [base_img] if base_img else []
    if not cat_id:
        return photos
    for seq in range(2, 5):
        url = f"https://can01e.sheltermanager.com/service?account=mf2728&method=animal_image&animalid={cat_id}&seq={seq}"
        try:
            r = requests.get(url, timeout=3)
            if r.status_code == 200 and r.content != b"NOPIC" and len(r.content) > 100:
                photos.append(url)
            else:
                break
        except Exception:
            break
    return photos

def scrape_meow_cats():
    """
    Scrapes adoptable cats from MEOW Foundation including multiple images.
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
            
            bio_el = b.select_one(".cat-bio")
            bio = bio_el.get_text(separator=" ", strip=True) if bio_el else ""
            
            # Check if adopted
            if "adopted" in name.lower() or "has been adopted" in bio.lower():
                logger.info(f"Skipping adopted cat: {name}")
                continue
                
            sex_match = re.search(r"Sex:\s*([A-Za-z]+)", details_text)
            sex = sex_match.group(1).strip() if sex_match else "Unknown"
            
            age_match = re.search(r"Age:\s*([^.]+)", details_text)
            age = age_match.group(1).strip() if age_match else "Unknown"
            
            cats.append({
                "id": f"meow_{cat_id}" if cat_id else f"meow_{name.lower().replace(' ', '_')}",
                "raw_id": cat_id,
                "name": name,
                "shelter": "MEOW Foundation",
                "shelter_location": "Calgary, AB (35 Skyline Cres NE)",
                "shelter_phone": "(403) 230-6033",
                "sex": sex,
                "age_str": age,
                "breed": "Domestic Shorthair / Rescue Mix",
                "personality": personality,
                "image_url": img_url,
                "images": [img_url] if img_url else [],
                "photos_count": 1 if img_url else 0,
                "bio": bio,
                "adoption_url": MEOW_URL,
                "source_type": "Cat-Only Rescue Shelter"
            })
            
        # Probe extra pictures in parallel for kittens / candidates
        def fetch_extra(c):
            if c.get("raw_id"):
                c["images"] = _get_extra_photos_for_cat(c["raw_id"], c["image_url"])
                c["photos_count"] = len(c["images"])
            return c
            
        with ThreadPoolExecutor(max_workers=8) as ex:
            cats = list(ex.map(fetch_extra, cats))
            
    except Exception as e:
        logger.error(f"Error scraping MEOW Foundation: {e}")
        
    return cats
