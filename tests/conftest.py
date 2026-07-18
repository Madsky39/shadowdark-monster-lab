"""Make src/ importable from the tests, same as the app and CLI tools do."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
