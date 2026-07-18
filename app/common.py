"""M9: shared cached loaders, connection, and constants for the multipage app.

Every page under app/pages_/ imports from here rather than from each other or
from src/ directly for the cached/shared pieces -- this is the one place data
loading and model fitting happen, so the dashboard, the written reports, and
the CLI tools all stay backed by the same src/ functions (see design
principle 2, "no drift," in the spec).
"""

import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from analysis import (  # noqa: E402  (path must be set before this import)
    fit_ac_scaling,
    fit_cr_to_lv,
    fit_hp_scaling,
    fit_level_to_attack_bonus,
    fit_lv_model,
    fit_lv_model_a,
    fit_lv_threat_model,
    load_crosswalk_pairs,
    load_sd_features_with_metrics,
    lv_model_outliers,
)
import build_crosswalk  # noqa: E402
import ingest_open5e  # noqa: E402
import ingest_shadowdark  # noqa: E402
import ingest_spells  # noqa: E402
import parse_stats  # noqa: E402

DB_PATH = ROOT / "data" / "monsterlab.db"


def _has_table(table: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    try:
        return (
            conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            is not None
        )
    finally:
        conn.close()


def ensure_database() -> None:
    """Cloud deploys start from a fresh checkout with no monsterlab.db (it's gitignored,
    a build artifact -- see README). Build it once from the committed raw JSON caches
    (data/raw/shadowdark/, data/raw/open5e/) the same way run_all.py does locally, so a
    fresh Streamlit Cloud container bootstraps itself on first load instead of crashing.
    sd_monsters/fe_monsters/sd_attacks/crosswalk/sd_spells are built here -- the spells
    ingest is fast and comes from the same freely licensed source as the bestiary, so
    it's included; the PDF-intake stretch goal (sd_monsters_custom/sd_attacks_custom)
    is local-only and never runs here (see src/parse_pdf_statblocks.py /
    src/ingest_pdf_statblocks.py).

    Streamlit Cloud redeploys don't necessarily wipe the container's filesystem, so a
    DB built by an older version of this function (before sd_spells existed) can still
    be sitting there -- DB_PATH.exists() alone would wrongly skip the top-up and every
    page reading sd_spells would crash. Check for the specific table a new version
    added rather than just file presence, so upgrading in place also works."""
    if not DB_PATH.exists():
        with st.spinner("First run: building the database from cached data..."):
            ingest_shadowdark.main()
            conn = sqlite3.connect(DB_PATH)
            try:
                pages = ingest_open5e.fetch_pages(refresh=False)
                ingest_open5e.build_fe_monsters(conn, pages)
            finally:
                conn.close()
            parse_stats.main()
            build_crosswalk.main()
            ingest_spells.main()
        return

    if not _has_table("sd_spells"):
        with st.spinner("Adding spell data..."):
            ingest_spells.main()


@st.cache_resource
def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH), check_same_thread=False)


@st.cache_data
def load_data(_conn: sqlite3.Connection) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    # sd_df carries the M10 metric columns (effective_dpr/effective_hp/
    # threat_score/archetype_ratio) so the Insights models and future pages
    # share one load path with the reports.
    sd_df = load_sd_features_with_metrics(_conn)
    fe_df = pd.read_sql("SELECT * FROM fe_monsters", _conn)
    pairs = load_crosswalk_pairs(_conn)
    return sd_df, fe_df, pairs


@st.cache_data
def fit_models(sd_df: pd.DataFrame, pairs: pd.DataFrame) -> dict:
    return {
        "lv": fit_lv_model(sd_df),
        "lv_a": fit_lv_model_a(sd_df),
        "lv_b": fit_lv_threat_model(sd_df),
        "cr_to_lv": fit_cr_to_lv(pairs),
        "hp_scaling": fit_hp_scaling(pairs),
        "ac_scaling": fit_ac_scaling(pairs),
        "level_to_bonus": fit_level_to_attack_bonus(sd_df),
    }


def apply_cross_system_fit(result: dict, x: float) -> float:
    """Apply an already-fit fit_cross_system_model() result to a single new x value."""
    x_feature = np.log1p([[x]]) if result["log_x"] else [[x]]
    return float(result["model"].predict(x_feature)[0])


LICENSE_FOOTER = (
    "This work is an independent product published under the Shadowdark RPG "
    "Third-Party License and is not affiliated with The Arcane Library, LLC. "
    "Shadowdark RPG © 2023 The Arcane Library, LLC.\n\n"
    "This work includes material taken from the System Reference Document 5.1 "
    '("SRD 5.1") by Wizards of the Coast LLC and available at '
    "https://dnd.wizards.com/resources/systems-reference-document. The SRD 5.1 "
    "is licensed under the Creative Commons Attribution 4.0 International "
    "License available at https://creativecommons.org/licenses/by/4.0/legalcode."
)


def render_license_footer() -> None:
    st.divider()
    st.caption(LICENSE_FOOTER)
