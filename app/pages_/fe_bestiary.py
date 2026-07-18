"""M12: 5e SRD bestiary explorer, parallel in spirit to the Shadowdark one.

The predicted SD LV column applies the same M7 CR-to-LV fit the Converter
page uses (models["cr_to_lv"] from the shared fit_models), so the two pages
cannot disagree about a monster; the crosswalk column joins the same pairs
table the M7 fits were trained on.
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

sd_df, fe_df, pairs = load_data(get_connection())
models = fit_models(sd_df, pairs)

st.subheader("5e SRD bestiary")

filter_cols = st.columns(4)
with filter_cols[0]:
    cr_min, cr_max = float(fe_df["cr"].min()), float(fe_df["cr"].max())
    cr_range = st.slider("CR range", min_value=cr_min, max_value=cr_max, value=(cr_min, cr_max))
with filter_cols[1]:
    types = sorted(fe_df["type"].dropna().unique())
    selected_types = st.multiselect("Type", types, default=types)
with filter_cols[2]:
    sizes = sorted(fe_df["size"].dropna().unique())
    selected_sizes = st.multiselect("Size", sizes, default=sizes)
with filter_cols[3]:
    name_search = st.text_input("Search name")

filtered = fe_df[
    fe_df["cr"].between(*cr_range)
    & fe_df["type"].isin(selected_types)
    & fe_df["size"].isin(selected_sizes)
]
if name_search:
    filtered = filtered[filtered["name"].str.contains(name_search, case=False, na=False)]

# Predicted SD LV: the M7 CR-to-LV fit, applied vectorized. Same model object
# the Converter page uses; shown to one decimal here where the Converter
# rounds to a whole LV for its stat block.
cr_fit = models["cr_to_lv"]
cr_values = filtered["cr"].to_numpy().reshape(-1, 1)
x_feature = np.log1p(cr_values) if cr_fit["log_x"] else cr_values
filtered = filtered.assign(
    predicted_sd_lv=np.clip(cr_fit["model"].predict(x_feature), 0, None).round(1),
    sd_crosswalk=filtered["name"].map(
        pairs.drop_duplicates("fe_name").set_index("fe_name")["sd_name"]
    ),
)

st.caption(f"{len(filtered)} of {len(fe_df)} monsters shown")
st.dataframe(
    filtered[
        ["name", "cr", "predicted_sd_lv", "ac", "hp", "size", "type", "sd_crosswalk"]
    ],
    width="stretch",
    hide_index=True,
)
st.caption(
    "predicted_sd_lv applies the M7 CR-to-LV fit "
    f"(level = {cr_fit['slope']:.3f} * CR + {cr_fit['intercept']:.3f}, "
    f"R2 = {cr_fit['r_squared']:.3f}) -- the bridge to the Converter page, "
    "which rounds it to a whole LV and adds AC/HP/attack bonus. sd_crosswalk "
    "names the matched Shadowdark monster where one exists in the M4 "
    "crosswalk."
)

fig = px.histogram(filtered, x="cr", nbins=31, title="CR distribution (filtered)")
st.plotly_chart(fig, width="stretch")
