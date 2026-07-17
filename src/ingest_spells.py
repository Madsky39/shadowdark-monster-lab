"""Stretch goal: load the Shadowdark core spell list into sd_spells.

Source: dickloraine/shadowdark-resources, data/spell_data.json (cached at
data/raw/shadowdark/spell_data.json alongside the bestiary -- see
ingest_shadowdark.py). All 85 entries are 'source': 'Core', so no filtering
is needed, same as the bestiary.

Run standalone: python src/ingest_spells.py
"""

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_PATH = ROOT / "data" / "raw" / "shadowdark" / "spell_data.json"
DB_PATH = ROOT / "data" / "monsterlab.db"

SCHEMA = """
CREATE TABLE sd_spells (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    tier INTEGER NOT NULL,
    classes TEXT,
    dc INTEGER,
    range TEXT,
    duration TEXT,
    description TEXT
);
"""


def load_spells(raw_path: Path) -> list[dict]:
    with open(raw_path, encoding="utf-8") as f:
        return json.load(f)


def build_sd_spells(conn: sqlite3.Connection, spells: list[dict]) -> None:
    conn.executescript("DROP TABLE IF EXISTS sd_spells;" + SCHEMA)

    rows = [
        (
            s["name"],
            s["tier"],
            ",".join(sorted(s.get("classes", []))),
            s.get("dc"),
            s.get("range"),
            s.get("duration"),
            s.get("description"),
        )
        for s in spells
    ]

    conn.executemany(
        "INSERT INTO sd_spells (name, tier, classes, dc, range, duration, description) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def main() -> None:
    if not RAW_PATH.exists():
        raise SystemExit(
            f"Missing {RAW_PATH}. Run ingest_shadowdark.py first (it documents where "
            "the cached shadowdark-resources JSON comes from)."
        )

    spells = load_spells(RAW_PATH)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        build_sd_spells(conn, spells)
        count = conn.execute("SELECT COUNT(*) FROM sd_spells").fetchone()[0]
        print(f"Loaded {count} spells into sd_spells ({DB_PATH}).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
