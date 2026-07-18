"""Stretch goal: load monster stat blocks parsed from owned PDFs into
sd_monsters_custom / sd_attacks_custom.

This project only ever ingests freely-licensed data (the Shadowdark core
JSON, the 5e SRD) directly. Stat blocks from other books you own --
Cursed Scrolls, third-party products -- aren't included here and can't be
fetched by this project; per the Shadowdark Parser README, JSON derived
from them "should only be used for personal use." The workflow is:

1. Copy the statblock text out of your own PDF.
2. Run it through ashleytowner/shadowdark-parser yourself (a separate,
   Node-based CLI tool -- not a dependency of this Python project):
       npx shadowdark-parser -b -o parsed.json your_statblocks.txt
   (-b bulk-parses a file with multiple stat blocks back to back.)
3. Point this script at that JSON: `python src/ingest_pdf_statblocks.py
   --input parsed.json --source "Cursed Scrolls 1"`

The parser's Monster JSON shape (from its src/entity.ts) is:
    {type, name, description, ac, armor?, hp, movementDistance,
     movementType?, strength, dexterity, constitution, intelligence,
     wisdom, charisma, alignment, level, traits: [{name, description}],
     attacks: [[{quantity?, name, range?, bonus?, damage?}, ...], ...]}
Its ability score fields are already Shadowdark modifiers (e.g. -2, +2),
same convention as our own str_mod..cha_mod, and its per-attack `damage`
field is the same "dice [+ rider]" text our own parse_damage() (from
parse_stats.py) already knows how to split -- reused here rather than
re-implemented, so a Cursed Scrolls monster's avg_damage is computed
exactly the same way a core monster's is.

Unlike the core ingest scripts, this one does NOT drop-and-rebuild its
tables on every run: your personal library accumulates across however many
books/sessions you process. Re-running on the same file is still safe --
each monster is upserted by name (old rows with that name are replaced,
not duplicated) -- but two different runs over two different files both
add to the same tables rather than one replacing the other. Both tables
live in data/monsterlab.db, which is gitignored, so nothing derived from a
book you own ever gets committed to this repo.

Run standalone: python src/ingest_pdf_statblocks.py --input parsed.json --source "Cursed Scrolls 1"
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from parse_stats import parse_damage  # noqa: E402

DB_PATH = ROOT / "data" / "monsterlab.db"

MONSTERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS sd_monsters_custom (
    id INTEGER PRIMARY KEY,
    source TEXT,
    name TEXT NOT NULL UNIQUE,
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

ATTACKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS sd_attacks_custom (
    id INTEGER PRIMARY KEY,
    monster_id INTEGER NOT NULL REFERENCES sd_monsters_custom(id),
    num_attacks INTEGER,
    attack_name TEXT,
    attack_bonus INTEGER,
    damage_dice TEXT,
    avg_damage REAL,
    rider_text TEXT
);
"""


def to_int(value, field: str, monster_name: str, skipped: list[str]) -> int | None:
    """Level/AC/HP are usually plain numbers but can be a variable stat like '*' or a
    dice formula in the source schema; those don't fit our INTEGER columns, so log and
    skip that monster rather than crash or silently coerce something meaningless."""
    try:
        return int(value)
    except (TypeError, ValueError):
        skipped.append(f"{monster_name}: non-numeric {field} ({value!r})")
        return None


def format_attack_text(attack: dict) -> str:
    """Rebuild a human-readable 'N name (range) +bonus (damage)' string for attacks_raw,
    matching the core bestiary's convention -- for display only, not reparsed."""
    text = ""
    if attack.get("quantity"):
        text += f"{attack['quantity']} "
    text += attack["name"]
    if attack.get("range"):
        text += f" ({attack['range']})"
    if attack.get("bonus"):
        text += f" {attack['bonus']}"
    if attack.get("damage"):
        text += f" ({attack['damage']})"
    return text


def format_attacks_raw(attack_groups: list[list[dict]]) -> str:
    return " or ".join(" and ".join(format_attack_text(a) for a in group) for group in attack_groups)


def flatten_attacks(attack_groups: list[list[dict]]) -> list[dict]:
    """Same simplification sd_attacks makes: don't preserve the and/or grouping, just
    one row per individual attack option."""
    return [attack for group in attack_groups for attack in group]


def convert_monster(entity: dict, source: str, skipped: list[str]) -> tuple[dict, list[dict]] | None:
    name = entity["name"]
    level = to_int(entity.get("level"), "level", name, skipped)
    ac = to_int(entity.get("ac"), "ac", name, skipped)
    hp = to_int(entity.get("hp"), "hp", name, skipped)
    if level is None or ac is None or hp is None:
        return None

    move = entity["movementDistance"]
    if entity.get("movementType"):
        move += f" ({entity['movementType']})"

    traits = [{"name": t["name"], "description": t["description"]} for t in entity.get("traits", [])]

    monster_row = {
        "source": source,
        "name": name,
        "level": level,
        "ac": ac,
        "hp": hp,
        "attacks_raw": format_attacks_raw(entity.get("attacks", [])),
        "move": move,
        "armor_type": entity.get("armor"),
        "str_mod": entity["strength"],
        "dex_mod": entity["dexterity"],
        "con_mod": entity["constitution"],
        "int_mod": entity["intelligence"],
        "wis_mod": entity["wisdom"],
        "cha_mod": entity["charisma"],
        "alignment": entity.get("alignment"),
        "description": entity.get("description"),
        "traits_json": json.dumps(traits),
    }

    attack_rows = []
    for attack in flatten_attacks(entity.get("attacks", [])):
        damage_dice = avg_damage = rider_text = None
        if attack.get("damage"):
            damage_dice, avg_damage, rider_text = parse_damage(attack["damage"])
        bonus = attack.get("bonus")
        attack_rows.append(
            {
                "num_attacks": int(attack["quantity"]) if attack.get("quantity") else 1,
                "attack_name": attack["name"],
                "attack_bonus": int(bonus) if bonus else None,
                "damage_dice": damage_dice,
                "avg_damage": avg_damage,
                "rider_text": rider_text,
            }
        )

    return monster_row, attack_rows


def upsert_monster(conn: sqlite3.Connection, monster_row: dict, attack_rows: list[dict]) -> None:
    """Replace any existing custom monster with the same name, so re-running on the
    same file updates rather than duplicates."""
    existing = conn.execute(
        "SELECT id FROM sd_monsters_custom WHERE name = ?", (monster_row["name"],)
    ).fetchone()
    if existing:
        conn.execute("DELETE FROM sd_attacks_custom WHERE monster_id = ?", (existing[0],))
        conn.execute("DELETE FROM sd_monsters_custom WHERE id = ?", (existing[0],))

    columns = list(monster_row)
    cursor = conn.execute(
        f"INSERT INTO sd_monsters_custom ({', '.join(columns)}) "
        f"VALUES ({', '.join('?' for _ in columns)})",
        [monster_row[c] for c in columns],
    )
    monster_id = cursor.lastrowid

    for attack_row in attack_rows:
        conn.execute(
            """
            INSERT INTO sd_attacks_custom (
                monster_id, num_attacks, attack_name, attack_bonus,
                damage_dice, avg_damage, rider_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                monster_id,
                attack_row["num_attacks"],
                attack_row["attack_name"],
                attack_row["attack_bonus"],
                attack_row["damage_dice"],
                attack_row["avg_damage"],
                attack_row["rider_text"],
            ),
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="JSON file from shadowdark-parser")
    parser.add_argument("--source", required=True, help="Label for where these came from, e.g. 'Cursed Scrolls 1'")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)
    entities = data if isinstance(data, list) else [data]

    monsters = [e for e in entities if e.get("type") == "monster"]
    non_monsters = len(entities) - len(monsters)

    skipped: list[str] = []
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(MONSTERS_SCHEMA + ATTACKS_SCHEMA)
        loaded = 0
        for entity in monsters:
            converted = convert_monster(entity, args.source, skipped)
            if converted is None:
                continue
            monster_row, attack_rows = converted
            upsert_monster(conn, monster_row, attack_rows)
            loaded += 1
        conn.commit()

        total = conn.execute("SELECT COUNT(*) FROM sd_monsters_custom").fetchone()[0]
        print(f"Loaded {loaded} monster(s) from {args.input} (source: {args.source!r}).")
        if non_monsters:
            print(f"Skipped {non_monsters} non-monster entit(y/ies) (spells/items/tables).")
        if skipped:
            print(f"Skipped {len(skipped)} monster(s) with non-numeric level/ac/hp:")
            for line in skipped:
                print(f"  {line}")
        print(f"sd_monsters_custom now has {total} monster(s) total.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
