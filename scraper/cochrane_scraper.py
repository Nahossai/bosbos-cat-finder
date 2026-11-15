import requests
from bs4 import BeautifulSoup
import re
import logging

logger = logging.getLogger(__name__)

COCHRANE_URL = "https://www.cochranehumane.ca/adopt"

def scrape_cochrane_cats():
    """
    Scrapes adoptable cats from Cochrane & Area Humane Society including all gallery photos.
    Filters out cats already adopted.
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
            
            # Filter out cats that are already adopted
            is_adopted = any(k in name.lower() or k in text.lower() for k in [
                "i've been adopted", "ive been adopted", "adopted! 🥳", "status: adopted"
            ])
            if is_adopted:
                logger.info(f"Skipping adopted cat: {name}")
                continue
                
            name_clean = re.sub(r"-\s*I've Been Adopted.*", "", name, flags=re.I).strip()
            
            img_el = item.find("img")
            base_img = img_el.get("src") if img_el else ""
            
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
            
            # Photos collection
            photos = []
            if base_img:
                photos.append(base_img)
                
            bio = f"{name_clean} is a lovely {breed} kitten currently looking for a forever home at Cochrane Humane Society."
            
            # Fetch detail page for all gallery photos
            if link and link != COCHRANE_URL:
                try:
                    d_resp = requests.get(link, headers=headers, timeout=8)
                    if d_resp.status_code == 200:
                        d_soup = BeautifulSoup(d_resp.text, "html.parser")
                        # Strictly scope image search to this animal's own profile header
                        # Never scrape .product7_image-wrapper which contains other shelter animals/dogs
                        header_sec = d_soup.select_one(".section_product-header3, .product-header3_component")
                        if header_sec:
                            for g_img in header_sec.find_all("img"):
                                src = g_img.get("src")
                                if src and "website-files" in src:
                                    if not any(k in src.lower() for k in ["logo", "icon", "paw", "vector", "svg", "footer", "adopted", "sponsor"]):
                                        if src not in photos:
                                            photos.append(src)
                                    
                        # Also check if bio paragraphs exist
                        bio_p = d_soup.select(".product-header3_description p, .rich-text p")
                        if bio_p:
                            bio_texts = [p.get_text(separator=" ", strip=True) for p in bio_p if p.get_text(strip=True)]
                            if bio_texts:
                                bio = " ".join(bio_texts)
                except Exception as de:
                    logger.warning(f"Could not fetch Cochrane detail page for {name_clean}: {de}")
                    
            if not photos and base_img:
                photos = [base_img]
                
            primary_image = photos[0] if photos else ""
            
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
                "image_url": primary_image,
                "images": photos,
                "photos_count": len(photos),
                "bio": bio,
                "adoption_url": link,
                "source_type": "Humane Society"
            })
    except Exception as e:
        logger.error(f"Error scraping Cochrane Humane: {e}")
        
    return cats
