import requests
from bs4 import BeautifulSoup
import re
import logging

logger = logging.getLogger(__name__)

CHS_URL = "https://www.calgaryhumane.ca/adopt/cats/"

def scrape_chs_cats():
    """
    Scrapes adoptable cats from Calgary Humane Society.
    Returns a list of standardized cat dictionaries.
    """
    cats = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        resp = requests.get(CHS_URL, headers=headers, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        items = soup.select("div.pp_listitem")
        for item in items:
            name_el = item.select_one(".pp_inlinename")
            name = name_el.get_text(strip=True) if name_el else "Unknown"
            
            img_el = item.select_one("img.pp_heroimage")
            img_url = img_el.get("src", "") if img_el else ""
            
            link_el = item.select_one("a[href^='?id=']")
            animal_id = link_el.get("href", "").replace("?id=", "") if link_el else ""
            detail_url = f"https://www.calgaryhumane.ca/adopt/cats/?id={animal_id}" if animal_id else CHS_URL
            
            item_text = item.get_text(separator=" ", strip=True)
            
            # Sex detection
            classes = item.get("class", [])
            if "pp_Female" in classes:
                sex = "Female"
            elif "pp_Male" in classes:
                sex = "Male"
            else:
                sex_match = re.search(r"Sex:\s*([A-Za-z]+)", item_text)
                sex = sex_match.group(1).strip() if sex_match else "Unknown"
                
            # Age detection
            age_match = re.search(r"Age:\s*([^<]+?)(?:Sex:|$)", item_text)
            age = age_match.group(1).strip() if age_match else "Unknown"
            
            # Breed detection
            breed_match = re.search(r"Breed:\s*([^<]+)", item_text)
            breed = breed_match.group(1).strip() if breed_match else "Domestic Shorthair"
            
            # Calgary Humane Society bio
            bio = ""
            
            cats.append({
                "id": f"chs_{animal_id}" if animal_id else f"chs_{name.lower().replace(' ', '_')}",
                "name": name,
                "shelter": "Calgary Humane Society",
                "shelter_location": "Calgary, AB (4455 110 Ave SE)",
                "shelter_phone": "(403) 205-4455",
                "sex": sex,
                "age_str": age,
                "breed": breed,
                "personality": "Available for Adoption",
                "image_url": img_url,
                "bio": bio,
                "adoption_url": detail_url,
                "source_type": "Humane Society Shelter"
            })
    except Exception as e:
        logger.error(f"Error scraping Calgary Humane Society: {e}")
        
    return cats
