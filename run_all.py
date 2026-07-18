"""Run the full pipeline in order: ingest -> parse -> crosswalk -> EDA/models.

Each step is also runnable standalone (see README); this just calls them in
the right order with the same interpreter, stopping on the first failure
rather than continuing on a broken table.

Run: python run_all.py
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

STEPS = [
    ROOT / "src" / "ingest_shadowdark.py",
    ROOT / "src" / "ingest_open5e.py",
    ROOT / "src" / "parse_stats.py",
    ROOT / "src" / "build_crosswalk.py",
    ROOT / "src" / "ingest_spells.py",
    ROOT / "src" / "analysis.py",
]


def main() -> None:
    for step in STEPS:
        print(f"\n=== {step.relative_to(ROOT)} ===", flush=True)
        result = subprocess.run([sys.executable, str(step)], cwd=ROOT)
        if result.returncode != 0:
            raise SystemExit(f"{step.relative_to(ROOT)} failed (exit {result.returncode})")

    print("\nAll steps completed. Launch the dashboard with: streamlit run app/dashboard.py")


if __name__ == "__main__":
    main()
