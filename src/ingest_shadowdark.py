"""M1: Load the Shadowdark core bestiary JSON into sd_monsters.

Source: dickloraine/shadowdark-resources, data/bestiary_data.json (cached
locally at data/raw/shadowdark/bestiary_data.json). Every record in that
file is 'source': 'Core', so no filtering is needed to get the full core
bestiary.

Run standalone: python src/ingest_shadowdark.py
"""

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_PATH = ROOT / "data" / "raw" / "shadowdark" / "bestiary_data.json"
DB_PATH = ROOT / "data" / "monsterlab.db"

SCHEMA = """
CREATE TABLE sd_monsters (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    level INTEGER NOT NULL,
    ac INTEGER,
    hp INTEGER,
    attacks_raw TEXT,
    move TEXT,
    armor_type TEXT,
    str_mod INTEGER,
    dex_mod INTEGER,
    con_mod INTEGER,
    int_mod INTEGER,
    wis_mod INTEGER,
    cha_mod INTEGER,
    alignment TEXT,
    description TEXT,
    traits_json TEXT
);
"""


def parse_mod(value: str) -> int:
    """Stat mods arrive as signed strings like '+2' or '-1'; int() handles the sign fine."""
    return int(value)


def load_monsters(raw_path: Path) -> list[dict]:
    with open(raw_path, encoding="utf-8") as f:
        return json.load(f)


def build_sd_monsters(conn: sqlite3.Connection, monsters: list[dict]) -> None:
    conn.executescript("DROP TABLE IF EXISTS sd_monsters;" + SCHEMA)

    rows = []
    for m in monsters:
        stats = m.get("stats", {})
        rows.append(
            (
                m["name"],
                m["level"],
                m.get("ac"),
                m.get("hp"),
                m.get("attack"),
                m.get("movement"),
                m.get("armor_type") or None,
                parse_mod(stats.get("str", "+0")),
                parse_mod(stats.get("dex", "+0")),
                parse_mod(stats.get("con", "+0")),
                parse_mod(stats.get("int", "+0")),
                parse_mod(stats.get("wis", "+0")),
                parse_mod(stats.get("cha", "+0")),
                m.get("alignment"),
                m.get("description"),
                json.dumps(m.get("actions", [])),
            )
        )

    conn.executemany(
        """
        INSERT INTO sd_monsters (
            name, level, ac, hp, attacks_raw, move, armor_type,
            str_mod, dex_mod, con_mod, int_mod, wis_mod, cha_mod,
            alignment, description, traits_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()


def main() -> None:
    if not RAW_PATH.exists():
        raise SystemExit(
            f"Missing {RAW_PATH}. Clone dickloraine/shadowdark-resources and "
            "copy data/bestiary_data.json to that path."
        )

    monsters = load_monsters(RAW_PATH)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        build_sd_monsters(conn, monsters)
        count = conn.execute("SELECT COUNT(*) FROM sd_monsters").fetchone()[0]
        print(f"Loaded {count} monsters into sd_monsters ({DB_PATH}).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
