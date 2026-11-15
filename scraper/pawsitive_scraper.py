import requests
from bs4 import BeautifulSoup
import json
import re
import calendar
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

PAWSITIVE_URL = "https://www.pawsitivematch.org/adoptable-cats"
BASE_URL = "https://www.pawsitivematch.org"
SHELTER_NAME = "Pawsitive Match Rescue Foundation"
SHELTER_LOCATION = "Calgary, AB"
SHELTER_PHONE = "(403) 456-5998"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

MONTHS_MAP = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}

def _clean_wix_image_url(val: str) -> str:
    """
    Normalizes Wix image URLs or slugs to a public static image CDN URL.
    E.g. wix:image://v1/b0bcb0_...~mv2.jpg/filename.jpg#originWidth=...
    -> https://static.wixstatic.com/media/b0bcb0_...~mv2.jpg
    """
    if not val:
        return ""
    if val.startswith("http"):
        return val
    m = re.search(r"wix:image://v1/([^/#]+)", val)
    if m:
        return f"https://static.wixstatic.com/media/{m.group(1)}"
    if "~mv2" in val or val.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        return f"https://static.wixstatic.com/media/{val}"
    return ""

def _compute_age_string(bio: str, age_category: str) -> str:
    """
    Computes an informative age string from the cat's bio (e.g. 'born approximately August 2026')
    and category (e.g. 'Kitten', 'Adult', 'Senior').
    """
    now = datetime.utcnow()
    m = re.search(r"born\s+approximately\s+([A-Za-z]+)\s+(\d{4})", bio, re.I)
    if m:
        b_month_name = m.group(1).lower()
        b_year = int(m.group(2))
        b_month = MONTHS_MAP.get(b_month_name)
        if b_month:
            diff_m = (now.year - b_year) * 12 + (now.month - b_month)
            if diff_m <= 0:
                diff_m = 1
            if diff_m < 12:
                return f"{diff_m} months old (born {m.group(1)} {b_year})"
            else:
                years = diff_m // 12
                rem = diff_m % 12
                if rem:
                    return f"{years} years {rem} months old"
                return f"{years} years old"

    if age_category.lower() == "kitten":
        return "Kitten (under 6 months)"
    elif age_category:
        return age_category

    return "Unknown"

def scrape_pawsitive_cats() -> list[dict]:
    """
    Scrapes adoptable cats from Pawsitive Match Rescue Foundation (Wix CMS).
    Extracts structured JSON from <script id="wix-warmup-data"> in the AdoptableCats collection.
    Returns a list of standardized cat dictionaries adhering to the PROJECT.md interface contract.
    """
    cats = []

    try:
        resp = requests.get(PAWSITIVE_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        warmup_script = soup.find("script", id="wix-warmup-data")
        if not warmup_script or not warmup_script.string:
            logger.error("Could not find <script id='wix-warmup-data'> on Pawsitive Match page.")
            return cats

        data = json.loads(warmup_script.string)
        records = (
            data.get("appsWarmupData", {})
            .get("dataBinding", {})
            .get("dataStore", {})
            .get("recordsByCollectionId", {})
            .get("AdoptableCats", {})
        )

        logger.info(f"Found {len(records)} adoptable cat records in Pawsitive Match warmup data.")

        for record_key, cat in records.items():
            cat_id = cat.get("_id") or record_key
            name = (cat.get("title_fld") or "Unknown").strip()

            # Description field contains age, sex, and breed separated by dots
            desc_html = cat.get("description_fld") or ""
            clean_desc = BeautifulSoup(desc_html, "html.parser").get_text(strip=True)
            parts = [p.strip() for p in clean_desc.split("·") if p.strip()]

            # Bio description
            bio_raw = (cat.get("desc") or "").strip()
            # Clean stray HTML tags from bio if any
            bio = BeautifulSoup(bio_raw, "html.parser").get_text(separator=" ", strip=True) if "<" in bio_raw else bio_raw

            # Sex extraction
            clean_lower = clean_desc.lower()
            if "female" in clean_lower:
                sex = "Female"
            elif "male" in clean_lower:
                sex = "Male"
            else:
                # Search bio for gendered pronouns
                if re.search(r"\b(she|her)\b", bio, re.I):
                    sex = "Female"
                elif re.search(r"\b(he|him|his)\b", bio, re.I):
                    sex = "Male"
                else:
                    sex = "Unknown"

            # Breed extraction
            breed = "Domestic Shorthair"
            if len(parts) >= 3:
                breed = parts[2].strip()
            elif len(parts) == 2 and parts[1].strip() not in ["Female", "Male"]:
                breed = parts[1].strip()

            # Age string computation
            age_category = parts[0].strip() if parts else "Unknown"
            age_str = _compute_age_string(bio, age_category)

            # Images extraction (primary + mediagallery)
            images = []
            primary_url = _clean_wix_image_url(cat.get("image_fld", ""))
            if primary_url:
                images.append(primary_url)

            gallery = cat.get("mediagallery") or []
            for item in gallery:
                img_candidate = item.get("slug") or item.get("src") or ""
                img_url = _clean_wix_image_url(img_candidate)
                if img_url and img_url not in images:
                    images.append(img_url)

            primary_image = images[0] if images else ""

            # Adoption profile URL
            link = cat.get("link-adoptable-cats-1-title_fld", "")
            if not link:
                for k in cat:
                    if "link" in k and isinstance(cat[k], str) and cat[k]:
                        link = cat[k]
                        break

            if link and link.startswith("http"):
                adoption_url = link
            elif link:
                adoption_url = f"{BASE_URL}{link}"
            else:
                adoption_url = PAWSITIVE_URL

            fallback_bio = bio if bio else f"{name} is a {sex.lower()} {breed} looking for a loving home with Pawsitive Match Rescue Foundation."

            cats.append({
                "id": f"pmrf-{cat_id}",
                "raw_id": cat_id,
                "name": name,
                "shelter": SHELTER_NAME,
                "shelter_location": SHELTER_LOCATION,
                "shelter_phone": SHELTER_PHONE,
                "sex": sex,
                "age_str": age_str,
                "breed": breed,
                "personality": "Available for Adoption",
                "image_url": primary_image,
                "images": images,
                "photos_count": len(images),
                "bio": fallback_bio,
                "adoption_url": adoption_url,
                "source_type": "Foster-Based Rescue"
            })

    except Exception as e:
        logger.error(f"Error scraping Pawsitive Match: {e}")

    return cats
