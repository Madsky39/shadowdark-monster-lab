"""M9: 5e bestiary page -- new in v2, placeholder for now.

Full scope (CR/type/size filters, live CR histogram, predicted SD LV column,
crosswalk match column) is M12. This is a minimal version so the page is
reachable and useful in the meantime rather than empty.
"""

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "src"))

from common import get_connection, load_data  # noqa: E402

sd_df, fe_df, pairs = load_data(get_connection())

st.subheader("5e SRD bestiary")
st.caption(
    "Minimal view for now -- type/size filters, a live CR histogram, a predicted "
    "SD LV column, and crosswalk matches arrive in M12."
)

name_search = st.text_input("Search name")
filtered = fe_df
if name_search:
    filtered = filtered[filtered["name"].str.contains(name_search, case=False, na=False)]

st.caption(f"{len(filtered)} of {len(fe_df)} monsters shown")
st.dataframe(
    filtered[["name", "cr", "ac", "hp", "size", "type"]],
    width="stretch",
    hide_index=True,
)
