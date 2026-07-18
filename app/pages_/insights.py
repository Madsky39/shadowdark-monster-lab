"""M11: Insights landing page -- LV model v2.

Renders Model A (the no-HP model, the one with interpretable coefficients)
and Model B (LV from threat_score alone), with the v1 full model demoted to
the validation footnote it turned out to be. All numbers come from the same
shared fit functions the written report uses (analysis.fit_lv_model_a /
fit_lv_threat_model via common.fit_models), so the page and
reports/lv_model.txt cannot drift.

M15 adds the archetype scatter and the empirical difficulty validation here.
"""

import sys
from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "src"))

from common import fit_models, get_connection, load_data  # noqa: E402
from analysis import lv_model_outliers  # noqa: E402

sd_df, fe_df, pairs = load_data(get_connection())
models = fit_models(sd_df, pairs)


def predicted_vs_actual(result: dict, title: str):
    fig = px.scatter(
        result["df"],
        x="predicted_level",
        y="level",
        hover_name="name",
        title=title,
    )
    lo, hi = result["df"]["level"].min(), result["df"]["level"].max()
    fig.add_trace(
        go.Scatter(x=[lo, hi], y=[lo, hi], mode="lines", name="perfect prediction")
    )
    return fig


def outlier_columns(result: dict, n: int = 10) -> None:
    punches_above, punches_below = lv_model_outliers(result, n=n)
    col_above, col_below = st.columns(2)
    with col_above:
        st.markdown("**Punch above their weight** (stats justify a higher LV)")
        st.dataframe(punches_above, width="stretch", hide_index=True)
    with col_below:
        st.markdown("**Punch below their weight** (assigned a higher LV than stats justify)")
        st.dataframe(punches_below, width="stretch", hide_index=True)


st.subheader("What predicts Shadowdark LV")
st.markdown(
    "HP tracks LV at r = 0.998 because Shadowdark gives monsters one hit die "
    "per level: HP is derived from LV by construction, not discovered. A model "
    "that includes HP is therefore a data-quality validation, not an insight. "
    "The two models below are the ones built to say something."
)

# ---------------------------------------------------------------------------
# Model A: no-HP model
# ---------------------------------------------------------------------------
a_result = models["lv_a"]

st.subheader("Model A: what buys a level, HP excluded")
metric_col, text_col = st.columns([1, 3])
metric_col.metric("R-squared", f"{a_result['r_squared']:.3f}")
text_col.caption(
    "LV regressed on AC, best attack bonus, best avg damage, best num attacks, "
    "and best stat mod. With HP out, the coefficients are interpretable: each "
    "one says how much of a level that stat buys."
)

coef_fig = px.bar(
    x=a_result["coefficients"].index,
    y=a_result["coefficients"].values,
    labels={"x": "feature", "y": "coefficient"},
    title="Model A coefficients (LV per unit of each feature)",
)
st.plotly_chart(coef_fig, width="stretch")

st.plotly_chart(
    predicted_vs_actual(a_result, "Model A: predicted vs. actual LV"),
    width="stretch",
)

st.markdown("**Model A outliers.** The punch-below list is now nearly all "
            "spellcasters and rider-effect monsters (Druid, Lich, Viperian "
            "Wizard, Goblin Shaman, Rat Swarm): their danger is in spells and "
            "special abilities the attack parser cannot see.")
outlier_columns(a_result)

# ---------------------------------------------------------------------------
# Model B: threat model
# ---------------------------------------------------------------------------
b_result = models["lv_b"]

st.subheader("Model B: one number against printed LV")
metric_col, text_col = st.columns([1, 3])
metric_col.metric("R-squared", f"{b_result['r_squared']:.3f}")
text_col.caption(
    "LV regressed on threat_score alone: sqrt(effective_dpr * effective_hp) "
    "from the M10 metrics module, expected damage output times expected "
    "damage soak against a reference party. One derived number recovers "
    "most of printed LV."
)

st.plotly_chart(
    predicted_vs_actual(b_result, "Model B: predicted vs. actual LV"),
    width="stretch",
)

st.markdown("**Model B outliers.** The punch-below list recovers the v1 "
            "outlier roster (Archmage, Hydra, Medusa, Lich, Vampire, Druid): "
            "monsters whose printed LV prices in petrify, curses, regeneration, "
            "or spellcasting that no attack-math metric can measure.")
outlier_columns(b_result)

# ---------------------------------------------------------------------------
# Comparison with the v1 full model
# ---------------------------------------------------------------------------
st.subheader("Model comparison")
v1_result = models["lv"]
comparison = pd.DataFrame(
    [
        {
            "model": "v1 full (M6)",
            "features": "AC, HP, attack bonus, avg damage, num attacks, stat mod",
            "R-squared": round(v1_result["r_squared"], 3),
            "what it is for": "validation: data matches the 1-hit-die-per-level rule",
        },
        {
            "model": "Model A",
            "features": "the same, HP excluded",
            "R-squared": round(a_result["r_squared"], 3),
            "what it is for": "interpretation: what each stat buys at a level",
        },
        {
            "model": "Model B",
            "features": "threat_score only",
            "R-squared": round(b_result["r_squared"], 3),
            "what it is for": "single-metric difficulty check",
        },
    ]
)
st.dataframe(comparison, width="stretch", hide_index=True)
st.caption(
    "Full residual tables for every model: reports/lv_model.txt, regenerated "
    "by python src/analysis.py from the same fit functions this page calls."
)
