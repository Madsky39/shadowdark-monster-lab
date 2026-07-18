"""M14: Monte Carlo combat simulator UI -- real per-PC party composition.

Three build modes (manual grid, quick, random) and two variance modes
(fixed / reroll), all through the same build_pc_* / run_monte_carlo
functions the CLI uses.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "src"))

from common import fit_models, get_connection, load_data  # noqa: E402
from combat_sim import (  # noqa: E402
    ARMOR_BONUS,
    CLASS_WEAPONS,
    HIT_DICE,
    STAT_NAMES,
    build_pc_manual,
    build_pc_quick,
    build_pc_random,
    load_monster,
    run_monte_carlo,
)

sd_df, fe_df, pairs = load_data(get_connection())
models = fit_models(sd_df, pairs)
bonus_fit = models["level_to_bonus"]

st.subheader("Monte Carlo combat simulator: party vs. a Shadowdark monster")
st.caption(
    "Simplified simulation, not a full rules engine -- no initiative, spells, "
    "talents, or conditions; one attack per PC per round; the monster targets "
    "a random living PC with each attack. PC hit dice, stat rolls, and gear "
    "tables follow the actual rules; attack bonus is the LV model's own "
    "LV-to-attack-bonus fit -- see README for the full caveat."
)

monster_name = st.selectbox("Monster", sorted(sd_df["name"].unique()), key="combat_monster")

mode_col, variance_col = st.columns(2)
with mode_col:
    build_mode = st.radio(
        "Party build mode",
        ["Manual", "Quick", "Random"],
        horizontal=True,
        help="Manual: specify every PC in the grid. Quick: pick class and "
             "level per PC, stats and gear are rolled from class-legal "
             "tables. Random: class rolled too.",
    )
with variance_col:
    variance_mode = st.radio(
        "Variance mode",
        ["fixed", "reroll"],
        horizontal=True,
        help="fixed: build the party once and run every trial against it -- "
             "answers \"how does this party fare?\" and reports per-PC death "
             "rates. reroll: rebuild the party every trial -- answers \"how "
             "dangerous is this monster for a random party of this shape?\" "
             "Different questions, different variance.",
    )

if build_mode == "Manual":
    default_rows = pd.DataFrame(
        [
            {"name": "Brand", "cls": "fighter", "level": 3, "str": 16, "dex": 12,
             "con": 14, "int": 8, "wis": 10, "cha": 10, "armor": "chainmail",
             "shield": True, "weapon_die": "1d8"},
            {"name": "Mira", "cls": "priest", "level": 3, "str": 12, "dex": 10,
             "con": 12, "int": 10, "wis": 16, "cha": 13, "armor": "chainmail",
             "shield": True, "weapon_die": "1d6"},
            {"name": "Sly", "cls": "thief", "level": 3, "str": 10, "dex": 16,
             "con": 11, "int": 12, "wis": 10, "cha": 14, "armor": "leather",
             "shield": False, "weapon_die": "1d6"},
            {"name": "Zeth", "cls": "wizard", "level": 3, "str": 8, "dex": 13,
             "con": 10, "int": 17, "wis": 12, "cha": 10, "armor": "none",
             "shield": False, "weapon_die": "1d4"},
        ]
    )
    party_grid = st.data_editor(
        default_rows,
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "cls": st.column_config.SelectboxColumn("cls", options=list(HIT_DICE), required=True),
            "armor": st.column_config.SelectboxColumn("armor", options=list(ARMOR_BONUS), required=True),
            "level": st.column_config.NumberColumn("level", min_value=1, max_value=10, step=1),
        },
    )
elif build_mode == "Quick":
    default_rows = pd.DataFrame(
        [
            {"cls": "fighter", "level": 3},
            {"cls": "priest", "level": 3},
            {"cls": "thief", "level": 3},
            {"cls": "wizard", "level": 3},
        ]
    )
    party_grid = st.data_editor(
        default_rows,
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "cls": st.column_config.SelectboxColumn("cls", options=list(HIT_DICE), required=True),
            "level": st.column_config.NumberColumn("level", min_value=1, max_value=10, step=1),
        },
    )
else:
    size_col, level_col = st.columns(2)
    random_size = size_col.number_input("Party size", min_value=1, max_value=10, value=4)
    random_level = level_col.number_input("Party level", min_value=1, max_value=10, value=3)

trial_col, seed_col = st.columns(2)
trials = trial_col.number_input("Trials", min_value=100, max_value=20000, value=5000, step=100)
seed = seed_col.number_input(
    "Seed (reproducible; same seed, same result)", min_value=0, value=42
)

if st.button("Run simulation"):
    rng = np.random.default_rng(int(seed))

    if build_mode == "Manual":
        rows = party_grid.to_dict("records")

        def party_factory():
            return [
                build_pc_manual(
                    cls=row["cls"],
                    level=int(row["level"]),
                    stats={s: int(row[s]) for s in STAT_NAMES},
                    armor=row["armor"],
                    shield=bool(row["shield"]),
                    weapon="custom",
                    attack_bonus_result=bonus_fit,
                    rng=rng,
                    name=str(row["name"]),
                    weapon_die=str(row["weapon_die"]),
                )
                for row in rows
            ]
    elif build_mode == "Quick":
        rows = party_grid.to_dict("records")

        def party_factory():
            return [
                build_pc_quick(row["cls"], int(row["level"]), bonus_fit, rng, f"PC{i + 1}")
                for i, row in enumerate(rows)
            ]
    else:
        def party_factory():
            return [
                build_pc_random(int(random_level), bonus_fit, rng, f"PC{i + 1}")
                for i in range(int(random_size))
            ]

    monster = load_monster(get_connection(), monster_name)
    result = run_monte_carlo(party_factory, monster, int(trials), rng, variance_mode)

    st.write(
        f"Monster: {monster.name} (AC {monster.ac}, HP {monster.hp}, "
        f"{monster.num_attacks}x attack +{monster.attack_bonus} {monster.damage_dice})"
    )

    if variance_mode == "fixed":
        party = result["party"]
        st.dataframe(
            pd.DataFrame(
                [
                    {"name": p.name, "class": p.cls, "level": p.level, "HP": p.hp,
                     "AC": p.ac, "attack bonus": p.attack_bonus,
                     "weapon": f"{p.weapon} ({p.weapon_die})",
                     "armor": p.armor + (" + shield" if p.shield else "")}
                    for p in party
                ]
            ),
            width="stretch",
            hide_index=True,
        )
    else:
        st.caption("Party rebuilt every trial (reroll variance).")

    metric_cols = st.columns(4)
    metric_cols[0].metric("Party win rate", f"{result['party_win_rate']:.1%}")
    metric_cols[1].metric("Party wipe rate", f"{result['party_wipe_rate']:.1%}")
    metric_cols[2].metric("Timeout rate", f"{result['timeout_rate']:.1%}")
    metric_cols[3].metric("Average rounds", f"{result['avg_rounds']:.1f}")

    outcome_fig = px.bar(
        x=["Party win", "Party wipe", "Timeout"],
        y=[result["party_win_rate"], result["party_wipe_rate"], result["timeout_rate"]],
        labels={"x": "outcome", "y": "rate"},
        title=f"Outcome distribution over {int(trials)} trials ({variance_mode} variance)",
    )
    st.plotly_chart(outcome_fig, width="stretch")

    if "pc_death_rates" in result:
        death_fig = px.bar(
            x=list(result["pc_death_rates"]),
            y=list(result["pc_death_rates"].values()),
            labels={"x": "PC", "y": "death rate"},
            title="Per-PC death rate (fixed party)",
        )
        st.plotly_chart(death_fig, width="stretch")
