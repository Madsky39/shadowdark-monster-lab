"""M14: seeded, deterministic invariants for the combat simulator v2.

No DB dependency: the attack-bonus fit is faked with the same slope and
intercept the real fit produces on the committed data (see test_metrics'
ATK_REF test for the check that those numbers stay true), and the monsters
are Combatants built from the real printed stats of the referenced
monsters.
"""

import numpy as np
import pytest

from combat_sim import (
    CLASS_ARMOR,
    CLASS_WEAPONS,
    Combatant,
    build_pc_manual,
    build_pc_quick,
    build_pc_random,
    roll_stats,
    run_monte_carlo,
    stat_mod,
)


class FakeFitModel:
    """Mimics the sklearn model inside fit_level_to_attack_bonus()'s result,
    with the coefficients that fit produces on the committed core data."""

    def predict(self, X):
        return [0.5627 * x[0] + 1.0615 for x in X]


BONUS_FIT = {"model": FakeFitModel()}

# Real printed stats: Owlbear (LV 3) and The Tarrasque (LV 30), best attack
# routine as sd_attacks parses it.
OWLBEAR = Combatant(name="Owlbear", hp=30, max_hp=30, ac=13, attack_bonus=5,
                    damage_dice="1d10", num_attacks=2)
LV1_MONSTER = Combatant(name="LV1ish", hp=9, max_hp=9, ac=12, attack_bonus=1,
                        damage_dice="1d6", num_attacks=1)
TARRASQUE = Combatant(name="The Tarrasque", hp=140, max_hp=140, ac=22,
                      attack_bonus=13, damage_dice="5d10", num_attacks=4)


def quick_party(cls_levels, rng):
    return [
        build_pc_quick(cls, level, BONUS_FIT, rng, f"PC{i + 1}")
        for i, (cls, level) in enumerate(cls_levels)
    ]


class TestStatMath:
    def test_stat_mod_matches_rulebook_table(self):
        # 3d6 range endpoints and the table's steps
        assert stat_mod(3) == -4
        assert stat_mod(9) == -1
        assert stat_mod(10) == 0
        assert stat_mod(13) == 1
        assert stat_mod(18) == 4

    def test_roll_stats_is_3d6_straight_down(self):
        rng = np.random.default_rng(0)
        for _ in range(200):
            stats = roll_stats(rng)
            assert set(stats) == {"str", "dex", "con", "int", "wis", "cha"}
            assert all(3 <= v <= 18 for v in stats.values())


class TestHpRules:
    def test_per_level_minimum_respected(self):
        # CON 3 is a -4 mod; every d4 roll lands below +1, so only the
        # min-1-per-level rule keeps this wizard alive. HP must be exactly
        # level at the floor, never below.
        rng = np.random.default_rng(7)
        stats = {"str": 10, "dex": 10, "con": 3, "int": 10, "wis": 10, "cha": 10}
        for level in [1, 5, 10]:
            for _ in range(50):
                pc = build_pc_manual("wizard", level, stats, "none", False,
                                     "staff", BONUS_FIT, rng)
                assert pc.hp == level

    def test_hp_scales_with_level(self):
        rng = np.random.default_rng(7)
        stats = {"str": 10, "dex": 10, "con": 14, "int": 10, "wis": 10, "cha": 10}
        lvl1 = [build_pc_manual("fighter", 1, stats, "none", False, "longsword",
                                BONUS_FIT, rng).hp for _ in range(100)]
        lvl5 = [build_pc_manual("fighter", 5, stats, "none", False, "longsword",
                                BONUS_FIT, rng).hp for _ in range(100)]
        assert np.mean(lvl5) > 4 * np.mean(lvl1)


class TestClassLegalGear:
    def test_wizards_never_roll_armor(self):
        rng = np.random.default_rng(11)
        for _ in range(300):
            pc = build_pc_quick("wizard", 3, BONUS_FIT, rng)
            assert pc.armor == "none"
            assert not pc.shield
            assert pc.weapon in CLASS_WEAPONS["wizard"]

    def test_random_pcs_always_class_legal(self):
        rng = np.random.default_rng(13)
        for _ in range(500):
            pc = build_pc_random(3, BONUS_FIT, rng)
            assert pc.armor in CLASS_ARMOR[pc.cls]
            assert pc.weapon in CLASS_WEAPONS[pc.cls]
            if pc.cls in ("thief", "wizard"):
                assert not pc.shield


class TestSimInvariants:
    def test_level5_party_beats_lv1_monster(self):
        rng = np.random.default_rng(42)
        result = run_monte_carlo(
            lambda: quick_party([("fighter", 5), ("priest", 5), ("thief", 5), ("wizard", 5)], rng),
            LV1_MONSTER, 300, rng, "fixed",
        )
        assert result["party_win_rate"] > 0.98

    def test_lone_level1_pc_vs_tarrasque(self):
        rng = np.random.default_rng(42)
        result = run_monte_carlo(
            lambda: quick_party([("fighter", 1)], rng),
            TARRASQUE, 300, rng, "fixed",
        )
        assert result["party_win_rate"] < 0.01

    def test_fixed_mode_reports_death_rates_reroll_does_not(self):
        rng = np.random.default_rng(42)
        fixed = run_monte_carlo(
            lambda: quick_party([("fighter", 3), ("thief", 3)], rng),
            OWLBEAR, 200, rng, "fixed",
        )
        assert "pc_death_rates" in fixed
        assert len(fixed["pc_death_rates"]) == 2

        rng = np.random.default_rng(42)
        reroll = run_monte_carlo(
            lambda: quick_party([("fighter", 3), ("thief", 3)], rng),
            OWLBEAR, 200, rng, "reroll",
        )
        assert "pc_death_rates" not in reroll

    def test_same_seed_same_result(self):
        results = []
        for _ in range(2):
            rng = np.random.default_rng(123)
            results.append(
                run_monte_carlo(
                    lambda: quick_party([("fighter", 3)] * 4, rng),
                    OWLBEAR, 200, rng, "reroll",
                )
            )
        assert results[0]["party_win_rate"] == results[1]["party_win_rate"]
        assert results[0]["avg_rounds"] == results[1]["avg_rounds"]

    def test_invalid_variance_mode_rejected(self):
        rng = np.random.default_rng(0)
        with pytest.raises(ValueError):
            run_monte_carlo(lambda: quick_party([("fighter", 1)], rng),
                            OWLBEAR, 10, rng, "sometimes")
