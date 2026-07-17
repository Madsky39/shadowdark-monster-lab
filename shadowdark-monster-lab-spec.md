# Shadowdark Monster Lab

A weekend data analytics project: build a pipeline that ingests Shadowdark RPG and D&D 5e SRD monster data, stores it in SQLite, analyzes what actually drives monster level (LV), derives an empirical 5e-to-Shadowdark conversion model, and serves it all from a Streamlit dashboard with a monster converter tab.

Owner context: the builder is practicing the full analytics life cycle (acquire, store, clean, explore, model, present) ahead of a data analytics master's program. Prefer clarity over cleverness. He should be able to read every SQL query and understand every modeling step. Explain schema and modeling decisions in comments.

## Tech stack

- Python 3.11+
- requests (Open5e API), sqlite3 (stdlib, no ORM), pandas, scikit-learn, plotly, streamlit
- No Docker, no async, no config frameworks. One requirements.txt, one SQLite file.

## Data sources

1. Shadowdark core data (monsters, spells, items) as JSON, licensed free under the Shadowdark License:
   - Repo: https://github.com/dickloraine/shadowdark-resources (JSON lives in the `data/` folder)
   - Clone it or download the raw JSON files. Inspect the actual structure before writing the loader; do not assume field names.
2. D&D 5e SRD monsters via the Open5e API:
   - https://api.open5e.com/ (monsters endpoint, paginated JSON)
   - Filter to SRD/open content documents. Handle pagination. Cache the raw responses to `data/raw/` so re-runs do not hammer the API.
3. Optional later expansion (NOT this weekend): ashleytowner/shadowdark-parser can convert stat blocks from owned PDFs (e.g., Cursed Scrolls) into JSON for personal use.

Licensing note: all output is for personal use. Keep the Shadowdark third-party license attribution line in the README.

## Project structure

```
shadowdark-monster-lab/
  README.md
  requirements.txt
  data/
    raw/            # cached source JSON, gitignored
    monsterlab.db   # SQLite database, gitignored
  src/
    ingest_shadowdark.py
    ingest_open5e.py
    parse_stats.py      # attack string parsing, derived columns
    build_crosswalk.py  # match monsters that exist in both systems
    analysis.py         # EDA queries + regression, importable functions
  notebooks/            # optional scratch space
  app/
    dashboard.py        # Streamlit
```

## Database schema (SQLite)

Design for readable SQL, not normalization purity. Suggested tables; adjust to the real source data after inspecting it:

**sd_monsters**: id, name, level (INTEGER, the target variable), ac, hp, attacks_raw (TEXT), move, str_mod, dex_mod, con_mod, int_mod, wis_mod, cha_mod, alignment, traits_json (TEXT)

**sd_attacks** (parsed from attacks_raw): monster_id, num_attacks, attack_name, attack_bonus, damage_dice, avg_damage (REAL, computed from dice notation), rider_text
- Shadowdark attack strings look like: `1 beak +2 (1d4 + blood drain)`. Parse with regex. Log and skip unparseable rows rather than crashing; report a parse success rate.

**fe_monsters** (5e): id, name, cr (REAL, convert fractions like "1/4" to 0.25), ac, hp, hit_dice, size, type, str, dex, con, int, wis, cha, actions_json, document_slug

**crosswalk**: sd_id, fe_id, match_type ('exact' | 'fuzzy' | 'manual'), confidence, notes
- Build by lowercase exact name match first, then fuzzy match (difflib is fine) with a review threshold. Write fuzzy candidates to a CSV for human review rather than auto-accepting below 0.9 similarity.

## Milestones

Each milestone must end in a working, runnable state. Stop-anytime is a design goal.

**M1 - Shadowdark ingest.** Load the Shadowdark monster JSON into sd_monsters. Done when: `SELECT COUNT(*)` returns the full core bestiary and a spot-check of 5 named monsters matches the book.

**M2 - Open5e ingest.** Pull SRD monsters with pagination and caching into fe_monsters. Done when: count is in the plausible SRD range (hundreds), CRs parsed to floats, raw JSON cached locally.

**M3 - Stat parsing.** Populate sd_attacks with parsed attack data and avg_damage. Done when: parse success rate is reported and >90%, failures logged to a file.

**M4 - Crosswalk.** Match monsters present in both systems. Done when: exact matches are loaded, fuzzy candidates are in a review CSV, and there are at least ~30 matched pairs to model on.

**M5 - EDA.** analysis.py functions + a few saved plots answering the priority questions below. Done when: each question has a query/plot and a one-line finding written into README.

**M6 - LV model.** Linear regression predicting sd_monsters.level from AC, HP, attack bonus, avg damage, num attacks, best stat mod. Report coefficients, R², and the top 10 largest residuals in both directions (over- and under-statted monsters). Keep it interpretable; no ensemble models.

**M7 - Cross-system scaling.** On crosswalk pairs: fit CR-to-LV, plus how HP and AC translate between systems. Simple regression with a plot of the fitted curve over the scatter.

**M8 - Dashboard.** Streamlit app with tabs: (1) bestiary explorer with filters, (2) LV model findings incl. outlier tables, (3) converter: input 5e stats (or pick an SRD monster from a dropdown), output suggested Shadowdark LV, AC, HP, and attack bonus using the M6/M7 models, displayed as a Shadowdark-style stat block.

## Analysis questions, in priority order

1. What actually predicts Shadowdark monster LV, and how much variance does each stat explain?
2. Which monsters are statistical outliers for their LV (punch above/below their weight)? Table both directions.
3. On matched monsters, what is the empirical 5e CR to Shadowdark LV mapping? Is it linear, log, or piecewise?
4. How do HP and AC scale between the two systems at equivalent threat?
5. Distribution questions for flavor: LV histogram, AC vs LV spread, damage-per-round by LV band.

## Constraints

- Every script runnable standalone: `python src/ingest_shadowdark.py` etc., plus a `make all` or single `run_all.py`.
- Deterministic re-runs: ingest scripts drop and rebuild their own tables.
- Comment the why, not the what, especially in schema and modeling code.
- No web scraping. Only the sources listed above.
- Keep dependencies to the stack listed. Ask before adding any others.

## Stretch goals (only if all milestones complete)

- Monte Carlo combat simulator: a party of N level-X Shadowdark PCs vs a chosen monster, a few thousand trials, output survival probability and average rounds.
- Spell data ingest and analysis (tier vs effect patterns).
- PDF stat block intake via shadowdark-parser for owned books.
