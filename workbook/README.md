# Monster Lab Workbook

A guided gym for the full data-analytics lifecycle, run at small scale against this
repo's real data. Every notebook is one phase; by the end of 08 you have personally
framed a question, acquired data from a live API, designed storage, cleaned messy
text, explored and visualized, fit and de-biased a model, validated it, and written
it up for a non-technical reader.

## Launching

From the repo root:

```sh
venv/bin/jupyter lab workbook
```

The notebooks expect their working directory to be `workbook/` (Jupyter does this
automatically when you open them). Notebook 00 verifies your whole environment —
run it first; if it passes, everything else will find what it needs.

## The order

| # | Notebook | Phase |
|---|----------|-------|
| 00 | `00_setup.ipynb` | Environment check (complete code — just run it) |
| 01 | `01_frame.ipynb` | Problem framing |
| 02 | `02_acquire.ipynb` | Data acquisition (Open5e spells API) |
| 03 | `03_store.ipynb` | Storage & SQL |
| 04 | `04_clean.ipynb` | Cleaning messy text |
| 05 | `05_explore.ipynb` | EDA |
| 06 | `06_model.ipynb` | Modeling (and a trap) |
| 07 | `07_validate.ipynb` | Evaluation |
| 08 | `08_communicate.ipynb` | The findings memo |

Do them in order — each notebook leans on the previous one (03 literally reads the
file 02 saves).

## Rules of engagement

- **The asserts are the teacher.** Every exercise ends in a check cell. A failing
  assert tells you *what* is wrong (wrong count, wrong value, wrong shape) — never
  *how* to fix it. That's the point: diagnosis is the skill.
- **Debug before asking for help.** Read the assert message, print the intermediate
  values, form a hypothesis, test it. Ten minutes of being stuck is not a problem;
  it's the workout.
- **Hints escalate, so take them in order.** Hint 1 is the concept; hint 2 names the
  function or clause to look up. Neither is ever a line of code.
- **If you ask an AI for help, ask for a hint, not the code.** "What concept am I
  missing about GROUP BY vs HAVING?" builds the skill; "write me the query" builds
  nothing you'll own in the master's program. The same goes for pasting the check
  cell in and asking what passes it.
- **Never modify `data/monsterlab.db`.** The notebooks connect to it read-only.
  Everything you create lives under `workbook/data/` (your raw downloads and your
  own `workbook.db`).

## Expected effort

**One to two evenings per notebook.** If a notebook takes twenty minutes, you
probably skimmed the writing prompts — the prose cells (01, the "state the claim"
lines, 08) are as much the exercise as the code. If one exercise eats a whole
evening, that's normal for 04's parser and 06's residuals.
