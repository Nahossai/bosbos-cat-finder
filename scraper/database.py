import sqlite3
import json
import os
from datetime import datetime

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
            bio TEXT,
            adoption_url TEXT,
            bosbos_score INTEGER,
            color_category TEXT,
            cute_tags TEXT,
            first_seen TEXT,
            last_seen TEXT,
            is_new_today INTEGER DEFAULT 1,
            status TEXT DEFAULT 'active',
            likes_count INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn

def save_and_update_cats(matched_cats, db_path=DB_PATH, json_path=JSON_PATH):
    """
    Inserts or updates matched cats in SQLite, tracks first_seen vs new_today,
    and exports a sorted JSON file for the web frontend.
    """
    conn = init_db(db_path)
    cur = conn.cursor()
    now_iso = datetime.utcnow().isoformat()
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    
    seen_ids = set()
    
    for cat in matched_cats:
        cat_id = cat["id"]
        seen_ids.add(cat_id)
        
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
                    image_url = ?, bio = ?, adoption_url = ?, bosbos_score = ?,
                    color_category = ?, cute_tags = ?, last_seen = ?, is_new_today = ?,
                    status = 'active'
                WHERE id = ?
            """, (
                cat["name"], cat["shelter"], cat.get("shelter_location", ""), cat.get("shelter_phone", ""),
                cat["sex"], cat["age_str"], cat.get("age_weeks"), cat.get("breed", ""), cat.get("personality", ""),
                cat.get("image_url", ""), cat.get("bio", ""), cat.get("adoption_url", ""), cat.get("bosbos_score", 0),
                cat.get("color_category", ""), json.dumps(cat.get("cute_tags", [])), now_iso, is_new,
                cat_id
            ))
        else:
            cur.execute("""
                INSERT INTO cats (
                    id, name, shelter, shelter_location, shelter_phone,
                    sex, age_str, age_weeks, breed, personality,
                    image_url, bio, adoption_url, bosbos_score,
                    color_category, cute_tags, first_seen, last_seen,
                    is_new_today, status, likes_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'active', 0)
            """, (
                cat_id, cat["name"], cat["shelter"], cat.get("shelter_location", ""), cat.get("shelter_phone", ""),
                cat["sex"], cat["age_str"], cat.get("age_weeks"), cat.get("breed", ""), cat.get("personality", ""),
                cat.get("image_url", ""), cat.get("bio", ""), cat.get("adoption_url", ""), cat.get("bosbos_score", 0),
                cat.get("color_category", ""), json.dumps(cat.get("cute_tags", [])), now_iso, now_iso
            ))
            
    # Mark cats not seen in this scrape as adopted/removed
    if seen_ids:
        placeholders = ",".join(["?"] * len(seen_ids))
        cur.execute(f"UPDATE cats SET status = 'adopted' WHERE id NOT IN ({placeholders}) AND status = 'active'", list(seen_ids))
        
    conn.commit()
    
    # Query all active matched cats ordered by bosbos_score DESC
    cur.execute("""
        SELECT id, name, shelter, shelter_location, shelter_phone, sex, age_str, age_weeks,
               breed, personality, image_url, bio, adoption_url, bosbos_score, color_category,
               cute_tags, first_seen, last_seen, is_new_today, status, likes_count
        FROM cats
        WHERE status = 'active'
        ORDER BY bosbos_score DESC, age_weeks ASC
    """)
    rows = cur.fetchall()
    
    columns = [
        "id", "name", "shelter", "shelter_location", "shelter_phone", "sex", "age_str", "age_weeks",
        "breed", "personality", "image_url", "bio", "adoption_url", "bosbos_score", "color_category",
        "cute_tags", "first_seen", "last_seen", "is_new_today", "status", "likes_count"
    ]
    
    export_list = []
    for r in rows:
        d = dict(zip(columns, r))
        d["cute_tags"] = json.loads(d["cute_tags"]) if d["cute_tags"] else []
        d["is_new_today"] = bool(d["is_new_today"])
        export_list.append(d)
        
    conn.close()
    
    # Export to JSON
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": now_iso,
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
