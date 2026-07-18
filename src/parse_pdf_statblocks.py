"""Local PDF stat block intake: an alternative front door to the same
sd_monsters_custom / sd_attacks_custom tables as ingest_pdf_statblocks.py,
without the Node.js / shadowdark-parser dependency or the copy-paste step.

This reads a PDF you own directly with pdfplumber (pure Python, no external
CLI tool), extracts each stat block with a regex-based grammar, and calls
ingest_pdf_statblocks.upsert_monster() to write it -- so the DB write and
upsert-by-name semantics live in exactly one place, not two. Attack clauses
are split and parsed with parse_stats.SPLIT_CLAUSES_RE / parse_clause(), the
same M3 grammar the core bestiary's attacks_raw already uses, so a PDF
monster's avg_damage is computed exactly the same way a core monster's is.

Like ingest_pdf_statblocks.py, this only ever writes to
data/monsterlab.db (gitignored) and is never imported by app/dashboard.py or
any app/pages_/*.py -- nothing derived from a book you own reaches the
deployed app. See the "Licensing wall" design principle in
shadowdark-monster-lab-spec-v2.md.

Text layout assumed (the Shadowdark core rulebook's stat block convention):
    NAME
    LV <level>, <Alignment>, <type text>
    AC <ac> HP <hp> ATK <attack text, same grammar as attacks_raw> MV <move>
    S <mod> D <mod> C <mod> I <mod> W <mod> CH <mod>
    [trait/description prose until the next stat block]
Whitespace (including line wraps from the PDF's column layout) is collapsed
before matching, so exact line breaks in the source PDF don't matter -- only
the left-to-right order of these labeled fields does. Real third-party books
vary in wording and field order; this is a best-effort extraction, not a
guaranteed-correct parser. Run with --debug to see exactly what was matched
before it's written, and treat every import as something to spot-check
against the book, the same way M3 logs (rather than guesses at) attack
clauses it can't parse.

Caveat: built and tested against a hand-written text fixture matching this
documented layout (no real third-party PDF was available to test against).
If your book formats stat blocks differently, --debug will show 0 or
garbled matches -- adjust MONSTER_RE below for your book's layout rather
than trusting a silent partial import.

Run standalone:
    python src/parse_pdf_statblocks.py --pdf mybook.pdf --source "Cursed Scrolls 1"
    python src/parse_pdf_statblocks.py --pdf mybook.pdf --source "..." --debug --dry-run
"""

import argparse
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ingest_pdf_statblocks import (  # noqa: E402
    ATTACKS_SCHEMA,
    DB_PATH,
    MONSTERS_SCHEMA,
    upsert_monster,
)
from parse_stats import SPLIT_CLAUSES_RE, parse_clause  # noqa: E402

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

# One capitalized word (allows internal hyphens/apostrophes for names like
# "Will-O-Wisp" or "Mordanticus"), 1-5 words, so we don't grab a whole
# sentence of trailing prose as part of the name.
_NAME_WORD = r"[A-Z][a-zA-Z'’\-]*"
_NAME = rf"(?P<name>{_NAME_WORD}(?:\s{_NAME_WORD}){{0,4}})"

# All fields are matched by literal label in left-to-right order on
# whitespace-collapsed text (see module docstring); the lazy .+? groups
# between labels are why line wraps in the source PDF don't matter.
MONSTER_RE = re.compile(
    rf"{_NAME}\s+"
    r"(?:LV|Level)\s*(?P<level>\d+)\s*,\s*"
    r"(?P<alignment>Lawful|Neutral|Chaotic)\s*,\s*"
    r"(?P<type>.+?)\s+"
    r"AC\s*(?P<ac>\d+)\s+HP\s*(?P<hp>\d+)\s+ATK\s*(?P<atk>.+?)\s+MV\s*(?P<move>.+?)\s+"
    r"S\s*(?P<str>[+-]?\d+)\s*D\s*(?P<dex>[+-]?\d+)\s*C\s*(?P<con>[+-]?\d+)\s*"
    r"I\s*(?P<int>[+-]?\d+)\s*W\s*(?P<wis>[+-]?\d+)\s*CH\s*(?P<cha>[+-]?\d+)"
)

MAX_DESCRIPTION_CHARS = 2000


def extract_text(pdf_path: Path) -> str:
    if pdfplumber is None:
        raise SystemExit(
            "pdfplumber is required for local PDF parsing: pip install pdfplumber "
            "(it's in requirements.txt, marked local-only)."
        )
    with pdfplumber.open(pdf_path) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(pages)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_attacks(atk_text: str, name: str, failures: list[str]) -> tuple[str, list[dict]]:
    """Reuse M3's exact attack-clause grammar. A clause that doesn't parse is
    logged and dropped, same as core ingest -- the rest of the monster still
    loads."""
    attacks_raw = atk_text.strip()
    clauses = [c.strip() for c in SPLIT_CLAUSES_RE.split(attacks_raw) if c.strip()]
    attack_rows = []
    for clause in clauses:
        parsed = parse_clause(clause)
        if parsed is None:
            failures.append(f"{name}: unparseable attack clause {clause!r}")
            continue
        attack_rows.append(parsed)
    return attacks_raw, attack_rows


def parse_blocks(text: str, source: str, failures: list[str]) -> list[tuple[dict, list[dict]]]:
    normalized = normalize(text)
    matches = list(MONSTER_RE.finditer(normalized))
    results = []

    for i, m in enumerate(matches):
        name = m.group("name").strip()
        end = m.end()
        next_start = matches[i + 1].start() if i + 1 < len(matches) else len(normalized)
        description = normalized[end:next_start].strip()[:MAX_DESCRIPTION_CHARS] or None

        attacks_raw, attack_rows = parse_attacks(m.group("atk"), name, failures)
        if not attack_rows:
            failures.append(f"{name}: no attack clauses parsed, monster skipped")
            continue

        monster_row = {
            "source": source,
            "name": name,
            "level": int(m.group("level")),
            "ac": int(m.group("ac")),
            "hp": int(m.group("hp")),
            "attacks_raw": attacks_raw,
            "move": m.group("move").strip(),
            "armor_type": None,
            "str_mod": int(m.group("str")),
            "dex_mod": int(m.group("dex")),
            "con_mod": int(m.group("con")),
            "int_mod": int(m.group("int")),
            "wis_mod": int(m.group("wis")),
            "cha_mod": int(m.group("cha")),
            "alignment": m.group("alignment"),
            "description": description,
            "traits_json": "[]",
        }
        results.append((monster_row, attack_rows))

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, help="Path to a PDF you own")
    parser.add_argument("--source", required=True, help="Label for provenance, e.g. 'Cursed Scrolls 1'")
    parser.add_argument("--debug", action="store_true", help="Print each parsed monster before writing")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report, don't write to the DB")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        raise SystemExit(f"No such file: {pdf_path}")

    text = extract_text(pdf_path)
    failures: list[str] = []
    parsed = parse_blocks(text, args.source, failures)

    if args.debug:
        for monster_row, attack_rows in parsed:
            print(f"--- {monster_row['name']} (LV {monster_row['level']}) ---")
            print(f"  AC {monster_row['ac']}  HP {monster_row['hp']}  MV {monster_row['move']}")
            print(f"  ATK {monster_row['attacks_raw']}")
            print(f"  {len(attack_rows)} attack clause(s) parsed")
            print(
                f"  S{monster_row['str_mod']:+d} D{monster_row['dex_mod']:+d} "
                f"C{monster_row['con_mod']:+d} I{monster_row['int_mod']:+d} "
                f"W{monster_row['wis_mod']:+d} CH{monster_row['cha_mod']:+d}"
            )

    print(f"Matched {len(parsed)} monster(s) in {pdf_path.name}.")
    if failures:
        print(f"{len(failures)} issue(s) logged:")
        for line in failures:
            print(f"  {line}")

    if args.dry_run:
        print("--dry-run set, nothing written to the database.")
        return

    if not parsed:
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(MONSTERS_SCHEMA + ATTACKS_SCHEMA)
        for monster_row, attack_rows in parsed:
            upsert_monster(conn, monster_row, attack_rows)
        conn.commit()

        total = conn.execute("SELECT COUNT(*) FROM sd_monsters_custom").fetchone()[0]
        print(f"Loaded {len(parsed)} monster(s) from {pdf_path.name} (source: {args.source!r}).")
        print(f"sd_monsters_custom now has {total} monster(s) total.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
