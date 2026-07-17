"""Stretch goal: tier vs. effect patterns in the Shadowdark core spell list.

sd_spells has no "effect type" field, so effect tags here are a simple,
auditable keyword classifier over each spell's description -- not NLP, just
substring matching against a short, hand-picked keyword list per category
(read EFFECT_KEYWORDS below to see exactly why any spell got tagged the way
it did). A spell can match multiple categories (e.g. Shield Of Faith reads
as both "protection" and "buff"); one that matches none is tagged "other".
This is an approximation, not a rules-accurate taxonomy -- good enough to
see whether higher-tier spells skew toward different effects, not a
substitute for reading the actual spell text.

Run standalone: python src/analyze_spells.py
"""

import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "monsterlab.db"
FIGURES_DIR = ROOT / "reports" / "figures"
REPORT_PATH = ROOT / "reports" / "spell_analysis.txt"

# Keyword -> category, checked as a case-insensitive substring of the spell's
# name + description (name is included because a spell's mechanical effect is
# sometimes only named, not described -- e.g. Charm Person's text says
# "beguile," never "charm"). Order doesn't matter; a spell can hit several
# categories, and one that hits none is tagged "other" -- expect a real
# "other" bucket, this is a keyword net, not a full taxonomy.
EFFECT_KEYWORDS = {
    "damage": ["damage", "dies", "instantly dies", "turns a creature", "into ash"],
    "healing": ["heal", "regain", "regains", "curse", "illness", "affliction"],
    "control": [
        "paralyz", "stun", "frighten", "charm", "beguile", "sleep", "disadvantage",
        "blind", "deafen", "confus", "can't take actions", "can't move", "obeys",
        "flee", "compel",
    ],
    "buff": [
        "advantage", "bonus to", "luck token", "+1 to attack", "additional",
        "magical +", "becomes magical",
    ],
    "protection": [
        "armor class becomes", "impervious", "resist", "protective",
        "bonus to your armor class", "no spells can be cast", "null-magic",
    ],
    "summon": ["summon", "conjuring a", "come to your aid", "under your control"],
    "divination": [
        "ask the gm", "learn the", "discern", "commune", "portent",
        "question", "truthfully", "message", "distant place", "scrying",
    ],
    "utility": [
        "teleport", "fly", "transform", "polymorph", "shapechange", "dimension",
        "misty step", "levitate", "feather fall", "floating disk", "gaseous form",
        "alter self", "float", "illusio", "invisib", "duplicate",
    ],
}


def classify_effects(name: str, description: str) -> list[str]:
    text = f"{name} {description}".lower()
    tags = [cat for cat, keywords in EFFECT_KEYWORDS.items() if any(k in text for k in keywords)]
    return tags or ["other"]


def load_spells_with_tags(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM sd_spells", conn)
    df["effect_tags"] = df.apply(lambda r: classify_effects(r["name"], r["description"]), axis=1)
    return df


def tier_vs_effect_table(df: pd.DataFrame) -> pd.DataFrame:
    """Explode multi-tag spells into one row per (tier, tag) before cross-tabulating."""
    exploded = df.explode("effect_tags").reset_index(drop=True)
    return pd.crosstab(exploded["tier"], exploded["effect_tags"])


def plot_tier_vs_effect(table: pd.DataFrame) -> None:
    fig = px.imshow(
        table,
        labels={"x": "effect tag", "y": "tier", "color": "spell count"},
        title="Shadowdark core spells: tier vs. effect tag",
        text_auto=True,
    )
    fig.write_html(FIGURES_DIR / "spell_tier_vs_effect.html", include_plotlyjs="cdn")


def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        df = load_spells_with_tags(conn)
        table = tier_vs_effect_table(df)
        plot_tier_vs_effect(table)

        tag_by_tier_share = table.div(table.sum(axis=1), axis=0)

        lines = ["## Spell tier vs. effect patterns (stretch goal)", ""]
        lines.append(f"{len(df)} core spells, tiers 1-{df['tier'].max()}.")
        lines.append("")
        lines.append("Spell counts by tier x effect tag:")
        lines.append(table.to_string())
        lines.append("")
        lines.append("Share of each tier's spells per effect tag:")
        lines.append(tag_by_tier_share.round(2).to_string())
        lines.append("")
        lines.append("Class split (wizard/priest/both) by tier:")
        class_table = pd.crosstab(df["tier"], df["classes"])
        lines.append(class_table.to_string())

        report = "\n".join(lines)
        print(report)
        REPORT_PATH.write_text(report + "\n", encoding="utf-8")
        print(f"\nReport saved to {REPORT_PATH}; plot saved to {FIGURES_DIR / 'spell_tier_vs_effect.html'}.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
