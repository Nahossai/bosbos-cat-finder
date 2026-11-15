import requests
from bs4 import BeautifulSoup
import re
import html
import logging

logger = logging.getLogger(__name__)

FRFA_PAGES = [
    {
        "page_id": 2766,
        "category": "individual",
        "api_url": "https://frfa.ca/wp-json/wp/v2/pages/2766",
        "web_url": "https://frfa.ca/adopt-a-cat/individuals/",
        "personality": "Available for Adoption"
    },
    {
        "page_id": 2761,
        "category": "bonded",
        "api_url": "https://frfa.ca/wp-json/wp/v2/pages/2761",
        "web_url": "https://frfa.ca/adopt-a-cat/bonded-pairs/",
        "personality": "Bonded Pair"
    }
]

SHELTER_NAME = "Feline Rescue Foundation of Alberta (FRFA)"
SHELTER_LOCATION = "Calgary, AB"
SHELTER_PHONE = "(403) 247-2489"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/json,*/*"
}


def _clean_text(raw_text: str) -> str:
    """Cleans text, strips HTML and normalizes whitespace."""
    if not raw_text:
        return ""
    soup = BeautifulSoup(raw_text, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def _parse_sex_from_text(desc: str) -> str:
    """Infers sex from description using explicit terms and pronoun frequency."""
    if not desc or "[description coming]" in desc.lower():
        return "Unknown"

    lower_desc = desc.lower()
    # Check explicit terms
    has_female = bool(re.search(r"\b(female|spayed)\b", lower_desc))
    has_male = bool(re.search(r"\b(male|neutered)\b", lower_desc))

    if has_female and not has_male:
        return "Female"
    if has_male and not has_female:
        return "Male"

    # Pronoun frequency count
    he_count = len(re.findall(r"\b(he|him|his)\b", lower_desc))
    she_count = len(re.findall(r"\b(she|her|hers)\b", lower_desc))

    if she_count > he_count and she_count >= 2:
        return "Female"
    if he_count > she_count and he_count >= 2:
        return "Male"

    return "Unknown"


def _parse_age_from_text(desc: str) -> str:
    """Extracts age string from description with priority on explicit birth year or age."""
    if not desc or "[description coming]" in desc.lower():
        return "Unknown"

    m_yob = re.search(
        r"(?:year\s+of\s+birth|dob|born|birthdate)\s*(?:is|in|:)?\s*([A-Za-z0-9\s,]+?\d{4})",
        desc,
        re.IGNORECASE
    )
    if m_yob:
        return m_yob.group(0).strip()

    m_age = re.search(r"(\d+)\s*(?:years?|months?|weeks?)\s*(?:old)?", desc, re.IGNORECASE)
    if m_age:
        return m_age.group(0).strip()

    if re.search(r"\b(wee\s+kitten|young\s+kitten|kitten|kittens)\b", desc, re.IGNORECASE):
        return "Kitten"

    if re.search(r"\bsenior\b", desc, re.IGNORECASE):
        return "Senior"
    if re.search(r"\badult\b", desc, re.IGNORECASE):
        return "Adult"

    return "Adult"


def _extract_cats_from_html(html_content: str, source_cfg: dict) -> list[dict]:
    """Parses FooGallery items from HTML into standardized cat dicts."""
    soup = BeautifulSoup(html_content, "html.parser")
    items = soup.find_all("div", class_=lambda c: c and "fg-item" in c)
    cats = []

    for item in items:
        a_tag = item.find("a")
        img_tag = item.find("img")

        attachment_id = a_tag.get("data-attachment-id", "") if a_tag else ""
        caption_title = a_tag.get("data-caption-title", "") if a_tag else ""
        caption_desc = a_tag.get("data-caption-desc", "") if a_tag else ""
        full_img_url = a_tag.get("href", "") if a_tag else ""

        img_alt = img_tag.get("alt", "") if img_tag else ""
        img_src = img_tag.get("src", "") if img_tag else ""
        img_fg = img_tag.get("data-src-fg", "") if img_tag else ""

        # Determine name
        raw_name = caption_title or img_alt or "FRFA Cat"
        name = html.unescape(raw_name).strip()

        # Generate unique shelter ID
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        cat_id = f"frfa-{attachment_id}" if attachment_id else f"frfa-{slug}"

        # Clean biography
        cleaned_desc = _clean_text(caption_desc)
        if not cleaned_desc or "[description coming]" in cleaned_desc.lower():
            bio = f"{name} is available for adoption at {SHELTER_NAME}."
        else:
            bio = cleaned_desc

        # Determine age and sex
        age_str = _parse_age_from_text(cleaned_desc)
        sex = _parse_sex_from_text(cleaned_desc)

        # Collect images
        photos = []
        for url in [full_img_url, img_fg, img_src]:
            if url and url.startswith("http") and url not in photos:
                photos.append(url)

        primary_image = photos[0] if photos else ""

        cats.append({
            "id": cat_id,
            "name": name,
            "shelter": SHELTER_NAME,
            "shelter_location": SHELTER_LOCATION,
            "shelter_phone": SHELTER_PHONE,
            "sex": sex,
            "age_str": age_str,
            "breed": "Domestic Shorthair",
            "personality": source_cfg.get("personality", "Available for Adoption"),
            "image_url": primary_image,
            "images": photos,
            "photos_count": len(photos),
            "bio": bio,
            "adoption_url": source_cfg.get("web_url", "https://frfa.ca/adopt-a-cat/"),
            "source_type": "Rescue Organization"
        })

    return cats


def scrape_frfa_cats() -> list[dict]:
    """
    Scrapes adoptable cats from Feline Rescue Foundation of Alberta (FRFA)
    covering both individual cats and bonded pairs.
    Returns a list of standardized cat dictionaries.
    """
    cats = []
    seen_ids = set()

    for cfg in FRFA_PAGES:
        html_content = ""
        # 1. Try WP REST API first
        try:
            resp = requests.get(cfg["api_url"], headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                html_content = data.get("content", {}).get("rendered", "")
        except Exception as e:
            logger.warning(f"Could not fetch FRFA WP REST API page {cfg['page_id']}: {e}")

        # 2. Fall back to direct web page if REST API fails or returned empty
        if not html_content:
            try:
                web_resp = requests.get(cfg["web_url"], headers=HEADERS, timeout=15)
                if web_resp.status_code == 200:
                    html_content = web_resp.text
            except Exception as e:
                logger.warning(f"Could not fetch FRFA web page {cfg['web_url']}: {e}")

        if not html_content:
            continue

        try:
            page_cats = _extract_cats_from_html(html_content, cfg)
            for c in page_cats:
                if c["id"] not in seen_ids:
                    seen_ids.add(c["id"])
                    cats.append(c)
        except Exception as pe:
            logger.error(f"Error parsing FRFA page {cfg['page_id']}: {pe}")

    return cats
