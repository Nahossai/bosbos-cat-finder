import sqlite3
import json
import os
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "bosbos.db")
JSON_PATH = os.path.join(os.path.dirname(__file__), "..", "public", "data", "cats.json")

def init_db(db_path=DB_PATH):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cats (
            id TEXT PRIMARY KEY,
            name TEXT,
            shelter TEXT,
            shelter_location TEXT,
            shelter_phone TEXT,
            sex TEXT,
            age_str TEXT,
            age_weeks REAL,
            breed TEXT,
            personality TEXT,
            image_url TEXT,
            images TEXT,
            bio TEXT,
            adoption_url TEXT,
            bosbos_score INTEGER,
            color_category TEXT,
            cute_tags TEXT,
            first_seen TEXT,
            last_seen TEXT,
            is_new_today INTEGER DEFAULT 1,
            status TEXT DEFAULT 'active',
            likes_count INTEGER DEFAULT 0,
            is_bosbos_match INTEGER DEFAULT 0
        )
    """)
    
    # Check if images / is_bosbos_match columns exist (migration)
    cur.execute("PRAGMA table_info(cats)")
    cols = [col[1] for col in cur.fetchall()]
    if "images" not in cols:
        cur.execute("ALTER TABLE cats ADD COLUMN images TEXT")
    if "is_bosbos_match" not in cols:
        cur.execute("ALTER TABLE cats ADD COLUMN is_bosbos_match INTEGER DEFAULT 0")
        cur.execute("UPDATE cats SET is_bosbos_match = 1 WHERE bosbos_score > 0")
        
    conn.commit()
    return conn

def export_to_json(db_path=DB_PATH, json_path=JSON_PATH):
    """
    Exports active Bosbos matching candidate cats from SQLite to JSON
    strictly ordered by bosbos_score DESC, age_weeks ASC.
    """
    conn = init_db(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, shelter, shelter_location, shelter_phone, sex, age_str, age_weeks,
               breed, personality, image_url, images, bio, adoption_url, bosbos_score, color_category,
               cute_tags, first_seen, last_seen, is_new_today, status, likes_count
        FROM cats
        WHERE status = 'active' AND is_bosbos_match = 1
        ORDER BY bosbos_score DESC, age_weeks ASC
    """)
    rows = cur.fetchall()
    
    columns = [
        "id", "name", "shelter", "shelter_location", "shelter_phone", "sex", "age_str", "age_weeks",
        "breed", "personality", "image_url", "images", "bio", "adoption_url", "bosbos_score", "color_category",
        "cute_tags", "first_seen", "last_seen", "is_new_today", "status", "likes_count"
    ]
    
    export_list = []
    for r in rows:
        d = dict(zip(columns, r))
        d["cute_tags"] = json.loads(d["cute_tags"]) if d["cute_tags"] else []
        d["is_new_today"] = bool(d["is_new_today"])
        
        # Parse images list
        try:
            d["images"] = json.loads(d["images"]) if d["images"] else []
        except Exception:
            d["images"] = []
            
        if not d["images"] and d["image_url"]:
            d["images"] = [d["image_url"]]
            
        d["photos_count"] = len(d["images"])
        export_list.append(d)
        
    conn.close()
    
    now = datetime.utcnow()
    now_iso = str(now.isoformat())
    
    try:
        import zoneinfo
        calgary_tz = zoneinfo.ZoneInfo("America/Edmonton")
        if isinstance(now, datetime) and getattr(now, "tzinfo", None) is None:
            now_utc = now.replace(tzinfo=timezone.utc)
            calgary_now = now_utc.astimezone(calgary_tz)
            calgary_time_str = str(calgary_now.strftime("%b %d, %Y, %I:%M %p %Z"))
        elif isinstance(now, datetime):
            calgary_now = now.astimezone(calgary_tz)
            calgary_time_str = str(calgary_now.strftime("%b %d, %Y, %I:%M %p %Z"))
        else:
            calgary_time_str = str(now_iso)
    except Exception:
        calgary_time_str = str(now_iso)

    # Export to JSON
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": now_iso,
            "updated_at_calgary": calgary_time_str,
            "timezone": "America/Edmonton",
            "total_candidates": len(export_list),
            "target_criteria": {
                "name": "Bosbos",
                "sex": "Female",
                "max_age_weeks": 20,
                "preferred_palette": "Bright White, Cream, Colorpoints, Light Calico/Pastel"
            },
            "cats": export_list
        }, f, indent=2)
        
    return export_list

def save_and_update_cats(matched_cats, all_raw_cats=None, db_path=DB_PATH, json_path=JSON_PATH):
    """
    Inserts or updates all scraped cats in SQLite, tracks first_seen vs new_today,
    tracks Bosbos match status (is_bosbos_match),
    marks no-longer-available cats for scraped shelters as 'adopted' (only if shelter was scraped
    and cat ID was missing from that shelter),
    and exports a sorted JSON file with all matching candidate cats for the web frontend.
    """
    conn = init_db(db_path)
    cur = conn.cursor()
    now_iso = datetime.utcnow().isoformat()
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    
    matched_dict = {cat["id"]: cat for cat in matched_cats if cat.get("id")}
    source_pool = all_raw_cats if all_raw_cats is not None else matched_cats
    
    cats_to_process = {}
    for cat in source_pool:
        cat_id = cat.get("id")
        if cat_id:
            # If in matched_cats, prefer matched enriched dict with is_bosbos_match=1
            if cat_id in matched_dict:
                cats_to_process[cat_id] = (matched_dict[cat_id], 1)
            else:
                cats_to_process[cat_id] = (cat, 1 if cat.get("is_bosbos_match") or cat.get("is_match") else 0)
    for cat in matched_cats:
        cat_id = cat.get("id")
        if cat_id and cat_id not in cats_to_process:
            cats_to_process[cat_id] = (cat, 1)
            
    for cat, is_match in cats_to_process.values():
        cat_id = cat["id"]
        
        # Ensure images list
        photos = cat.get("images") or ([cat.get("image_url")] if cat.get("image_url") else [])
        primary_img = photos[0] if photos else cat.get("image_url", "")
        photos_json = json.dumps(photos)
        
        # Check if already in db
        cur.execute("SELECT first_seen, likes_count FROM cats WHERE id = ?", (cat_id,))
        row = cur.fetchone()
        
        if row:
            first_seen, existing_likes = row
            # If first seen today, it's still new today
            is_new = 1 if first_seen.startswith(today_str) else 0
            cur.execute("""
                UPDATE cats SET
                    name = ?, shelter = ?, shelter_location = ?, shelter_phone = ?,
                    sex = ?, age_str = ?, age_weeks = ?, breed = ?, personality = ?,
                    image_url = ?, images = ?, bio = ?, adoption_url = ?, bosbos_score = ?,
                    color_category = ?, cute_tags = ?, last_seen = ?, is_new_today = ?,
                    status = 'active', is_bosbos_match = ?
                WHERE id = ?
            """, (
                cat["name"], cat["shelter"], cat.get("shelter_location", ""), cat.get("shelter_phone", ""),
                cat["sex"], cat["age_str"], cat.get("age_weeks"), cat.get("breed", ""), cat.get("personality", ""),
                primary_img, photos_json, cat.get("bio", ""), cat.get("adoption_url", ""), cat.get("bosbos_score", 0),
                cat.get("color_category", ""), json.dumps(cat.get("cute_tags", [])), now_iso, is_new,
                is_match, cat_id
            ))
        else:
            cur.execute("""
                INSERT INTO cats (
                    id, name, shelter, shelter_location, shelter_phone,
                    sex, age_str, age_weeks, breed, personality,
                    image_url, images, bio, adoption_url, bosbos_score,
                    color_category, cute_tags, first_seen, last_seen,
                    is_new_today, status, likes_count, is_bosbos_match
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'active', 0, ?)
            """, (
                cat_id, cat["name"], cat["shelter"], cat.get("shelter_location", ""), cat.get("shelter_phone", ""),
                cat["sex"], cat["age_str"], cat.get("age_weeks"), cat.get("breed", ""), cat.get("personality", ""),
                primary_img, photos_json, cat.get("bio", ""), cat.get("adoption_url", ""), cat.get("bosbos_score", 0),
                cat.get("color_category", ""), json.dumps(cat.get("cute_tags", [])), now_iso, now_iso,
                is_match
            ))
            
    # Mark cats from scraped shelters that are NO LONGER available as 'adopted'
    # Only update a cat to 'adopted' if its shelter was in the active scraped shelters of the current run,
    # AND its ID was not seen among the active cats for that shelter.
    scraped_shelters = set(c["shelter"] for c in source_pool if c.get("shelter"))
    all_raw_active_ids = set(c["id"] for c in source_pool if c.get("id"))
    
    for shelter_name in scraped_shelters:
        cur.execute("SELECT id FROM cats WHERE shelter = ? AND status = 'active'", (shelter_name,))
        stored_active = [r[0] for r in cur.fetchall()]
        for st_id in stored_active:
            if st_id not in all_raw_active_ids:
                cur.execute("UPDATE cats SET status = 'adopted' WHERE id = ?", (st_id,))
                
    conn.commit()
    conn.close()
    
    return export_to_json(db_path=db_path, json_path=json_path)
