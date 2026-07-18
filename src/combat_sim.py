"""M14: Monte Carlo combat simulator v2 -- a party of individually built
Shadowdark PCs vs. a chosen monster from sd_monsters/sd_attacks.

This is a simplified simulation, not a full Shadowdark rules engine -- no
initiative rolls (party always acts, then the monster acts, each round),
no spells/talents/conditions, one attack per PC per round. It models the
core d20-vs-AC / roll-damage attrition loop plus Shadowdark's actual crit
rule (natural 20 doubles the damage dice, natural 1 always misses), which
is enough to answer "does this fight go well?" without pretending to
replicate every rule in the book.

Targeting rule: for each of its attacks, the monster targets one living PC
chosen uniformly at random. No focus fire, no marking, no tanking -- simple
and documented rather than clever and hidden.

Party construction has three modes, shared by the CLI and the dashboard UI:
  build_pc_manual  everything specified (class, level, stats, gear).
  build_pc_quick   class and level given, everything else rolled.
  build_pc_random  class rolled too.
Randomization follows the actual rules, not convenience:
  - Stats: 3d6 straight down per ability; mods derived from scores
    ((score - 10) // 2, which matches the rulebook's mod table across the
    3-18 range 3d6 can produce).
  - HP: rolled per level on the class hit die (Fighter d8, Priest d6,
    Thief d4, Wizard d4) plus CON mod per level, minimum 1 per level.
  - Gear: rolled from class-legal tables only (no wizard in plate) -- see
    CLASS_ARMOR / CLASS_WEAPONS below.
  - Attack bonus: fit_level_to_attack_bonus() from analysis.py evaluated
    at the PC's level, kept from v1 -- Shadowdark levels are calibrated so
    a same-level monster is a fair fight for the party, so "what attack
    bonus does a level-X monster have" is a reasonable, data-grounded
    stand-in for a level-X PC's attack bonus, rather than guessing at
    class talent progressions.

Variance modes (never silently picked -- both the CLI and UI make it an
explicit choice):
  fixed   build/roll the party once, run N trials against it. Answers
          "how does this party fare?" Adds per-PC death rates.
  reroll  rebuild the party from scratch every trial. Answers "how
          dangerous is this monster for a random party of this shape?"

Run standalone (v1 invocations still work):
    python src/combat_sim.py --monster Owlbear --party-size 4 --party-level 3
    python src/combat_sim.py --monster Owlbear --build-mode random --party-level 3 --variance-mode reroll
    python src/combat_sim.py --monster Owlbear --party-spec party.example.json --seed 42
"""

import argparse
import json
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
STAT_NAMES = ["str", "dex", "con", "int", "wis", "cha"]

# Class-legal gear tables. These mirror the Weapons/Armor lines of each
# class description in the Shadowdark core rulebook (Fighter: all armor and
# weapons; Priest: all armor, a blunt-leaning weapon list; Thief: leather
# only, light blades; Wizard: no armor, dagger or staff), with damage dice
# from the core weapon table. Two simplifications, stated: the list is
# melee-only (the sim has no range model), and two-handed restrictions are
# ignored (a rolled shield stacks with any rolled weapon).
CLASS_ARMOR = {
    "fighter": ["leather", "chainmail", "plate"],
    "priest": ["leather", "chainmail", "plate"],
    "thief": ["leather"],
    "wizard": ["none"],
}
CLASS_SHIELD = {"fighter": True, "priest": True, "thief": False, "wizard": False}
CLASS_WEAPONS = {
    "fighter": {"longsword": "1d8", "bastard sword": "1d8", "warhammer": "1d10", "spear": "1d6"},
    "priest": {"mace": "1d6", "longsword": "1d8", "warhammer": "1d10", "club": "1d4"},
    "thief": {"shortsword": "1d6", "dagger": "1d4", "club": "1d4"},
    "wizard": {"dagger": "1d4", "staff": "1d4"},
}

DICE_RE = re.compile(r"^(\d+)d(\d+)$")


@dataclass
class PC:
    name: str
    cls: str
    level: int
    stats: dict[str, int]  # the six ability scores, not mods
    armor: str
    shield: bool
    weapon: str
    weapon_die: str
    # Derived at build time: hp rolled on the class hit die, ac from the
    # armor math, attack bonus from the level fit.
    hp: int
    ac: int
    attack_bonus: int


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


def stat_mod(score: int) -> int:
    """(score - 10) // 2 -- matches the rulebook mod table for scores 3-18."""
    return (score - 10) // 2


def roll_stats(rng: np.random.Generator) -> dict[str, int]:
    """3d6 straight down per ability, per the character creation rules."""
    return {name: int(rng.integers(1, 7, size=3).sum()) for name in STAT_NAMES}


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


def roll_hp(cls: str, level: int, con_mod: int, rng: np.random.Generator) -> int:
    """Rolled per level on the class hit die + CON mod, minimum 1 per level."""
    hit_die = HIT_DICE[cls]
    return sum(
        max(1, int(rng.integers(1, hit_die + 1)) + con_mod) for _ in range(level)
    )


def pc_attack_bonus(level: int, attack_bonus_result: dict) -> int:
    return round(float(attack_bonus_result["model"].predict([[level]])[0]))


def build_pc_manual(
    cls: str,
    level: int,
    stats: dict[str, int],
    armor: str,
    shield: bool,
    weapon: str,
    attack_bonus_result: dict,
    rng: np.random.Generator,
    name: str = "PC",
    weapon_die: str | None = None,
) -> PC:
    """Everything specified; only HP is rolled (it is always rolled -- the
    rules never grant fixed HP). weapon_die overrides the gear table for
    weapons the tables don't list. Manual mode does not enforce class
    legality: your table, your rules."""
    if weapon_die is None:
        weapon_die = CLASS_WEAPONS[cls].get(weapon, "1d6")
    return PC(
        name=name,
        cls=cls,
        level=level,
        stats=dict(stats),
        armor=armor,
        shield=shield,
        weapon=weapon,
        weapon_die=weapon_die,
        hp=roll_hp(cls, level, stat_mod(stats["con"]), rng),
        ac=10 + stat_mod(stats["dex"]) + ARMOR_BONUS[armor] + (2 if shield else 0),
        attack_bonus=pc_attack_bonus(level, attack_bonus_result),
    )


def build_pc_quick(
    cls: str,
    level: int,
    attack_bonus_result: dict,
    rng: np.random.Generator,
    name: str = "PC",
) -> PC:
    """Class and level given; stats and gear rolled from class-legal tables."""
    stats = roll_stats(rng)
    armor = str(rng.choice(CLASS_ARMOR[cls]))
    shield = bool(CLASS_SHIELD[cls] and rng.integers(0, 2))
    weapon = str(rng.choice(list(CLASS_WEAPONS[cls])))
    return build_pc_manual(
        cls, level, stats, armor, shield, weapon, attack_bonus_result, rng, name
    )


def build_pc_random(
    level: int,
    attack_bonus_result: dict,
    rng: np.random.Generator,
    name: str = "PC",
) -> PC:
    """Class rolled too."""
    cls = str(rng.choice(list(HIT_DICE)))
    return build_pc_quick(cls, level, attack_bonus_result, rng, name)


def monster_from_row(row) -> Combatant:
    """Build a Combatant from one load_sd_features() row.

    A few monsters' best (highest expected-damage) attack has no damage dice
    at all -- e.g. a shaman whose best option is "1 spell +2" -- so this
    falls back to 1d4 for those rather than crashing.
    """
    return Combatant(
        name=row["name"],
        hp=int(row["hp"]),
        max_hp=int(row["hp"]),
        ac=int(row["ac"]),
        attack_bonus=int(row["best_attack_bonus"]) if pd_notna(row["best_attack_bonus"]) else 0,
        damage_dice=row["best_damage_dice"] if pd_notna(row["best_damage_dice"]) else "1d4",
        num_attacks=int(row["best_num_attacks"]) if pd_notna(row["best_num_attacks"]) else 1,
    )


def load_monster(conn: sqlite3.Connection, name: str) -> Combatant:
    """Pull a monster's own stats out of sd_monsters/sd_attacks (same features M6 uses)."""
    df = load_sd_features(conn)
    row = df.loc[df["name"].str.lower() == name.lower()]
    if row.empty:
        raise SystemExit(f"No Shadowdark monster named {name!r} in sd_monsters.")
    return monster_from_row(row.iloc[0])


def pd_notna(value) -> bool:
    return value == value  # NaN != NaN; avoids importing pandas just for this check


def attack_roll(attack_bonus: int, defender_ac: int, rng: np.random.Generator) -> tuple[bool, bool]:
    """One d20 attack roll. Returns (hit, crit). Natural 1 always misses, natural 20 always hits and crits."""
    d20 = int(rng.integers(1, 21))
    if d20 == 1:
        return False, False
    if d20 == 20:
        return True, True
    return d20 + attack_bonus >= defender_ac, False


def simulate_one_combat(
    party: list[PC],
    monster: Combatant,
    rng: np.random.Generator,
    max_rounds: int = 50,
) -> tuple[str, int, list[bool]]:
    """One trial. Returns (outcome, rounds, died) where outcome is
    'party_win', 'party_wipe', or 'timeout' and died[i] is whether party[i]
    dropped during the fight.

    Each round the living PCs all attack with their own bonus and weapon
    die, then the monster makes its attacks, each against one living PC
    chosen uniformly at random (see module docstring).
    """
    hp = [p.hp for p in party]
    alive = [True] * len(party)
    m_hp = monster.hp

    for round_num in range(1, max_rounds + 1):
        for i, pc in enumerate(party):
            if not alive[i] or m_hp <= 0:
                continue
            hit, crit = attack_roll(pc.attack_bonus, monster.ac, rng)
            if hit:
                m_hp -= roll_damage(pc.weapon_die, rng, crit)
        if m_hp <= 0:
            return "party_win", round_num, [not a for a in alive]

        for _ in range(monster.num_attacks):
            living = [i for i, a in enumerate(alive) if a]
            if not living:
                break
            target = living[int(rng.integers(0, len(living)))]
            hit, crit = attack_roll(monster.attack_bonus, party[target].ac, rng)
            if hit:
                hp[target] -= roll_damage(monster.damage_dice, rng, crit)
                if hp[target] <= 0:
                    alive[target] = False
        if not any(alive):
            return "party_wipe", round_num, [True] * len(party)

    return "timeout", max_rounds, [not a for a in alive]


def run_monte_carlo(
    party_factory,
    monster: Combatant,
    n_trials: int,
    rng: np.random.Generator,
    variance_mode: str = "fixed",
) -> dict:
    """Run n_trials combats. party_factory is a zero-argument callable
    returning a fresh list[PC]; in 'fixed' mode it is called once and the
    same party fights every trial (per-PC death rates are reported), in
    'reroll' mode it is called per trial (death rates are omitted -- the
    seats are filled by different characters every time).
    """
    if variance_mode not in ("fixed", "reroll"):
        raise ValueError(f"variance_mode must be 'fixed' or 'reroll', got {variance_mode!r}")

    party = party_factory() if variance_mode == "fixed" else None
    death_counts = [0] * len(party) if party else None

    outcomes = []
    rounds = []
    for _ in range(n_trials):
        trial_party = party if variance_mode == "fixed" else party_factory()
        outcome, n_rounds, died = simulate_one_combat(trial_party, monster, rng)
        outcomes.append(outcome)
        rounds.append(n_rounds)
        if variance_mode == "fixed":
            for i, d in enumerate(died):
                death_counts[i] += d

    outcomes = np.array(outcomes)
    rounds = np.array(rounds)
    result = {
        "n_trials": n_trials,
        "variance_mode": variance_mode,
        "party_win_rate": float((outcomes == "party_win").mean()),
        "party_wipe_rate": float((outcomes == "party_wipe").mean()),
        "timeout_rate": float((outcomes == "timeout").mean()),
        "avg_rounds": float(rounds.mean()),
        "avg_rounds_on_win": float(rounds[outcomes == "party_win"].mean()) if (outcomes == "party_win").any() else None,
    }
    if variance_mode == "fixed":
        result["party"] = party
        result["pc_death_rates"] = {
            f"{p.name} ({p.cls} {p.level})": c / n_trials
            for p, c in zip(party, death_counts)
        }
    return result


def load_party_spec(path: str, attack_bonus_result: dict, rng: np.random.Generator) -> list[PC]:
    """Build a party from a JSON list of PC dicts (see party.example.json)."""
    with open(path, encoding="utf-8") as f:
        spec = json.load(f)
    party = []
    for i, pc in enumerate(spec):
        party.append(
            build_pc_manual(
                cls=pc["cls"],
                level=pc["level"],
                stats=pc["stats"],
                armor=pc.get("armor", "none"),
                shield=pc.get("shield", False),
                weapon=pc.get("weapon", "dagger"),
                attack_bonus_result=attack_bonus_result,
                rng=rng,
                name=pc.get("name", f"PC{i + 1}"),
                weapon_die=pc.get("weapon_die"),
            )
        )
    return party


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--monster", required=True, help="Shadowdark monster name (sd_monsters)")
    parser.add_argument("--party-size", type=int, default=4)
    parser.add_argument("--party-level", type=int, default=1)
    parser.add_argument(
        "--build-mode", choices=["manual", "quick", "random"], default="manual",
        help="manual: uniform party from the flags below; quick: stats/gear "
             "rolled per PC; random: class rolled too",
    )
    parser.add_argument(
        "--variance-mode", choices=["fixed", "reroll"], default="fixed",
        help="fixed: build the party once, run all trials against it (how "
             "does this party fare); reroll: rebuild the party every trial "
             "(how dangerous is this monster for a random party of this shape)",
    )
    parser.add_argument(
        "--party-spec", default=None,
        help="JSON file with a list of PC dicts (see party.example.json); "
             "overrides the build/size/level flags",
    )
    # v1 flags, still honored in manual mode.
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

        if args.party_spec:
            def party_factory():
                return load_party_spec(args.party_spec, attack_bonus_result, rng)
        elif args.build_mode == "random":
            def party_factory():
                return [
                    build_pc_random(args.party_level, attack_bonus_result, rng, f"PC{i + 1}")
                    for i in range(args.party_size)
                ]
        elif args.build_mode == "quick":
            def party_factory():
                return [
                    build_pc_quick(args.class_name, args.party_level, attack_bonus_result, rng, f"PC{i + 1}")
                    for i in range(args.party_size)
                ]
        else:
            # v1-compatible manual mode: a uniform party from the flags. The
            # v1 --con-mod/--dex-mod flags set mods; scores are recovered as
            # 10 + 2*mod so the same numbers come out of the new stat math.
            stats = {name: 10 for name in STAT_NAMES}
            stats["con"] = 10 + 2 * args.con_mod
            stats["dex"] = 10 + 2 * args.dex_mod

            def party_factory():
                return [
                    build_pc_manual(
                        args.class_name, args.party_level, stats, args.armor,
                        args.shield, "custom", attack_bonus_result, rng,
                        name=f"PC{i + 1}", weapon_die=args.weapon_dice,
                    )
                    for i in range(args.party_size)
                ]

        monster = load_monster(conn, args.monster)

        result = run_monte_carlo(party_factory, monster, args.trials, rng, args.variance_mode)

        if args.variance_mode == "fixed":
            party = result["party"]
            print(f"Party ({args.variance_mode} mode):")
            for p in party:
                print(f"  {p.name}: level {p.level} {p.cls}, HP {p.hp}, AC {p.ac}, "
                      f"+{p.attack_bonus} {p.weapon} ({p.weapon_die}), "
                      f"{p.armor}{' + shield' if p.shield else ''}")
        else:
            print(f"Party: rebuilt every trial ({args.variance_mode} mode)")
        print(f"Monster: {monster.name} (AC {monster.ac}, HP {monster.hp}, "
              f"{monster.num_attacks}x attack +{monster.attack_bonus} {monster.damage_dice})")
        print()

        print(f"Trials: {result['n_trials']} ({result['variance_mode']} variance)")
        print(f"Party win rate: {result['party_win_rate']:.1%}")
        print(f"Party wipe rate: {result['party_wipe_rate']:.1%}")
        print(f"Timeout rate: {result['timeout_rate']:.1%}")
        print(f"Average rounds: {result['avg_rounds']:.1f}")
        if result["avg_rounds_on_win"] is not None:
            print(f"Average rounds (on win): {result['avg_rounds_on_win']:.1f}")
        if "pc_death_rates" in result:
            print("Per-PC death rates:")
            for label, rate in result["pc_death_rates"].items():
                print(f"  {label}: {rate:.1%}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
