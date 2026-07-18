"""M13: Spells page -- filters, tagged table, and the tier-vs-effect heatmap.

The effect tags and the heatmap figure come from analyze_spells.py
(load_spells_with_tags / tier_vs_effect_table / make_tier_vs_effect_fig),
the same functions that write reports/spell_analysis.txt and the saved
figure -- EFFECT_KEYWORDS lives in exactly one place.
"""

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "src"))

from common import get_connection  # noqa: E402
from analyze_spells import (  # noqa: E402
    load_spells_with_tags,
    make_tier_vs_effect_fig,
    tier_vs_effect_table,
)


@st.cache_data
def load_tagged_spells():
    return load_spells_with_tags(get_connection())


spells_df = load_tagged_spells()

st.subheader("Shadowdark core spells")
st.caption(f"{len(spells_df)} core spells, tiers 1-{spells_df['tier'].max()}")

filter_cols = st.columns(3)
with filter_cols[0]:
    tiers = sorted(spells_df["tier"].unique())
    selected_tiers = st.multiselect("Tier", tiers, default=tiers)
with filter_cols[1]:
    all_classes = sorted({c for classes in spells_df["classes"] for c in classes.split(",")})
    selected_classes = st.multiselect("Class", all_classes, default=all_classes)
with filter_cols[2]:
    search = st.text_input("Search name or description")

filtered = spells_df[
    spells_df["tier"].isin(selected_tiers)
    & spells_df["classes"].apply(
        lambda classes: any(c in selected_classes for c in classes.split(","))
    )
]
if search:
    filtered = filtered[
        filtered["name"].str.contains(search, case=False, na=False)
        | filtered["description"].str.contains(search, case=False, na=False)
    ]

st.caption(f"{len(filtered)} of {len(spells_df)} spells shown")

display = filtered.assign(effect_tags=filtered["effect_tags"].str.join(", "))
st.dataframe(
    display[["name", "tier", "classes", "dc", "range", "duration", "effect_tags", "description"]],
    width="stretch",
    hide_index=True,
)

st.subheader("Tier vs. effect")
st.caption(
    "Effect tags are a keyword net (EFFECT_KEYWORDS in analyze_spells.py), not "
    "a rules-accurate taxonomy: a spell can match several tags, and one that "
    "matches none is tagged \"other\" -- 9-21 percent of each tier here. Read "
    "this as a rough pattern-finder."
)
st.plotly_chart(
    make_tier_vs_effect_fig(tier_vs_effect_table(spells_df)),
    width="stretch",
)
