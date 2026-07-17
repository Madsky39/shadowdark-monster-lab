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
python src/analysis.py            # M5: EDA plots -> reports/figures/
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
- [ ] M6 -- LV model
- [ ] M7 -- Cross-system scaling
- [ ] M8 -- Dashboard

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
