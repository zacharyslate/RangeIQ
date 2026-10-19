from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from ranch_ai.rancher.api import create_app
from ranch_ai.rancher.snapshot import is_live, rain_totals
from ranch_ai.rancher.status import combine, drought_signal, grass_signal, rain_signal, range_trend_signal
from ranch_ai.rancher.store import AppStore, herd_days_by_pasture
from ranch_ai.services.auth_service import AuthService


# --- status rules -----------------------------------------------------------------
def test_rain_signal_levels_and_wording():
    assert rain_signal(2.0, 8.0, 0.5, source="x", as_of="d").level == "concern"   # 25 %
    assert rain_signal(5.0, 8.0, 1.0, source="x", as_of="d").level == "watch"     # 62 %
    ok = rain_signal(8.0, 8.0, 3.0, source="x", as_of="d")
    assert ok.level == "ok" and "100% of normal" in ok.text
    assert rain_signal(None, 8.0, None, source=None, as_of=None).level == "unavailable"
    assert rain_signal(3.0, 0.0, None, source=None, as_of=None).level == "unavailable"


def test_grass_and_drought_and_trend_signals():
    assert grass_signal(-25, source=None, as_of=None).level == "concern"
    assert grass_signal(-12, source=None, as_of=None).level == "watch"
    assert "greener than normal" in grass_signal(15, source=None, as_of=None).text
    assert drought_signal("D3", source=None, as_of=None).level == "concern"
    assert drought_signal("D1", source=None, as_of=None).level == "watch"
    assert drought_signal("None", source=None, as_of=None).level == "ok"
    assert range_trend_signal("declining", "stable", source=None, as_of=None).level == "watch"
    assert range_trend_signal("stable", "stable", source=None, as_of=None).level == "ok"


def test_combine_never_guesses_without_data():
    nothing = [rain_signal(None, None, None, source=None, as_of=None), grass_signal(None, source=None, as_of=None)]
    assert combine(nothing).status == "unknown"
    two_concerns = [rain_signal(1, 8, 0, source=None, as_of=None), grass_signal(-30, source=None, as_of=None)]
    assert combine(two_concerns).status == "act"
    one_watch = [rain_signal(8, 8, 2, source=None, as_of=None), drought_signal("D0", source=None, as_of=None)]
    status = combine(one_watch)
    assert status.status == "watch" and status.headline.startswith("Watch:")
    assert combine([rain_signal(8, 8, 2, source=None, as_of=None)]).status == "good"


def test_mock_modes_are_not_live():
    assert is_live("real") and is_live("cached") and is_live("stale-cache") and is_live("live-cached")
    assert not is_live("mock") and not is_live("fallback-mock") and not is_live(None)


# --- rain math -----------------------------------------------------------------------
def test_rain_totals_against_prior_years():
    dates = pd.date_range("2016-01-01", "2026-10-10", freq="D")
    precip = np.full(len(dates), 0.05)
    precip[dates >= pd.Timestamp("2026-07-13")] = 0.025  # this summer at half the usual daily rate
    result = rain_totals(pd.DataFrame({"date": dates, "public_precip_in": precip}))
    assert result["as_of"] == "2026-10-10"
    assert result["normal_90d_in"] == pytest.approx(4.5, rel=0.01)
    assert result["rain_90d_in"] == pytest.approx(2.25, rel=0.02)
    assert result["normal_years"] == 10


def test_rain_totals_needs_enough_history():
    dates = pd.date_range("2025-06-01", "2026-10-10", freq="D")
    result = rain_totals(pd.DataFrame({"date": dates, "public_precip_in": 0.03}))
    assert result["normal_90d_in"] is None  # only one prior year


# --- store --------------------------------------------------------------------------
def test_logs_are_idempotent_and_scoped(tmp_path):
    store = AppStore(tmp_path / "app.sqlite")
    entry = {"client_id": "abc-1", "kind": "rain", "inches": 0.6, "logged_at": "2026-10-12T14:00:00+00:00"}
    _, created = store.add_log("ranch-a", entry)
    _, created_again = store.add_log("ranch-a", entry)
    assert created and not created_again
    assert len(store.list_logs("ranch-a")) == 1
    assert store.list_logs("ranch-b") == []
    with pytest.raises(ValueError):
        store.add_log("ranch-b", entry)  # someone else's id
    with pytest.raises(ValueError):
        store.add_log("ranch-a", {"client_id": "x", "kind": "party"})
    assert store.delete_log("ranch-a", "abc-1") and store.list_logs("ranch-a") == []


def test_sessions_expire_and_end(tmp_path):
    store = AppStore(tmp_path / "app.sqlite")
    token = store.create_session("u1", "ranch-a")
    assert store.session(token) == {"user_id": "u1", "workspace_id": "ranch-a"}
    assert store.session("not-a-token") is None
    store.end_session(token)
    assert store.session(token) is None
    expired = store.create_session("u1", "ranch-a", days=-1)
    assert store.session(expired) is None


def test_herd_days_from_moves():
    now = datetime(2026, 10, 13, tzinfo=timezone.utc)
    logs = [
        {"kind": "move", "pasture_id": "north", "from_pasture_id": None, "logged_at": (now - timedelta(days=40)).isoformat()},
        {"kind": "move", "pasture_id": "south", "from_pasture_id": "north", "logged_at": (now - timedelta(days=10)).isoformat()},
        {"kind": "rain", "pasture_id": "south", "logged_at": now.isoformat()},
    ]
    days = herd_days_by_pasture(logs, today=now)
    assert days["south"] == {"days_in": 10}
    assert days["north"] == {"days_rested": 10}


# --- API ----------------------------------------------------------------------------
@pytest.fixture()
def client(tmp_path):
    auth = AuthService(tmp_path / "auth.sqlite")
    user = auth.create_user(email="zach@example.com", password="CorrectHorse9", full_name="Zach",
                            ranch_name="Caja Caliente", ranch_address="Alpine, TX")
    store = AppStore(tmp_path / "app.sqlite")
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<!doctype html><title>RangeIQ</title>")
    (web / "sw.js").write_text("// sw")
    app = create_app(store=store, auth=auth, web_dir=web)
    test_client = TestClient(app, base_url="https://testserver")
    test_client.user = user  # type: ignore[attr-defined]
    test_client.store = store  # type: ignore[attr-defined]
    return test_client


def test_api_requires_login(client):
    assert client.get("/api/snapshot").status_code == 401
    assert client.get("/api/logs").status_code == 401
    bad = client.post("/api/login", json={"email": "zach@example.com", "password": "wrong-password"})
    assert bad.status_code == 401


def test_api_login_snapshot_and_log_sync(client):
    ok = client.post("/api/login", json={"email": "zach@example.com", "password": "CorrectHorse9"})
    assert ok.status_code == 200 and ok.json()["ranch"] == "Caja Caliente"
    assert "httponly" in ok.headers["set-cookie"].lower()
    assert client.get("/api/snapshot").json()["pending"] is True

    client.store.save_snapshot(client.user.workspace_id, {"generated_at": "2026-10-13T05:00:00+00:00", "pastures": []})
    assert client.get("/api/snapshot").json()["generated_at"] == "2026-10-13T05:00:00+00:00"

    batch = [
        {"client_id": "p1-1", "kind": "rain", "inches": 0.4},
        {"client_id": "p1-2", "kind": "note", "text": "Trough float stuck", "pasture_id": "CC-001"},
        {"client_id": "p1-3", "kind": "bogus"},
    ]
    result = client.post("/api/logs", json=batch).json()
    assert result["saved"] == ["p1-1", "p1-2"] and result["errors"][0]["client_id"] == "p1-3"
    # Re-sending after a dropped connection must not duplicate.
    assert client.post("/api/logs", json=batch[:2]).json()["saved"] == ["p1-1", "p1-2"]
    assert len(client.get("/api/logs").json()) == 2
    assert client.delete("/api/logs/p1-1").json()["deleted"] is True

    client.post("/api/logout")
    assert client.get("/api/logs").status_code == 401


def test_api_serves_app_and_never_caches_service_worker(client):
    assert client.get("/", follow_redirects=False).headers["location"] == "/app/"
    page = client.get("/app/")
    assert page.status_code == 200 and "RangeIQ" in page.text
    assert client.get("/app/sw.js").headers["cache-control"] == "no-cache"


def test_api_process_stays_light():
    code = (
        "import sys; sys.path.insert(0, 'src'); import ranch_ai.rancher.api; "
        "heavy = [m for m in ('pandas', 'sklearn', 'rasterio', 'streamlit', 'plotly') if m in sys.modules]; "
        "print(','.join(heavy))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == ""


def test_service_worker_is_up_to_date():
    """sw.js must be regenerated (python scripts/build_sw.py) whenever web/app changes, or phones keep old files."""
    import importlib.util
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("build_sw", root / "scripts" / "build_sw.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    current = re.search(r'VERSION = "rangeiq-([0-9a-f]+)"', (module.APP / "sw.js").read_text()).group(1)
    assert current == module.version_hash(), "Run: python scripts/build_sw.py"
    assert "vendor/three/three.module.min.js" not in module.files()  # 3D library is on-demand, not precached


# --- 3D terrain assets, worker guard, admin ------------------------------------------
def _demo_grid_and_pastures(tmp_path):
    from ranch_ai.config import Settings
    from ranch_ai.terrain import TerrainService
    from ranch_ai.utils.io import load_pastures

    pastures = load_pastures()
    grid = TerrainService(Settings(), cache_dir=tmp_path / "tc").load(pastures, provider="mock").grid
    return grid, pastures


def test_height_quantization_round_trip(tmp_path):
    from ranch_ai.rancher.terrain3d import dequantize, height_grid, quantize

    grid, _ = _demo_grid_and_pastures(tmp_path)
    z, cell = height_grid(grid, max_side=128)
    assert max(z.shape) <= 128 and cell >= grid.resolution_m
    payload, z0, zscale = quantize(z)
    back = dequantize(payload, z0, zscale, z.shape[1], z.shape[0])
    assert np.abs(back - z).max() <= zscale  # sub-millimetre for a ranch-scale relief


def test_terrain_assets_relief_fallback_and_outlines_inside_mesh(tmp_path):
    from ranch_ai.rancher.terrain3d import build_terrain_assets

    grid, pastures = _demo_grid_and_pastures(tmp_path)
    assets = build_terrain_assets(grid, pastures, fetch_imagery=False)
    meta = assets["meta"]
    assert assets["texture"][:8] == b"\x89PNG\r\n\x1a\n" and meta["texture_source"] == "relief"
    assert len(assets["height"]) == meta["nx"] * meta["ny"] * 2
    ring = meta["outlines"][0]["ring"]
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    # The default parcel sits inside the 120 m buffer, so it must fall well inside the mesh.
    assert 0 < min(xs) and max(xs) < meta["width_m"] and 0 < min(ys) and max(ys) < meta["height_m"]
    assert 100 < min(xs) < 140 and 100 < min(ys) < 140


def test_account_without_boundary_never_gets_sample_ranch(tmp_path):
    from ranch_ai.rancher.worker import build_workspace, workspace_inputs

    _, pastures, label = workspace_inputs("user-nobody-0000000000")
    assert pastures is None and label is None
    store = AppStore(tmp_path / "app.sqlite")
    report = build_workspace("user-nobody-0000000000", store=store, include_terrain=False)
    assert report["status"] == "no boundary uploaded"
    assert store.latest_snapshot("user-nobody-0000000000")["setup_needed"] is True


def test_force_live_switches_only_mock_providers():
    from ranch_ai.config import Settings
    from ranch_ai.rancher.worker import force_live_providers

    s = Settings()
    s.weather.provider = "mock"
    s.public_data.drought.provider = "mock"
    s.alerts.provider = "nws"
    changed = force_live_providers(s)
    assert s.weather.provider == "nws" and s.public_data.drought.provider == "usdm"
    assert "alerts" not in changed and {"weather", "drought"} <= set(changed)


def test_api_serves_terrain_to_signed_in_user_only(client):
    assert client.get("/api/terrain/meta").status_code == 401
    client.post("/api/login", json={"email": "zach@example.com", "password": "CorrectHorse9"})
    assert client.get("/api/terrain/meta").status_code == 404
    client.store.save_terrain(client.user.workspace_id, {"nx": 2, "ny": 2}, b"\x00\x00" * 4, b"\xff\xd8jpeg", "image/jpeg")
    assert client.get("/api/terrain/meta").json()["nx"] == 2
    height = client.get("/api/terrain/height")
    assert height.content == b"\x00\x00" * 4 and height.headers["content-type"] == "application/octet-stream"
    assert client.get("/api/terrain/texture").headers["content-type"] == "image/jpeg"
    assert client.get("/api/terrain/secrets").status_code == 404


def test_admin_finds_account_by_email(tmp_path, capsys):
    from ranch_ai.rancher import admin

    auth = AuthService(tmp_path / "auth.sqlite")
    auth.create_user(email="rancher@example.com", password="CorrectHorse9", full_name="Pat Rancher",
                     ranch_name="Mesa Ranch", ranch_address="Marfa, TX")
    user = admin.find_account("Rancher@Example.com", auth_db=tmp_path / "auth.sqlite")
    info = admin.describe(user)
    assert info["ranch"] == "Mesa Ranch" and info["boundary_file"] is None and "pastures" not in info
    with pytest.raises(SystemExit):
        admin.find_account("nobody@example.com", auth_db=tmp_path / "auth.sqlite")


# --- GitHub-hosted app: bearer tokens, CORS, sign-in throttle ---------------------------
@pytest.fixture()
def pages_client(tmp_path):
    auth = AuthService(tmp_path / "auth.sqlite")
    user = auth.create_user(email="zach@example.com", password="CorrectHorse9", full_name="Zach",
                            ranch_name="Caja Caliente", ranch_address="Alpine, TX")
    store = AppStore(tmp_path / "app.sqlite")
    app = create_app(store=store, auth=auth, web_dir=tmp_path / "none", allowed_origins=["https://zacharyslate.github.io"])
    c = TestClient(app, base_url="https://rangeiq.org")
    c.user, c.store = user, store  # type: ignore[attr-defined]
    return c


def test_bearer_token_works_without_cookies(pages_client):
    token = pages_client.post("/api/login", json={"email": "zach@example.com", "password": "CorrectHorse9"}).json()["token"]
    pages_client.cookies.clear()
    assert pages_client.get("/api/me").status_code == 401
    auth = {"Authorization": f"Bearer {token}"}
    assert pages_client.get("/api/me", headers=auth).json()["ranch"] == "Caja Caliente"
    assert pages_client.post("/api/logs", headers=auth, json={"client_id": "t-1", "kind": "rain", "inches": 0.3}).json()["saved"] == ["t-1"]
    pages_client.post("/api/logout", headers=auth)
    assert pages_client.get("/api/me", headers=auth).status_code == 401


def test_cors_allows_github_pages_only(pages_client):
    pre = pages_client.options("/api/snapshot", headers={
        "Origin": "https://zacharyslate.github.io", "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization"})
    assert pre.status_code == 200
    assert pre.headers["access-control-allow-origin"] == "https://zacharyslate.github.io"
    assert "authorization" in pre.headers["access-control-allow-headers"].lower()
    evil = pages_client.options("/api/snapshot", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in evil.headers
    simple = pages_client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in simple.headers


def test_sign_in_is_throttled_after_repeated_failures(pages_client):
    bad = {"email": "zach@example.com", "password": "wrong-password"}
    codes = [pages_client.post("/api/login", json=bad).status_code for _ in range(9)]
    assert codes[:8] == [401] * 8 and codes[8] == 429
    # Even the right password waits out the window, so guessing can't continue.
    good = pages_client.post("/api/login", json={"email": "zach@example.com", "password": "CorrectHorse9"})
    assert good.status_code == 429


# --- satellite greenness: window, thinning, sort fallback ---------------------------------
def _scene(day: str, cloud: float) -> dict:
    return {"id": day, "properties": {"datetime": f"{day}T17:00:00Z", "eo:cloud_cover": cloud}}


def test_thin_items_keeps_clearest_scenes_per_month():
    from ranch_ai.vegetation.ndvi_client import thin_items_per_month

    items = [_scene("2026-09-02", 25), _scene("2026-09-07", 1), _scene("2026-09-12", 9), _scene("2026-09-17", 4),
             _scene("2026-10-02", 30), _scene("2026-10-07", 12)]
    kept = thin_items_per_month(items, 2)
    assert [i["id"] for i in kept] == ["2026-09-07", "2026-09-17", "2026-10-02", "2026-10-07"]


def test_stac_query_is_newest_first_and_falls_back_without_sort(monkeypatch):
    from ranch_ai.vegetation.ndvi_client import EarthSearchSTACNDVIProvider, build_earth_search_query

    feature = {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [[[-103.5, 29.6], [-103.49, 29.6], [-103.49, 29.61], [-103.5, 29.6]]]}}
    query = build_earth_search_query(feature, start_date="2026-01-01", end_date="2026-10-01")
    assert query["sortby"] == [{"field": "properties.datetime", "direction": "desc"}]

    sent = []

    class Resp:
        def __init__(self, code):
            self.status_code = code
        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(self.status_code)
        def json(self):
            return {"features": []}

    provider = EarthSearchSTACNDVIProvider(retries=1, backoff_seconds=0)
    monkeypatch.setattr(provider.session, "post", lambda url, json, **kw: (sent.append(json), Resp(400 if "sortby" in json else 200))[1])
    assert provider._search_items(query) == {"features": []}
    assert "sortby" in sent[0] and "sortby" not in sent[1]


def test_status_job_gives_greenness_its_own_weekly_window(monkeypatch, tmp_path):
    import pandas as pd
    from ranch_ai.config import Settings
    from ranch_ai.rancher import snapshot as snap_mod
    from ranch_ai.utils.io import load_pastures
    from ranch_ai.vegetation.vegetation_service import VegetationService

    calls = {}
    real = VegetationService.build_artifacts

    def spy(self, pastures, *, start_date, end_date, history_years=None):
        calls.update(start=pd.Timestamp(start_date), end=pd.Timestamp(end_date), years=history_years)
        return real(self, pastures, start_date=start_date, end_date=end_date, history_years=history_years)

    monkeypatch.setattr(VegetationService, "build_artifacts", spy)
    s = Settings()
    for name in ("historical_weather", "soils", "drought", "vegetation"):
        getattr(s.public_data, name).provider = "mock"
    s.weather.provider = s.alerts.provider = "mock"
    snap_mod.build_snapshot(s, load_pastures(), include_terrain=False, today=pd.Timestamp("2026-10-15"))  # a Thursday
    assert calls["end"] == pd.Timestamp("2026-10-12")          # Monday: same cache key all week
    assert calls["start"] == pd.Timestamp("2026-04-12")
    assert calls["years"] == snap_mod.NDVI_HISTORY_YEARS == 5   # ~5.5 years of Sentinel-2, not 20


def test_public_bundle_can_skip_vegetation():
    import pandas as pd
    from ranch_ai.config import Settings
    from ranch_ai.services.public_data_service import PublicDataService
    from ranch_ai.utils.io import load_pastures

    s = Settings()
    for name in ("historical_weather", "soils", "drought", "vegetation"):
        getattr(s.public_data, name).provider = "mock"
    bundle = PublicDataService(s).load_public_data_bundle(load_pastures(), pd.Timestamp("2026-01-01"), pd.Timestamp("2026-03-01"),
                                                          include_vegetation=False)
    assert bundle.vegetation_artifacts is None and bundle.vegetation.empty
    assert not any(st.component.startswith("Vegetation") for st in bundle.source_status)
