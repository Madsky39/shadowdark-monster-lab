"""M9: Shadowdark bestiary explorer (v1 behavior unchanged for core data).

M16: when personal-use custom data is present locally (has_custom_data --
never on the deployed app), the core rows are tagged source='Core', unioned
with sd_monsters_custom, and a source filter appears.
"""

import sys
from pathlib import Path

import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "src"))

from common import (  # noqa: E402
    get_connection,
    has_custom_data,
    load_custom_features,
    load_data,
    render_refresh_button,
)

sd_df, fe_df, pairs = load_data(get_connection())

custom_mode = has_custom_data(get_connection())
if custom_mode:
    import pandas as pd

    custom_df = load_custom_features(get_connection())
    sd_df = pd.concat(
        [sd_df.assign(source="Core"), custom_df], ignore_index=True, sort=False
    )
    st.subheader("Shadowdark bestiary (core + custom)")
else:
    st.subheader("Shadowdark core bestiary")

filter_cols = st.columns(4 if custom_mode else 3)
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
if custom_mode:
    with filter_cols[3]:
        sources = sorted(sd_df["source"].dropna().unique())
        selected_sources = st.multiselect("Source", sources, default=sources)
    filtered = filtered[filtered["source"].isin(selected_sources)]
    render_refresh_button()
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
if custom_mode:
    display_cols.insert(1, "source")
st.dataframe(filtered[display_cols], width="stretch", hide_index=True)

fig = px.histogram(filtered, x="level", nbins=31, title="LV distribution (filtered)")
st.plotly_chart(fig, width="stretch")
