import requests
from bs4 import BeautifulSoup
import re
import logging

logger = logging.getLogger(__name__)

COCHRANE_URL = "https://www.cochranehumane.ca/adopt"

def scrape_cochrane_cats():
    """
    Scrapes adoptable cats from Cochrane & Area Humane Society.
    Returns a list of standardized cat dictionaries.
    """
    cats = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        resp = requests.get(COCHRANE_URL, headers=headers, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        items = soup.select(".w-dyn-item")
        for item in items:
            text = item.get_text(separator=" ", strip=True)
            if "Type: Cat" not in text:
                continue
                
            name_el = item.find(["h2", "h3", "h4"])
            name = name_el.get_text(strip=True) if name_el else "Unknown"
            
            # Clean up name if it has "Adopted" status
            is_adopted = "I've Been Adopted" in name or "Adopted" in text
            name_clean = re.sub(r"-\s*I've Been Adopted.*", "", name).strip()
            
            # If already adopted, we can skip or mark as adopted
            if is_adopted:
                continue
                
            img_el = item.find("img")
            img_url = img_el.get("src") if img_el else ""
            
            link_el = item.find("a", href=True)
            link = link_el["href"] if link_el else COCHRANE_URL
            if not link.startswith("http"):
                link = f"https://www.cochranehumane.ca{link}"
                
            sex_match = re.search(r"Sex:\s*([A-Za-z]+)", text)
            sex = sex_match.group(1).strip() if sex_match else "Unknown"
            
            age_match = re.search(r"Age:\s*([0-9]+\s*(?:Months|Month|Weeks|Week|Years|Year|Under 1 Year))", text, re.I)
            age = age_match.group(1).strip() if age_match else "Under 1 Year"
            
            breed_match = re.search(r"Breed:\s*([A-Za-z\s]+?)(?:Age:|$)", text)
            breed = breed_match.group(1).strip() if breed_match else "Domestic Shorthair"
            
            cats.append({
                "id": f"cochrane_{name_clean.lower().replace(' ', '_')}",
                "name": name_clean,
                "shelter": "Cochrane & Area Humane Society",
                "shelter_location": "Cochrane, AB (West Calgary commuter area)",
                "shelter_phone": "(403) 932-2072",
                "sex": sex,
                "age_str": age,
                "breed": breed,
                "personality": "Available for Adoption",
                "image_url": img_url,
                "bio": f"{name_clean} is a lovely {breed} kitten currently looking for a forever home at Cochrane Humane Society.",
                "adoption_url": link,
                "source_type": "Humane Society"
            })
    except Exception as e:
        logger.error(f"Error scraping Cochrane Humane: {e}")
        
    return cats
