"""M9: Insights landing page.

For now this carries over the v1 M6 "LV Model Findings" tab content unchanged
(so that v1 functionality stays reachable through the new navigation). M11
replaces this with Model A (no-HP) / Model B (threat score) and a reframed
writeup, and M15 adds the archetype scatter and difficulty-validation
summary as the landing-page centerpiece -- this page is the one both will be
written into.
"""

import sys
from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "src"))

from common import fit_models, get_connection, load_data  # noqa: E402
from analysis import lv_model_outliers  # noqa: E402

sd_df, fe_df, pairs = load_data(get_connection())
models = fit_models(sd_df, pairs)

st.subheader("M6: what predicts Shadowdark LV")
st.caption(
    "This is the v1 model, carried over as-is for now. M11 adds a no-HP model "
    "(the one whose coefficients are actually interpretable) and a single-feature "
    "threat-score model alongside it; M15 adds an empirical difficulty scatter."
)

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
st.plotly_chart(coef_fig, width="stretch")

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
st.plotly_chart(pred_fig, width="stretch")

st.subheader("Outliers: which monsters punch above/below their weight")
punches_above, punches_below = lv_model_outliers(lv_result, n=10)
col_above, col_below = st.columns(2)
with col_above:
    st.markdown("**Punch above their weight** (stats justify a higher LV)")
    st.dataframe(punches_above, width="stretch", hide_index=True)
with col_below:
    st.markdown("**Punch below their weight** (assigned a higher LV than stats justify)")
    st.dataframe(punches_below, width="stretch", hide_index=True)
