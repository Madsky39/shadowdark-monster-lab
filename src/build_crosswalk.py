"""M4: Match monsters that exist in both sd_monsters and fe_monsters.

Two passes:
1. Exact: lowercase name equality. Shadowdark and 5e SRD share a lot of
   basic bestiary names (goblin, owlbear, aboleth, ...), so this alone
   covers most of the crosswalk.
2. Fuzzy: Shadowdark names many variant monsters "Category, Descriptor"
   (e.g. "Giant, Fire", "Wolf, Dire", "Demon, Dretch") while 5e SRD uses
   "Descriptor Category" or drops the category word entirely ("Fire
   Giant", "Dire Wolf", "Dretch"). A straight character-diff on the raw
   strings scores these matches inconsistently depending on word order,
   so both names are normalized by lowercasing, splitting off the comma
   part, and sorting the tokens alphabetically before running difflib --
   that makes "giant, fire" and "fire giant" compare as identical token
   sets instead of two differently-ordered strings.

   Fuzzy matches scoring >= 0.9 on that normalized comparison are
   auto-accepted (match_type='fuzzy'). Everything else is a judgment call
   (does "Devil, Imp" really mean "Imp", or is the top-scoring "Ice Devil"
   right?), so instead of guessing we write the top-3 candidates for every
   still-unmatched sd_monster to a review CSV and leave the row out of
   crosswalk until a human confirms it.

match_type='manual' is reserved for pairs a human adds themselves after
reviewing the CSV -- this script never writes that value.

Run standalone: python src/build_crosswalk.py
"""

import csv
import difflib
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "monsterlab.db"
REVIEW_CSV_PATH = ROOT / "data" / "crosswalk_fuzzy_review.csv"

FUZZY_AUTO_ACCEPT = 0.9
FUZZY_REVIEW_FLOOR = 0.3  # below this, a candidate isn't worth showing a reviewer
CANDIDATES_PER_MONSTER = 3

SCHEMA = """
CREATE TABLE crosswalk (
    sd_id INTEGER NOT NULL REFERENCES sd_monsters(id),
    fe_id INTEGER NOT NULL REFERENCES fe_monsters(id),
    match_type TEXT NOT NULL CHECK (match_type IN ('exact', 'fuzzy', 'manual')),
    confidence REAL NOT NULL,
    notes TEXT
);
"""


def normalize(name: str) -> str:
    """Lowercase, drop punctuation, and sort tokens so word order can't affect the diff."""
    name = name.lower()
    name = re.sub(r"[^a-z0-9,\s]", "", name)
    tokens = []
    for part in re.split(r"\s*,\s*", name):
        tokens.extend(part.split())
    tokens = [t for t in tokens if t != "the"]
    return " ".join(sorted(tokens))


def build_crosswalk(conn: sqlite3.Connection) -> dict:
    conn.executescript("DROP TABLE IF EXISTS crosswalk;" + SCHEMA)

    sd_monsters = conn.execute("SELECT id, name FROM sd_monsters").fetchall()
    fe_monsters = conn.execute("SELECT id, name FROM fe_monsters").fetchall()

    sd_by_lower = {name.lower(): (sid, name) for sid, name in sd_monsters}
    fe_by_lower = {name.lower(): (fid, name) for fid, name in fe_monsters}

    exact_keys = set(sd_by_lower) & set(fe_by_lower)
    crosswalk_rows = []
    for key in exact_keys:
        sid, _ = sd_by_lower[key]
        fid, _ = fe_by_lower[key]
        crosswalk_rows.append((sid, fid, "exact", 1.0, None))

    unmatched_sd = [sd_by_lower[k] for k in set(sd_by_lower) - exact_keys]
    unmatched_fe = [fe_by_lower[k] for k in set(fe_by_lower) - exact_keys]

    # Normalized fe names can collide (rare); keep the first fe monster for each.
    fe_norm_to_id_name = {}
    for fid, fname in unmatched_fe:
        fe_norm_to_id_name.setdefault(normalize(fname), (fid, fname))
    fe_norms = list(fe_norm_to_id_name.keys())

    fuzzy_auto_count = 0
    review_rows = []

    for sid, sname in unmatched_sd:
        norm = normalize(sname)
        candidates = difflib.get_close_matches(
            norm, fe_norms, n=CANDIDATES_PER_MONSTER, cutoff=FUZZY_REVIEW_FLOOR
        )
        scored = [(difflib.SequenceMatcher(None, norm, c).ratio(), c) for c in candidates]
        scored.sort(reverse=True)

        if scored and scored[0][0] >= FUZZY_AUTO_ACCEPT:
            ratio, best_norm = scored[0]
            fid, fname = fe_norm_to_id_name[best_norm]
            crosswalk_rows.append(
                (sid, fid, "fuzzy", ratio, f"auto-accepted: '{sname}' ~ '{fname}'")
            )
            fuzzy_auto_count += 1
            continue

        if not scored:
            review_rows.append((sname, sid, None, None, None, None))
            continue

        for rank, (ratio, cand_norm) in enumerate(scored, start=1):
            fid, fname = fe_norm_to_id_name[cand_norm]
            review_rows.append((sname, sid, rank, fname, fid, round(ratio, 3)))

    conn.executemany(
        "INSERT INTO crosswalk (sd_id, fe_id, match_type, confidence, notes) VALUES (?, ?, ?, ?, ?)",
        crosswalk_rows,
    )
    conn.commit()

    with open(REVIEW_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["sd_name", "sd_id", "candidate_rank", "fe_candidate_name", "fe_id", "confidence"]
        )
        writer.writerows(review_rows)

    return {
        "exact": len(exact_keys),
        "fuzzy_auto": fuzzy_auto_count,
        "total_pairs": len(crosswalk_rows),
        "unmatched_sd_reviewed": len({r[1] for r in review_rows}),
    }


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        stats = build_crosswalk(conn)
        print(f"Exact matches: {stats['exact']}")
        print(f"Fuzzy auto-accepted (>= {FUZZY_AUTO_ACCEPT}): {stats['fuzzy_auto']}")
        print(f"Total crosswalk pairs: {stats['total_pairs']}")
        print(
            f"{stats['unmatched_sd_reviewed']} unmatched sd_monsters have candidates "
            f"in {REVIEW_CSV_PATH} for manual review."
        )
        if stats["total_pairs"] < 30:
            raise SystemExit(f"Only {stats['total_pairs']} pairs; need at least ~30 to model on.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
