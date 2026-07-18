"""M11 + M15: Insights landing page.

The archetype scatter and empirical difficulty validation (M15) lead the
page, followed by Model A (the no-HP model, the one with interpretable
coefficients) and Model B (LV from threat_score alone), with the v1 full
model demoted to the validation footnote it turned out to be. All numbers
come from the same shared functions the written reports use
(analysis.difficulty_validation / fit_lv_model_a / fit_lv_threat_model), so
the page and reports/ cannot drift. Win rates come from the committed
reports/sim_results.csv; if it is missing locally the page hints at
python src/batch_sim.py instead of crashing.
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
from analysis import difficulty_validation, load_sim_results, lv_model_outliers  # noqa: E402

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


# ---------------------------------------------------------------------------
# M15: archetype scatter (the landing-page centerpiece) + validation
# ---------------------------------------------------------------------------
st.subheader("The bestiary at a glance")

sim_df = load_sim_results()

scatter_df = sd_df[sd_df["effective_dpr"] > 0].copy()
n_dropped = len(sd_df) - len(scatter_df)
hover_data = {"level": True}
if sim_df is not None:
    scatter_df = scatter_df.merge(sim_df[["name", "win_rate"]], on="name", how="left")
    hover_data["win_rate"] = ":.1%"

scatter = px.scatter(
    scatter_df,
    x="effective_hp",
    y="effective_dpr",
    color="level",
    hover_name="name",
    hover_data=hover_data,
    log_x=True,
    log_y=True,
    labels={"effective_hp": "effective HP (damage to drop it)",
            "effective_dpr": "effective DPR (expected damage per round)"},
    title="Every core monster: offense vs. defense (log-log), colored by LV",
)
scatter.add_annotation(
    xref="paper", yref="paper", x=0.02, y=0.98, showarrow=False,
    text="<b>glass cannons</b><br>hit hard, drop fast",
)
scatter.add_annotation(
    xref="paper", yref="paper", x=0.98, y=0.02, showarrow=False,
    text="<b>sponges</b><br>soak damage, hit soft",
)
st.plotly_chart(scatter, width="stretch")
caption = (
    "effective_dpr and effective_hp from src/metrics.py (M10): expected damage "
    "output and required damage input against a reference party. "
    f"{n_dropped} monsters with no parsed damaging attack are omitted (log axes)."
)
if sim_df is not None:
    caption += " Hover shows the reference party's simulated win rate."
st.caption(caption)

if sim_df is None:
    st.info("No reports/sim_results.csv -- run python src/batch_sim.py to add "
            "simulated win rates and the difficulty validation below.")
else:
    st.subheader("Does the metric survive contact with the simulator?")
    validation = difficulty_validation(sim_df, models["lv_a"], models["lv_b"])
    c = validation["correlations"]

    st.markdown(
        f"Reference-party win rates for all {c['n_all']} core monsters "
        f"({int(sim_df['trials'].iloc[0])} trials each, seed "
        f"{int(sim_df['seed'].iloc[0])}; party definition in src/batch_sim.py). "
        "Spearman rank correlation with win rate, matched set first "
        "(LV 10 and under, where party level equals monster LV; above that "
        "the party is clamped at level 10 by design):"
    )
    corr_cols = st.columns(4)
    corr_cols[0].metric("printed LV (matched)", f"{c['matched_lv_vs_win']:+.3f}")
    corr_cols[1].metric("threat_score (matched)", f"{c['matched_threat_vs_win']:+.3f}")
    corr_cols[2].metric("printed LV (all)", f"{c['all_lv_vs_win']:+.3f}")
    corr_cols[3].metric("threat_score (all)", f"{c['all_threat_vs_win']:+.3f}")
    st.markdown(
        "**threat_score predicts simulated outcomes better than printed LV on "
        "both sets.** The gap is the rider effects: printed LV prices in "
        "abilities the sim and the metric both cannot see."
    )

    st.markdown(
        "**Disagreement table.** Monsters whose printed LV sits far above what "
        "threat_score predicts (Model B residual) while the sim also finds them "
        "easier than their LV median (win_excess at or above 0). Two independent "
        "measurements agreeing against printed LV is the signature of "
        "rider-dependent danger: petrify, curses, level drain, spellcasting. "
        "a_residual cross-references the M11 Model A outliers."
    )
    st.dataframe(validation["disagreement"], width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# M11: LV models
# ---------------------------------------------------------------------------
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
