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
from ranch_ai.services.workspace_bundle_service import create_pretrained_workspace_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a local RangeIQ bundle for a user and ranch boundary.")
    parser.add_argument("--email", required=True, help="Target user email for the bundle manifest.")
    parser.add_argument("--ranch-name", required=True, help="Ranch name to persist into the bundle.")
    parser.add_argument("--ranch-address", required=True, help="Ranch address to persist into the bundle.")
    parser.add_argument("--latitude", required=True, type=float, help="Ranch latitude.")
    parser.add_argument("--longitude", required=True, type=float, help="Ranch longitude.")
    parser.add_argument("--boundary", required=True, help="Path to a GeoJSON, JSON, KML, or KMZ boundary file.")
    parser.add_argument("--bundle-dir", required=True, help="Output directory for the trained workspace bundle.")
    parser.add_argument("--weeks", type=int, default=26, help="Weekly modeling window.")
    parser.add_argument("--history-years", type=int, default=10, help="Vegetation history window in years.")
    parser.add_argument("--seed", type=int, default=42, help="Scenario random seed.")
    parser.add_argument("--theme-mode", default="High Plains Day", help="Appearance mode saved with the workspace.")
    parser.add_argument("--map-basemap", default="naip", help="Map basemap saved with the workspace.")
    args = parser.parse_args()

    result = create_pretrained_workspace_bundle(
        email=args.email,
        ranch_name=args.ranch_name,
        ranch_address=args.ranch_address,
        ranch_latitude=args.latitude,
        ranch_longitude=args.longitude,
        boundary_path=args.boundary,
        bundle_dir=args.bundle_dir,
        weeks=args.weeks,
        history_years=args.history_years,
        seed=args.seed,
        theme_mode=args.theme_mode,
        map_basemap=args.map_basemap,
        app_settings=load_settings(),
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
