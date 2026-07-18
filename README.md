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
- [x] M10 -- Combat metrics module (below)
- [x] M11 -- LV model v2 and reframed writeup (below)
- [x] M12 -- 5e Bestiary page (see dashboard section)
- [x] M13 -- Spells page (see dashboard section; built before M12 per the
      spec's suggested order)
- [x] M14 -- Combat simulator v2 (below)
- [x] M15 -- Empirical difficulty validation (below)
- [x] M16 -- Custom-data gating polish (below)

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

## LV model (M6, reframed in M11)

Full report (coefficients, R², top-10 residuals both directions):
`python src/analysis.py` writes it to `reports/lv_model.txt`.

A plain `sklearn.linear_model.LinearRegression` predicting `level` from AC,
HP, best attack bonus, best avg damage, best num attacks, and best stat mod
gets **R² = 0.997**. HP tracking LV at r = 0.998 is not a finding: Shadowdark
gives monsters one hit die per level, so HP is derived from LV by
construction. This model confirms the printed data matches the rules as
written. It is a data-quality validation, not an insight, and its
coefficients (all under 0.06 in magnitude, mixed signs) should not be
interpreted. The models that are built to say something are in M11 below.

## LV model v2 (M11)

Two models replace the v1 model as the ones worth reading, both in
`reports/lv_model.txt` and rendered on the Insights page from the same fit
functions.

**Model A (no-HP model), R² = 0.817.** The v1 feature set with HP excluded:
AC, best attack bonus, best avg damage, best num attacks, best stat mod.
With HP out, the coefficients are interpretable. Attack bonus dominates at
+0.95 LV per point, followed by num attacks (+0.51) and best stat mod
(+0.29); AC and avg damage contribute little at the margin (+0.17 and
+0.12). The outliers sharpen exactly as expected: the punch-below list is
now nearly all spellcasters and rider-effect monsters (Mordanticus, Druid,
Viperian Wizard, Lich, Dryad, Goblin Shaman, Rat Swarm), whose danger the
attack parser cannot see.

**Model B (threat model), R² = 0.789.** `level = 0.159 * threat_score +
2.71`, with threat_score from M10. One derived number recovers most of
printed LV. Its punch-below list recovers the v1 outlier roster (Archmage,
Hydra, Medusa, Lich, Vampire, Druid): monsters whose printed LV prices in
petrify, curses, regeneration, or spellcasting that no attack-math metric
can measure.

Comparison: v1 full model (R² 0.997) is validation, Model A (0.817) is
interpretation, Model B (0.789) is a single-metric difficulty check. The
drop from 0.997 to 0.82 is the honest size of the signal once the
rules-derived HP column stops doing the work.

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

1. **Insights** (default landing page): the M15 archetype scatter
   (offense vs. defense, log-log, colored by LV, win rate on hover) leads
   the page, followed by the difficulty-validation summary with the
   disagreement table, then the M11 LV model v2 content -- Model A
   (no-HP) with coefficients, predicted-vs-actual scatter, and outlier
   tables; Model B (threat score); and the three-model comparison table.
   If `reports/sim_results.csv` is missing locally the page shows a hint
   to run `python src/batch_sim.py` instead of crashing.
2. **Shadowdark Bestiary**: filter the Shadowdark core bestiary by level
   range, alignment, and name search; see the filtered table and a live LV
   histogram. Unchanged from v1.
3. **5e Bestiary**: filter the 322 SRD monsters by CR range, type, size,
   and name search, with a live CR histogram. A predicted SD LV column
   applies the same M7 CR-to-LV fit the Converter uses (shown to one
   decimal; the Converter rounds it to a whole LV), and an sd_crosswalk
   column names the matched Shadowdark monster for the 143 monsters in the
   M4 crosswalk.
4. **Converter**: pick an SRD monster from a dropdown (auto-fills its
   CR/HP/AC) or enter stats manually, and get a suggested Shadowdark stat
   block (LV/AC/HP/attack bonus) using the M7 fits, plus an expander
   showing the exact formulas used. Attack bonus isn't a direct
   cross-system fit (M7 didn't cover it -- there's no single 5e "attack
   bonus" column to translate from); it's `fit_level_to_attack_bonus()`,
   fit on Shadowdark's own LV-to-attack-bonus relationship and applied to
   the predicted LV. Unchanged from v1.
5. **Spells**: filter the 85 core spells by tier, class, and name or
   description search; the table shows each spell's effect tags, and the
   tier-vs-effect heatmap renders live from the same
   `analyze_spells.py` functions that write the saved report figure
   (`EFFECT_KEYWORDS` lives in exactly one place). The keyword-net caveat
   stays visible on the page.
6. **Combat Simulator**: the M14 rebuild -- party built per PC in an
   editable grid (manual mode) or rolled from class-legal tables (quick
   and random modes), an explicit fixed/reroll variance toggle with the
   two questions each answers, a seed input for reproducibility, and
   per-PC death rates charted in fixed mode. Same `build_pc_*` and
   `run_monte_carlo` functions as the CLI.

`ensure_database()` (in `app/common.py`) also runs the spells ingest on a
cold start now, since `sd_spells` comes from the same freely licensed
source as the bestiary and the ingest is fast.

## Combat metrics (M10)

`src/metrics.py` computes derived combat metrics from `sd_monsters` +
`sd_attacks` at load time (pure functions, no I/O, nothing stored in the
DB). The formulas:

- **effective_dpr** -- expected damage per round against a reference AC.
  Per attack clause: `num_attacks * avg_damage * p_hit`, where
  `p_hit = clamp((21 + attack_bonus - ac_ref) / 20, 0.05, 0.95)`. The
  floor and ceiling encode "natural 1 always misses" / "natural 20 always
  hits". Crit bonus damage is ignored for simplicity. `sd_attacks` does
  not preserve the or/and grouping of attack routines (see M3), so each
  row is treated as an alternative and the best (highest expected damage
  against the reference AC) one is used, the same choice v1's `best_*`
  columns made.
- **effective_hp** -- raw damage a reference attacker must output to drop
  the monster: `hp / p_hit(atk_ref vs monster AC)`, same clamp.
- **threat_score** -- `sqrt(effective_dpr * effective_hp)`, the candidate
  single-number difficulty metric (same construction idea as the 5e DMG's
  offensive/defensive CR average). Correlates with printed LV at r=0.89
  on the core bestiary.
- **archetype_ratio** -- `effective_dpr / effective_hp`. Not a level
  predictor (offense and defense both rise with level, so the ratio
  cancels the level signal; r=0.14 with LV): it is an archetype axis,
  high = glass cannon, low = sponge/tank.

Reference constants, both data-derived (documented in the module, enforced
by tests): `AC_REF = 17` is the sim's armor math for a mid-level PC
(10 + DEX +1 + chainmail +4 + shield +2); `ATK_REF = 3.87` is
`fit_level_to_attack_bonus()` evaluated at the median core monster LV
(5.0).

Tests live in `tests/` (introduced with this milestone): run
`python -m pytest tests/` after building the DB. Hand-computed expected
values for real monsters, clamp edge cases, and constants-consistency
checks that fail if the committed data drifts from the documented
derivations.

## Empirical difficulty validation (M15)

The payoff question: does M10's threat_score predict simulated outcomes
better than printed LV does? Yes, on both measures.

`python src/batch_sim.py` runs every core monster against a standardized
reference party and records win rates to `reports/sim_results.csv`
(committed -- it derives entirely from freely licensed core data, and the
dashboard reads the committed file rather than rerunning a minutes-long
sim on cloud cold start). The reference party is the yardstick, so its
definition is fixed and stated in the module docstring: 4 PCs, one of each
class, at the monster's LV clamped to 1-10, fixed median stats (all 10s,
+1 CON), standard class gear, fixed variance mode, and a per-monster
seeded RNG so the whole CSV reproduces exactly from the same `--seed`
(verified: two runs, identical files). 2000 trials per monster by default.

Findings (full report: `reports/difficulty_validation.txt`, regenerated by
`python src/analysis.py` when the CSV exists; also rendered on Insights):

- **Spearman rank correlation with win rate**: printed LV scores -0.408 on
  the matched set (LV <= 10, party level equals monster LV) and -0.554
  over all monsters; threat_score scores **-0.586 and -0.690**. The
  derived metric beats the printed number on both sets. Above LV 10 the
  party is clamped at level 10 by design, so the all-monsters numbers
  include outmatched fights; both are reported.
- **Disagreement table**: monsters whose printed LV sits far above what
  threat_score predicts while the sim also finds them easier than their
  LV median. Two independent measurements agreeing against printed LV is
  the signature of rider-dependent danger, and the table recovers the v1
  outlier list with an explanation attached: Mordanticus, Archmage, Hydra,
  Lich, Viperian Wizard, Vampire, Druid, Medusa, Mage, Mummy -- petrify,
  curses, level drain, and spellcasting that the attack parser cannot see.
  Model A residuals are carried alongside as the M11 cross-reference.
- **Archetype scatter** (Insights centerpiece): effective_dpr vs.
  effective_hp, log-log, colored by LV, hover with name and win rate,
  corners annotated (glass cannons top-left, sponges bottom-right).

## Monte Carlo combat simulator (v1 stretch goal, rebuilt in M14)

```bash
python src/combat_sim.py --monster Owlbear --party-size 4 --party-level 3 --trials 5000
python src/combat_sim.py --monster Owlbear --build-mode random --party-level 3 --variance-mode reroll
python src/combat_sim.py --monster Owlbear --party-spec party.example.json --seed 42
```

Simulates a party of individually built PCs vs. a chosen `sd_monsters`
entry, round by round (party attacks, then the monster attacks back),
tracking Shadowdark's actual crit rule (natural 20 doubles the damage dice,
natural 1 always misses). Each PC attacks with their own bonus and weapon
die; the monster targets one living PC chosen uniformly at random per
attack (simple and documented, no focus fire). Over `--trials` runs it
reports win/wipe/timeout rates, average rounds, and per-PC death rates in
fixed variance mode.

Party construction has three modes, shared by the CLI and the dashboard:
manual (everything specified, per PC), quick (class and level given, the
rest rolled), and random (class rolled too). Randomization follows the
actual rules: stats are 3d6 straight down with mods derived from scores,
HP is rolled per level on the class hit die (Fighter d8, Priest d6, Thief
and Wizard d4) plus CON mod with a minimum of 1 per level, and gear is
rolled from class-legal tables only (a wizard can never roll plate) --
`CLASS_ARMOR`/`CLASS_WEAPONS` in `src/combat_sim.py` mirror the class
descriptions' Weapons/Armor lines with damage dice from the core weapon
table, melee-only and ignoring two-handed restrictions (both stated in the
module).

Variance mode is always an explicit choice because it changes the question:
`fixed` builds the party once and runs every trial against it ("how does
this party fare?"), `reroll` rebuilds the party every trial ("how dangerous
is this monster for a random party of this shape?"). The same Owlbear that
a fixed level-3 party of fighters beats 99.9% of the time wipes 29% of
randomly rolled level-3 parties.

Attack bonus is the one deliberate approximation kept from v1: it reuses
`fit_level_to_attack_bonus()`, since Shadowdark levels are calibrated so a
same-level monster is a fair fight -- "what attack bonus does a level-X
monster have" is a reasonable, data-grounded stand-in for a level-X PC's,
rather than a guessed talent progression.

`--party-spec party.json` takes a JSON list of PC dicts (see
`party.example.json` in the repo). The v1 flags (`--party-size`,
`--party-level`, `--class-name`, `--armor`, `--con-mod`, `--dex-mod`,
`--weapon-dice`) still work and build a uniform party in manual mode; the
v1 mod flags map onto scores as 10 + 2*mod. Sim invariants are covered in
`tests/test_combat_sim.py` (a level-5 party beats a LV 1 monster nearly
always, a lone level-1 PC vs. The Tarrasque nearly never, per-level HP
minimums hold, rolled gear is always class-legal, same seed gives the same
result).

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

## Custom-data features (M16, local only)

Everything that touches the personal-use PDF-intake tables
(`sd_monsters_custom`/`sd_attacks_custom`) is gated behind
`has_custom_data()` in `app/common.py`, which requires all three of: the
table exists, it has rows, and the environment opts in with
`MONSTERLAB_LOCAL=1`. The env var is belt-and-suspenders for the licensing
wall: the deployed app never sets it, so even an accidentally committed DB
could not light these features up there. The gating logic is covered in
`tests/test_gating.py`.

```bash
MONSTERLAB_LOCAL=1 streamlit run app/dashboard.py
```

With the gate open:

- The **Shadowdark Bestiary** unions core rows (tagged `Core`) with your
  custom monsters and gains a source filter, plus a refresh button that
  clears the data cache after a CLI ingest runs while the app is up.
- The **Combat Simulator** monster dropdown includes custom entries, built
  through the same feature derivation and `monster_from_row()` as core
  monsters.
- **Insights** gains a balance-check section scoring each custom monster
  against the core-fit Model A and threat model: what LV would these stats
  predict for a core monster, and the delta against the printed LV.

There is no upload widget and never will be on the deployed app; custom
intake is CLI-only and local-only (`src/ingest_pdf_statblocks.py` /
`src/parse_pdf_statblocks.py`).

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
