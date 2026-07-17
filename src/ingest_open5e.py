"""M2: Pull D&D 5e SRD monsters from the Open5e API into fe_monsters.

Open5e's root endpoint (https://api.open5e.com/) currently serves v1 under
/v1/. The /monsters/ list spans many third-party sourcebooks (Tome of
Beasts, Creature Codex, ...); we filter to document__slug=wotc-srd, which
is the open-content 5e SRD (~322 monsters), via the documents endpoint
(https://api.open5e.com/v1/documents/).

Pagination is standard DRF: {count, next, previous, results}, 50/page by
default. We page through `next` until it's null, and cache every page's
raw JSON response to data/raw/open5e/ so re-runs don't hit the API again
unless --refresh is passed.

Run standalone: python src/ingest_open5e.py [--refresh]
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "raw" / "open5e"
DB_PATH = ROOT / "data" / "monsterlab.db"

API_URL = "https://api.open5e.com/v1/monsters/"
DOCUMENT_SLUG = "wotc-srd"

SCHEMA = """
CREATE TABLE fe_monsters (
    id INTEGER PRIMARY KEY,
    slug TEXT UNIQUE,
    name TEXT NOT NULL,
    cr REAL,
    ac INTEGER,
    hp INTEGER,
    hit_dice TEXT,
    size TEXT,
    type TEXT,
    str INTEGER,
    dex INTEGER,
    con INTEGER,
    int INTEGER,
    wis INTEGER,
    cha INTEGER,
    actions_json TEXT,
    document_slug TEXT
);
"""


def parse_cr(challenge_rating: str) -> float:
    """CR arrives as '0', '1/8', '1/4', '1/2', or a whole number string."""
    if "/" in challenge_rating:
        num, denom = challenge_rating.split("/")
        return int(num) / int(denom)
    return float(challenge_rating)


def fetch_pages(refresh: bool) -> list[dict]:
    """Page through the API via `next`, caching each raw page to disk."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    pages = []
    page_num = 1
    url = f"{API_URL}?document__slug={DOCUMENT_SLUG}"

    while url:
        cache_path = CACHE_DIR / f"monsters_page_{page_num}.json"
        if cache_path.exists() and not refresh:
            page = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            page = resp.json()
            cache_path.write_text(json.dumps(page, indent=2), encoding="utf-8")

        pages.append(page)
        url = page.get("next")
        page_num += 1

    return pages


def build_fe_monsters(conn: sqlite3.Connection, pages: list[dict]) -> None:
    conn.executescript("DROP TABLE IF EXISTS fe_monsters;" + SCHEMA)

    rows = []
    for page in pages:
        for m in page["results"]:
            actions_blob = {
                "actions": m.get("actions") or [],
                "bonus_actions": m.get("bonus_actions") or [],
                "reactions": m.get("reactions") or [],
                "legendary_actions": m.get("legendary_actions") or [],
                "special_abilities": m.get("special_abilities") or [],
            }
            rows.append(
                (
                    m["slug"],
                    m["name"],
                    parse_cr(m["challenge_rating"]),
                    m.get("armor_class"),
                    m.get("hit_points"),
                    m.get("hit_dice"),
                    m.get("size"),
                    m.get("type"),
                    m.get("strength"),
                    m.get("dexterity"),
                    m.get("constitution"),
                    m.get("intelligence"),
                    m.get("wisdom"),
                    m.get("charisma"),
                    json.dumps(actions_blob),
                    m.get("document__slug"),
                )
            )

    conn.executemany(
        """
        INSERT INTO fe_monsters (
            slug, name, cr, ac, hp, hit_dice, size, type,
            str, dex, con, int, wis, cha, actions_json, document_slug
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--refresh", action="store_true", help="Re-fetch from the API instead of using cached pages."
    )
    args = parser.parse_args()

    pages = fetch_pages(refresh=args.refresh)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        build_fe_monsters(conn, pages)
        count, min_cr, max_cr = conn.execute(
            "SELECT COUNT(*), MIN(cr), MAX(cr) FROM fe_monsters"
        ).fetchone()
        print(f"Loaded {count} SRD monsters into fe_monsters ({DB_PATH}).")
        print(f"CR range: {min_cr} to {max_cr}")
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
