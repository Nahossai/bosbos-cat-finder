import requests
from bs4 import BeautifulSoup
import re
import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

CALGARY_URL = "https://24petconnect.com/CalgaryAdopt?at=cat"
BASE_URL = "https://24petconnect.com"
SHELTER_NAME = "City of Calgary Animal Services"
SHELTER_LOCATION = "2201 Portland Street SE, Calgary, AB"
SHELTER_PHONE = "(403) 268-2489"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def _fetch_calgary_detail(cat: dict) -> dict:
    """
    Fetches the detail page for a City of Calgary animal to extract
    the rich biography from og:description and any additional image URLs.
    """
    aid = cat.get("raw_id")
    detail_url = cat.get("adoption_url")
    if not aid or not detail_url:
        return cat

    try:
        resp = requests.get(detail_url, headers=HEADERS, timeout=8)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Extract og:description
            desc_meta = soup.find("meta", property="og:description")
            if desc_meta and desc_meta.get("content"):
                content = desc_meta["content"].strip()
                # Clean up any duplicate spacing or trailing ellipsis
                clean_bio = re.sub(r"\s+", " ", content).strip()
                if clean_bio:
                    cat["bio"] = clean_bio

            # Extract any additional image URLs from detail page
            photos = list(cat.get("images", []))
            for img in soup.find_all("img"):
                src = img.get("src", "")
                if "/image/" in src:
                    full_src = src if src.startswith("http") else f"{BASE_URL}{src}"
                    if full_src not in photos:
                        photos.append(full_src)

            if photos:
                cat["images"] = photos
                cat["image_url"] = photos[0]
                cat["photos_count"] = len(photos)
    except Exception as e:
        logger.warning(f"Could not fetch Calgary detail page for {cat.get('name')} ({aid}): {e}")

    return cat

def scrape_calgary_cats() -> list[dict]:
    """
    Scrapes adoptable cats from City of Calgary Animal Services (24Petconnect).
    Parses div.gridResult items and extracts detail pages for full bios and images.
    Returns a list of standardized cat dictionaries adhering to the PROJECT.md interface contract.
    """
    cats = []
    seen_ids = set()

    try:
        resp = requests.get(CALGARY_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Discover pages if pagination exists
        urls_to_scrape = [CALGARY_URL]
        page_links = soup.select("ul.pagination li.page-item span.page-link[onclick*='MoreAnimals']")
        for pl in page_links:
            onclick = pl.get("onclick", "")
            m = re.search(r"MoreAnimals\(['\"]?(\d+)['\"]?,\s*['\"]?([^'\"]+)['\"]?,\s*['\"]?([^'\"]+)['\"]?\)", onclick)
            if m:
                idx, url_name, at_val = m.groups()
                p_url = f"{BASE_URL}/{url_name}?index={idx}&at={at_val}"
                if p_url not in urls_to_scrape:
                    urls_to_scrape.append(p_url)

        for page_idx, page_url in enumerate(urls_to_scrape):
            if page_idx > 0:
                try:
                    p_resp = requests.get(page_url, headers=HEADERS, timeout=20)
                    p_resp.raise_for_status()
                    p_soup = BeautifulSoup(p_resp.text, "html.parser")
                except Exception as pe:
                    logger.warning(f"Could not fetch Calgary page {page_url}: {pe}")
                    continue
            else:
                p_soup = soup

            grid_items = p_soup.select("div.gridResult")
            for div in grid_items:
                # Animal ID
                aid = div.get("id", "").replace("Result_", "").strip()
                if not aid:
                    onclick = div.get("onclick", "")
                    m = re.search(r"Details\([^,]+,\s*[^,]+,\s*['\"]([^'\"]+)['\"]", onclick)
                    if m:
                        aid = m.group(1).strip()
                if not aid or aid in seen_ids:
                    continue
                seen_ids.add(aid)

                # Name
                name_el = div.select_one("div.line_Name span.text_Name")
                raw_name = name_el.get_text(strip=True) if name_el else aid
                clean_name = re.sub(r"\s*\(A\d+\)\s*$", "", raw_name, flags=re.I).strip().title()
                if not clean_name:
                    clean_name = raw_name.strip()

                # Sex / Gender
                gender_el = div.select_one("div.line_Gender span.text_Gender")
                gender_raw = gender_el.get_text(strip=True) if gender_el else ""
                gender_lower = gender_raw.lower()
                if "female" in gender_lower:
                    sex = "Female"
                elif "male" in gender_lower:
                    sex = "Male"
                else:
                    sex = "Unknown"

                # Age
                age_el = div.select_one("div.line_Age span.text_Age")
                age_str = age_el.get_text(strip=True) if age_el else "Unknown"

                # Breed
                breed_el = div.select_one("div.line_Breed span.text_Breed")
                breed = breed_el.get_text(strip=True) if breed_el else "Domestic Shorthair"

                # Animal type verification
                atype_el = div.select_one("div.line_Animaltype span.text_Animaltype")
                atype_str = atype_el.get_text(strip=True).lower() if atype_el else "cat"
                if "cat" not in atype_str:
                    continue

                # Primary Image
                img_el = div.select_one("img")
                img_src = img_el.get("src", "") if img_el else ""
                if img_src and not img_src.startswith("http"):
                    img_src = f"{BASE_URL}{img_src}"
                photos = [img_src] if img_src else []

                detail_url = f"{BASE_URL}/DetailsMain/CLGR/{aid}"
                fallback_bio = f"{clean_name} is a {sex.lower()} {breed} ({age_str}) currently available for adoption at City of Calgary Animal Services."

                cats.append({
                    "id": f"CLGR-{aid}",
                    "raw_id": aid,
                    "name": clean_name,
                    "shelter": SHELTER_NAME,
                    "shelter_location": SHELTER_LOCATION,
                    "shelter_phone": SHELTER_PHONE,
                    "sex": sex,
                    "age_str": age_str,
                    "breed": breed,
                    "personality": "Available for Adoption",
                    "image_url": img_src,
                    "images": photos,
                    "photos_count": len(photos),
                    "bio": fallback_bio,
                    "adoption_url": detail_url,
                    "source_type": "Municipal Animal Services"
                })

        # Fetch detail pages in parallel to enrich bio and images
        if cats:
            with ThreadPoolExecutor(max_workers=6) as executor:
                cats = list(executor.map(_fetch_calgary_detail, cats))

    except Exception as e:
        logger.error(f"Error scraping City of Calgary Animal Services: {e}")

    return cats
