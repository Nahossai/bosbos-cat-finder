import requests
from bs4 import BeautifulSoup
import re
import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

MEOW_URL = "https://meowfoundation.com/adoptable-cats/"
REGAL_URL = "https://www.regalcatcafe.com/meet-our-cats"

def _get_extra_photos_for_cat(cat_id: str, base_img: str) -> list[str]:
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

def scrape_regal_cafe_cats(headers: dict) -> list[dict]:
    """
    Scrapes adoptable MEOW Foundation cats hosted at official satellite partner Regal Cat Cafe.
    Filters out cats marked as adopted.
    """
    regal_cats = []
    try:
        resp = requests.get(REGAL_URL, headers=headers, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"Failed to fetch Regal Cat Cafe: HTTP {resp.status_code}")
            return regal_cats

        soup = BeautifulSoup(resp.text, "html.parser")
        blocks = soup.select(".sqs-block-image")

        seen_names = set()
        for block in blocks:
            text = block.get_text(separator=" ", strip=True)
            if "Age:" not in text:
                continue

            # Split name and details before Age:
            name_part = text.split("Age:")[0].strip()

            # Skip cats with adopted marker
            is_adopted = bool(re.search(r"\b(adopted!|adopted)\b", name_part, re.I))
            if is_adopted:
                continue

            # Clean name
            clean_name = re.sub(r"-\s*Adopted.*", "", name_part, flags=re.I)
            clean_name = re.sub(r"@\s*Meow\s*Foundation", "", clean_name, flags=re.I).strip()
            clean_name = re.sub(r"[-\s]+$", "", clean_name).strip()

            if not clean_name or clean_name in seen_names:
                continue
            seen_names.add(clean_name)

            img = block.find("img")
            img_url = (img.get("src") or img.get("data-src") or "") if img else ""
            if img_url.startswith("//"):
                img_url = "https:" + img_url

            # Normalize sex
            g_match = re.search(r"Gender:\s*([A-Za-z]+)", text)
            g_raw = g_match.group(1).strip() if g_match else "Unknown"
            if g_raw.lower() in ["female", "f"]:
                sex = "Female"
            elif g_raw.lower() in ["male", "m"]:
                sex = "Male"
            else:
                sex = "Unknown"

            # Age
            a_match = re.search(r"Age:\s*([^G]+?)(?:Gender:|$)", text)
            age = a_match.group(1).strip() if a_match else "Unknown"

            # Breed / Markings
            m_match = re.search(r"Markings:\s*(.*?)(?:Go Home Date|$)", text)
            breed = m_match.group(1).strip() if m_match else "Domestic Shorthair"

            # Bio text
            b_match = re.search(r"Go Home Date[^\d]+\d{1,2}(?:st|nd|rd|th)?\s*,\s*\d{4}\s*(.*)", text, re.I)
            bio = b_match.group(1).strip() if b_match else text

            safe_id = re.sub(r"[^a-z0-9_]", "", clean_name.lower().replace(" ", "_"))
            regal_cats.append({
                "id": f"meow_regal_{safe_id}",
                "name": clean_name,
                "shelter": "MEOW Foundation",
                "shelter_location": "Regal Cat Cafe (303 10 St NW, Kensington, Calgary)",
                "shelter_phone": "(403) 455-2287",
                "sex": sex,
                "age_str": age,
                "breed": breed,
                "personality": "Available for Adoption",
                "image_url": img_url,
                "images": [img_url] if img_url else [],
                "photos_count": 1 if img_url else 0,
                "bio": bio,
                "adoption_url": REGAL_URL,
                "source_type": "Cat Cafe Partner / MEOW Foundation"
            })
    except Exception as e:
        logger.warning(f"Error scraping Regal Cat Cafe: {e}")

    return regal_cats

def scrape_meow_cats() -> list[dict]:
    """
    Scrapes adoptable cats from MEOW Foundation including all gallery images,
    plus cats hosted at satellite partner Regal Cat Cafe.
    Returns a unified list of standardized cat dictionaries.
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
            personality = b.get("data-personality", "").strip() or "Available for Adoption"

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
            sex_raw = sex_match.group(1).strip() if sex_match else "Unknown"
            if sex_raw.lower() in ["female", "f"]:
                sex = "Female"
            elif sex_raw.lower() in ["male", "m"]:
                sex = "Male"
            else:
                sex = "Unknown"

            age_match = re.search(r"Age:\s*([^.]+)", details_text)
            age = age_match.group(1).strip() if age_match else "Unknown"

            safe_name = re.sub(r"[^a-z0-9_]", "", name.lower().replace(" ", "_"))
            safe_id = f"meow_{cat_id}" if cat_id else f"meow_{safe_name}"

            cats.append({
                "id": safe_id,
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
                "adoption_url": f"https://meowfoundation.com/adoptable-cats/#cat-{cat_id}" if cat_id else MEOW_URL,
                "source_type": "Cat-Only Rescue Shelter"
            })

        # Probe extra pictures in parallel for kittens / candidates
        def fetch_extra(c: dict) -> dict:
            if c.get("raw_id"):
                c["images"] = _get_extra_photos_for_cat(c["raw_id"], c["image_url"])
                c["photos_count"] = len(c["images"])
                c.pop("raw_id", None)
            return c

        with ThreadPoolExecutor(max_workers=8) as ex:
            cats = list(ex.map(fetch_extra, cats))

        # Also scrape satellite partner Regal Cat Cafe
        regal_cats = scrape_regal_cafe_cats(headers)
        cats.extend(regal_cats)

    except Exception as e:
        logger.error(f"Error scraping MEOW Foundation: {e}")

    return cats
