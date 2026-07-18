"""M9: Spells page -- new in v2, placeholder for now.

Full scope (tier/class filters, name/description search, tier-vs-effect
heatmap sharing analyze_spells.EFFECT_KEYWORDS) is M13. This is a minimal
version so the page is reachable in the meantime rather than empty.
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "src"))

from common import get_connection  # noqa: E402

st.subheader("Shadowdark core spells")
st.caption(
    "Minimal view for now -- tier/class filters, description search, and the "
    "tier-vs-effect heatmap arrive in M13."
)

spells_df = pd.read_sql("SELECT * FROM sd_spells", get_connection())
st.caption(f"{len(spells_df)} core spells")
st.dataframe(
    spells_df[["name", "tier", "classes", "dc", "range", "duration"]],
    width="stretch",
    hide_index=True,
)
