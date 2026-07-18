"""M9: 5e -> Shadowdark converter -- moved unchanged from the v1
"5e -> Shadowdark Converter" tab into its own page.
"""

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "src"))

from common import apply_cross_system_fit, fit_models, get_connection, load_data  # noqa: E402

sd_df, fe_df, pairs = load_data(get_connection())
models = fit_models(sd_df, pairs)

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
