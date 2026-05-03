from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ranch_ai.config import load_settings
from ranch_ai.services.workspace_bundle_service import apply_pretrained_workspace_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="Attach a pretrained RangeIQ workspace bundle to a user account.")
    parser.add_argument("--bundle-dir", required=True, help="Directory containing manifest.json, models, and boundary.")
    parser.add_argument("--email", help="Override target email. Defaults to the manifest email.")
    args = parser.parse_args()

    result = apply_pretrained_workspace_bundle(
        bundle_dir=args.bundle_dir,
        email=args.email,
        app_settings=load_settings(),
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
