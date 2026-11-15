import requests
from bs4 import BeautifulSoup
import re
import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

CHS_BASE = "https://www.calgaryhumane.ca/adopt/cats/"

def scrape_chs_cats() -> list[dict]:
    """
    Scrapes adoptable cats from Calgary Humane Society across all PetPress pagination pages (?pg=1, ?pg=2, ...).
    Bypasses WP Engine / Cloudflare caching via pagination queries and headers.
    Inspects detail page memos to identify "started the adoption process" and sets personality to "Adoption Pending".
    Returns a list of standardized cat dictionaries.
    """
    cats = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
    }

    raw_items = []
    seen_ids = set()
    pg = 1

    try:
        while True:
            page_url = f"{CHS_BASE}?pg={pg}"
            resp = requests.get(page_url, headers=headers, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            items = soup.select("div.pp_listitem")
            if not items:
                break

            new_items_found = 0
            for item in items:
                name_el = item.select_one(".pp_inlinename")
                name = name_el.get_text(strip=True) if name_el else "Unknown"

                link_el = item.select_one("a[href^='?id=']")
                animal_id = link_el.get("href", "").replace("?id=", "").strip() if link_el else ""
                if animal_id and animal_id in seen_ids:
                    continue
                if animal_id:
                    seen_ids.add(animal_id)
                new_items_found += 1

                img_el = item.select_one("img.pp_heroimage")
                base_img = img_el.get("src", "") if img_el else ""
                detail_url = f"{CHS_BASE}?id={animal_id}" if animal_id else CHS_BASE

                item_text = item.get_text(separator=" ", strip=True)

                # Sex detection
                classes = item.get("class", [])
                if "pp_Female" in classes:
                    sex = "Female"
                elif "pp_Male" in classes:
                    sex = "Male"
                else:
                    sex_match = re.search(r"Sex:\s*([A-Za-z]+)", item_text)
                    sex_raw = sex_match.group(1).strip() if sex_match else "Unknown"
                    if sex_raw.lower() in ["female", "f"]:
                        sex = "Female"
                    elif sex_raw.lower() in ["male", "m"]:
                        sex = "Male"
                    else:
                        sex = "Unknown"

                # Age detection
                age_match = re.search(r"Age:\s*([^<]+?)(?:Sex:|$)", item_text)
                age = age_match.group(1).strip() if age_match else "Unknown"

                # Breed detection
                breed_match = re.search(r"Breed:\s*([^<]+)", item_text)
                breed = breed_match.group(1).strip() if breed_match else "Domestic Shorthair"

                safe_id = f"chs_{animal_id}" if animal_id else f"chs_{re.sub(r'[^a-z0-9_]', '', name.lower().replace(' ', '_'))}"

                raw_items.append({
                    "id": safe_id,
                    "name": name,
                    "shelter": "Calgary Humane Society",
                    "shelter_location": "Calgary, AB (4455 110 Ave SE)",
                    "shelter_phone": "(403) 205-4455",
                    "sex": sex,
                    "age_str": age,
                    "breed": breed,
                    "animal_id": animal_id,
                    "base_img": base_img,
                    "detail_url": detail_url,
                    "source_type": "Humane Society Shelter"
                })

            pag_el = soup.select_one(".pp_paginationlinkset")
            if not pag_el or f"?pg={pg+1}" not in str(pag_el) or new_items_found == 0:
                break
            pg += 1

        def fetch_detail(c: dict) -> dict:
            photos = [c["base_img"]] if c.get("base_img") else []
            bio = ""
            status = "Available for Adoption"

            if c.get("animal_id"):
                try:
                    d_resp = requests.get(c["detail_url"], headers=headers, timeout=8)
                    if d_resp.status_code == 200:
                        d_soup = BeautifulSoup(d_resp.text, "html.parser")

                        detail_imgs = [img.get("src") for img in d_soup.select("#pp_photosection img, .pp_photodiv img") if img.get("src")]
                        for d_img in detail_imgs:
                            if d_img not in photos:
                                photos.append(d_img)

                        memo_el = d_soup.select_one("#pp_memo")
                        if memo_el:
                            bio = memo_el.get_text(separator=" ", strip=True)
                            if any(k in bio.lower() for k in [
                                "started the adoption process",
                                "no longer available",
                                "adoption pending",
                                "application pending"
                            ]):
                                status = "Adoption Pending"
                except Exception as de:
                    logger.warning(f"Could not fetch CHS detail page for {c['name']} ({c['animal_id']}): {de}")

            c["image_url"] = photos[0] if photos else ""
            c["images"] = photos
            c["photos_count"] = len(photos)
            c["bio"] = bio
            c["personality"] = status
            c["adoption_url"] = c["detail_url"]
            c.pop("base_img", None)
            c.pop("detail_url", None)
            c.pop("animal_id", None)
            return c

        with ThreadPoolExecutor(max_workers=6) as ex:
            cats = list(ex.map(fetch_detail, raw_items))

    except Exception as e:
        logger.error(f"Error scraping Calgary Humane Society: {e}")

    return cats
