"""M15: the reference party is a yardstick -- it must be stable and stated."""

import numpy as np

from batch_sim import (
    REFERENCE_GEAR,
    REFERENCE_STATS,
    build_reference_party,
    reference_party_level,
)
from combat_sim import CLASS_ARMOR, CLASS_WEAPONS
from test_combat_sim import BONUS_FIT


class TestReferenceParty:
    def test_level_clamped_to_pc_range(self):
        assert reference_party_level(0) == 1
        assert reference_party_level(5) == 5
        assert reference_party_level(10) == 10
        assert reference_party_level(30) == 10

    def test_one_of_each_class_with_legal_standard_gear(self):
        rng = np.random.default_rng(0)
        party = build_reference_party(3, BONUS_FIT, rng)
        assert [p.cls for p in party] == ["fighter", "priest", "thief", "wizard"]
        for p in party:
            assert p.armor in CLASS_ARMOR[p.cls]
            assert p.weapon in CLASS_WEAPONS[p.cls]
            assert p.stats == REFERENCE_STATS

    def test_median_stats_are_fixed_not_rolled(self):
        assert all(v == 10 for k, v in REFERENCE_STATS.items() if k != "con")
        assert REFERENCE_STATS["con"] == 12

    def test_same_seed_same_party(self):
        parties = [
            build_reference_party(5, BONUS_FIT, np.random.default_rng(9))
            for _ in range(2)
        ]
        assert [p.hp for p in parties[0]] == [p.hp for p in parties[1]]

    def test_gear_table_covers_all_classes(self):
        assert set(REFERENCE_GEAR) == {"fighter", "priest", "thief", "wizard"}
