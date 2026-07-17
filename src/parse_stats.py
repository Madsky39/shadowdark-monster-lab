"""M3: Parse sd_monsters.attacks_raw into sd_attacks rows with avg_damage.

Attack strings look like `1 beak +2 (1d4 + blood drain)`, and a monster can
list several such clauses joined by " or " (alternative attacks, e.g. melee
vs. ranged) or " and " (a multiattack routine, e.g. "2 claw +5 (1d8) and
1 bite +5 (1d10)"). We don't preserve that or/and distinction in the
schema -- both just explode into one sd_attacks row per clause.

Each clause is: <count> <name> [(range)] [+bonus] [(damage)], e.g.
    2 poisoned dagger (close/near) +6 (2d4)
    1 spell +2                          -- no damage paren at all
    1 horn                              -- no bonus, no damage
The damage paren can hold a dice expression, a flat number, and/or rider
text, all joined with "+": (1d12 + 2 + Moonbite properties) is dice 1d12,
flat +2, and rider "Moonbite properties". avg_damage sums the dice's
expected value (n * (die+1)/2) with any flat modifier; text tokens go to
rider_text instead of the damage total.

Unparseable clauses (rare -- e.g. "1d4 lightning bolt", which isn't in
<count> <name> form) are logged to data/sd_attacks_parse_failures.txt and
skipped rather than crashing the ingest.

Run standalone: python src/parse_stats.py
"""

import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "monsterlab.db"
FAILURES_PATH = ROOT / "data" / "sd_attacks_parse_failures.txt"

SCHEMA = """
CREATE TABLE sd_attacks (
    id INTEGER PRIMARY KEY,
    monster_id INTEGER NOT NULL REFERENCES sd_monsters(id),
    num_attacks INTEGER,
    attack_name TEXT,
    attack_bonus INTEGER,
    damage_dice TEXT,
    avg_damage REAL,
    rider_text TEXT
);
"""

SPLIT_CLAUSES_RE = re.compile(r"\s+(?:or|and)\s+")

# <count> <name> [(range)] [+bonus] [(damage)] -- name is non-greedy so the
# optional groups after it (range/bonus/damage) can claim their own text.
CLAUSE_RE = re.compile(
    r"^(?P<num>\d+)\s+(?P<name>.+?)"
    r"(?:\s*\((?P<range>(?:close|near|far|double)[^)]*)\))?"
    r"(?:\s*\+\s*(?P<bonus>\d+))?"
    r"(?:\s*\((?P<damage>[^)]*)\))?$"
)

DICE_RE = re.compile(r"^(\d+)d(\d+)$")


def parse_damage(damage: str) -> tuple[str | None, float, str | None]:
    """Split a damage paren's contents into (dice_notation, avg_damage, rider_text)."""
    tokens = [t.strip() for t in damage.split("+") if t.strip()]

    dice_notation = None
    avg_damage = 0.0
    riders = []

    for i, token in enumerate(tokens):
        dice_match = DICE_RE.match(token)
        if dice_match:
            n, die = int(dice_match.group(1)), int(dice_match.group(2))
            avg_damage += n * (die + 1) / 2
            if i == 0:
                dice_notation = token
        elif token.isdigit():
            avg_damage += int(token)
        else:
            riders.append(token)

    rider_text = "; ".join(riders) if riders else None
    return dice_notation, avg_damage, rider_text


def parse_clause(clause: str) -> dict | None:
    m = CLAUSE_RE.match(clause)
    if not m:
        return None

    damage_dice = avg_damage = rider_text = None
    if m.group("damage"):
        damage_dice, avg_damage, rider_text = parse_damage(m.group("damage"))

    return {
        "num_attacks": int(m.group("num")),
        "attack_name": m.group("name").strip(),
        "attack_bonus": int(m.group("bonus")) if m.group("bonus") else None,
        "damage_dice": damage_dice,
        "avg_damage": avg_damage,
        "rider_text": rider_text,
    }


def build_sd_attacks(conn: sqlite3.Connection) -> tuple[int, int]:
    conn.executescript("DROP TABLE IF EXISTS sd_attacks;" + SCHEMA)

    monsters = conn.execute("SELECT id, name, attacks_raw FROM sd_monsters").fetchall()

    rows = []
    failures = []
    total_clauses = 0

    for monster_id, name, attacks_raw in monsters:
        if not attacks_raw:
            continue
        clauses = [c.strip() for c in SPLIT_CLAUSES_RE.split(attacks_raw)]
        for clause in clauses:
            total_clauses += 1
            parsed = parse_clause(clause)
            if parsed is None:
                failures.append((name, attacks_raw, clause))
                continue
            rows.append(
                (
                    monster_id,
                    parsed["num_attacks"],
                    parsed["attack_name"],
                    parsed["attack_bonus"],
                    parsed["damage_dice"],
                    parsed["avg_damage"],
                    parsed["rider_text"],
                )
            )

    conn.executemany(
        """
        INSERT INTO sd_attacks (
            monster_id, num_attacks, attack_name, attack_bonus,
            damage_dice, avg_damage, rider_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()

    with open(FAILURES_PATH, "w", encoding="utf-8") as f:
        f.write(f"{len(failures)} of {total_clauses} attack clauses failed to parse.\n\n")
        for name, raw, clause in failures:
            f.write(f"{name}: clause={clause!r} full_attacks_raw={raw!r}\n")

    return total_clauses, len(failures)


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        total_clauses, num_failures = build_sd_attacks(conn)
        num_parsed = total_clauses - num_failures
        success_rate = num_parsed / total_clauses if total_clauses else 0.0
        row_count = conn.execute("SELECT COUNT(*) FROM sd_attacks").fetchone()[0]

        print(f"Parsed {num_parsed}/{total_clauses} attack clauses ({success_rate:.1%}).")
        print(f"Loaded {row_count} rows into sd_attacks ({DB_PATH}).")
        if num_failures:
            print(f"{num_failures} failures logged to {FAILURES_PATH}.")
        if success_rate < 0.9:
            raise SystemExit(f"Parse success rate {success_rate:.1%} is below the 90% target.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
