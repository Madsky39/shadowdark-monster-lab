"""M15: batch simulation -- every core monster vs. the standardized reference
party, win rates recorded to reports/sim_results.csv.

The reference party is the yardstick everything in the difficulty study is
measured against, so its definition is fixed and stated here:

  - 4 PCs, one of each class (fighter, priest, thief, wizard).
  - Party level = the monster's printed LV clamped to the PC-reasonable
    range 1-10. Above LV 10 the party is outmatched by design; the analysis
    documents how that tail is handled.
  - Fixed variance mode: the party is built once per monster and all trials
    run against it.
  - Fixed median stats: all ability scores 10, except CON 12 (+1 mod). No
    3d6 rolling -- the yardstick must not wobble.
  - Standard class gear (REFERENCE_GEAR below): fighter in chainmail with
    shield and longsword, priest in chainmail with shield and mace, thief
    in leather with shortsword, wizard unarmored with staff.
  - HP is still rolled (the rules never grant fixed HP), but from a
    deterministic per-monster RNG seeded with (seed, monster id), so the
    whole CSV reproduces exactly from the same --seed regardless of row
    order or subsetting.

The CSV is derived entirely from freely licensed core data, so it is
committed to the repo. The dashboard reads the committed file;
ensure_database() never runs this script (a full run is minutes, not
seconds). Regenerate with:

    python src/batch_sim.py            # 2000 trials per monster, seed 42
    python src/batch_sim.py --trials 500 --seed 7
"""

import argparse
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from analysis import (  # noqa: E402
    fit_level_to_attack_bonus,
    load_sd_features_with_metrics,
)
from combat_sim import (  # noqa: E402
    STAT_NAMES,
    build_pc_manual,
    monster_from_row,
    run_monte_carlo,
)

DB_PATH = ROOT / "data" / "monsterlab.db"
OUTPUT_PATH = ROOT / "reports" / "sim_results.csv"

REFERENCE_LEVEL_MIN = 1
REFERENCE_LEVEL_MAX = 10

# All 10s, +1 CON: the median 3d6 character, held fixed so the yardstick
# does not wobble between monsters.
REFERENCE_STATS = {name: 10 for name in STAT_NAMES} | {"con": 12}

# (armor, shield, weapon, weapon_die) per class -- standard starting-style
# loadouts from the class-legal tables in combat_sim.py.
REFERENCE_GEAR = {
    "fighter": ("chainmail", True, "longsword", "1d8"),
    "priest": ("chainmail", True, "mace", "1d6"),
    "thief": ("leather", False, "shortsword", "1d6"),
    "wizard": ("none", False, "staff", "1d4"),
}


def reference_party_level(monster_level: int) -> int:
    return int(np.clip(monster_level, REFERENCE_LEVEL_MIN, REFERENCE_LEVEL_MAX))


def build_reference_party(level: int, attack_bonus_result: dict, rng: np.random.Generator) -> list:
    return [
        build_pc_manual(
            cls=cls,
            level=level,
            stats=REFERENCE_STATS,
            armor=armor,
            shield=shield,
            weapon=weapon,
            attack_bonus_result=attack_bonus_result,
            rng=rng,
            name=cls.capitalize(),
            weapon_die=weapon_die,
        )
        for cls, (armor, shield, weapon, weapon_die) in REFERENCE_GEAR.items()
    ]


def run_batch(conn: sqlite3.Connection, trials: int, seed: int) -> pd.DataFrame:
    df = load_sd_features_with_metrics(conn)
    attack_bonus_result = fit_level_to_attack_bonus(df)

    records = []
    for _, row in df.iterrows():
        rng = np.random.default_rng([seed, int(row["id"])])
        party_level = reference_party_level(int(row["level"]))
        monster = monster_from_row(row)

        result = run_monte_carlo(
            lambda: build_reference_party(party_level, attack_bonus_result, rng),
            monster, trials, rng, "fixed",
        )

        records.append(
            {
                "name": row["name"],
                "level": int(row["level"]),
                "party_level": party_level,
                "threat_score": round(float(row["threat_score"]), 4),
                "effective_dpr": round(float(row["effective_dpr"]), 4),
                "effective_hp": round(float(row["effective_hp"]), 4),
                "win_rate": result["party_win_rate"],
                "avg_rounds": round(result["avg_rounds"], 3),
                "trials": trials,
                "seed": seed,
            }
        )

    return pd.DataFrame(records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=2000, help="trials per monster")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    try:
        results = run_batch(conn, args.trials, args.seed)
    finally:
        conn.close()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(out_path, index=False)
    print(f"Simulated {len(results)} monsters x {args.trials} trials (seed {args.seed}).")
    print(f"Results written to {out_path}.")
    print()
    print("Win rate summary by printed LV band:")
    bands = pd.cut(results["level"], bins=[-1, 3, 7, 10, 30], labels=["0-3", "4-7", "8-10", "11+"])
    print(results.groupby(bands, observed=True)["win_rate"].agg(["mean", "min", "max"]).round(3).to_string())


if __name__ == "__main__":
    main()
