"""M9: Shadowdark core bestiary explorer -- moved unchanged from the v1
"Bestiary Explorer" tab into its own page.
"""

import sys
from pathlib import Path

import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "src"))

from common import get_connection, load_data  # noqa: E402

sd_df, fe_df, pairs = load_data(get_connection())

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
st.dataframe(filtered[display_cols], width="stretch", hide_index=True)

fig = px.histogram(filtered, x="level", nbins=31, title="LV distribution (filtered)")
st.plotly_chart(fig, width="stretch")
