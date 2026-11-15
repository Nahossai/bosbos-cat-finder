import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

COCHRANE_BASE = "https://www.cochranehumane.ca/adopt"

def scrape_cochrane_cats() -> list[dict]:
    """
    Scrapes adoptable cats from Cochrane & Area Humane Society across all Webflow CMS pages.
    Dynamically follows `a.w-pagination-next` until all pages are retrieved.
    Extracts multi-photo galleries and full bio text from detail pages.
    Filters out cats already adopted.
    Returns a list of standardized cat dictionaries.
    """
    cats = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    current_url = COCHRANE_BASE
    raw_items = []
    seen_urls = set()

    try:
        while current_url and current_url not in seen_urls:
            seen_urls.add(current_url)
            resp = requests.get(current_url, headers=headers, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            items = soup.select(".w-dyn-item")
            for item in items:
                text = item.get_text(separator=" ", strip=True)
                if "Type: Cat" not in text:
                    continue

                name_el = item.find(["h2", "h3", "h4"])
                name = name_el.get_text(strip=True) if name_el else "Unknown"

                # Comprehensive check for adopted cats in title or item text
                # Webflow cards contain adopted markers like:
                # "Martin - I've Been Adopted! 🥳", "Hocus & Pocus - We've Been Adopted! 🥳"
                is_adopted = any(k in name.lower() or k in text.lower() for k in [
                    "i've been adopted", "ive been adopted", "we've been adopted",
                    "weve been adopted", "been adopted", "adopted! 🥳", "status: adopted",
                    "adopted!"
                ])
                if is_adopted:
                    logger.info(f"Skipping adopted Cochrane cat: {name}")
                    continue

                # Clean name of any adopted suffixes or hyphens
                name_clean = re.sub(r"-\s*(?:I've|We've)?\s*Been Adopted.*", "", name, flags=re.I).strip()
                name_clean = re.sub(r"-\s*Adopted.*", "", name_clean, flags=re.I).strip()
                name_clean = re.sub(r"[-\s]+$", "", name_clean).strip()

                img_el = item.find("img")
                base_img = img_el.get("src") if img_el else ""

                link_el = item.find("a", href=True)
                link = urljoin(COCHRANE_BASE, link_el["href"]) if link_el else COCHRANE_BASE

                # Sex detection normalized to Female, Male, or Unknown
                sex_match = re.search(r"Sex:\s*([A-Za-z]+)", text)
                sex_raw = sex_match.group(1).strip() if sex_match else "Unknown"
                if sex_raw.lower() in ["female", "f"]:
                    sex = "Female"
                elif sex_raw.lower() in ["male", "m"]:
                    sex = "Male"
                else:
                    sex = "Unknown"

                # Age detection
                age_match = re.search(r"Age:\s*([0-9]+\s*(?:Months|Month|Weeks|Week|Years|Year|Under 1 Year))", text, re.I)
                age = age_match.group(1).strip() if age_match else "Under 1 Year"

                # Breed detection
                breed_match = re.search(r"Breed:\s*([A-Za-z\s]+?)(?:Age:|$)", text)
                breed = breed_match.group(1).strip() if breed_match else "Domestic Shorthair"

                safe_id_name = re.sub(r"[^a-z0-9_]", "", name_clean.lower().replace(" ", "_"))
                raw_items.append({
                    "id": f"cochrane_{safe_id_name}",
                    "name": name_clean,
                    "shelter": "Cochrane & Area Humane Society",
                    "shelter_location": "Cochrane, AB (West Calgary commuter area)",
                    "shelter_phone": "(403) 932-2072",
                    "sex": sex,
                    "age_str": age,
                    "breed": breed,
                    "personality": "Available for Adoption",
                    "base_img": base_img,
                    "adoption_url": link,
                    "source_type": "Humane Society"
                })

            # Follow Webflow dynamic pagination
            next_btn = soup.select_one("a.w-pagination-next")
            if next_btn and next_btn.get("href"):
                current_url = urljoin(COCHRANE_BASE, next_btn["href"])
            else:
                current_url = None

        def fetch_detail(c: dict) -> dict:
            photos = [c["base_img"]] if c.get("base_img") else []
            bio = f"{c['name']} is a lovely {c['breed']} ({c['age_str']}) currently available for adoption at Cochrane & Area Humane Society."
            link = c.get("adoption_url")
            if link and link != COCHRANE_BASE:
                try:
                    d_resp = requests.get(link, headers=headers, timeout=8)
                    if d_resp.status_code == 200:
                        d_soup = BeautifulSoup(d_resp.text, "html.parser")

                        # Strictly scope image search to profile header component
                        header_sec = d_soup.select_one(".section_product-header3, .product-header3_component")
                        if header_sec:
                            for g_img in header_sec.find_all("img"):
                                src = g_img.get("src")
                                if src and "website-files" in src:
                                    if not any(k in src.lower() for k in ["logo", "icon", "paw", "vector", "svg", "footer", "adopted", "sponsor"]):
                                        if src not in photos:
                                            photos.append(src)

                        # Extract rich bio from .product-header3_bio-wrapper or fallback classes
                        bio_el = d_soup.select_one(".product-header3_bio-wrapper, .product-header3_description, .rich-text")
                        if bio_el and bio_el.get_text(strip=True):
                            bio = bio_el.get_text(separator=" ", strip=True)
                except Exception as de:
                    logger.warning(f"Could not fetch Cochrane detail page for {c['name']}: {de}")

            c["images"] = photos
            c["photos_count"] = len(photos)
            c["image_url"] = photos[0] if photos else ""
            c["bio"] = bio
            c.pop("base_img", None)
            return c

        with ThreadPoolExecutor(max_workers=6) as ex:
            cats = list(ex.map(fetch_detail, raw_items))

    except Exception as e:
        logger.error(f"Error scraping Cochrane Humane: {e}")

    return cats
