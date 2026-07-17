"""Stretch goal: Monte Carlo combat simulator, party of N level-X Shadowdark
PCs vs. a chosen monster from sd_monsters/sd_attacks.

This is a simplified simulation, not a full Shadowdark rules engine -- no
initiative rolls (party always acts, then the monster acts, each round),
no spells/talents/conditions, one attack per PC per round. It models the
core d20-vs-AC / roll-damage attrition loop plus Shadowdark's actual crit
rule (natural 20 doubles the damage dice, natural 1 always misses), which
is enough to answer "does this fight go well?" without pretending to
replicate every rule in the book.

PC stats are a deliberately simple, adjustable approximation rather than
an exact reimplementation of Shadowdark's per-class talent tables (which
this project never ingested and isn't fully confident of down to the
level-by-level bonus):
  - HP uses the actual, well-documented hit die per class (Fighter d8,
    Priest d6, Thief d4, Wizard d4): level 1 is max die + CON mod, each
    later level rolls the die + CON mod (min 1 gained per level, matching
    the core rule).
  - AC uses the standard armor math (10 + DEX mod + armor bonus), with
    leather/chainmail/plate bonuses of +1/+4/+5 and shield +2. These were
    cross-checked against our own sd_monsters data grouped by armor_type
    (mean AC: leather 12.6, chainmail 13.9, plate 16.0 -- consistent with
    10+dex+bonus for typical dex mods).
  - Attack bonus reuses fit_level_to_attack_bonus() from analysis.py --
    Shadowdark levels are calibrated so a same-level monster is a fair
    fight for the party, so "what attack bonus does a level-X monster
    have" is a reasonable, data-grounded stand-in for a level-X PC's
    attack bonus, rather than guessing at class talent progressions.
All of these are overridable -- pass your own numbers if your table's
characters differ.

Run standalone: python src/combat_sim.py --monster Owlbear --party-size 4 --party-level 3
"""

import argparse
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from analysis import fit_level_to_attack_bonus, load_sd_features  # noqa: E402

DB_PATH = ROOT / "data" / "monsterlab.db"

HIT_DICE = {"fighter": 8, "priest": 6, "thief": 4, "wizard": 4}
ARMOR_BONUS = {"none": 0, "leather": 1, "chainmail": 4, "plate": 5}
DICE_RE = re.compile(r"^(\d+)d(\d+)$")


@dataclass
class Combatant:
    name: str
    hp: int
    max_hp: int
    ac: int
    attack_bonus: int
    damage_dice: str
    num_attacks: int = 1
    alive: bool = True


def parse_dice(dice: str) -> tuple[int, int]:
    m = DICE_RE.match(dice.strip())
    if not m:
        raise ValueError(f"Not a dice expression: {dice!r}")
    return int(m.group(1)), int(m.group(2))


def roll_damage(dice: str, rng: np.random.Generator, crit: bool = False) -> int:
    n, d = parse_dice(dice)
    if crit:
        n *= 2
    return int(rng.integers(1, d + 1, size=n).sum())


def make_pc(level: int, class_name: str, con_mod: int, dex_mod: int, armor: str,
            shield: bool, weapon_dice: str, attack_bonus_result: dict, name: str,
            rng: np.random.Generator) -> Combatant:
    hit_die = HIT_DICE[class_name]
    hp = hit_die + con_mod  # level 1: max die
    for _ in range(level - 1):
        hp += max(1, int(rng.integers(1, hit_die + 1)) + con_mod)
    hp = max(1, hp)

    ac = 10 + dex_mod + ARMOR_BONUS[armor] + (2 if shield else 0)

    x_feature = [[level]]
    attack_bonus = round(float(attack_bonus_result["model"].predict(x_feature)[0]))

    return Combatant(
        name=name, hp=hp, max_hp=hp, ac=ac, attack_bonus=attack_bonus,
        damage_dice=weapon_dice, num_attacks=1,
    )


def make_party(n: int, level: int, attack_bonus_result: dict, rng: np.random.Generator,
               class_name: str = "fighter", con_mod: int = 1, dex_mod: int = 1,
               armor: str = "chainmail", shield: bool = True,
               weapon_dice: str = "1d8") -> list[Combatant]:
    return [
        make_pc(level, class_name, con_mod, dex_mod, armor, shield, weapon_dice,
                attack_bonus_result, name=f"PC{i + 1}", rng=rng)
        for i in range(n)
    ]


def load_monster(conn: sqlite3.Connection, name: str) -> Combatant:
    """Pull a monster's own stats out of sd_monsters/sd_attacks (same features M6 uses).

    A few monsters' best (highest expected-damage) attack has no damage dice
    at all -- e.g. a shaman whose best option is "1 spell +2" -- so this
    falls back to 1d4 for those rather than crashing.
    """
    df = load_sd_features(conn)
    row = df.loc[df["name"].str.lower() == name.lower()]
    if row.empty:
        raise SystemExit(f"No Shadowdark monster named {name!r} in sd_monsters.")
    row = row.iloc[0]
    return Combatant(
        name=row["name"],
        hp=int(row["hp"]),
        max_hp=int(row["hp"]),
        ac=int(row["ac"]),
        attack_bonus=int(row["best_attack_bonus"]) if pd_notna(row["best_attack_bonus"]) else 0,
        damage_dice=row["best_damage_dice"] if pd_notna(row["best_damage_dice"]) else "1d4",
        num_attacks=int(row["best_num_attacks"]) if pd_notna(row["best_num_attacks"]) else 1,
    )


def pd_notna(value) -> bool:
    return value == value  # NaN != NaN; avoids importing pandas just for this check


def attack_roll(attacker: Combatant, defender_ac: int, rng: np.random.Generator) -> tuple[bool, bool]:
    """One d20 attack roll. Returns (hit, crit). Natural 1 always misses, natural 20 always hits and crits."""
    d20 = int(rng.integers(1, 21))
    if d20 == 1:
        return False, False
    if d20 == 20:
        return True, True
    return d20 + attacker.attack_bonus >= defender_ac, False


def simulate_one_combat(party: list[Combatant], monster: Combatant, rng: np.random.Generator,
                         max_rounds: int = 50) -> tuple[str, int]:
    """One trial. Returns (outcome, rounds) where outcome is 'party_win', 'party_wipe', or 'timeout'."""
    pcs = [Combatant(**p.__dict__) for p in party]
    m = Combatant(**monster.__dict__)

    for round_num in range(1, max_rounds + 1):
        for pc in pcs:
            if not pc.alive or m.hp <= 0:
                continue
            hit, crit = attack_roll(pc, m.ac, rng)
            if hit:
                m.hp -= roll_damage(pc.damage_dice, rng, crit)
        if m.hp <= 0:
            return "party_win", round_num

        for _ in range(m.num_attacks):
            living = [pc for pc in pcs if pc.alive]
            if not living:
                break
            target = living[int(rng.integers(0, len(living)))]
            hit, crit = attack_roll(m, target.ac, rng)
            if hit:
                target.hp -= roll_damage(m.damage_dice, rng, crit)
                if target.hp <= 0:
                    target.alive = False
        if not any(pc.alive for pc in pcs):
            return "party_wipe", round_num

    return "timeout", max_rounds


def run_monte_carlo(party: list[Combatant], monster: Combatant, n_trials: int,
                     rng: np.random.Generator) -> dict:
    outcomes = []
    rounds = []
    for _ in range(n_trials):
        outcome, n_rounds = simulate_one_combat(party, monster, rng)
        outcomes.append(outcome)
        rounds.append(n_rounds)

    outcomes = np.array(outcomes)
    rounds = np.array(rounds)
    return {
        "n_trials": n_trials,
        "party_win_rate": float((outcomes == "party_win").mean()),
        "party_wipe_rate": float((outcomes == "party_wipe").mean()),
        "timeout_rate": float((outcomes == "timeout").mean()),
        "avg_rounds": float(rounds.mean()),
        "avg_rounds_on_win": float(rounds[outcomes == "party_win"].mean()) if (outcomes == "party_win").any() else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--monster", required=True, help="Shadowdark monster name (sd_monsters)")
    parser.add_argument("--party-size", type=int, default=4)
    parser.add_argument("--party-level", type=int, default=1)
    parser.add_argument("--class-name", default="fighter", choices=list(HIT_DICE))
    parser.add_argument("--armor", default="chainmail", choices=list(ARMOR_BONUS))
    parser.add_argument("--shield", action="store_true", default=True)
    parser.add_argument("--con-mod", type=int, default=1)
    parser.add_argument("--dex-mod", type=int, default=1)
    parser.add_argument("--weapon-dice", default="1d8")
    parser.add_argument("--trials", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    try:
        rng = np.random.default_rng(args.seed)

        sd_df = load_sd_features(conn)
        attack_bonus_result = fit_level_to_attack_bonus(sd_df)

        party = make_party(
            args.party_size, args.party_level, attack_bonus_result, rng,
            class_name=args.class_name, con_mod=args.con_mod, dex_mod=args.dex_mod,
            armor=args.armor, shield=args.shield, weapon_dice=args.weapon_dice,
        )
        monster = load_monster(conn, args.monster)

        print(f"Party: {args.party_size}x level {args.party_level} {args.class_name}")
        print(f"  HP {[p.hp for p in party]}, AC {party[0].ac}, attack bonus +{party[0].attack_bonus}")
        print(f"Monster: {monster.name} (AC {monster.ac}, HP {monster.hp}, "
              f"{monster.num_attacks}x attack +{monster.attack_bonus} {monster.damage_dice})")
        print()

        result = run_monte_carlo(party, monster, args.trials, rng)
        print(f"Trials: {result['n_trials']}")
        print(f"Party win rate: {result['party_win_rate']:.1%}")
        print(f"Party wipe rate: {result['party_wipe_rate']:.1%}")
        print(f"Timeout rate: {result['timeout_rate']:.1%}")
        print(f"Average rounds: {result['avg_rounds']:.1f}")
        if result["avg_rounds_on_win"] is not None:
            print(f"Average rounds (on win): {result['avg_rounds_on_win']:.1f}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
