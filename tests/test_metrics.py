"""M10: hand-computed expected values and clamp edge cases for src/metrics.py.

The hand-computed cases use explicit ac_ref/atk_ref arguments (17 and 4) so
the arithmetic stays checkable on paper; the module constants themselves are
covered separately, including DB-backed tests that fail if the committed core
data drifts from the documented derivations.
"""

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from metrics import (
    AC_REF,
    ATK_REF,
    add_combat_metrics,
    archetype_ratio,
    effective_dpr,
    effective_hp,
    hit_probability,
    threat_score,
)

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "monsterlab.db"

# Aboleth's real attack rows: "2 tentacle (near) +5 (1d8 + curse) or 1 tail +5 (3d6)"
ABOLETH_ATTACKS = [
    {"num_attacks": 2, "attack_bonus": 5, "avg_damage": 4.5},
    {"num_attacks": 1, "attack_bonus": 5, "avg_damage": 10.5},
]


class TestHitProbability:
    def test_midrange(self):
        # (21 + 5 - 17) / 20 = 0.45
        assert hit_probability(5, 17) == pytest.approx(0.45)

    def test_ceiling_high_bonus_low_ac(self):
        # raw (21 + 30 - 10) / 20 = 2.05 -> clamped: a nat 1 still misses
        assert hit_probability(30, 10) == 0.95

    def test_floor_low_bonus_high_ac(self):
        # raw (21 - 5 - 25) / 20 = -0.45 -> clamped: a nat 20 still hits
        assert hit_probability(-5, 25) == 0.05


class TestEffectiveDpr:
    def test_aboleth_best_alternative_wins(self):
        # vs AC 17 both rows have p_hit 0.45:
        #   tentacles: 2 * 4.5 * 0.45 = 4.05
        #   tail:      1 * 10.5 * 0.45 = 4.725  <- best
        assert effective_dpr(ABOLETH_ATTACKS, ac_ref=17) == pytest.approx(4.725)

    def test_acolyte_damageless_spell_contributes_zero(self):
        # "1 mace +1 (1d6) or 1 spell +2" -- the spell row has no damage dice,
        # which is a real zero, so the mace (1 * 3.5 * 0.25 = 0.875) wins.
        attacks = [
            {"num_attacks": 1, "attack_bonus": 1, "avg_damage": 3.5},
            {"num_attacks": 1, "attack_bonus": 2, "avg_damage": None},
        ]
        assert effective_dpr(attacks, ac_ref=17) == pytest.approx(0.875)

    def test_missing_bonus_and_count_defaults(self):
        # No bonus listed -> 0; no count -> 1. 1 * 4.0 * p_hit(0 vs 17) = 4.0 * 0.2
        attacks = [{"num_attacks": None, "attack_bonus": None, "avg_damage": 4.0}]
        assert effective_dpr(attacks, ac_ref=17) == pytest.approx(0.8)

    def test_no_attacks_is_zero(self):
        assert effective_dpr([]) == 0.0

    def test_accepts_dataframe(self):
        df = pd.DataFrame(ABOLETH_ATTACKS)
        assert effective_dpr(df, ac_ref=17) == pytest.approx(4.725)

    def test_floor_applies_against_extreme_ac(self):
        # p_hit clamps at 0.05 no matter how high the reference AC is.
        attacks = [{"num_attacks": 1, "attack_bonus": 2, "avg_damage": 10.0}]
        assert effective_dpr(attacks, ac_ref=100) == pytest.approx(0.5)


class TestEffectiveHp:
    def test_aboleth(self):
        # p_hit(4 vs AC 16) = (21 + 4 - 16) / 20 = 0.45 -> 39 / 0.45
        assert effective_hp({"hp": 39, "ac": 16}, atk_ref=4) == pytest.approx(39 / 0.45)

    def test_clamp_very_high_ac(self):
        # raw p_hit would be negative; the 0.05 floor caps effective HP at 20x
        assert effective_hp({"hp": 10, "ac": 40}, atk_ref=4) == pytest.approx(200.0)

    def test_clamp_very_low_ac(self):
        # raw p_hit would exceed 1; the 0.95 ceiling keeps effective HP above raw HP
        assert effective_hp({"hp": 10, "ac": 1}, atk_ref=4) == pytest.approx(10 / 0.95)


class TestCombiners:
    def test_threat_score_is_geometric_mean(self):
        assert threat_score(4.0, 100.0) == pytest.approx(20.0)

    def test_archetype_ratio(self):
        assert archetype_ratio(4.0, 100.0) == pytest.approx(0.04)


class TestAddCombatMetrics:
    def test_composes_and_zero_fills(self):
        monsters = pd.DataFrame(
            [
                {"id": 1, "name": "Aboleth-like", "hp": 39, "ac": 16},
                {"id": 2, "name": "No-attacks", "hp": 10, "ac": 40},
            ]
        )
        attacks = pd.DataFrame(
            [{"monster_id": 1, **row} for row in ABOLETH_ATTACKS]
        )
        out = add_combat_metrics(monsters, attacks, ac_ref=17, atk_ref=4)

        aboleth = out.loc[out["id"] == 1].iloc[0]
        assert aboleth["effective_dpr"] == pytest.approx(4.725)
        assert aboleth["effective_hp"] == pytest.approx(39 / 0.45)
        assert aboleth["threat_score"] == pytest.approx((4.725 * 39 / 0.45) ** 0.5)
        assert aboleth["archetype_ratio"] == pytest.approx(4.725 / (39 / 0.45))

        empty = out.loc[out["id"] == 2].iloc[0]
        assert empty["effective_dpr"] == 0.0
        assert empty["effective_hp"] == pytest.approx(200.0)
        assert empty["threat_score"] == 0.0
        assert empty["archetype_ratio"] == 0.0

    def test_does_not_mutate_inputs(self):
        monsters = pd.DataFrame([{"id": 1, "hp": 10, "ac": 12}])
        attacks = pd.DataFrame([{"monster_id": 1, "num_attacks": 1, "attack_bonus": None, "avg_damage": 3.5}])
        add_combat_metrics(monsters, attacks)
        assert "effective_dpr" not in monsters.columns
        assert attacks["attack_bonus"].isna().all()


needs_db = pytest.mark.skipif(
    not DB_PATH.exists(), reason="data/monsterlab.db not built (run run_all.py)"
)


class TestReferenceConstants:
    def test_ac_ref_matches_sim_armor_math(self):
        # AC_REF documents itself as the sim's mid-level PC armor math;
        # assert against combat_sim's actual table so they can't drift apart.
        from combat_sim import ARMOR_BONUS

        assert AC_REF == 10 + 1 + ARMOR_BONUS["chainmail"] + 2

    @needs_db
    def test_atk_ref_matches_fit_at_median_lv(self):
        # ATK_REF documents itself as fit_level_to_attack_bonus() at the
        # median core LV; recompute both from the DB and fail on data drift.
        from analysis import fit_level_to_attack_bonus, load_sd_features

        conn = sqlite3.connect(DB_PATH)
        try:
            df = load_sd_features(conn)
        finally:
            conn.close()
        fit = fit_level_to_attack_bonus(df)
        expected = fit["slope"] * df["level"].median() + fit["intercept"]
        assert ATK_REF == pytest.approx(expected, abs=1e-3)

    @needs_db
    def test_aboleth_from_real_db(self):
        # End-to-end on real data with the real module constants: the Aboleth
        # rows above are its actual sd_attacks rows, so this catches schema or
        # parse drift that the synthetic fixtures cannot.
        conn = sqlite3.connect(DB_PATH)
        try:
            attacks = pd.read_sql(
                "SELECT a.* FROM sd_attacks a JOIN sd_monsters m ON m.id = a.monster_id "
                "WHERE m.name = 'Aboleth'",
                conn,
            )
        finally:
            conn.close()
        assert effective_dpr(attacks, ac_ref=AC_REF) == pytest.approx(4.725)
