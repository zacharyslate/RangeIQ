"""Nightly worker: build each ranch's phone-app snapshot and store it.

    python -m ranch_ai.rancher.worker                 # every account's ranch
    python -m ranch_ai.rancher.worker --workspace ID  # one ranch
    python -m ranch_ai.rancher.worker --demo          # labeled sample data when sources are down

Run it from a systemd timer (see deploy/systemd/rangeiq-worker.*.example).
All the slow and memory-hungry work (network pulls, rasters, pandas) happens
here, never while a rancher is waiting on the phone.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

from ranch_ai.config import Settings, load_settings, normalize_workspace_id, settings as default_settings
from ranch_ai.rancher.store import AppStore
from ranch_ai.utils.io import load_pastures

DEFAULT_WORKSPACE = "default"


def account_workspaces(auth_db_path: Path) -> list[str]:
    if not Path(auth_db_path).exists():
        return []
    with sqlite3.connect(auth_db_path) as conn:
        try:
            rows = conn.execute("SELECT workspace_id FROM users ORDER BY created_at").fetchall()
        except sqlite3.Error:
            return []
    return [normalize_workspace_id(row[0]) for row in rows if row[0]]


def workspace_inputs(workspace_id: str, base: Settings = default_settings):
    """Settings + pasture boundaries for a workspace, as saved from the desktop console."""
    config_path = base.workspace_config_path_for(workspace_id)
    app_settings = load_settings(config_path) if config_path.exists() else load_settings()
    pastures = None
    state_path = base.workspace_state_path_for(workspace_id)
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            info = state.get("saved_boundary") or {}
            path, name = info.get("path"), info.get("filename")
            if path and name and Path(path).exists():
                pastures = load_pastures(uploaded_name=name, uploaded_bytes=Path(path).read_bytes())
        except (OSError, ValueError, json.JSONDecodeError):
            pastures = None
    if pastures is None:
        pastures = load_pastures(app_settings.default_pasture_path)
    return app_settings, pastures


def run(workspaces: list[str], *, store: AppStore, demo: bool = False, include_terrain: bool = True) -> int:
    from ranch_ai.rancher.snapshot import build_snapshot

    failures = 0
    for workspace_id in workspaces:
        started = time.time()
        try:
            app_settings, pastures = workspace_inputs(workspace_id)
            snapshot = build_snapshot(
                app_settings,
                pastures,
                logs=store.list_logs(workspace_id, limit=1000),
                demo=demo,
                include_terrain=include_terrain,
            )
            store.save_snapshot(workspace_id, snapshot)
            live = sum(1 for s in snapshot["sources"] if s.get("live"))
            print(f"[rangeiq-worker] {workspace_id}: {len(snapshot['pastures'])} pastures, "
                  f"{live}/{len(snapshot['sources'])} sources live, {time.time() - started:.1f}s")
        except Exception as exc:  # noqa: BLE001 - one bad ranch must not stop the others
            failures += 1
            print(f"[rangeiq-worker] {workspace_id}: FAILED: {exc}", file=sys.stderr)
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build RangeIQ phone-app snapshots.")
    parser.add_argument("--workspace", action="append", help="Workspace id (repeatable). Default: every account.")
    parser.add_argument("--demo", action="store_true", help="Allow labeled sample data when sources are unavailable.")
    parser.add_argument("--no-terrain", action="store_true", help="Skip the lidar terrain summary.")
    parser.add_argument("--db", help="App database path (default: data/processed/rangeiq_app.sqlite).")
    args = parser.parse_args(argv)

    store = AppStore(args.db)
    workspaces = [normalize_workspace_id(w) for w in args.workspace] if args.workspace else account_workspaces(default_settings.auth_db_path)
    if not workspaces:
        workspaces = [DEFAULT_WORKSPACE]
    failures = run(workspaces, store=store, demo=args.demo, include_terrain=not args.no_terrain)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
