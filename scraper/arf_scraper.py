import requests
from bs4 import BeautifulSoup
import re
import html
import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

ARF_API_URL = "https://arf.ab.ca/wp-json/wp/v2/arf_animal?animal_type=20&per_page=100"
SHELTER_NAME = "Animal Rescue Foundation (ARF) Alberta"
SHELTER_LOCATION = "Calgary, AB"
SHELTER_PHONE = "(403) 243-1910"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

PAGE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def _clean_text(raw_html: str) -> str:
    """Strips HTML tags and unescapes HTML entities."""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def _parse_arf_name(title_rendered: str) -> str:
    """
    Cleans name from title rendered by WordPress.
    Examples:
      '4569F: Cream' -> 'Cream'
      '4554M: Teddy' -> 'Teddy'
      '4433M' -> '4433M'
    """
    unescaped = html.unescape(title_rendered).strip()
    if ":" in unescaped:
        parts = unescaped.split(":", 1)
        name_part = parts[1].strip()
        if name_part:
            return name_part
    return unescaped


def _fetch_arf_detail(cat: dict) -> dict:
    """
    Fetches the detail page for an ARF cat to extract exact Age,
    location tags (e.g. PetSmart - Airdrie), and any extra photos.
    """
    link = cat.get("adoption_url")
    if not link:
        return cat

    try:
        resp = requests.get(link, headers=PAGE_HEADERS, timeout=12)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")

            # Extract Age from tag group: <div class="wp-block-group arf-tag-group"><p>Age: 8 months</p></div>
            for tag_div in soup.find_all(class_=lambda c: c and "arf-tag-group" in c):
                tag_text = tag_div.get_text(strip=True)
                age_match = re.search(r"Age:\s*([^\n\r|]+)", tag_text, re.IGNORECASE)
                if age_match:
                    parsed_age = age_match.group(1).strip()
                    if parsed_age:
                        cat["age_str"] = parsed_age
                        break

            # Extract Location from taxonomy adoption tags (e.g. PetSmart - Airdrie)
            loc_tags = soup.select(".taxonomy-adoption_tags a")
            for lt in loc_tags:
                tag_name = lt.get_text(strip=True)
                if tag_name and "adopt" not in tag_name.lower():
                    cat["shelter_location"] = f"Calgary, AB ({tag_name})"
                    break

            # Extract any additional cat image from detail content (stopping before More Adoptable Animals)
            existing_imgs = list(cat.get("images", []))
            # Locate "More Adoptable Animals" section to avoid other animals' images
            more_heading = soup.find(lambda t: t.name in ["h2", "h3", "h4", "p"] and "More Adoptable Animals" in t.get_text())
            for img in soup.find_all("img"):
                # If image appears after "More Adoptable Animals" heading, stop
                if more_heading and img.find_previous(lambda t: t == more_heading):
                    continue
                src = img.get("src", "")
                if src and "/uploads/" in src and "logo" not in src.lower() and "icon" not in src.lower():
                    if not any(pat in src.lower() for pat in ["wave", "syringe", "microchip", "cone", "stretch", "awc"]):
                        if src not in existing_imgs:
                            existing_imgs.append(src)

            if existing_imgs:
                cat["images"] = existing_imgs
                if not cat.get("image_url"):
                    cat["image_url"] = existing_imgs[0]
                cat["photos_count"] = len(existing_imgs)

    except Exception as e:
        logger.warning(f"Could not fetch ARF detail page for {cat.get('name')}: {e}")

    return cat


def scrape_arf_cats() -> list[dict]:
    """
    Scrapes adoptable cats from Animal Rescue Foundation (ARF) Alberta
    using the public WordPress REST API endpoint and detail page parsing.
    Returns a list of standardized cat dictionaries.
    """
    cats = []

    try:
        resp = requests.get(ARF_API_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        raw_items = resp.json()

        for item in raw_items:
            cat_id = item.get("id")
            if not cat_id:
                continue

            raw_title = item.get("title", {}).get("rendered", "")
            name = _parse_arf_name(raw_title)

            # Determine Sex from taxonomy: 25 = Female, 24 = Male
            animal_sex = item.get("animal_sex", [])
            if 25 in animal_sex:
                sex = "Female"
            elif 24 in animal_sex:
                sex = "Male"
            else:
                # Fallback to checking title for 'F' or 'M'
                if re.search(r"\d+[Ff]\b", raw_title):
                    sex = "Female"
                elif re.search(r"\d+[Mm]\b", raw_title):
                    sex = "Male"
                else:
                    sex = "Unknown"

            # Primary image from Yoast OG image or featured media
            photos = []
            yoast_imgs = item.get("yoast_head_json", {}).get("og_image", [])
            if yoast_imgs and isinstance(yoast_imgs, list):
                for img_obj in yoast_imgs:
                    url = img_obj.get("url")
                    if url and url not in photos:
                        photos.append(url)

            primary_image = photos[0] if photos else ""

            # Bio text
            content_html = item.get("content", {}).get("rendered", "")
            bio = _clean_text(content_html)

            # Excerpt / personality
            excerpt_html = item.get("excerpt", {}).get("rendered", "")
            excerpt_text = _clean_text(excerpt_html)
            personality = excerpt_text if excerpt_text else "Available for Adoption"

            adoption_url = item.get("link", f"https://arf.ab.ca/arf_animal/{item.get('slug', '')}/")

            cat_dict = {
                "id": f"arf-{cat_id}",
                "name": name,
                "shelter": SHELTER_NAME,
                "shelter_location": SHELTER_LOCATION,
                "shelter_phone": SHELTER_PHONE,
                "sex": sex,
                "age_str": "Unknown",
                "breed": "Domestic Shorthair",
                "personality": personality,
                "image_url": primary_image,
                "images": photos,
                "photos_count": len(photos),
                "bio": bio,
                "adoption_url": adoption_url,
                "source_type": "Rescue Organization"
            }
            cats.append(cat_dict)

        # Enrich cats with Age and Location from detail pages in parallel
        if cats:
            with ThreadPoolExecutor(max_workers=6) as executor:
                cats = list(executor.map(_fetch_arf_detail, cats))

    except Exception as e:
        logger.error(f"Error scraping ARF Alberta: {e}")

    return cats
