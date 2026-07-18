"""M9: Streamlit multipage entrypoint.

Runs ensure_database() and defines the st.navigation structure, nothing
else -- all page content lives under app/pages_/, all shared cached
loaders/constants live in app/common.py.

Run: streamlit run app/dashboard.py
"""

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "src"))

from common import ensure_database, render_license_footer  # noqa: E402

st.set_page_config(page_title="Shadowdark Monster Lab", layout="wide")

ensure_database()

PAGES_DIR = ROOT / "app" / "pages_"

pages = [
    st.Page(str(PAGES_DIR / "insights.py"), title="Insights", icon=":material/insights:", default=True),
    st.Page(str(PAGES_DIR / "sd_bestiary.py"), title="Shadowdark Bestiary", icon=":material/pest_control:"),
    st.Page(str(PAGES_DIR / "fe_bestiary.py"), title="5e Bestiary", icon=":material/menu_book:"),
    st.Page(str(PAGES_DIR / "converter.py"), title="Converter", icon=":material/swap_horiz:"),
    st.Page(str(PAGES_DIR / "spells.py"), title="Spells", icon=":material/auto_fix_high:"),
    st.Page(str(PAGES_DIR / "simulator.py"), title="Combat Simulator", icon=":material/swords:"),
]

st.title("Shadowdark Monster Lab")

navigation = st.navigation(pages)
navigation.run()

render_license_footer()
