"""M8: Streamlit dashboard -- bestiary explorer, LV model findings, 5e -> Shadowdark
converter, and (stretch goal) a Monte Carlo combat simulator.

Run: streamlit run app/dashboard.py
"""

import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from analysis import (  # noqa: E402  (path must be set before this import)
    fit_ac_scaling,
    fit_cr_to_lv,
    fit_hp_scaling,
    fit_level_to_attack_bonus,
    fit_lv_model,
    load_crosswalk_pairs,
    load_sd_features,
    lv_model_outliers,
)
from combat_sim import (  # noqa: E402
    ARMOR_BONUS,
    HIT_DICE,
    load_monster,
    make_party,
    run_monte_carlo,
)

DB_PATH = ROOT / "data" / "monsterlab.db"

st.set_page_config(page_title="Shadowdark Monster Lab", layout="wide")


@st.cache_resource
def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH), check_same_thread=False)


@st.cache_data
def load_data(_conn: sqlite3.Connection) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sd_df = load_sd_features(_conn)
    fe_df = pd.read_sql("SELECT * FROM fe_monsters", _conn)
    pairs = load_crosswalk_pairs(_conn)
    return sd_df, fe_df, pairs


@st.cache_data
def fit_models(sd_df: pd.DataFrame, pairs: pd.DataFrame) -> dict:
    return {
        "lv": fit_lv_model(sd_df),
        "cr_to_lv": fit_cr_to_lv(pairs),
        "hp_scaling": fit_hp_scaling(pairs),
        "ac_scaling": fit_ac_scaling(pairs),
        "level_to_bonus": fit_level_to_attack_bonus(sd_df),
    }


def apply_cross_system_fit(result: dict, x: float) -> float:
    """Apply an already-fit fit_cross_system_model() result to a single new x value."""
    x_feature = np.log1p([[x]]) if result["log_x"] else [[x]]
    return float(result["model"].predict(x_feature)[0])


sd_df, fe_df, pairs = load_data(get_connection())
models = fit_models(sd_df, pairs)

st.title("Shadowdark Monster Lab")

tab_explorer, tab_model, tab_converter, tab_combat = st.tabs(
    ["Bestiary Explorer", "LV Model Findings", "5e -> Shadowdark Converter", "Combat Simulator"]
)

# ---------------------------------------------------------------------------
# Tab 1: Bestiary explorer
# ---------------------------------------------------------------------------
with tab_explorer:
    st.subheader("Shadowdark core bestiary")

    filter_cols = st.columns(3)
    with filter_cols[0]:
        level_range = st.slider(
            "Level range",
            min_value=int(sd_df["level"].min()),
            max_value=int(sd_df["level"].max()),
            value=(int(sd_df["level"].min()), int(sd_df["level"].max())),
        )
    with filter_cols[1]:
        alignments = sorted(sd_df["alignment"].dropna().unique())
        selected_alignments = st.multiselect("Alignment", alignments, default=alignments)
    with filter_cols[2]:
        name_search = st.text_input("Search name")

    filtered = sd_df[
        sd_df["level"].between(*level_range)
        & sd_df["alignment"].isin(selected_alignments)
    ]
    if name_search:
        filtered = filtered[filtered["name"].str.contains(name_search, case=False, na=False)]

    st.caption(f"{len(filtered)} of {len(sd_df)} monsters shown")

    display_cols = [
        "name",
        "level",
        "ac",
        "hp",
        "alignment",
        "attacks_raw",
        "best_attack_bonus",
        "best_stat_mod",
    ]
    st.dataframe(filtered[display_cols], use_container_width=True, hide_index=True)

    fig = px.histogram(filtered, x="level", nbins=31, title="LV distribution (filtered)")
    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Tab 2: LV model findings
# ---------------------------------------------------------------------------
with tab_model:
    st.subheader("M6: what predicts Shadowdark LV")

    lv_result = models["lv"]
    st.metric("R-squared", f"{lv_result['r_squared']:.3f}")
    st.caption(
        "HP alone correlates with LV at r=0.998, so this model is close to learning "
        "“HP predicts LV” and validating that with four smaller, collinear "
        "predictors -- see README for the full caveat."
    )

    coef_fig = px.bar(
        x=lv_result["coefficients"].index,
        y=lv_result["coefficients"].values,
        labels={"x": "feature", "y": "coefficient"},
        title="LV model coefficients",
    )
    st.plotly_chart(coef_fig, use_container_width=True)

    pred_fig = px.scatter(
        lv_result["df"],
        x="predicted_level",
        y="level",
        hover_name="name",
        title="Predicted vs. actual LV",
    )
    lo, hi = lv_result["df"]["level"].min(), lv_result["df"]["level"].max()
    pred_fig.add_trace(
        go.Scatter(x=[lo, hi], y=[lo, hi], mode="lines", name="perfect prediction")
    )
    st.plotly_chart(pred_fig, use_container_width=True)

    st.subheader("Outliers: which monsters punch above/below their weight")
    punches_above, punches_below = lv_model_outliers(lv_result, n=10)
    col_above, col_below = st.columns(2)
    with col_above:
        st.markdown("**Punch above their weight** (stats justify a higher LV)")
        st.dataframe(punches_above, use_container_width=True, hide_index=True)
    with col_below:
        st.markdown("**Punch below their weight** (assigned a higher LV than stats justify)")
        st.dataframe(punches_below, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Tab 3: Converter
# ---------------------------------------------------------------------------
with tab_converter:
    st.subheader("Convert a 5e SRD monster to a suggested Shadowdark stat block")

    input_mode = st.radio("Input", ["Pick an SRD monster", "Manual entry"], horizontal=True)

    if input_mode == "Pick an SRD monster":
        monster_name = st.selectbox("SRD monster", sorted(fe_df["name"].unique()))
        row = fe_df.loc[fe_df["name"] == monster_name].iloc[0]
        cr, hp, ac = float(row["cr"]), float(row["hp"]), float(row["ac"])
        st.caption(f"5e stats: CR {row['cr']}, HP {row['hp']}, AC {row['ac']}")
    else:
        monster_name = "Custom monster"
        col1, col2, col3 = st.columns(3)
        cr = col1.number_input("5e CR", min_value=0.0, value=1.0, step=0.125)
        hp = col2.number_input("5e HP", min_value=1.0, value=20.0, step=1.0)
        ac = col3.number_input("5e AC", min_value=1.0, value=13.0, step=1.0)

    cr_result = models["cr_to_lv"]
    predicted_level = max(0, round(apply_cross_system_fit(cr_result, cr)))
    predicted_hp = max(1, round(apply_cross_system_fit(models["hp_scaling"], hp)))
    predicted_ac = round(apply_cross_system_fit(models["ac_scaling"], ac))
    predicted_bonus = round(
        apply_cross_system_fit(models["level_to_bonus"], predicted_level)
    )

    with st.container(border=True):
        st.markdown(f"### {monster_name}")
        st.markdown(f"**LV {predicted_level}**")
        st.markdown(f"AC {predicted_ac}  |  HP {predicted_hp}  |  ATK {predicted_bonus:+d}")

    with st.expander("How this was calculated"):
        st.write(
            f"LV = {cr_result['slope']:.4f} * "
            f"{'log1p(CR)' if cr_result['log_x'] else 'CR'} + "
            f"{cr_result['intercept']:.4f}  (R2={cr_result['r_squared']:.3f})"
        )
        st.write(
            f"Shadowdark HP = {models['hp_scaling']['slope']:.4f} * 5e HP + "
            f"{models['hp_scaling']['intercept']:.4f}  "
            f"(R2={models['hp_scaling']['r_squared']:.3f})"
        )
        st.write(
            f"Shadowdark AC = {models['ac_scaling']['slope']:.4f} * 5e AC + "
            f"{models['ac_scaling']['intercept']:.4f}  "
            f"(R2={models['ac_scaling']['r_squared']:.3f})"
        )
        st.write(
            f"Attack bonus = {models['level_to_bonus']['slope']:.4f} * predicted LV + "
            f"{models['level_to_bonus']['intercept']:.4f}  "
            f"(R2={models['level_to_bonus']['r_squared']:.3f}) -- fit on Shadowdark's own "
            "LV-to-attack-bonus relationship, not a cross-system translation (M7 didn't "
            "fit one; there's no single 5e “attack bonus” column to translate from)."
        )

# ---------------------------------------------------------------------------
# Tab 4: Combat simulator (stretch goal)
# ---------------------------------------------------------------------------
with tab_combat:
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
        st.plotly_chart(outcome_fig, use_container_width=True)
