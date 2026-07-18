# Shadowdark Monster Lab

A weekend data analytics project: ingest Shadowdark RPG and D&D 5e SRD monster data,
store it in SQLite, analyze what actually drives Shadowdark monster level (LV),
derive an empirical 5e-to-Shadowdark conversion model, and serve it all from a
Streamlit dashboard with a monster converter tab.

**Live dashboard: [monsterlab.streamlit.app](https://monsterlab.streamlit.app)**

See [shadowdark-monster-lab-spec.md](shadowdark-monster-lab-spec.md) for the v1 spec
(M1-M8 plus stretch goals, complete) and
[shadowdark-monster-lab-spec-v2.md](shadowdark-monster-lab-spec-v2.md) for the v2 spec
(multipage restructure, new metrics, empirical difficulty study; in progress).

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
python src/ingest_spells.py       # sd_spells: 85 core spells
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

Stretch goals:

- [x] Monte Carlo combat simulator (below)
- [x] Spell data ingest and analysis (below)
- [x] PDF stat block intake via shadowdark-parser for owned books (below)
- [x] PDF stat block intake parsed locally, no Node.js required (below)

v2 status (see [shadowdark-monster-lab-spec-v2.md](shadowdark-monster-lab-spec-v2.md)):

- [x] M9 -- Multipage restructure (above)
- [ ] M10-M16 -- not started

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

## Dashboard (M8, restructured to multipage in M9)

`streamlit run app/dashboard.py` -- a multipage app using `st.Page` /
`st.navigation`. `app/dashboard.py` is just the entrypoint (runs
`ensure_database()`, defines the navigation); the shared cached data/model
loading (`load_data`, `fit_models`) and the license footer live in
`app/common.py`, which every page imports from -- no page imports from
another page, so there's one place data loading can drift from the reports/
CLI, not several. Pages:

1. **Insights** (default landing page): currently the v1 "LV Model
   Findings" content (M6's R², coefficients chart, predicted-vs-actual
   scatter, and both outlier tables from `lv_model_outliers()`), carried
   over as-is. M11 replaces this with the no-HP and threat-score models;
   M15 adds the archetype scatter and difficulty-validation summary as the
   landing-page centerpiece.
2. **Shadowdark Bestiary**: filter the Shadowdark core bestiary by level
   range, alignment, and name search; see the filtered table and a live LV
   histogram. Unchanged from v1.
3. **5e Bestiary**: new in v2. Minimal for now (name search over the SRD
   monster list) -- CR/type/size filters, a live CR histogram, a predicted
   Shadowdark LV column, and crosswalk matches arrive in M12.
4. **Converter**: pick an SRD monster from a dropdown (auto-fills its
   CR/HP/AC) or enter stats manually, and get a suggested Shadowdark stat
   block (LV/AC/HP/attack bonus) using the M7 fits, plus an expander
   showing the exact formulas used. Attack bonus isn't a direct
   cross-system fit (M7 didn't cover it -- there's no single 5e "attack
   bonus" column to translate from); it's `fit_level_to_attack_bonus()`,
   fit on Shadowdark's own LV-to-attack-bonus relationship and applied to
   the predicted LV. Unchanged from v1.
5. **Spells**: new in v2. Minimal for now (table of all 85 core spells) --
   tier/class filters and the tier-vs-effect heatmap arrive in M13.
6. **Combat Simulator**: the Monte Carlo stretch goal (see below), with
   inputs for the monster, party size/level/class/gear, and trial count,
   running live in-browser (5000 trials resolves well under a second).
   Still the v1 uniform party_size x party_level version; rebuilt with real
   per-PC composition in M14.

`ensure_database()` (in `app/common.py`) also runs the spells ingest on a
cold start now, since `sd_spells` comes from the same freely licensed
source as the bestiary and the ingest is fast.

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

## Stretch goal: spell data ingest and analysis

```bash
python src/ingest_spells.py    # sd_spells: 85 core spells
python src/analyze_spells.py   # tier vs. effect report + heatmap
```

`sd_spells` loads tier, classes, DC, range, duration, and description for
all 85 core spells (same source/cache as the bestiary). There's no "effect
type" field in the source data, so `analyze_spells.py` tags each spell's
*name + description* against a short, hand-picked keyword list per category
(damage/healing/control/buff/protection/summon/divination/utility) --
`EFFECT_KEYWORDS` in that file is the whole classifier, readable top to
bottom, not a model. A spell can match several tags; one that matches none
is tagged "other" (9-21% per tier here) -- that's an expected keyword-net
miss rate, not a bug, and the report/heatmap (`reports/spell_analysis.txt`,
`reports/figures/spell_tier_vs_effect.html`) should be read as a rough
pattern-finder, not a rules-accurate taxonomy.

Findings: **summon spells only appear at tier 3+** (0% of tiers 1-2, then
6/5/13% of tiers 3/4/5) -- Shadowdark reserves conjuring allies for
higher-tier casters. **Buff spells cluster at the tier extremes** (19%/15%
of tiers 1/2, dropping to 0% at tier 3, then back up to 13% at tier 5).
**Damage-spell share is flat across tiers** (12-17%) -- tiers scale damage
*amount* (bigger dice), not how often a tier's spell list is damage-focused.
**The wizard:priest split is stable across all five tiers** (roughly 2:1
wizard-leaning at every tier, no tier where one class dominates more than
another).

## Stretch goal: PDF stat block intake for owned books

This project only ever ingests freely-licensed data directly (the
Shadowdark core JSON, the 5e SRD). Stat blocks from other books you own --
Cursed Scrolls, third-party products -- can't be fetched or committed here;
per [shadowdark-parser](https://github.com/ashleytowner/shadowdark-parser)'s
own README, JSON derived from them "should only be used for personal use."
So the workflow is split across a tool boundary:

1. Copy the statblock text out of your own PDF.
2. Run it through shadowdark-parser yourself -- a separate, Node-based CLI
   tool, **not** a dependency of this Python project:
   ```bash
   npx shadowdark-parser -b -o parsed.json your_statblocks.txt
   ```
3. Point this script at that JSON:
   ```bash
   python src/ingest_pdf_statblocks.py --input parsed.json --source "Cursed Scrolls 1"
   ```

That loads monsters into `sd_monsters_custom` / `sd_attacks_custom` --
same shape as the core `sd_monsters`/`sd_attacks`, plus a `source` column
for provenance across however many books you process. Unlike the core
ingest scripts, this one does **not** drop-and-rebuild on every run (your
personal library accumulates over time); instead each monster is upserted
by name, so re-running on the same file updates rather than duplicates.
Both tables live inside `data/monsterlab.db`, which is gitignored, so
nothing derived from a book you own is ever committed. Attack damage is
parsed by reusing `parse_damage()` from `parse_stats.py` (M3), so a Cursed
Scrolls monster's avg_damage is computed exactly the same way a core
monster's is. Entries with a non-numeric level/AC/HP (shadowdark-parser
allows a variable stat like `*`) are logged and skipped rather than
crashing the ingest, same philosophy as M3's parse failures.

Caveat: this environment has no Node.js/npm, so the integration was
validated against a hand-built JSON fixture matching shadowdark-parser's
documented output schema (from reading its `entity.ts`/`statblock.ts`/
`attacks.ts` source directly) rather than the actual tool's output. The
field mapping should be exact, but if a future shadowdark-parser release
changes its schema, re-verify against real output before trusting it on a
real book.

### Alternative: parsing a PDF directly, no Node.js required

`src/parse_pdf_statblocks.py` is a second front door into the same
`sd_monsters_custom` / `sd_attacks_custom` tables that skips the Node.js
tool and the copy-paste step entirely:

```bash
python src/parse_pdf_statblocks.py --pdf mybook.pdf --source "Cursed Scrolls 1"
```

It reads the PDF locally with `pdfplumber` (a pure-Python dependency, listed
in `requirements.txt` but never imported by `app/dashboard.py` or any
`app/pages_/*.py` -- the deployed app never touches it), extracts each stat
block with a regex grammar matching the Shadowdark core rulebook's layout
(`NAME` / `LV n, Alignment, Type` / `AC n HP n ATK ... MV ...` /
`S x D x C x I x W x CH x`), and calls the same `upsert_monster()` from
`ingest_pdf_statblocks.py` to write it -- so there's exactly one place that
owns the DB write and upsert-by-name logic, not two. Attack clauses reuse
`parse_stats.SPLIT_CLAUSES_RE` / `parse_clause()` directly, the same M3
grammar the core bestiary already uses, so avg_damage is computed exactly
the same way for a PDF monster as for a core one.

This is a best-effort extraction, not a guaranteed-correct parser --
third-party books format stat blocks differently. Use `--debug` to print
every field it matched before anything is written, and `--dry-run` to parse
without touching the database:

```bash
python src/parse_pdf_statblocks.py --pdf mybook.pdf --source "..." --debug --dry-run
```

A monster with an unparseable attack clause still loads (the bad clause is
logged and dropped, same as M3); a monster the regex can't find at all
isn't silently skipped -- it just won't appear in the debug output or the
matched count, so check that count against the book's actual monster count.
Validated against a hand-written text fixture matching the documented
layout, not a real third-party PDF (none was available in this
environment) -- if your book's layout differs, adjust `MONSTER_RE` in that
file for it rather than trusting a partial import. Same as
`ingest_pdf_statblocks.py`, both tables live only in the gitignored
`data/monsterlab.db`; nothing from a book you own is ever committed or
reaches the deployed app.

## Deployment: Streamlit Community Cloud

Live at **[monsterlab.streamlit.app](https://monsterlab.streamlit.app)**.

`data/monsterlab.db` is gitignored (it's a build artifact, not source), so
a fresh clone -- including a fresh Streamlit Cloud container -- doesn't
have it. `app/dashboard.py` handles that itself: it calls
`ensure_database()` (defined in `app/common.py`) before building the
navigation, which runs the ingest/parse/crosswalk/spells pipeline once on
first load if the DB is missing, using the small cached JSON already
committed at `data/raw/shadowdark/` and `data/raw/open5e/` (both
freely-licensed source data, unlike the PDF-intake stretch goals' tables,
which are local-only and never run here). That first load takes a few
seconds longer; every load after is instant, same as running `run_all.py`
locally then launching normally.
