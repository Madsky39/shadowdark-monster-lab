"""M10: derived combat metrics from sd_monsters + sd_attacks rows.

Pure functions only -- no I/O in this module. Callers (analysis.py, the app's
shared loaders) pass in dataframes or rows and get values back; metrics are
computed at load time, never stored in the DB.

The metric family, composed from two primitives:

  effective_dpr  expected damage per round against a reference AC. Per attack
                 clause: num_attacks * avg_damage * p_hit, where
                 p_hit = clamp((21 + attack_bonus - ac_ref) / 20, 0.05, 0.95).
                 The floor and ceiling encode "natural 1 always misses" /
                 "natural 20 always hits". Crit bonus damage is ignored for
                 simplicity (stated in the report). sd_attacks does not
                 preserve the or/and grouping of attack routines (see
                 parse_stats.py), so each row is treated as an alternative
                 routine and the best (highest expected damage) one is used --
                 the same choice v1's "best_*" columns made, except scored by
                 expected damage against the reference AC instead of raw
                 round damage.
  effective_hp   raw damage a reference attacker must output to drop the
                 monster: hp / p_hit(atk_ref vs monster AC), same clamp.
  threat_score   sqrt(effective_dpr * effective_hp) -- the candidate
                 single-number difficulty metric (same construction idea as
                 the 5e DMG's offensive/defensive CR average).
  archetype_ratio  effective_dpr / effective_hp. Not a level predictor
                 (offense and defense both rise with level, so the ratio
                 cancels the level signal); it is an archetype axis:
                 high = glass cannon, low = sponge/tank.

threat_score and archetype_ratio take the two computed metrics rather than a
monster row, so the (slightly expensive) primitives are computed once and
combined cheaply; add_combat_metrics() does the full composition for a whole
dataframe at once.
"""

import math
from collections.abc import Iterable, Mapping

import pandas as pd

# p_hit bounds: a natural 1 always misses and a natural 20 always hits, so no
# attack ever hits less than 1-in-20 or more than 19-in-20.
P_HIT_FLOOR = 0.05
P_HIT_CEIL = 0.95

# Reference AC: the party AC the combat sim's armor math produces for a
# mid-level PC -- 10 + DEX mod (+1, the sim's default) + chainmail (+4) +
# shield (+2) = 17, mirroring combat_sim.py's ARMOR_BONUS table and defaults
# (not imported from there to keep this module dependency-free; tests assert
# the two stay consistent).
AC_REF = 17

# Reference attack bonus: fit_level_to_attack_bonus() (analysis.py) evaluated
# at the median core monster LV. On the committed core data the fit is
# best_attack_bonus = 0.5627 * level + 1.0615 (R^2 = 0.80) and the median LV
# is 5.0, giving 3.8749. Not computed here because this module does no I/O;
# tests recompute it from the DB and fail if the data drifts from this value.
ATK_REF = 3.8749


def hit_probability(attack_bonus: float, target_ac: float) -> float:
    """P(d20 + attack_bonus >= target_ac), clamped to [0.05, 0.95]."""
    return min(P_HIT_CEIL, max(P_HIT_FLOOR, (21 + attack_bonus - target_ac) / 20))


def _attack_rows(monster_attacks) -> list[dict]:
    """Accept a DataFrame of sd_attacks rows or an iterable of mappings."""
    if isinstance(monster_attacks, pd.DataFrame):
        return monster_attacks.to_dict("records")
    return [dict(row) for row in monster_attacks]


def effective_dpr(monster_attacks, ac_ref: float = AC_REF) -> float:
    """Expected damage per round against ac_ref; best alternative attack row wins.

    Missing values get the same treatment fit_lv_model() gives them: no listed
    bonus or no damage dice are real zeros for that attack (e.g. a caster's
    "1 spell +2" clause has no damage), not missing data; a missing
    num_attacks means a single attack.
    """
    best = 0.0
    for row in _attack_rows(monster_attacks):
        num = row.get("num_attacks")
        avg = row.get("avg_damage")
        bonus = row.get("attack_bonus")
        num = 1 if num is None or pd.isna(num) else num
        avg = 0.0 if avg is None or pd.isna(avg) else avg
        bonus = 0 if bonus is None or pd.isna(bonus) else bonus
        best = max(best, num * avg * hit_probability(bonus, ac_ref))
    return best


def effective_hp(monster: Mapping, atk_ref: float = ATK_REF) -> float:
    """Raw damage a reference attacker must output on average to drop the monster."""
    return monster["hp"] / hit_probability(atk_ref, monster["ac"])


def threat_score(effective_dpr: float, effective_hp: float) -> float:
    """sqrt(effective_dpr * effective_hp): geometric mean of offense and defense."""
    return math.sqrt(effective_dpr * effective_hp)


def archetype_ratio(effective_dpr: float, effective_hp: float) -> float:
    """effective_dpr / effective_hp: high = glass cannon, low = sponge/tank."""
    return effective_dpr / effective_hp


def add_combat_metrics(
    monsters_df: pd.DataFrame,
    attacks_df: pd.DataFrame,
    ac_ref: float = AC_REF,
    atk_ref: float = ATK_REF,
) -> pd.DataFrame:
    """Return a copy of monsters_df with all four metric columns added.

    monsters_df needs id/hp/ac (sd_monsters shape); attacks_df needs
    monster_id/num_attacks/avg_damage/attack_bonus (sd_attacks shape).
    Monsters with no parsed attack rows get effective_dpr 0 (and therefore
    threat_score and archetype_ratio 0), not NaN -- "no parseable attacks"
    is a real, meaningful zero for the same reason it is in fit_lv_model().
    """
    a = attacks_df.copy()
    a["num_attacks"] = a["num_attacks"].fillna(1)
    a["avg_damage"] = a["avg_damage"].fillna(0.0)
    a["attack_bonus"] = a["attack_bonus"].fillna(0)

    p_hit = ((21 + a["attack_bonus"] - ac_ref) / 20).clip(P_HIT_FLOOR, P_HIT_CEIL)
    per_row = a["num_attacks"] * a["avg_damage"] * p_hit
    edpr = per_row.groupby(a["monster_id"]).max()

    df = monsters_df.copy()
    df["effective_dpr"] = df["id"].map(edpr).fillna(0.0)
    p_hit_ref = ((21 + atk_ref - df["ac"]) / 20).clip(P_HIT_FLOOR, P_HIT_CEIL)
    df["effective_hp"] = df["hp"] / p_hit_ref
    df["threat_score"] = (df["effective_dpr"] * df["effective_hp"]) ** 0.5
    df["archetype_ratio"] = df["effective_dpr"] / df["effective_hp"]
    return df
