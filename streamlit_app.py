from __future__ import annotations

from pathlib import Path
import runpy


PROJECT_ROOT = Path(__file__).resolve().parent
runpy.run_path(str(PROJECT_ROOT / "app" / "dashboard.py"), run_name="__main__")
