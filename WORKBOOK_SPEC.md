# Monster Lab Workbook: a guided data-lifecycle gym

## Purpose and prime directive

This adds a `workbook/` directory of Jupyter notebooks to the existing
shadowdark-monster-lab repo. The notebooks are EXERCISES for the repo owner, who
is preparing for a data analytics master's program. He writes the analysis code
himself. Your job is to build the scaffolding, hints, and answer checks.

**PRIME DIRECTIVE: Never write solution code in a TODO cell. Not as a comment,
not as a docstring example, not "just to show the pattern." A TODO cell contains
only: the task description, the starter variable names, and `...` placeholders.
If you are ever unsure whether something counts as a solution, leave it out.**

The one exception: notebook 00 and the first cell of each notebook may contain
complete *setup* code (imports, db connection, loading a dataframe) since setup
is not the skill being trained.

## How each exercise cell works

Every exercise is three cells:

1. **Task cell (markdown):** states the question in plain language, names the
   phase skill being practiced, and defines what variable(s) the learner must
   produce (e.g., "produce a dataframe `ac_by_band` with columns lv_band,
   avg_ac").
2. **Work cell (code):** starter skeleton with `...` placeholders only.
3. **Check cell (code):** asserts against known-good values computed from the
   existing database/pipeline (row counts, specific values rounded to 2-3
   decimals, column names, R-squared to 2 decimals, etc.). On pass, print a
   short confirmation plus one sentence of context. On fail, the assert message
   should say WHAT is wrong (wrong row count, wrong value) but never HOW to fix
   it.

Hints go in a collapsed `<details><summary>Hint</summary>` block in the task
cell: at most 2 hints per exercise, hint 1 conceptual, hint 2 naming the
function/clause to look up (e.g., "look up pandas .groupby and .agg") -- never
a code line.

Compute the known-good check values yourself while building the workbook (you
may write throwaway scripts to derive them; delete the scripts after). Do not
leave your derivation code in the notebooks.

## The notebooks (one per lifecycle phase)

**00_setup.ipynb** -- Environment check. Complete working code (no exercises):
connect to `data/monsterlab.db`, print table names and row counts, render one
plot to confirm matplotlib works. Ends with a markdown map of the lifecycle
phases and which notebook covers each.

**01_frame.ipynb** -- Problem framing (business understanding). No code.
Markdown prompts where he writes: a one-paragraph problem statement for the
monster lab, three specific answerable questions, and for each question what
data would answer it and what a wrong answer would cost a GM at the table.
Include a good/bad example of a problem statement (on an unrelated topic, e.g.
coffee shop sales, so it can't be copied).

**02_acquire.ipynb** -- Data acquisition. He pulls the Open5e SPELLS endpoint
himself (different endpoint from anything in src/, so no existing code answers
it): requests with params, pagination loop, save raw JSON to
`workbook/data/raw/`. Exercises: fetch one page; count total results from the
response metadata; loop all pages politely; cache so re-runs skip the network.
Checks: file exists, JSON parses, expected record count (derive the current
count while building; assert with a sensible tolerance, e.g. +/- 10%, since
the API can change).

**03_store.ipynb** -- Storage and data management. He designs a table for the
spells he pulled: writes the CREATE TABLE himself (task cell specifies required
columns and types in words, not SQL), loads rows with executemany, then answers
three questions with SQL only: counts by school/level, a WHERE + ORDER BY, a
JOIN against fe_monsters is not possible with spells so instead a GROUP BY with
HAVING. Checks: schema via PRAGMA table_info, row count, query results.

**04_clean.ipynb** -- Cleaning and preparation. Give him 15 raw Shadowdark
attack strings (hardcode them in the setup cell, chosen from the real data to
cover: simple, multi-clause with and/or, ranged, negative bonus, rider text,
and one genuinely unparseable). He writes his own regex/parsing function and
computes his parse success rate. Checks: his parsed output for specific strings
matches known-good tuples; final cell compares his success rate to the
pipeline's 99.7% and links to src/parse_stats.py as the "official" solution to
study AFTER passing.

**05_explore.ipynb** -- EDA. Against sd_monsters/sd_attacks: LV distribution
(histogram + skew), AC vs LV scatter, damage-per-round by LV band, correlation
matrix of the model features. Each plot exercise is followed by a markdown
prompt: "State in one sentence what this chart claims." Checks: correlation
values, band means.

**06_model.ipynb** -- Modeling. The leakage discovery, earned first-hand:
(a) fit LinearRegression with HP included, check asserts R-squared ~= 0.997;
(b) markdown cell asks "Why should this worry you?" BEFORE any reveal;
(c) a details block then explains hit-die-per-level leakage;
(d) he refits without HP, check asserts R-squared ~= 0.82;
(e) he extracts and interprets coefficients, and pulls the top-5 residuals
both directions. Checks: R-squared values to 2 decimals, top-residual monster
names as sets.

**07_validate.ipynb** -- Evaluation. Train/test split (fixed random_state) and
comparison of train vs test R-squared; residual plot; Spearman vs Pearson on
win_rate vs printed LV using reports/sim_results.csv, with a markdown prompt on
why rank correlation fits ordinal-ish game levels. Checks: split scores within
tolerance, correlation values.

**08_communicate.ipynb** -- Communication. No new computation. He writes a
findings memo (300-500 words, audience: a GM who has never seen a regression)
covering: what was measured, the three most defensible findings, one limitation,
one recommendation. Provide a structure outline and a checklist cell he
self-scores. End with a markdown cell mapping everything he just did to the
seven phases of a data analytics life cycle, with blanks for him to fill in
what he did for each phase (this doubles as prep for his first course's
reflection task).

## Mechanics

- All notebooks read the EXISTING `data/monsterlab.db` (plus workbook/data/ for
  02-03). Never modify existing tables; workbook-created tables get a `wb_`
  prefix or live in `workbook/data/workbook.db`.
- Add `jupyterlab`, `scipy` to requirements.txt if missing.
- `workbook/README.md`: how to launch, the rules of engagement (asserts are the
  teacher; debug before asking for help; when asking an AI for help, ask for a
  hint not the code), expected effort (1-2 evenings per notebook), and the
  order.
- Commit message: "Workbook: guided lifecycle notebooks (exercises only, no
  solutions)".
- After building, verify the prime directive by grepping the notebooks: no
  TODO/work cell may contain a complete assignment to the target variable.

## Definition of done

A learner who completes 01-08 has personally executed every lifecycle phase at
small scale: framed a question, acquired data from an API, designed storage,
cleaned messy text, explored and visualized, fit and de-biased a model,
validated it, and written it up for a non-technical reader.
