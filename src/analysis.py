"""M5 (EDA) + M6 (LV model) + M7 (cross-system scaling).

load_sd_features() and load_crosswalk_pairs() are the two places that turn
the raw tables into per-monster/per-pair feature tables; the EDA and both
regressions import and reuse them rather than re-deriving columns.

The eda_* functions each answer one of the README's priority questions
with a saved plot, intentionally stopping at descriptive/visual
exploration -- any trend line drawn there is a plain numpy.polyfit for
visual reference, not a reported model. The actual fitted models (with
coefficients and R^2 worth reporting) are fit_lv_model() for M6 and
fit_cr_to_lv()/fit_hp_scaling()/fit_ac_scaling() for M7; plot_fitted_model()
draws their real fitted curve over the scatter, not a disclaimed one.

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
CROSSWALK_REPORT_PATH = ROOT / "reports" / "crosswalk_models.txt"

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


def load_crosswalk_pairs(conn: sqlite3.Connection) -> pd.DataFrame:
    """One row per crosswalk pair with both systems' LV/CR, HP, and AC."""
    return pd.read_sql(
        """
        SELECT sd.name AS sd_name, sd.level, sd.hp AS sd_hp, sd.ac AS sd_ac,
               fe.name AS fe_name, fe.cr, fe.hp AS fe_hp, fe.ac AS fe_ac
        FROM crosswalk cw
        JOIN sd_monsters sd ON sd.id = cw.sd_id
        JOIN fe_monsters fe ON fe.id = cw.fe_id
        """,
        conn,
    )


def eda_crosswalk_scatters(conn: sqlite3.Connection) -> pd.DataFrame:
    """Q3/Q4: on matched monsters, how do CR/LV, HP, and AC line up across systems."""
    pairs = load_crosswalk_pairs(conn)

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


def lv_model_outliers(result: dict, n: int = 10) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split fit_lv_model's residuals into the two outlier tables M6/M8 both need.

    residual = actual level - predicted level. Negative residual means the
    model, looking only at AC/HP/attack/damage, expected a *higher* LV than
    the monster was actually given -- i.e. it punches above its weight for
    its assigned LV. Positive residual is the reverse: assigned a higher LV
    than its raw combat stats alone would justify, i.e. punches below its
    weight (its danger, if any, likely comes from riders/abilities instead).
    """
    df = result["df"]
    cols = ["name", "level", "predicted_level", "residual"]
    punches_above = df.nsmallest(n, "residual")[cols]
    punches_below = df.nlargest(n, "residual")[cols]
    return punches_above, punches_below


def report_lv_model(result: dict, n: int = 10) -> str:
    """Format M6's done-criteria: coefficients, R^2, and the top-n residuals both directions."""
    lines = ["## LV model (M6)", ""]
    lines.append(f"R-squared: {result['r_squared']:.3f}")
    lines.append(f"Intercept: {result['intercept']:.3f}")
    lines.append("")
    lines.append("Coefficients:")
    for name, coef in result["coefficients"].items():
        lines.append(f"  {name}: {coef:+.4f}")

    punches_above, punches_below = lv_model_outliers(result, n)

    lines.append("")
    lines.append(f"Top {n} punch above their weight (stats justify a higher LV than assigned):")
    lines.append(punches_above.to_string(index=False))
    lines.append("")
    lines.append(f"Top {n} punch below their weight (assigned a higher LV than stats justify):")
    lines.append(punches_below.to_string(index=False))

    return "\n".join(lines)


def fit_cross_system_model(pairs: pd.DataFrame, x_col: str, y_col: str, log_x: bool = False) -> dict:
    """Simple regression of y_col on x_col (or log1p(x_col)) across crosswalk pairs."""
    from sklearn.linear_model import LinearRegression

    valid = pairs[[x_col, y_col]].dropna()
    x_raw = valid[x_col].to_numpy().reshape(-1, 1)
    x_feature = np.log1p(x_raw) if log_x else x_raw
    y = valid[y_col].to_numpy()

    model = LinearRegression()
    model.fit(x_feature, y)

    return {
        "model": model,
        "x_col": x_col,
        "y_col": y_col,
        "log_x": log_x,
        "slope": model.coef_[0],
        "intercept": model.intercept_,
        "r_squared": model.score(x_feature, y),
    }


def fit_cr_to_lv(pairs: pd.DataFrame) -> dict:
    """M7 Q3: fit LV ~ CR, trying both linear and log1p(CR) and keeping the better R^2.

    M5's EDA already found log-transforming CR made the correlation worse,
    not better (r=0.89 linear vs. r=0.83 on log1p(CR)) -- this refits both as
    actual models rather than just citing that correlation, but expects the
    same answer.
    """
    linear = fit_cross_system_model(pairs, "cr", "level", log_x=False)
    logged = fit_cross_system_model(pairs, "cr", "level", log_x=True)

    best, other = (linear, logged) if linear["r_squared"] >= logged["r_squared"] else (logged, linear)
    best["alternative_form"] = "log1p(CR)" if best is linear else "CR (linear)"
    best["alternative_r_squared"] = other["r_squared"]
    return best


def fit_hp_scaling(pairs: pd.DataFrame) -> dict:
    """M7 Q4: fit Shadowdark HP ~ 5e HP."""
    return fit_cross_system_model(pairs, "fe_hp", "sd_hp")


def fit_ac_scaling(pairs: pd.DataFrame) -> dict:
    """M7 Q4: fit Shadowdark AC ~ 5e AC."""
    return fit_cross_system_model(pairs, "fe_ac", "sd_ac")


def fit_level_to_attack_bonus(df: pd.DataFrame) -> dict:
    """M8 converter support: Shadowdark LV -> typical Shadowdark attack bonus.

    M7 only fit CR->LV and HP/AC scaling; it didn't cover attack bonus
    because there's no clean single "5e attack bonus" column to translate
    from. But M8's converter still needs to suggest one, and best_attack_bonus
    already correlates with level at r=0.90 within sd_monsters itself (M5/M6)
    -- so once M7's CR->LV fit gives a predicted LV, this simple univariate
    regression (fit on Shadowdark's own LV/attack-bonus relationship) turns
    that into a suggested attack bonus, without inventing a cross-system
    comparison the data doesn't support.
    """
    return fit_cross_system_model(df, "level", "best_attack_bonus")


def plot_fitted_model(pairs: pd.DataFrame, result: dict, title: str, out_name: str) -> None:
    """Scatter plus the actual fitted curve (unlike EDA's disclaimed polyfit trend lines)."""
    x_col, y_col = result["x_col"], result["y_col"]
    valid = pairs[["sd_name", x_col, y_col]].dropna()

    fig = px.scatter(valid, x=x_col, y=y_col, hover_name="sd_name", title=title)

    x_range = np.linspace(valid[x_col].min(), valid[x_col].max(), 100).reshape(-1, 1)
    x_feature = np.log1p(x_range) if result["log_x"] else x_range
    y_fit = result["model"].predict(x_feature)

    form = f"log1p({x_col})" if result["log_x"] else x_col
    label = f"fitted: {y_col} = {result['slope']:.3f}*{form} + {result['intercept']:.3f} (R2={result['r_squared']:.3f})"
    fig.add_trace(go.Scatter(x=x_range.flatten(), y=y_fit, mode="lines", name=label))
    fig.write_html(FIGURES_DIR / out_name, include_plotlyjs="cdn")


def report_crosswalk_models(cr_result: dict, hp_result: dict, ac_result: dict) -> str:
    """Format M7's done-criteria: fitted CR-to-LV, HP scaling, AC scaling."""
    lines = ["## Cross-system scaling (M7)", ""]

    cr_form = "log1p(CR)" if cr_result["log_x"] else "CR"
    lines.append(f"CR -> LV: best form is {cr_form} (R2={cr_result['r_squared']:.3f}; "
                 f"{cr_result['alternative_form']} scored R2={cr_result['alternative_r_squared']:.3f})")
    lines.append(f"  level = {cr_result['slope']:.4f} * {cr_form} + {cr_result['intercept']:.4f}")
    lines.append("")

    lines.append(f"5e HP -> Shadowdark HP: R2={hp_result['r_squared']:.3f}")
    lines.append(f"  sd_hp = {hp_result['slope']:.4f} * fe_hp + {hp_result['intercept']:.4f}")
    lines.append("")

    lines.append(f"5e AC -> Shadowdark AC: R2={ac_result['r_squared']:.3f}")
    lines.append(f"  sd_ac = {ac_result['slope']:.4f} * fe_ac + {ac_result['intercept']:.4f}")

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
        print()

        cr_result = fit_cr_to_lv(pairs)
        hp_result = fit_hp_scaling(pairs)
        ac_result = fit_ac_scaling(pairs)
        plot_fitted_model(pairs, cr_result, "5e CR -> Shadowdark LV (fitted)", "m7_cr_to_lv.html")
        plot_fitted_model(pairs, hp_result, "5e HP -> Shadowdark HP (fitted)", "m7_hp_scaling.html")
        plot_fitted_model(pairs, ac_result, "5e AC -> Shadowdark AC (fitted)", "m7_ac_scaling.html")

        crosswalk_report = report_crosswalk_models(cr_result, hp_result, ac_result)
        print(crosswalk_report)
        CROSSWALK_REPORT_PATH.write_text(crosswalk_report + "\n", encoding="utf-8")
        print()
        print(f"Cross-system scaling report saved to {CROSSWALK_REPORT_PATH}.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
