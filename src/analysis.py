"""M5 (EDA) + M6 (LV model) -- and shared feature-building for M7.

load_sd_features() is the one place that turns the raw sd_monsters /
sd_attacks tables into a per-monster feature table (best attack bonus,
best avg damage, best num attacks, best stat mod). Both the EDA and the
M6 regression below import and reuse it rather than re-deriving columns.

The eda_* functions each answer one of the README's priority questions
with a saved plot, intentionally stopping at descriptive/visual
exploration. Any trend line drawn there is a plain numpy.polyfit for
visual reference, not a reported model -- the actual fitted models (with
coefficients and R^2 worth reporting) are fit_lv_model() here for M6, and
will be M7's cross-system scaling fit.

Run standalone: python src/analysis.py
"""

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "monsterlab.db"
FIGURES_DIR = ROOT / "reports" / "figures"
REPORT_PATH = ROOT / "reports" / "lv_model.txt"

STAT_MOD_COLS = ["str_mod", "dex_mod", "con_mod", "int_mod", "wis_mod", "cha_mod"]


def load_sd_features(conn: sqlite3.Connection) -> pd.DataFrame:
    """One row per sd_monster with LV-model features derived from sd_attacks.

    A monster can list several attacks (alternative options joined by "or",
    or a multiattack routine joined by "and" -- sd_attacks doesn't keep that
    distinction, see parse_stats.py). We take the single highest-expected-
    damage attack option as "best_round_damage" -- a monster's most
    dangerous single attack -- rather than summing every row, which would
    overcount monsters that just have several alternative weapon choices.
    """
    monsters = pd.read_sql("SELECT * FROM sd_monsters", conn)
    attacks = pd.read_sql("SELECT * FROM sd_attacks", conn)

    attacks = attacks.assign(round_damage=attacks["num_attacks"] * attacks["avg_damage"])
    per_monster_best = attacks.sort_values("round_damage", ascending=False).groupby(
        "monster_id"
    ).first()

    df = monsters.merge(
        per_monster_best[["attack_bonus", "round_damage", "num_attacks", "avg_damage"]],
        left_on="id",
        right_index=True,
        how="left",
    ).rename(
        columns={
            "attack_bonus": "best_attack_bonus",
            "round_damage": "best_round_damage",
            "num_attacks": "best_num_attacks",
            "avg_damage": "best_avg_damage",
        }
    )
    df["best_stat_mod"] = df[STAT_MOD_COLS].max(axis=1)
    return df


def eda_lv_correlations(df: pd.DataFrame) -> pd.Series:
    """Q1: what correlates with LV, and how strongly?"""
    predictors = [
        "ac",
        "hp",
        "best_attack_bonus",
        "best_round_damage",
        "best_num_attacks",
        "best_stat_mod",
    ]
    corr = df[["level"] + predictors].corr()["level"].drop("level").sort_values(
        ascending=False
    )

    fig = px.bar(
        x=corr.index,
        y=corr.values,
        labels={"x": "predictor", "y": "correlation with level"},
        title="Correlation of candidate predictors with Shadowdark LV",
    )
    fig.write_html(FIGURES_DIR / "q1_lv_correlations.html", include_plotlyjs="cdn")
    return corr


def _scatter_with_trend(df: pd.DataFrame, x: str, y: str, title: str, out_name: str) -> None:
    """Plain scatter plus a numpy polyfit line, for visual reference only (not a fitted model)."""
    valid = df[[x, y]].dropna()
    fig = px.scatter(df, x=x, y=y, hover_name="name", title=title)

    slope, intercept = np.polyfit(valid[x], valid[y], 1)
    x_range = [valid[x].min(), valid[x].max()]
    fig.add_trace(
        go.Scatter(
            x=x_range,
            y=[slope * v + intercept for v in x_range],
            mode="lines",
            name="visual trend (not a fitted model)",
        )
    )
    fig.write_html(FIGURES_DIR / out_name, include_plotlyjs="cdn")


def eda_outlier_scatters(df: pd.DataFrame) -> None:
    """Q2: eyeball which monsters sit far from the LV trend (formal residuals come in M6)."""
    _scatter_with_trend(
        df, "best_round_damage", "level", "LV vs. best single-attack round damage", "q2_damage_vs_level.html"
    )
    _scatter_with_trend(df, "hp", "level", "LV vs. HP", "q2_hp_vs_level.html")


def eda_crosswalk_scatters(conn: sqlite3.Connection) -> pd.DataFrame:
    """Q3/Q4: on matched monsters, how do CR/LV, HP, and AC line up across systems."""
    pairs = pd.read_sql(
        """
        SELECT sd.name AS sd_name, sd.level, sd.hp AS sd_hp, sd.ac AS sd_ac,
               fe.name AS fe_name, fe.cr, fe.hp AS fe_hp, fe.ac AS fe_ac
        FROM crosswalk cw
        JOIN sd_monsters sd ON sd.id = cw.sd_id
        JOIN fe_monsters fe ON fe.id = cw.fe_id
        """,
        conn,
    )

    _scatter_with_trend(
        pairs.rename(columns={"sd_name": "name"}),
        "cr",
        "level",
        "5e CR vs. Shadowdark LV (crosswalk pairs)",
        "q3_cr_vs_level.html",
    )
    _scatter_with_trend(
        pairs.rename(columns={"sd_name": "name"}),
        "fe_hp",
        "sd_hp",
        "5e HP vs. Shadowdark HP (crosswalk pairs)",
        "q4_hp_scaling.html",
    )
    _scatter_with_trend(
        pairs.rename(columns={"sd_name": "name"}),
        "fe_ac",
        "sd_ac",
        "5e AC vs. Shadowdark AC (crosswalk pairs)",
        "q4_ac_scaling.html",
    )
    return pairs


def eda_distributions(df: pd.DataFrame) -> None:
    """Q5: flavor distributions -- LV histogram, AC spread by LV, damage-per-round by LV band."""
    fig = px.histogram(df, x="level", nbins=31, title="Shadowdark monster LV distribution")
    fig.write_html(FIGURES_DIR / "q5_level_histogram.html", include_plotlyjs="cdn")

    fig = px.strip(df, x="level", y="ac", hover_name="name", title="AC spread by LV")
    fig.write_html(FIGURES_DIR / "q5_ac_by_level.html", include_plotlyjs="cdn")

    bands = pd.cut(
        df["level"], bins=[-1, 3, 7, 11, 30], labels=["0-3", "4-7", "8-11", "12+"]
    )
    banded = df.assign(level_band=bands)
    fig = px.box(
        banded,
        x="level_band",
        y="best_round_damage",
        title="Best single-attack round damage by LV band",
    )
    fig.write_html(FIGURES_DIR / "q5_damage_by_level_band.html", include_plotlyjs="cdn")


LV_MODEL_FEATURES = [
    "ac",
    "hp",
    "best_attack_bonus",
    "best_avg_damage",
    "best_num_attacks",
    "best_stat_mod",
]


def fit_lv_model(df: pd.DataFrame) -> dict:
    """M6: interpretable linear regression of LV on AC/HP/attack bonus/avg damage/num attacks/best stat mod.

    A handful of monsters (e.g. pure spellcasters whose only listed attack
    is "1 spell +2", with no damage dice) have no avg_damage for their best
    attack; a missing attack entirely (Dryad's staff attack has no bonus
    listed at all pre-fix, none remain post-fix) would similarly leave a
    hole. Both cases are filled with 0 rather than dropped -- "no damage
    dice" and "no bonus" are real, meaningful zeros for those monsters, not
    missing data, and dropping them would throw away legitimate rows.
    """
    from sklearn.linear_model import LinearRegression

    model_df = df.copy()
    model_df[LV_MODEL_FEATURES] = model_df[LV_MODEL_FEATURES].fillna(0)

    X = model_df[LV_MODEL_FEATURES]
    y = model_df["level"]

    model = LinearRegression()
    model.fit(X, y)

    model_df["predicted_level"] = model.predict(X)
    model_df["residual"] = model_df["level"] - model_df["predicted_level"]

    coefficients = pd.Series(model.coef_, index=LV_MODEL_FEATURES).sort_values(
        ascending=False
    )

    return {
        "model": model,
        "coefficients": coefficients,
        "intercept": model.intercept_,
        "r_squared": model.score(X, y),
        "df": model_df,
    }


def report_lv_model(result: dict, n: int = 10) -> str:
    """Format M6's done-criteria: coefficients, R^2, and the top-n residuals both directions."""
    lines = ["## LV model (M6)", ""]
    lines.append(f"R-squared: {result['r_squared']:.3f}")
    lines.append(f"Intercept: {result['intercept']:.3f}")
    lines.append("")
    lines.append("Coefficients:")
    for name, coef in result["coefficients"].items():
        lines.append(f"  {name}: {coef:+.4f}")

    df = result["df"]
    # residual = actual level - predicted level. Negative residual means the
    # model, looking only at AC/HP/attack/damage, expected a *higher* LV than
    # the monster was actually given -- i.e. it punches above its weight for
    # its assigned LV. Positive residual is the reverse: assigned a higher LV
    # than its raw combat stats alone would justify, i.e. punches below its
    # weight (its danger, if any, likely comes from riders/abilities instead).
    punches_above = df.nsmallest(n, "residual")[["name", "level", "predicted_level", "residual"]]
    punches_below = df.nlargest(n, "residual")[["name", "level", "predicted_level", "residual"]]

    lines.append("")
    lines.append(f"Top {n} punch above their weight (stats justify a higher LV than assigned):")
    lines.append(punches_above.to_string(index=False))
    lines.append("")
    lines.append(f"Top {n} punch below their weight (assigned a higher LV than stats justify):")
    lines.append(punches_below.to_string(index=False))

    return "\n".join(lines)


def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        df = load_sd_features(conn)

        corr = eda_lv_correlations(df)
        print("Q1 correlations with level:")
        print(corr.to_string())
        print()

        eda_outlier_scatters(df)
        print("Q2 scatters saved (damage vs level, hp vs level).")
        print()

        pairs = eda_crosswalk_scatters(conn)
        print(f"Q3/Q4 crosswalk scatters saved ({len(pairs)} matched pairs).")
        print("CR vs level correlation:", pairs["cr"].corr(pairs["level"]))
        print("fe_hp vs sd_hp correlation:", pairs["fe_hp"].corr(pairs["sd_hp"]))
        print("fe_ac vs sd_ac correlation:", pairs["fe_ac"].corr(pairs["sd_ac"]))
        print()

        eda_distributions(df)
        print("Q5 distribution plots saved.")
        print()

        result = fit_lv_model(df)
        report = report_lv_model(result)
        print(report)
        REPORT_PATH.write_text(report + "\n", encoding="utf-8")
        print()
        print(f"LV model report saved to {REPORT_PATH}.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
