# Shadowdark Monster Lab - Spec v2

Follow-on to `shadowdark-monster-lab-spec.md`. v1 (M1-M8 plus the combat sim,
spell, and PDF-intake stretch goals) is complete and deployed at
monsterlab.streamlit.app. This spec covers the v2 milestones: a multipage
restructure, new derived combat metrics, a rebuilt LV model, a dedicated 5e
page, a spells page, a rewritten combat simulator with real party composition,
and an empirical difficulty study that validates the metrics against
simulation.

## Design principles (carried forward from v1, non-negotiable)

1. **One codebase, no fork.** There is no separate "home" and "deployed" app.
   Features that depend on personal-use data (the `sd_monsters_custom` /
   `sd_attacks_custom` tables built by `ingest_pdf_statblocks.py`) are gated
   at runtime by data presence. On Streamlit Cloud those tables never exist,
   so the features never render there.
2. **No drift.** The dashboard, the written reports, and the CLI tools must
   all call the same functions. Any new analysis lives in `src/` and is
   imported by the app, never reimplemented inside it.
3. **Licensing wall.** Nothing derived from owned books is ever committed to
   the repo or exposed on the deployed app. Derived artifacts from the core
   Shadowdark JSON and the 5e SRD (both freely licensed) may be committed.
4. **Rebuild-from-clean.** A fresh clone plus `python run_all.py` plus
   `streamlit run app/dashboard.py` must always work. `ensure_database()`
   must keep working on Streamlit Cloud cold starts and must stay fast
   (seconds, not minutes). Anything slow gets precomputed and committed as a
   small artifact instead.

## Milestones

### M9 - Multipage restructure

Convert the single-file tab layout to Streamlit multipage navigation using
`st.Page` and `st.navigation`.

- New layout:
  - `app/dashboard.py` - entrypoint: runs `ensure_database()`, defines the
    `st.navigation` structure, nothing else.
  - `app/common.py` - the shared cached loaders (`load_data`, `fit_models`)
    and any shared widgets/constants. All pages import from here.
  - `app/pages_/insights.py` - landing page (see M11/M15 for content).
  - `app/pages_/sd_bestiary.py` - the current Bestiary Explorer, unchanged
    behavior.
  - `app/pages_/fe_bestiary.py` - new 5e page (M12).
  - `app/pages_/converter.py` - current converter tab, unchanged behavior.
  - `app/pages_/spells.py` - new spells page (M13).
  - `app/pages_/simulator.py` - combat sim UI (rebuilt in M14).
- Use a directory name like `pages_` (with underscore) or register pages
  explicitly via `st.Page` so Streamlit's automatic `pages/` discovery does
  not fight the explicit navigation.
- Insights is the default landing page.
- Extend `ensure_database()` to also run the spells ingest
  (`ingest_spells.py`), since that data comes from the same freely licensed
  source and is fast.
- Acceptance: all v1 functionality reachable through the new navigation,
  cold start on a wiped `data/` directory still works, no page imports
  anything from another page (shared code goes through `app/common.py`).

### M10 - Combat metrics module (`src/metrics.py`)

New module of pure functions computing derived combat metrics from
`sd_monsters` + `sd_attacks` rows. No I/O in this module; it takes dataframes
or rows and returns values. Computed at load time, not stored in the DB.

- `effective_dpr(monster_attacks, ac_ref)` - expected damage per round
  against a reference AC. For each attack clause:
  `num_attacks * avg_damage * p_hit`, where
  `p_hit = clamp((21 + attack_bonus - ac_ref) / 20, 0.05, 0.95)`
  (floor and ceiling encode nat-1 always misses / nat-20 always hits;
  ignore crit bonus damage here for simplicity and say so in the report).
  Sum across the monster's attack routine. Where a monster has alternative
  routines rather than a combined one, use the best routine, consistent with
  how v1's "best" columns were chosen.
- `effective_hp(monster, atk_ref)` - raw damage a reference attacker must
  output to drop the monster:
  `hp * 20 / (21 + atk_ref - ac)`, clamped the same way.
- `threat_score(monster)` - `sqrt(effective_dpr * effective_hp)`. This is the
  candidate single-number difficulty metric (same construction idea as the
  5e DMG's offensive/defensive CR average).
- `archetype_ratio(monster)` - `effective_dpr / effective_hp`. Not a level
  predictor (offense and defense both rise with level, so the ratio cancels
  the level signal); it is an archetype axis: high = glass cannon,
  low = sponge/tank.
- Reference constants: derive `ac_ref` and `atk_ref` from the data rather
  than hardcoding magic numbers. `ac_ref` = the party AC the sim's armor
  math produces for a mid-level PC (document the derivation in a comment);
  `atk_ref` = `fit_level_to_attack_bonus()` evaluated at the median core
  monster LV. Expose both as module constants with a short docstring each.
- Add pytest coverage: hand-computed expected values for two or three known
  monsters, plus clamp edge cases (very high AC, very low attack bonus).
- Acceptance: `src/analysis.py` can import and use these; tests pass.

### M11 - LV model v2 and reframed writeup

The v1 M6 model (R² = 0.997) is dominated by HP, and HP is not a finding:
Shadowdark monsters get one hit die per level, so HP is mechanically derived
from LV by construction. Reframe accordingly.

- README change: state explicitly that HP tracking LV at r = 0.998 confirms
  the rules-as-written construction (1 HD per level), and that the v1 M6
  model is therefore a data-quality validation, not an insight.
- **Model A (no-HP model):** `LinearRegression` predicting `level` from AC,
  best attack bonus, best avg damage, best num attacks, best stat mod, with
  HP excluded. Report R², coefficients, and top-10 residuals both
  directions. This is the model whose coefficients are actually
  interpretable. Expect the spellcaster/rider outliers to sharpen.
- **Model B (threat model):** predict `level` from `threat_score` alone
  (single feature, from M10). Report R² and residuals.
- Comparison table in the report: v1 full model vs Model A vs Model B, with
  one paragraph on what each is for (validation / interpretation /
  single-metric difficulty).
- All of this goes through `src/analysis.py` and writes to
  `reports/lv_model.txt` (extend the existing report rather than adding a
  new file), and the Insights page renders the same numbers via the shared
  functions.
- Acceptance: report regenerates from clean, Insights page shows Model A and
  Model B results, README updated.

### M12 - 5e Bestiary page (`app/pages_/fe_bestiary.py`)

Dedicated explorer for `fe_monsters`, parallel in spirit to the Shadowdark
explorer.

- Filters: CR range slider, type multiselect, size multiselect, name search.
- Filtered table plus a live CR histogram.
- Add a computed `predicted SD LV` column using the M7 CR-to-LV fit from the
  shared `fit_models`, displayed alongside printed CR. Round to one decimal,
  and caption it as the bridge to the Converter page.
- If a row exists in the crosswalk, show the matched Shadowdark monster name
  in a column (join against the `crosswalk` table).
- Acceptance: page renders on cloud cold start, filters compose correctly,
  predicted LV matches what the Converter produces for the same monster.

### M13 - Spells page (`app/pages_/spells.py`)

- Filters: tier multiselect, class multiselect, name/description search.
- Filtered table of `sd_spells`.
- Tier-vs-effect heatmap rendered live with `st.plotly_chart`, produced by
  the same tagging function `analyze_spells.py` uses (import it; do not
  duplicate `EFFECT_KEYWORDS`).
- Keep the v1 caveat visible on the page: the effect tags are a keyword net
  with a known 9-21 percent "other" rate per tier, a rough pattern-finder,
  not a taxonomy.
- Acceptance: heatmap on the page matches
  `reports/figures/spell_tier_vs_effect.html` regenerated from the same DB.

### M14 - Combat simulator v2 (`src/combat_sim.py` rework)

Replace the uniform `party_size x party_level` party with real per-PC
composition and optional rules-accurate randomization.

- `@dataclass PC`: `cls` (Fighter/Priest/Thief/Wizard), `level`,
  `stats` (the six ability scores), `armor`, `weapon_die`, and derived
  `hp`, `ac`, `attack_bonus`.
- Party construction, three modes (shared functions used by both UI and
  CLI):
  - `build_pc_manual(...)` - everything specified.
  - `build_pc_quick(cls, level, rng)` - class and level given, everything
    else rolled.
  - `build_pc_random(level, rng)` - class rolled too.
- Randomization follows the actual rules, not convenience:
  - Stats: 3d6 straight down per ability, mods derived from scores.
  - HP: rolled per level on the class hit die (Fighter d8, Priest d6,
    Thief d4, Wizard d4) plus CON mod per level, minimum 1 per level.
  - Gear: rolled from class-legal tables only (no wizard in plate). Define
    the armor and weapon tables as module-level data with a comment citing
    which rulebook table they mirror.
  - Attack bonus: keep the v1 approach (`fit_level_to_attack_bonus()`
    evaluated at PC level) and keep the v1 README's justification for it.
- Combat loop changes: iterate over PC objects (each attacks with own
  bonus/die), monster targets a random living PC each round (state the
  targeting rule in the docstring; keep it simple and documented). Keep the
  v1 crit rules (nat 20 doubles damage dice, nat 1 always misses) and the
  timeout rule.
- **Variance mode toggle**, both UI and CLI: `fixed` (roll/build the party
  once, run N trials; answers "how does this party fare") vs `reroll`
  (rebuild the party every trial; answers "how dangerous is this monster
  for a random party of this shape"). Different questions, different
  variance; never silently pick one.
- Outputs: keep win/wipe/timeout rates and avg rounds; add per-PC death
  rate in fixed mode.
- CLI parity: keep the existing flags working where sensible; add
  `--party-spec party.json` (list of PC dicts) and `--variance-mode`.
  Include an example `party.example.json` in the repo.
- UI (`app/pages_/simulator.py`): party built via `st.data_editor` grid
  (one row per PC) for manual mode, plus quick and random modes; seed input
  for reproducibility.
- Pytest: deterministic tests with a seeded RNG (a level-5 party beats a
  LV 1 monster nearly always; a lone level-1 PC vs the Tarrasque nearly
  never; per-level HP minimums respected; wizards never roll plate).
- Acceptance: old CLI invocations from the v1 README still run (or the
  README is updated in the same commit), UI supports all three build modes
  and both variance modes.

### M15 - Empirical difficulty and metric validation

The payoff milestone: does the M10 threat score predict simulated outcomes
better than printed LV does?

- `src/batch_sim.py` - for every core monster, run the sim against a
  standardized reference party and record win rate. Reference party:
  4 PCs, one of each class, at a level equal to the monster's LV clamped to
  the PC-reasonable range (1-10), built in `fixed` mode from fixed median
  stats (all 10s, +1 CON) and standard class gear, seeded RNG. Document
  this definition in the module docstring; it is the yardstick everything
  is measured against, so it must be stable and stated.
  - Trials: 2000 per monster is plenty for a rate estimate; make it a flag.
  - Output: `reports/sim_results.csv` with monster name, LV, threat_score,
    effective_dpr, effective_hp, win_rate, avg_rounds, trials, seed.
  - This is derived entirely from freely licensed core data, so **commit
    the CSV**. The dashboard reads the committed CSV; `ensure_database()`
    does not run the batch sim (too slow for a cloud cold start). If the
    CSV is missing locally, the Insights page shows a one-line hint to run
    `python src/batch_sim.py` instead of crashing.
- Analysis (in `src/analysis.py`, reported to
  `reports/difficulty_validation.txt` and rendered on Insights):
  - Correlation of win_rate with printed LV vs with threat_score (at
    matched party level, or rank-correlate across the clamped range;
    document the handling of the LV > 10 tail).
  - **Disagreement table:** monsters where threat_score and the sim agree
    with each other but disagree with printed LV are candidates for
    rider-dependent danger (petrify, regeneration, curses, spellcasting)
    that the attack parser cannot see. This should recover and explain the
    v1 outlier list (Hydra, Medusa, Archmage, Wraith, and company) rather
    than just observing it.
- **Archetype scatter** on Insights: `effective_dpr` (y) vs `effective_hp`
  (x), log-log if the spread demands it, points colored by LV, hover with
  name and win rate. Annotate the corners (glass cannon / sponge). This is
  the landing-page centerpiece.
- Acceptance: `sim_results.csv` committed and reproducible from the seed,
  Insights shows the scatter and the validation summary, disagreement table
  cross-references the M11 Model A residuals.

### M16 (optional) - Custom-data gating polish

Only if time permits; the gating principle itself is mandatory for any
custom-data feature that ships.

- `has_custom_data(con)` in `app/common.py`: table exists AND has rows.
  Optionally AND with an env var (`MONSTERLAB_LOCAL=1`) as
  belt-and-suspenders so even an accidentally committed DB could not light
  these features up on the deployed app.
- When true: Shadowdark Bestiary gains a source filter (core rows tagged
  `source='Core'`, unioned with `sd_monsters_custom`); the simulator's
  monster dropdown includes custom entries; Insights gains a **balance
  check** section scoring custom monsters against the core-fit Model A and
  threat model ("this LV 6 monster's stats predict LV 8.3").
- Never add an upload widget that writes book-derived data into the shared
  DB on the deployed app. If in-browser intake is ever wanted on cloud, it
  must live in `st.session_state` only (per-session, in-memory) and default
  to off. For v2, simplest is: custom features are local-only.
- After any runtime ingest locally, clear `st.cache_data` so new rows
  appear.

## Cross-cutting requirements

- **Tests:** introduce pytest in this version. Minimum coverage: the M3
  attack parser (fixtures drawn from the weird real clauses), `src/metrics.py`
  math, sim invariants (M14 list), and `has_custom_data` gating logic. Add
  `pytest` to `requirements.txt` and a `tests/` directory.
- **Requirements:** pin versions in `requirements.txt` while touching it.
- **run_all.py:** update to include the spells ingest; batch sim stays a
  separate explicit step because of runtime.
- **README:** update for the multipage layout, the HP-is-rules-derived
  reframe, the new metrics with their formulas, the variance-mode
  distinction, the reference-party definition, and the committed
  `sim_results.csv`. Keep the licensing section intact.
- **Writing style for all reports and README additions:** plain and direct,
  no em dashes, no filler.

## Suggested build order

M9 (structure) -> M10 (metrics, with tests) -> M11 (models and reframe) ->
M13 (spells, small) -> M12 (5e page) -> M14 (sim rework) -> M15 (batch sim
and validation) -> M16 (optional).

M13 before M12 because it is smaller and exercises the new page structure
early; swap if convenient. M14 must precede M15. M10 and M11 are the
critical path for the Insights landing page.
