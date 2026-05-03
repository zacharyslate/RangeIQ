from __future__ import annotations

import argparse

from ranch_ai.data_sources.registry import run_health_check
from ranch_ai.pipeline import run_mvp_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the RangeIQ synthetic pilot pipeline.")
    parser.add_argument("--pastures", help="Optional path to a GeoJSON, JSON, KML, KMZ, or shapefile pasture boundary file.")
    parser.add_argument("--weeks", type=int, default=26, help="Number of weekly rows to generate per pasture.")
    parser.add_argument("--history-years", type=int, default=10, help="Number of monthly history years to generate.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible synthetic data.")
    parser.add_argument("--no-write", action="store_true", help="Skip writing CSV outputs to disk.")
    parser.add_argument("--check-api-sources", action="store_true", help="Print the free/open provider health check and exit.")
    parser.add_argument("--api-sources-config", help="Optional path to config/api_sources.yaml for the provider registry.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.check_api_sources:
        report = run_health_check(config_path=args.api_sources_config)
        print("\n".join(report.to_lines()))
        return 0

    artifacts = run_mvp_pipeline(
        pasture_path=args.pastures,
        weeks=args.weeks,
        history_years=args.history_years,
        seed=args.seed,
        write_outputs=not args.no_write,
    )

    latest = artifacts.latest_snapshot[
        ["pasture_id", "name", "pasture_condition_score", "water_risk_score", "stocking_risk_score", "recommendation"]
    ].to_string(index=False)

    print("RangeIQ pilot run complete.")
    print(f"Selected forage model: {artifacts.selected_forage_model}")
    print(latest)
    return 0
