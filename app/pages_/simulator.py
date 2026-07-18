"""M9: Monte Carlo combat simulator UI -- moved unchanged from the v1
"Combat Simulator" tab into its own page. Rebuilt for real per-PC party
composition in M14; this is still the v1 uniform party_size x party_level
version.
"""

import sys
from pathlib import Path

import numpy as np
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "src"))

from common import fit_models, get_connection, load_data  # noqa: E402
from combat_sim import (  # noqa: E402
    ARMOR_BONUS,
    HIT_DICE,
    load_monster,
    make_party,
    run_monte_carlo,
)

sd_df, fe_df, pairs = load_data(get_connection())
models = fit_models(sd_df, pairs)

st.subheader("Monte Carlo combat simulator: party vs. a Shadowdark monster")
st.caption(
    "Simplified simulation, not a full rules engine -- no initiative, spells, "
    "talents, or conditions; one attack per PC per round. PC stats are a "
    "documented approximation (real class hit dice, standard armor math, and "
    "the LV model's own LV-to-attack-bonus fit) -- see README for the full caveat."
)

monster_name = st.selectbox("Monster", sorted(sd_df["name"].unique()), key="combat_monster")

col1, col2, col3, col4 = st.columns(4)
party_size = col1.number_input("Party size", min_value=1, max_value=10, value=4)
party_level = col2.number_input(
    "Party level", min_value=0, max_value=int(sd_df["level"].max()), value=3
)
class_name = col3.selectbox("Class", list(HIT_DICE))
armor = col4.selectbox("Armor", list(ARMOR_BONUS), index=list(ARMOR_BONUS).index("chainmail"))

col5, col6, col7, col8 = st.columns(4)
shield = col5.checkbox("Shield (+2 AC)", value=True)
con_mod = col6.number_input("CON mod", min_value=-4, max_value=4, value=1)
dex_mod = col7.number_input("DEX mod", min_value=-4, max_value=4, value=1)
weapon_dice = col8.text_input("Weapon damage dice", value="1d8")

col9, col10 = st.columns(2)
trials = col9.number_input("Trials", min_value=100, max_value=20000, value=5000, step=100)
use_seed = col10.checkbox("Fixed seed (reproducible)", value=False)
seed = 42 if use_seed else None

if st.button("Run simulation"):
    rng = np.random.default_rng(seed)
    party = make_party(
        int(party_size), int(party_level), models["level_to_bonus"], rng,
        class_name=class_name, con_mod=int(con_mod), dex_mod=int(dex_mod),
        armor=armor, shield=shield, weapon_dice=weapon_dice,
    )
    monster = load_monster(get_connection(), monster_name)

    st.write(
        f"Party: {int(party_size)}x level {int(party_level)} {class_name}, "
        f"HP {[p.hp for p in party]}, AC {party[0].ac}, attack bonus +{party[0].attack_bonus}"
    )
    st.write(
        f"Monster: {monster.name} (AC {monster.ac}, HP {monster.hp}, "
        f"{monster.num_attacks}x attack +{monster.attack_bonus} {monster.damage_dice})"
    )

    result = run_monte_carlo(party, monster, int(trials), rng)

    metric_cols = st.columns(4)
    metric_cols[0].metric("Party win rate", f"{result['party_win_rate']:.1%}")
    metric_cols[1].metric("Party wipe rate", f"{result['party_wipe_rate']:.1%}")
    metric_cols[2].metric("Timeout rate", f"{result['timeout_rate']:.1%}")
    metric_cols[3].metric("Average rounds", f"{result['avg_rounds']:.1f}")

    outcome_fig = px.bar(
        x=["Party win", "Party wipe", "Timeout"],
        y=[result["party_win_rate"], result["party_wipe_rate"], result["timeout_rate"]],
        labels={"x": "outcome", "y": "rate"},
        title=f"Outcome distribution over {int(trials)} trials",
    )
    st.plotly_chart(outcome_fig, width="stretch")
