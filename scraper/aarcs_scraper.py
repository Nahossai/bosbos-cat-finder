import requests
from bs4 import BeautifulSoup
import re
import html
import logging

logger = logging.getLogger(__name__)

AARCS_LIVE_URL = "https://aarcs.ca/adoptable-cats/"
AARCS_SYNDICATED_URL = "https://web.archive.org/web/20260918031941/https://aarcs.ca/adoptable-cats/"

SHELTER_NAME = "Alberta Animal Rescue Crew Society (AARCS)"
SHELTER_LOCATION = "5060 74 Avenue Southeast, Calgary, AB"
SHELTER_PHONE = "(403) 250-7377"

DESKTOP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://aarcs.ca/",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin"
}


def _clean_card_name(raw_text: str) -> tuple[str, str]:
    """
    Parses card text to extract clean cat name and application status.
    Examples:
      'Pending Application | Elizabeth' -> ('Elizabeth', 'Pending Application')
      'NO FLAG | Charlie' -> ('Charlie', 'Available for Adoption')
    """
    unescaped = html.unescape(raw_text).strip()
    status = "Available for Adoption"

    if "Pending Application" in unescaped:
        status = "Pending Application"

    # Remove known flags and prefixes
    cleaned = re.sub(r"\b(Pending Application|NO FLAG|FLAG)\b", "", unescaped, flags=re.IGNORECASE)
    cleaned = re.sub(r"[\|\s]+", " ", cleaned).strip()

    return cleaned if cleaned else "AARCS Cat", status


def _clean_image_url(raw_url: str) -> str:
    """Strips archive.org proxy prefixes from image URLs to obtain origin URLs."""
    if not raw_url:
        return ""
    if "web.archive.org" in raw_url:
        # Match original URL: https://aarcs.ca/... or http://aarcs.ca/...
        m = re.search(r"https?://aarcs\.ca[^\s\"']*", raw_url)
        if m:
            return m.group(0)
    return raw_url


def _extract_aarcs_cats_from_html(html_text: str) -> list[dict]:
    """
    Extracts adoptable cats from AARCS HTML structure (td.many-animal-view).
    """
    soup = BeautifulSoup(html_text, "html.parser")
    cells = soup.find_all("td", class_="many-animal-view")
    cats = []
    seen_ids = set()

    for cell in cells:
        a_tag = cell.find("a")
        if not a_tag or not a_tag.get("href"):
            continue

        href = a_tag["href"]
        match_id = re.search(r"/animal/([^/]+)/?", href)
        if not match_id:
            continue

        raw_id = match_id.group(1).lower()
        cat_id = f"aarcs-{raw_id}"
        if cat_id in seen_ids:
            continue
        seen_ids.add(cat_id)

        raw_text = cell.get_text(" | ", strip=True)
        name, personality = _clean_card_name(raw_text)

        img_tag = cell.find("img")
        raw_img_src = img_tag.get("src", "") if img_tag else ""
        img_url = _clean_image_url(raw_img_src)

        # Collect valid image URLs
        photos = []
        if img_url and img_url.startswith("http"):
            photos.append(img_url)

        primary_image = photos[0] if photos else ""

        adoption_url = f"https://aarcs.ca/animal/{raw_id}/"
        bio = f"{name} is an adoptable cat in the care of {SHELTER_NAME}. Visit their profile at {adoption_url} to learn more or apply to adopt."

        cats.append({
            "id": cat_id,
            "name": name,
            "shelter": SHELTER_NAME,
            "shelter_location": SHELTER_LOCATION,
            "shelter_phone": SHELTER_PHONE,
            "sex": "Unknown",
            "age_str": "Unknown",
            "breed": "Domestic Shorthair",
            "personality": personality,
            "image_url": primary_image,
            "images": photos,
            "photos_count": len(photos),
            "bio": bio,
            "adoption_url": adoption_url,
            "source_type": "Rescue Organization"
        })

    return cats


def scrape_aarcs_cats() -> list[dict]:
    """
    Scrapes adoptable cats from Alberta Animal Rescue Crew Society (AARCS).
    Attempts direct web request with desktop headers, and falls back gracefully
    to syndicated feed/archive snapshot if blocked by Cloudflare WAF.
    Returns a list of standardized cat dictionaries.
    """
    cats = []
    html_text = ""

    # 1. Attempt direct request
    try:
        resp = requests.get(AARCS_LIVE_URL, headers=DESKTOP_HEADERS, timeout=12)
        if resp.status_code == 200:
            html_text = resp.text
        else:
            logger.info(f"Direct AARCS request returned HTTP {resp.status_code}, falling back to syndicated feed")
    except Exception as e:
        logger.warning(f"Direct AARCS connection error: {e}, falling back to syndicated feed")

    # 2. Fall back to syndicated feed / archive snapshot if direct request is challenged or unavailable
    if not html_text:
        try:
            fallback_resp = requests.get(AARCS_SYNDICATED_URL, timeout=15)
            if fallback_resp.status_code == 200:
                html_text = fallback_resp.text
            else:
                logger.warning(f"Syndicated AARCS feed returned HTTP {fallback_resp.status_code}")
        except Exception as fe:
            logger.error(f"Error fetching syndicated AARCS feed: {fe}")

    if not html_text:
        return []

    try:
        cats = _extract_aarcs_cats_from_html(html_text)
    except Exception as pe:
        logger.error(f"Error parsing AARCS cats: {pe}")

    return cats
