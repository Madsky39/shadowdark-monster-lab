# Shadowdark Monster Lab

A weekend data analytics project: ingest Shadowdark RPG and D&D 5e SRD monster data,
store it in SQLite, analyze what actually drives Shadowdark monster level (LV),
derive an empirical 5e-to-Shadowdark conversion model, and serve it all from a
Streamlit dashboard with a monster converter tab.

See [shadowdark-monster-lab-spec.md](shadowdark-monster-lab-spec.md) for the full
project spec, schema, and milestone list.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Running the pipeline

Each script is runnable standalone and rebuilds only its own table(s):

```bash
python src/ingest_shadowdark.py   # M1: sd_monsters
python src/ingest_open5e.py       # M2: fe_monsters (cached to data/raw/open5e/)
python src/parse_stats.py         # M3: sd_attacks
python src/build_crosswalk.py     # M4: crosswalk
python src/analysis.py            # M5-M7: EDA + LV model + cross-system scaling reports/plots
```

Or run the whole pipeline in order with `python run_all.py`.

Then launch the dashboard:

```bash
streamlit run app/dashboard.py
```

`data/monsterlab.db` and `data/raw/` are gitignored and rebuilt locally by these
scripts. `reports/figures/` (saved EDA plots) is also gitignored -- regenerate it
with `python src/analysis.py`.

## Data sources & licensing

- Shadowdark core monster data: [dickloraine/shadowdark-resources](https://github.com/dickloraine/shadowdark-resources)
  (`data/bestiary_data.json`), licensed free to use under the Shadowdark RPG
  Third-Party License.
- D&D 5e SRD monsters: [Open5e API](https://api.open5e.com/), filtered to
  `document__slug=wotc-srd`.

All output here is for personal use.

> This work is an independent product published under the Shadowdark RPG
> Third-Party License and is not affiliated with The Arcane Library, LLC.
> Shadowdark RPG © 2023 The Arcane Library, LLC.
>
> This work includes material taken from the System Reference Document 5.1
> ("SRD 5.1") by Wizards of the Coast LLC and available at
> https://dnd.wizards.com/resources/systems-reference-document. The SRD 5.1 is
> licensed under the Creative Commons Attribution 4.0 International License
> available at https://creativecommons.org/licenses/by/4.0/legalcode.

## Milestone status

- [x] M1 -- Shadowdark ingest (243 core monsters)
- [x] M2 -- Open5e ingest (322 SRD monsters)
- [x] M3 -- Attack string parsing (358/359 clauses, 99.7% success)
- [x] M4 -- Crosswalk (143 matched pairs: 114 exact, 29 fuzzy auto-accepted;
      100 lower-confidence candidates in `data/crosswalk_fuzzy_review.csv` for
      manual review)
- [x] M5 -- EDA (below)
- [x] M6 -- LV model (below)
- [x] M7 -- Cross-system scaling (below)
- [x] M8 -- Dashboard (below)

## EDA findings (M5)

Plots: `python src/analysis.py` writes to `reports/figures/`.

1. **What predicts LV?** HP tracks LV almost perfectly (r=0.998) -- Shadowdark
   clearly derives HP directly from level -- followed by best attack bonus
   (r=0.90) and best single-attack round damage (r=0.82); AC is the weakest
   predictor (r=0.66).
2. **Outliers.** Monsters like the Archdevil, Greater Fire Elemental, and
   Phoenix hit far harder than their LV alone would predict, while
   Mordanticus the Flayed, the Hydra, and Medusa hit much softer than their
   LV suggests -- their danger comes from riders/special abilities (petrify,
   regeneration, curses) rather than raw round damage.
3. **CR-to-LV mapping.** On the 143 crosswalk pairs, plain CR vs. LV
   correlates at r=0.89, and log-transforming either axis *reduces* that
   correlation -- the relationship looks closer to linear than log or
   piecewise.
4. **HP/AC scaling.** 5e HP vs. Shadowdark HP correlates strongly (r=0.90);
   5e AC vs. Shadowdark AC is weaker (r=0.79), consistent with AC being the
   weaker LV predictor above.
5. **Distributions.** LV is heavily right-skewed (most core monsters are
   LV 0-10; a long thin tail runs up to the Tarrasque at LV 30). AC spread
   narrows at higher LV bands, and best-single-attack round damage rises
   with LV band but with wide variance within each band.

## LV model (M6)

Full report (coefficients, R², top-10 residuals both directions):
`python src/analysis.py` writes it to `reports/lv_model.txt`.

A plain `sklearn.linear_model.LinearRegression` predicting `level` from AC,
HP, best attack bonus, best avg damage, best num attacks, and best stat mod
gets **R² = 0.997**. That's almost entirely HP doing the work -- HP alone
already correlates with LV at r=0.998 (see EDA finding 1), so this model is
close to learning "HP predictor" and validating that with the other four
predictors, whose coefficients (all under 0.06 in magnitude, mixed signs)
should be read cautiously given how collinear they are with HP and LV.

Because the fit is this tight, the residuals are small in absolute terms
(largest is only ~1.6 levels) -- there are no dramatic outliers, just mild
ones. The monsters that punch *above* their weight (raw stats justify a
higher LV than assigned) are mostly high-HP grapplers/ambushers -- Hydra,
Roper, stone/clay Golems, Bulette. The monsters that punch *below* their
weight (assigned a higher LV than stats justify) are almost all spellcasters
or incorporeal/legendary types -- Archmage, Druid, Mage, Wraith, Ghost,
Phoenix -- consistent with the EDA finding that their danger comes from
spells/abilities rather than raw AC/HP/attack numbers.

## Cross-system scaling (M7)

Full report: `python src/analysis.py` writes it to
`reports/crosswalk_models.txt`; fitted-curve-over-scatter plots go to
`reports/figures/m7_*.html`.

Three simple `LinearRegression` fits on the 143 crosswalk pairs, each trying
CR both as-is and log1p-transformed and keeping whichever scored higher
(matching M5's finding that log made the CR/LV correlation worse, not
better):

- **CR -> LV**: `level = 0.719 * CR + 2.31` (R² = 0.792, vs. 0.689 for
  log1p(CR)). Confirms M5's read that the relationship is closer to linear
  than log across the CR range in this data.
- **5e HP -> Shadowdark HP**: `sd_hp = 0.198 * fe_hp + 10.32` (R² = 0.810).
- **5e AC -> Shadowdark AC**: `sd_ac = 0.613 * fe_ac + 5.01` (R² = 0.630) --
  the weakest of the three fits, consistent with AC being the weakest LV
  predictor in M6 and the weakest cross-system correlation in M5.

These three formulas are the conversion math M8's dashboard tab will use to
turn a 5e monster's CR/HP/AC into suggested Shadowdark LV/HP/AC.

## Dashboard (M8)

`streamlit run app/dashboard.py` -- four tabs:

1. **Bestiary Explorer**: filter the Shadowdark core bestiary by level range,
   alignment, and name search; see the filtered table and a live LV
   histogram.
2. **LV Model Findings**: M6's R², coefficients chart, predicted-vs-actual
   scatter, and both outlier tables (punches above/below weight) from
   `lv_model_outliers()`.
3. **5e -> Shadowdark Converter**: pick an SRD monster from a dropdown (auto-
   fills its CR/HP/AC) or enter stats manually, and get a suggested
   Shadowdark stat block (LV/AC/HP/attack bonus) using the M7 fits, plus an
   expander showing the exact formulas used. Attack bonus isn't a direct
   cross-system fit (M7 didn't cover it -- there's no single 5e "attack
   bonus" column to translate from); it's `fit_level_to_attack_bonus()`,
   fit on Shadowdark's own LV-to-attack-bonus relationship and applied to
   the predicted LV.
4. **Combat Simulator**: the Monte Carlo stretch goal (see below), with
   inputs for the monster, party size/level/class/gear, and trial count,
   running live in-browser (5000 trials resolves well under a second).

All four tabs share cached data/model loading (`load_data`/`fit_models` in
`app/dashboard.py`) built on the same `src/analysis.py` and `src/combat_sim.py`
functions used by the M5-M7 reports and the standalone simulator CLI, so the
dashboard and the written reports/CLI can't drift apart from each other.

## Stretch goal: Monte Carlo combat simulator

```bash
python src/combat_sim.py --monster Owlbear --party-size 4 --party-level 3 --trials 5000
```

Simulates a party of N level-X PCs vs. a chosen `sd_monsters` entry, round
by round (party attacks, then the monster attacks back), tracking
Shadowdark's actual crit rule (natural 20 doubles the damage dice, natural 1
always misses). Over `--trials` runs it reports party win rate, wipe rate,
timeout rate, and average rounds to resolve the fight.

This isn't a full rules engine -- no initiative, spells, talents, or
conditions, one attack per PC per round. PC stats are a deliberately simple
approximation, not an exact reimplementation of Shadowdark's per-class
talent tables (which this project never ingested): HP uses the real,
well-documented hit dice per class (Fighter d8/Priest d6/Thief+Wizard d4)
and standard armor math (10 + DEX + armor bonus, cross-checked against our
own `sd_monsters` AC-by-`armor_type` averages); attack bonus reuses
`fit_level_to_attack_bonus()` from M8, since Shadowdark levels are
calibrated so a same-level monster is a fair fight -- "what attack bonus
does a level-X monster have" is a reasonable, data-grounded stand-in for a
level-X PC's, rather than a guessed talent progression. Every input
(class, armor, CON/DEX mod, weapon dice) is a CLI flag if your table's
numbers differ.
