import re

BRIGHT_WHITE_KEYWORDS = [
    "white", "cream", "flame point", "lynx point", "lilac point", "colorpoint", 
    "seal point", "ivory", "peach", "buff", "champagne", "snow", "pearl", "blonde"
]

BRIGHT_ACCENT_KEYWORDS = [
    "calico", "torbie", "silver", "light grey", "light gray", "orange and white",
    "ginger and white", "bicolor", "bi-color", "tuxedo", "pastel"
]

CUTE_KEYWORDS = [
    "cuddle", "cuddly", "sweet", "sweetest", "tiny", "little", "purr", "purring",
    "big eyes", "playful", "adorable", "gentle", "fluffy", "soft", "snuggle",
    "snuggles", "baby", "cozy", "friendly", "affectionate", "loving", "cute"
]

def parse_age_to_weeks(age_str: str):
    """
    Parses a string like '18 weeks', '2 Months', '4 months 3 days', '8 wks' into a float representing weeks.
    Returns None if cannot parse or age is unknown/adult.
    """
    if not age_str:
        return None
    
    text = age_str.lower().strip()
    
    # Check for years first - any year is > 20 weeks
    if "year" in text or "yr" in text:
        return 999.0
    
    total_weeks = 0.0
    found = False
    
    # Check months
    m_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:month|mo)", text)
    if m_match:
        total_weeks += float(m_match.group(1)) * 4.33
        found = True
        
    # Check weeks
    w_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:week|wk)", text)
    if w_match:
        total_weeks += float(w_match.group(1))
        found = True
        
    # Check days
    d_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:day)", text)
    if d_match:
        total_weeks += float(d_match.group(1)) / 7.0
        found = True
        
    if found:
        return round(total_weeks, 1)
        
    # If the text just has a number and mentions kitten
    if "kitten" in text or "baby" in text:
        num_match = re.search(r"\b(\d+)\b", text)
        if num_match:
            n = float(num_match.group(1))
            if n <= 20: # probably weeks
                return n
            
    return None

def calculate_bosbos_score(cat: dict) -> dict:
    """
    Evaluates a cat against Bosbos criteria:
    - Female strictly (dropped if not female)
    - Age <= 20 weeks (the younger the better)
    - White / Bright colors preferred
    - Cute features & affectionate personality

    Returns a dict with:
    - is_match: bool
    - score: int (0 to 100)
    - age_weeks: float or None
    - color_category: str
    - cute_tags: list[str]
    - score_breakdown: dict
    """
    sex = (cat.get("sex") or "").strip().lower()
    if sex not in ["female", "f"]:
        return {
            "is_match": False,
            "reason": f"Not female (sex: {cat.get('sex')})",
            "score": 0,
            "age_weeks": None
        }
        
    age_str = cat.get("age") or cat.get("age_str") or ""
    age_weeks = parse_age_to_weeks(age_str)
    
    # Hard filter: must be <= 20.5 weeks
    if age_weeks is None:
        # Check if labeled explicitly as kitten without age
        if "kitten" in (cat.get("bio", "") + " " + cat.get("breed", "")).lower():
            age_weeks = 12.0 # estimate standard kitten
        else:
            return {
                "is_match": False,
                "reason": "Unknown or unparseable age",
                "score": 0,
                "age_weeks": None
            }
            
    if age_weeks > 20.5:
        return {
            "is_match": False,
            "reason": f"Older than 20 weeks ({age_weeks} wks)",
            "score": 0,
            "age_weeks": age_weeks
        }
        
    # --- 1. Age Youth Score (Max 40 pts) ---
    # The younger the better!
    if age_weeks <= 9.0:
        age_score = 40
    elif age_weeks <= 12.0:
        age_score = 36
    elif age_weeks <= 15.0:
        age_score = 30
    elif age_weeks <= 18.0:
        age_score = 25
    else:
        age_score = 20
        
    # --- 2. Color / Coat Score (Max 40 pts) ---
    search_text = " ".join([
        cat.get("name", ""),
        cat.get("breed", ""),
        cat.get("colors", ""),
        cat.get("bio", "")
    ]).lower()
    
    color_category = "Standard"
    color_score = 10 # base
    
    # Check top tier bright/white
    for kw in BRIGHT_WHITE_KEYWORDS:
        if kw in search_text:
            color_score = 40
            color_category = "Bright White / Cream / Point"
            break
            
    if color_score < 40:
        for kw in BRIGHT_ACCENT_KEYWORDS:
            if kw in search_text:
                color_score = 30
                color_category = "Pastel / Calico / Light Mix"
                break
                
    # --- 3. Cute Features & Personality (Max 20 pts) ---
    found_cute_tags = []
    for kw in CUTE_KEYWORDS:
        if kw in search_text:
            found_cute_tags.append(kw)
            
    cute_points = 10 + min(len(found_cute_tags) * 2, 10) # 10 to 20 pts
    
    total_score = min(age_score + color_score + cute_points, 100)
    
    return {
        "is_match": True,
        "score": total_score,
        "age_weeks": age_weeks,
        "color_category": color_category,
        "cute_tags": list(set(found_cute_tags))[:6],
        "score_breakdown": {
            "age_points": age_score,
            "color_points": color_score,
            "cute_points": cute_points
        }
    }
