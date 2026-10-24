from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path
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


# --- ranch-hand app: field reports, photos, crew -------------------------------------
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200 + b"\xff\xd9"


def test_field_reports_drive_status():
    from ranch_ai.rancher.status import Signal, field_report_signal

    today = datetime(2026, 10, 19, tzinfo=timezone.utc)
    recent = (today - timedelta(days=2)).isoformat()
    old = (today - timedelta(days=30)).isoformat()
    sig = field_report_signal([{"taken_at": recent, "tags": ["Gate open"]},
                               {"logged_at": recent, "tags": ["Dead animal"], "by": "Luis"}], today)
    assert sig.level == "concern" and "Dead animal" in sig.text and "Luis" in sig.text
    assert field_report_signal([{"taken_at": old, "tags": ["Fence down"]}], today) is None
    assert field_report_signal([{"taken_at": recent, "tags": ["Good grass"]}], today).level == "ok"
    # A serious problem seen on the ground is enough for Act; one bad satellite/weather number is only Watch.
    assert combine([sig, Signal("rain", "Rain", "ok", "fine", "x", None)]).status == "act"
    assert combine([Signal("rain", "Rain", "concern", "dry", "x", None)]).status == "watch"
    assert combine([Signal("rain", "Rain", "concern", "dry", "x", None), Signal("grass", "Grass", "concern", "brown", "x", None)]).status == "act"


def _login(c, email="zach@example.com", password="CorrectHorse9"):
    r = c.post("/api/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _upload(c, headers, client_id, **meta):
    files = {"photo": ("p.jpg", JPEG, "image/jpeg"), "thumb": ("t.jpg", JPEG, "image/jpeg")}
    import json as _json
    return c.post("/api/photos", headers=headers, files=files,
                  data={"meta": _json.dumps({"client_id": client_id, "taken_at": "2026-10-18T15:00:00Z", **meta})})


def test_photos_upload_list_signed_links_and_delete(client, tmp_path, monkeypatch):
    monkeypatch.setenv("RANGEIQ_PHOTO_DIR", str(tmp_path / "photos"))
    owner = _login(client)
    r = _upload(client, owner, "ph-1", lat=30.3, lon=-103.6, heading_deg=270, tags=["Water low"], flagged=True,
                analysis={"green_pct": 41, "brown_bare_pct": 50})
    assert r.status_code == 200 and r.json()["created"] is True
    assert _upload(client, owner, "ph-1").json()["created"] is False          # re-send after lost signal
    assert _upload(client, owner, "bad id!").status_code == 400
    bad = client.post("/api/photos", headers=owner, data={"meta": '{"client_id": "x"}'},
                      files={"photo": ("p.png", b"\x89PNG....", "image/png"), "thumb": ("t.jpg", JPEG, "image/jpeg")})
    assert bad.status_code == 400

    [photo] = client.get("/api/photos", headers=owner).json()
    assert photo["heading_deg"] == 270 and photo["tags"] == ["Water low"] and photo["flagged"] and photo["by"] == "Zach"
    assert photo["analysis"]["green_pct"] == 41
    client.cookies.clear()
    assert client.get(photo["thumb_url"]).content == JPEG                     # signed link works without sign-in
    assert client.get(photo["image_url"].replace("sig=", "sig=0")).status_code == 403
    assert client.get(photo["image_url"].replace("kind=image", "kind=thumb")).status_code == 403
    assert client.delete("/api/photos/ph-1", headers=owner).json()["deleted"] is True
    assert client.get("/api/photos", headers=owner).json() == []
    assert client.get(photo["thumb_url"]).status_code == 404


def test_crew_code_join_roles_and_removal(client, tmp_path, monkeypatch):
    monkeypatch.setenv("RANGEIQ_PHOTO_DIR", str(tmp_path / "photos"))
    owner = _login(client)
    ws = client.user.workspace_id
    client.store.save_snapshot(ws, {"generated_at": "2026-10-19T05:00:00+00:00", "ranch": {"name": "Caja Caliente"}, "pastures": []})
    code = client.post("/api/crew/invites", headers=owner).json()["code"]
    assert len(code) == 7 and code[3] == "-"

    assert client.post("/api/join", json={"code": "ZZZ-ZZZ", "name": "Luis", "email": "luis@example.com",
                                          "password": "HandPass123"}).status_code == 400
    joined = client.post("/api/join", json={"code": code.lower().replace("-", " "), "name": "Luis",
                                            "email": "luis@example.com", "password": "HandPass123"})
    assert joined.status_code == 200 and joined.json()["role"] == "crew" and joined.json()["ranch"] == "Caja Caliente"
    hand = {"Authorization": f"Bearer {joined.json()['token']}"}
    client.cookies.clear()

    me = client.get("/api/me", headers=hand).json()
    assert me["role"] == "crew" and me["ranch"] == "Caja Caliente"
    assert client.get("/api/snapshot", headers=hand).json()["ranch"]["name"] == "Caja Caliente"   # sees the owner's ranch
    assert client.get("/api/crew", headers=hand).status_code == 403                                # can't manage the crew
    assert client.post("/api/crew/invites", headers=hand).status_code == 403
    # Hand logs work and photos on the owner's ranch, credited by name.
    assert client.post("/api/logs", headers=hand, json={"client_id": "h-1", "kind": "note", "tags": ["Fence down"]}).json()["saved"] == ["h-1"]
    assert _upload(client, hand, "h-ph").status_code == 200
    assert client.get("/api/logs", headers=owner).json()[0]["by"] == "Luis"
    assert client.get("/api/photos", headers=owner).json()[0]["by"] == "Luis"
    # Hands can delete their own entries but not the owner's.
    client.post("/api/logs", headers=owner, json={"client_id": "o-1", "kind": "rain", "inches": 0.2})
    assert client.delete("/api/logs/o-1", headers=hand).status_code == 403
    assert client.delete("/api/logs/h-1", headers=hand).json()["deleted"] is True
    # Signing in again lands on the owner's ranch, not an empty one of their own.
    assert client.post("/api/login", json={"email": "luis@example.com", "password": "HandPass123"}).json()["role"] == "crew"

    crew = client.get("/api/crew", headers=owner).json()
    assert [m["name"] for m in crew["members"]] == ["Luis"] and crew["invites"][0]["uses"] == 1
    luis_id = crew["members"][0]["user_id"]
    assert client.delete(f"/api/crew/members/{luis_id}", headers=owner).json()["removed"] is True
    assert client.get("/api/me", headers=hand).status_code == 401                                  # signed out everywhere
    assert client.delete(f"/api/crew/invites/{code}", headers=owner).json()["revoked"] is True
    assert client.post("/api/join", json={"code": code, "name": "X", "email": "x@example.com", "password": "HandPass123"}).status_code == 400


def test_worker_skips_crew_accounts(tmp_path):
    from ranch_ai.rancher.worker import account_workspaces

    auth = AuthService(tmp_path / "auth.sqlite")
    owner = auth.create_user(email="o@example.com", password="CorrectHorse9", full_name="O", ranch_name="R", ranch_address="TX")
    hand = auth.create_user(email="h@example.com", password="CorrectHorse9", full_name="H", ranch_name="R", ranch_address="Crew member")
    store = AppStore(tmp_path / "app.sqlite")
    store.add_member(hand.user_id, owner.workspace_id, "H")
    assert account_workspaces(tmp_path / "auth.sqlite", store) == [owner.workspace_id]


def test_keyless_greenness_source_falls_back_to_free_sentinel2():
    from ranch_ai.config import Settings
    from ranch_ai.rancher.worker import usable_providers

    s = Settings()
    s.public_data.vegetation.provider = "climate_engine"
    assert usable_providers(s, env={}) and s.public_data.vegetation.provider == "earth_search_stac"
    s.public_data.vegetation.provider = "climate_engine"
    assert usable_providers(s, env={"CLIMATE_ENGINE_API_KEY": "k"}) == [] and s.public_data.vegetation.provider == "climate_engine"
    s.public_data.vegetation.provider = "mock"
    assert usable_providers(s, env={}) == [] and s.public_data.vegetation.provider == "mock"


def test_tag_catalog_matches_phone_app():
    import json as _json
    import pathlib
    import re

    from ranch_ai.rancher.status import TAG_LEVELS

    js = (pathlib.Path(__file__).resolve().parents[1] / "web" / "app" / "app.js").read_text(encoding="utf-8")
    groups = _json.loads(re.search(r"/\*TAGS\*/(.*?)/\*END\*/", js, re.S).group(1))
    app_levels = {name: level for g in groups for name, level, _icon in g["tags"]}
    assert app_levels == TAG_LEVELS
    assert {"Feral hogs", "Rattlesnake", "Deer", "Washed-out road", "Fence damaged"} <= set(TAG_LEVELS)


def test_sightings_do_not_change_pasture_status_but_problems_do():
    from ranch_ai.rancher.status import field_report_signal

    today = datetime(2026, 10, 19, tzinfo=timezone.utc)
    seen = (today - timedelta(days=1)).isoformat()
    assert field_report_signal([{"logged_at": seen, "tags": ["Deer", "Rattlesnake", "New calf"]}], today) is None
    assert field_report_signal([{"logged_at": seen, "tags": ["Deer", "Feral hogs"]}], today).level == "watch"
    assert field_report_signal([{"logged_at": seen, "tags": ["Washed-out road", "Cattle out"]}], today).level == "concern"


def test_report_location_is_kept_and_checked(tmp_path):
    store = AppStore(tmp_path / "app.sqlite")
    row, _ = store.add_log("ws", {"client_id": "r1", "kind": "note", "tags": ["Feral hogs"], "lat": "30.1", "lon": -103.5,
                                  "accuracy_m": 7, "user_id": "spoofed"}, user_id="u1")
    assert row["lat"] == 30.1 and row["lon"] == -103.5 and row["user_id"] == "u1"
    row, _ = store.add_log("ws", {"client_id": "r2", "kind": "note", "lat": 999, "lon": "x"}, user_id="u1")
    assert "lat" not in row and "lon" not in row


def test_phone_sign_in_renews_itself_when_used(tmp_path):
    import sqlite3 as _sqlite3

    from ranch_ai.rancher.store import SESSION_DAYS

    store = AppStore(tmp_path / "app.sqlite")
    token = store.create_session("u1", "ws")
    soon = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(timespec="seconds")
    with _sqlite3.connect(tmp_path / "app.sqlite") as conn:
        conn.execute("UPDATE sessions SET expires_at = ?", (soon,))
    assert store.session(token)["user_id"] == "u1"
    with _sqlite3.connect(tmp_path / "app.sqlite") as conn:
        expires = datetime.fromisoformat(conn.execute("SELECT expires_at FROM sessions").fetchone()[0])
    assert expires > datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS - 2)
    assert SESSION_DAYS >= 365


def test_todo_list_add_check_off_repeat_undo_and_permissions(client):
    owner = _login(client)
    ws = client.user.workspace_id
    code = client.post("/api/crew/invites", headers=owner).json()["code"]
    hand = {"Authorization": "Bearer " + client.post("/api/join", json={"code": code, "name": "Luis", "email": "luis@example.com",
                                                                        "password": "HandPass123"}).json()["token"]}
    client.cookies.clear()
    ops = [
        {"op_id": "o1", "op": "add", "task_id": "t1", "title": "Fix north fence", "pasture_id": "P2", "due_date": "2026-10-20"},
        {"op_id": "o2", "op": "add", "task_id": "t2", "title": "Check waters", "repeat_days": 2, "due_date": "2026-10-19"},
        {"op_id": "o3", "op": "add", "task_id": "t3", "title": ""},
    ]
    res = client.post("/api/tasks", headers=owner, json=ops).json()
    assert res["applied"] == ["o1", "o2"] and res["errors"][0]["op_id"] == "o3"
    assert client.post("/api/tasks", headers=owner, json=ops[:2]).json()["applied"] == ["o1", "o2"]      # re-send is safe
    data = client.get("/api/tasks", headers=hand).json()
    assert {t["title"] for t in data["tasks"]} == {"Fix north fence", "Check waters"}
    assert {p["name"] for p in data["people"]} == {"Zach", "Luis"}

    # The hand checks both off (e.g. sent later from the field).
    res = client.post("/api/tasks", headers=hand, json=[{"op_id": "h1", "op": "done", "task_id": "t1", "at": "2026-10-19T15:00:00Z"},
                                                         {"op_id": "h2", "op": "done", "task_id": "t2", "at": "2026-10-19T15:05:00Z"}]).json()
    tasks = {t["task_id"]: t for t in res["tasks"]}
    assert tasks["t1"]["done_by_name"] == "Luis" and tasks["t1"]["done_at"].startswith("2026-10-19")
    assert tasks["t2"]["done_at"] is None and tasks["t2"]["due_date"] == "2026-10-21"                   # repeating: next due
    assert tasks["t2"]["history"][0]["by"] == "Luis"
    # Only the hand or the owner can undo; hands can't delete the owner's jobs.
    assert client.post("/api/tasks", headers=hand, json=[{"op_id": "h3", "op": "undo", "task_id": "t2"}]).json()["applied"] == ["h3"]
    assert {t["task_id"]: t for t in client.get("/api/tasks", headers=owner).json()["tasks"]}["t2"]["due_date"] == "2026-10-19"
    assert client.post("/api/tasks", headers=hand, json=[{"op_id": "h4", "op": "delete", "task_id": "t1"}]).json()["errors"]
    assert client.post("/api/tasks", headers=owner, json=[{"op_id": "o4", "op": "delete", "task_id": "t1"}]).json()["applied"] == ["o4"]
    assert [t["task_id"] for t in client.get("/api/tasks", headers=owner).json()["tasks"]] == ["t2"]


def test_one_login_for_two_ranches_with_partner_code_and_switching(client):
    # Justin owns Clear Creek; Zach owns Caja Caliente. Justin gives Zach a partner code.
    justin = client.app.state.auth.create_user(email="justin@example.com", password="ClearCreek9", full_name="Justin",
                                               ranch_name="Clear Creek Ranch", ranch_address="TX")
    store = client.store
    store.save_snapshot(justin.workspace_id, {"generated_at": "2026-10-19T05:00:00+00:00", "ranch": {"name": "Clear Creek Ranch"}, "pastures": []})
    store.save_snapshot(client.user.workspace_id, {"generated_at": "2026-10-19T05:00:00+00:00", "ranch": {"name": "Caja Caliente"}, "pastures": []})
    j = {"Authorization": "Bearer " + client.post("/api/login", json={"email": "justin@example.com", "password": "ClearCreek9"}).json()["token"]}
    code = client.post("/api/crew/invites", headers=j, json={"role": "partner"}).json()
    assert code["role"] == "owner" and code["max_uses"] == 1
    client.cookies.clear()

    # Zach joins with his EXISTING login (wrong password refused), and lands on Clear Creek as a partner.
    assert client.post("/api/join", json={"code": code["code"], "email": "zach@example.com", "password": "nope-nope"}).status_code == 401
    joined = client.post("/api/join", json={"code": code["code"], "email": "zach@example.com", "password": "CorrectHorse9"}).json()
    assert joined["ranch"] == "Clear Creek Ranch" and joined["role"] == "owner"
    assert {r["name"] for r in joined["ranches"]} == {"Caja Caliente", "Clear Creek Ranch"}
    z = {"Authorization": "Bearer " + joined["token"]}
    client.cookies.clear()
    assert client.get("/api/crew", headers=z).status_code == 200                       # partner can manage crew

    # Switch to Caja Caliente; the old token stops working, the new one opens the other ranch.
    sw = client.post("/api/switch", headers=z, json={"workspace_id": client.user.workspace_id}).json()
    assert sw["ranch"] == "Caja Caliente" and client.get("/api/me", headers=z).status_code == 401
    z2 = {"Authorization": "Bearer " + sw["token"]}
    assert client.get("/api/snapshot", headers=z2).json()["ranch"]["name"] == "Caja Caliente"
    assert client.post("/api/switch", headers=z2, json={"workspace_id": "user-someone-else"}).status_code == 403
    # Signing in again goes to the ranch the phone asks for.
    again = client.post("/api/login", json={"email": "zach@example.com", "password": "CorrectHorse9", "ranch": justin.workspace_id}).json()
    assert again["ranch"] == "Clear Creek Ranch"


def test_places_on_the_map(client):
    owner = _login(client)
    code = client.post("/api/crew/invites", headers=owner).json()["code"]
    hand = {"Authorization": "Bearer " + client.post("/api/join", json={"code": code, "name": "Luis", "email": "luis@example.com",
                                                                        "password": "HandPass123"}).json()["token"]}
    client.cookies.clear()
    blind = {"place_id": "pl1", "kind": "deer_blind", "name": "North blind", "lat": 30.31, "lon": -103.69, "photo_id": "ph9",
             "updated_at": "2026-10-19T10:00:00Z"}
    res = client.post("/api/places", headers=hand, json=[blind, {"place_id": "pl2", "kind": "spaceship", "name": "x", "lat": 1, "lon": 1},
                                                         {"place_id": "pl3", "kind": "pond", "name": "Big tank"}]).json()
    assert res["saved"] == ["pl1"] and len(res["errors"]) == 2
    tank = {"place_id": "pl4", "kind": "water_tank", "name": "Windmill tank", "lat": 30.30, "lon": -103.70}
    client.post("/api/places", headers=owner, json=tank)
    assert {p["name"] for p in client.get("/api/places", headers=hand).json()} == {"North blind", "Windmill tank"}
    # A late, older edit doesn't overwrite a newer one; hands can't change the owner's places.
    client.post("/api/places", headers=hand, json={**blind, "name": "Old name", "updated_at": "2026-10-18T10:00:00Z"})
    assert next(p for p in client.get("/api/places", headers=owner).json() if p["place_id"] == "pl1")["name"] == "North blind"
    assert client.post("/api/places", headers=hand, json={**tank, "name": "Mine now"}).json()["errors"]
    assert client.post("/api/places", headers=hand, json={"place_id": "pl4", "deleted": True}).json()["errors"]
    assert client.post("/api/places", headers=owner, json={"place_id": "pl4", "deleted": True}).json()["saved"] == ["pl4"]
    assert [p["place_id"] for p in client.get("/api/places", headers=owner).json()] == ["pl1"]


def test_photo_keeps_its_place(client, tmp_path, monkeypatch):
    monkeypatch.setenv("RANGEIQ_PHOTO_DIR", str(tmp_path / "photos"))
    owner = _login(client)
    assert _upload(client, owner, "pp1", place_id="pl1", lat=30.3, lon=-103.6).status_code == 200
    assert client.get("/api/photos", headers=owner).json()[0]["place_id"] == "pl1"


def test_photos_can_belong_to_a_report_or_a_job(client, tmp_path, monkeypatch):
    monkeypatch.setenv("RANGEIQ_PHOTO_DIR", str(tmp_path / "photos"))
    owner = _login(client)
    assert _upload(client, owner, "rp1", log_id="report-1", lat=30.3, lon=-103.6).status_code == 200
    assert _upload(client, owner, "jb1", task_id="job-1").status_code == 200
    got = {p["client_id"]: p for p in client.get("/api/photos", headers=owner).json()}
    assert (got["rp1"]["log_id"], got["rp1"]["task_id"]) == ("report-1", None)
    assert (got["jb1"]["task_id"], got["jb1"]["log_id"]) == ("job-1", None)
    assert client.delete("/api/photos/jb1", headers=owner).json() == {"deleted": True}      # removing a photo from a job
    assert [p["client_id"] for p in client.get("/api/photos", headers=owner).json()] == ["rp1"]


def test_usgs_water_map_turns_ponds_and_springs_into_pins(tmp_path):
    from ranch_ai.rancher.water_map import water_features

    pastures = pd.DataFrame({"pasture_id": ["A"], "geometry": [[[-103.70, 30.30], [-103.68, 30.30], [-103.68, 30.32], [-103.70, 30.32]]]})
    calls = []   # (the box query adds ~200 m around the ranch, so a neighbour's well just north is returned and must be dropped)

    class Resp:
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): pass
        def json(self): return self.payload

    def fake_get(url, params, timeout):
        calls.append(url)
        if url.endswith("/12/query"):
            square = [[-103.691, 30.311], [-103.689, 30.311], [-103.689, 30.313], [-103.691, 30.313], [-103.691, 30.311]]
            return Resp({"features": [
                {"properties": {"FTYPE": 436, "FCODE": 43614, "AREASQKM": 0.004, "PERMANENT_IDENTIFIER": "w1", "GNIS_NAME": None},
                 "geometry": {"type": "Polygon", "coordinates": [square]}},
                {"properties": {"FTYPE": 493, "FCODE": 49300, "PERMANENT_IDENTIFIER": "est"}, "geometry": {"type": "Polygon", "coordinates": [square]}}]})
        return Resp({"features": [{"properties": {"FTYPE": 458, "FCODE": 45800, "PERMANENT_IDENTIFIER": "s1", "GNIS_NAME": "Cottonwood Spring"},
                                   "geometry": {"type": "Point", "coordinates": [-103.695, 30.305]}},
                                  {"properties": {"FTYPE": 488, "FCODE": 48800, "PERMANENT_IDENTIFIER": "nb"},     # neighbour's well
                                   "geometry": {"type": "Point", "coordinates": [-103.6995, 30.3215]}}]})

    out = water_features("ws", pastures, tmp_path, get=fake_get)
    kinds = {f["kind"]: f for f in out["features"]}
    assert set(kinds) == {"tank", "spring"} and kinds["tank"]["intermittent"] and kinds["tank"]["acres"] == pytest.approx(0.99, abs=0.01)
    assert kinds["tank"]["lat"] == pytest.approx(30.312, abs=1e-4) and kinds["spring"]["name"] == "Cottonwood Spring"
    assert len(calls) == 2
    water_features("ws", pastures, tmp_path, get=fake_get)                 # cached: no new requests
    assert len(calls) == 2

    def down(*a, **k):
        raise ConnectionError("no route")
    assert water_features("other", pastures, tmp_path, get=down)["error"]


def test_sensor_places_keep_their_device_id(client):
    owner = _login(client)
    client.post("/api/places", headers=owner, json={"place_id": "s1", "kind": "sensor_water", "name": "Windmill tank level",
                                                    "lat": 30.3, "lon": -103.6, "device_id": " RIQ-0042 "})
    assert client.get("/api/places", headers=owner).json()[0]["device_id"] == "RIQ-0042"


KML = b"""<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name>North Flat</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
-103.70,30.30,0 -103.69,30.30,0 -103.69,30.31,0 -103.70,30.31,0 -103.70,30.30,0</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
<Placemark><name>Windmill</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
-103.69,30.30,0 -103.68,30.30,0 -103.68,30.31,0 -103.69,30.31,0 -103.69,30.30,0</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
<Placemark><name>Gate</name><Point><coordinates>-103.695,30.305,0</coordinates></Point></Placemark>
</Document></kml>"""


def test_ranch_setup_files_match_what_the_worker_reads(tmp_path):
    import zipfile as _zip

    from ranch_ai.rancher import setup as rs

    out = rs.save_boundary("user-zach-1", "Caja Caliente.kml", KML, root=tmp_path)
    assert out["pastures"] == 2 and out["names"] == ["North Flat", "Windmill"]
    p = rs.paths("user-zach-1", tmp_path)
    state = json.loads(p["state"].read_text())
    assert state["saved_boundary"]["filename"] == "Caja Caliente.kml" and Path(state["saved_boundary"]["path"]).read_bytes() == KML
    import yaml as _yaml
    cfg = _yaml.safe_load(p["config"].read_text())
    assert cfg["ranch"]["latitude"] == pytest.approx(30.305) and cfg["ranch"]["longitude"] == pytest.approx(-103.69)
    assert p["refresh"].exists() and rs.take_refresh_requests(root=tmp_path) == ["user-zach-1"] and not p["refresh"].exists()
    rs.set_ranch("user-zach-1", name="Caja Caliente", timezone="America/Chicago", root=tmp_path)
    assert _yaml.safe_load(p["config"].read_text())["ranch"]["name"] == "Caja Caliente"
    with pytest.raises(ValueError):
        rs.set_ranch("user-zach-1", timezone="Mars/Olympus", root=tmp_path)
    rs.set_pasture_names("user-zach-1", {"P1": "Big Flat", "P2": ""}, root=tmp_path)
    assert rs.describe("user-zach-1", root=tmp_path)["pasture_names"] == {"P1": "Big Flat"}
    # KMZ works; points-only, junk and huge files are refused with plain words
    buf = io.BytesIO()
    with _zip.ZipFile(buf, "w") as z:
        z.writestr("doc.kml", KML)
    assert rs.save_boundary("user-zach-1", "ranch.kmz", buf.getvalue(), root=tmp_path)["pastures"] == 2
    for name, data in (("pins.kml", KML.split(b"<Placemark>")[0] + b"<Placemark><Point><coordinates>1,1</coordinates></Point></Placemark></Document></kml>"),
                       ("x.kml", b"not xml"), ("x.shp", b"..."), ("big.kml", b"x" * (rs.MAX_BOUNDARY_BYTES + 1))):
        with pytest.raises(ValueError):
            rs.check_boundary(name, data)


def test_setup_api_is_owner_only(client):
    owner = _login(client)
    code = client.post("/api/crew/invites", headers=owner).json()["code"]
    hand = {"Authorization": "Bearer " + client.post("/api/join", json={"code": code, "name": "Luis", "email": "luis@example.com",
                                                                        "password": "HandPass123"}).json()["token"]}
    client.cookies.clear()
    assert client.get("/api/setup", headers=hand).status_code == 403
    bad = client.post("/api/setup/boundary", headers=owner, files={"file": ("ranch.txt", b"hello", "text/plain")})
    assert bad.status_code == 400 and "KML" in bad.json()["detail"]


def test_terrain_files_are_long_cached_and_client_errors_are_logged(client, capsys):
    owner = _login(client)
    client.store.save_terrain(client.user.workspace_id, {"nx": 2, "ny": 1}, b"\x00\x00\x01\x00", b"\xff\xd8\xff", "image/jpeg")
    r = client.get("/api/terrain/height?v=2026-10-19", headers=owner)
    assert r.status_code == 200 and "max-age=2592000" in r.headers["cache-control"]
    assert client.post("/api/client-error", content=b'{"where":"3d","error":"boom"}').json()["ok"] is True
    assert "[client-error]" in capsys.readouterr().out


def test_drawn_boundaries_lock_and_replace_the_uploaded_file(client, tmp_path):
    from ranch_ai.rancher.worker import drawn_pastures

    owner = _login(client)
    ws = client.user.workspace_id
    code = client.post("/api/crew/invites", headers=owner).json()["code"]
    hand = {"Authorization": "Bearer " + client.post("/api/join", json={"code": code, "name": "Luis", "email": "luis@example.com",
                                                                        "password": "HandPass123"}).json()["token"]}
    client.cookies.clear()
    square = [[-103.70, 30.30], [-103.69, 30.30], [-103.69, 30.31], [-103.70, 30.31]]
    client.store.save_snapshot(ws, {"generated_at": "2026-10-20T05:00:00+00:00", "ranch": {"name": "Caja Caliente"},
                                    "pastures": [{"id": "P1", "name": "North Flat", "outline": square + [square[0]]}]})
    # Boundaries start locked once there are pastures; unlocking copies the uploaded pastures in, keeping their ids.
    res = client.post("/api/boundaries/lock", headers=owner, json={"locked": False}).json()
    assert res["boundaries_locked"] is False and [s["shape_id"] for s in res["shapes"]] == ["P1"]
    assert client.post("/api/boundaries/lock", headers=hand, json={"locked": False}).status_code == 403
    # Owner redraws a pasture and adds one; a hand can't touch boundaries but can add a trail.
    moved = [[-103.701, 30.30], [-103.69, 30.30], [-103.69, 30.311], [-103.701, 30.311]]
    r = client.post("/api/shapes", headers=owner, json=[{"shape_id": "P1", "kind": "pasture", "name": "North Flat", "coords": moved},
                                                        {"shape_id": "new1", "kind": "pasture", "name": "Trap", "coords": square[:3]},
                                                        {"shape_id": "bad", "kind": "pasture", "name": "x", "coords": square[:2]}]).json()
    assert r["saved"] == ["P1", "new1"] and r["errors"][0]["shape_id"] == "bad"
    assert client.post("/api/shapes", headers=hand, json={"shape_id": "new1", "kind": "pasture", "coords": square}).json()["errors"]
    t = client.post("/api/shapes", headers=hand, json={"shape_id": "tr1", "kind": "game_trail", "name": "Deer run",
                                                       "coords": [[-103.70, 30.30], [-103.695, 30.305]], "source": "gps"}).json()
    assert t["saved"] == ["tr1"]
    assert client.post("/api/shapes", headers=hand, json={"shape_id": "tr2", "kind": "highway", "coords": square}).json()["errors"]
    # Locked again: nobody changes boundaries.
    client.post("/api/boundaries/lock", headers=owner, json={"locked": True})
    locked = client.post("/api/shapes", headers=owner, json={"shape_id": "new1", "kind": "pasture", "name": "Trap", "coords": square}).json()
    assert "locked" in locked["errors"][0]["error"]
    data = client.get("/api/shapes", headers=hand).json()
    assert data["boundaries_locked"] is True and data["boundary_source"] == "drawn"
    # The worker builds the ranch from the drawn pastures.
    pastures = drawn_pastures(ws, client.store)
    assert sorted(pastures["pasture_id"]) == ["P1", "new1"] and pastures["acres"].min() > 0


def test_file_pastures_start_locked_and_new_drawing_keeps_them(client):
    owner = _login(client)
    ws = client.user.workspace_id
    sq = [[-103.70, 30.30], [-103.69, 30.30], [-103.69, 30.31], [-103.70, 30.31]]
    client.store.save_snapshot(ws, {"generated_at": "2026-10-20T05:00:00+00:00", "pastures": [{"id": "P1", "name": "A", "outline": sq},
                                                                                                {"id": "P2", "name": "B", "outline": sq}]})
    assert client.get("/api/shapes", headers=owner).json()["boundaries_locked"] is True
    client.store.set_ranch_setting(ws, "boundaries_locked", False)          # e.g. unlocked before this fix
    client.post("/api/shapes", headers=owner, json={"shape_id": "n1", "kind": "pasture", "name": "New", "coords": sq[:3]})
    assert sorted(s["shape_id"] for s in client.get("/api/shapes", headers=owner).json()["shapes"]) == ["P1", "P2", "n1"]


def test_3d_code_is_never_served_stale(client):
    # The phone must not pair a new app.js with an old terrain3d.js (bug of 2026-10-20: "view3d.setLines is not a function").
    sw = (Path(__file__).resolve().parents[1] / "web" / "app" / "sw.js").read_text()
    assert 'terrain3d\\.js$/.test(url.pathname)' in sw and 'fetch(req, {cache: "no-cache"})' in sw
    web = client.app.routes  # app files are served with Cache-Control: no-cache (vendor/ and images excepted)
    r = client.get("/app/")
    assert r.headers.get("cache-control") == "no-cache"


def test_admin_summary_says_when_3d_is_behind_a_redrawn_boundary(tmp_path, monkeypatch, capsys):
    """The server summary (public CI output) reports drawn shapes by kind and whether the 3D build matches them,
    with no names or coordinates."""
    from ranch_ai.rancher import admin, worker

    store = AppStore(tmp_path / "app.sqlite")
    ws = "ws1"
    store.save_snapshot(ws, {"generated_at": datetime.now(timezone.utc).isoformat(), "pastures": [], "counts": {}, "sources": []})
    ring = [[-103.5, 29.6], [-103.49, 29.6], [-103.49, 29.61], [-103.5, 29.61]]
    for sid, kind, coords in [("P1", "pasture", ring), ("F1", "fence", ring[:2])]:
        store.save_shape(ws, {"shape_id": sid, "kind": kind, "name": "Secret name", "coords": coords,
                              "updated_at": datetime.now(timezone.utc).isoformat()}, user_id="u", user_name="Zach",
                         is_owner=True, boundaries_locked=False)
    meta = {"nx": 2, "ny": 2, "dem_source": "usgs_3dep", "dem_resolution_m": 10, "texture_source": "naip",
            "outline_hash": worker.outline_hash(worker.drawn_pastures(ws, store)), "updated_at": "2026-10-20T10:00:00Z"}
    store.save_terrain(ws, meta, b"h", b"t", "image/jpeg")
    monkeypatch.setattr(admin, "AppStore", lambda: store)
    monkeypatch.setattr(worker, "account_workspaces", lambda _p: [ws])
    monkeypatch.setattr(admin, "_ranch_layout", lambda *a: None)
    admin.summary()
    out = capsys.readouterr().out
    assert "drawn in the app: {'fence': 1, 'pasture': 1}" in out and "outlines match the current pastures: yes" in out
    assert "Secret name" not in out and "103.5" not in out
    store.save_shape(ws, {"shape_id": "P1", "kind": "pasture", "name": "Secret name", "coords": ring[:3],
                          "updated_at": (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat()},
                     user_id="u", user_name="Zach", is_owner=True, boundaries_locked=False)
    admin.summary()
    assert "outlines match the current pastures: NO, waiting for a rebuild" in capsys.readouterr().out


def test_anyone_can_resolve_a_problem_and_a_done_job_resolves_its_report(client, tmp_path, monkeypatch):
    from ranch_ai.rancher.status import field_report_signal

    monkeypatch.setenv("RANGEIQ_PHOTO_DIR", str(tmp_path / "photos"))
    owner = _login(client)
    code = client.post("/api/crew/invites", headers=owner).json()["code"]
    hand = {"Authorization": "Bearer " + client.post("/api/join", json={"code": code, "name": "Luis", "email": "luis@example.com",
                                                                        "password": "HandPass123"}).json()["token"]}
    client.cookies.clear()
    now = datetime.now(timezone.utc)
    t0 = lambda s: (now + timedelta(seconds=s)).isoformat()   # noqa: E731
    client.post("/api/logs", headers=owner, json=[{"client_id": "r1", "kind": "note", "tags": ["Cattle out"], "pasture_id": "P1", "logged_at": t0(0)},
                                                  {"client_id": "r2", "kind": "note", "tags": ["Fence down"], "pasture_id": "P2", "logged_at": t0(0)}])
    logs = lambda: {l["client_id"]: l for l in client.get("/api/logs", headers=owner).json()}   # noqa: E731
    pasture_reports = lambda pid: [l for l in logs().values() if l["pasture_id"] == pid and not l.get("resolved_at")]   # noqa: E731
    assert field_report_signal(pasture_reports("P1")).level == "concern"

    # a hand resolves the cattle-out report (crew can); it stops counting toward the pasture's status
    res = client.post("/api/resolve", headers=hand, json=[{"item_id": "r1", "resolved": True, "at": t0(10), "note": "All 12 back in"},
                                                          {"item_id": "nope", "resolved": True, "at": t0(10)}]).json()
    assert res["saved"] == ["r1"] and res["errors"][0]["retry"] is True
    r1 = logs()["r1"]
    assert (r1["resolved_by"], r1["resolve_note"]) == ("Luis", "All 12 back in") and field_report_signal(pasture_reports("P1")) is None
    # a late, older change from another phone doesn't undo it; a newer reopen does
    client.post("/api/resolve", headers=owner, json={"item_id": "r1", "resolved": False, "at": t0(5)})
    assert logs()["r1"].get("resolved_at")
    client.post("/api/resolve", headers=owner, json={"item_id": "r1", "resolved": False, "at": t0(20)})
    assert not logs()["r1"].get("resolved_at")

    # a job made from the fence report: checking it off resolves the report, undoing reopens it
    client.post("/api/tasks", headers=owner, json=[{"op_id": "a1", "op": "add", "task_id": "j1", "title": "Fix fence", "source_id": "r2", "at": t0(1)}])
    client.post("/api/tasks", headers=hand, json=[{"op_id": "d1", "op": "done", "task_id": "j1", "at": t0(30)}])
    r2 = logs()["r2"]
    assert r2["resolved_by"] == "Luis" and r2["resolved_via"] == "j1" and r2["resolve_note"] == "Job done: Fix fence"
    client.post("/api/tasks", headers=hand, json=[{"op_id": "u1", "op": "undo", "task_id": "j1", "at": t0(40)}])
    assert not logs()["r2"].get("resolved_at")
    # photos can be resolved too
    assert _upload(client, owner, "ph1", tags=["Water low"], pasture_id="P1").status_code == 200
    client.post("/api/resolve", headers=hand, json={"item_id": "ph1", "resolved": True, "at": t0(50)})
    assert client.get("/api/photos", headers=owner).json()[0]["resolved_by"] == "Luis"


def test_snapshot_ignores_resolved_reports():
    import pandas as pd
    from ranch_ai.config import Settings
    from ranch_ai.rancher import snapshot as snap_mod
    from ranch_ai.utils.io import load_pastures

    s = Settings()
    for name in ("historical_weather", "soils", "drought", "vegetation"):
        getattr(s.public_data, name).provider = "mock"
    s.weather.provider = s.alerts.provider = "mock"
    pastures = load_pastures()
    pid = str(pastures.iloc[0]["pasture_id"])
    now = datetime.now(timezone.utc).isoformat()
    report = {"client_id": "r1", "kind": "note", "tags": ["Cattle out"], "pasture_id": pid, "logged_at": now}
    field = lambda snap: [g for p in snap["pastures"] if p["id"] == pid for g in p["signals"] if g["key"] == "field"]   # noqa: E731
    open_snap = snap_mod.build_snapshot(s, pastures, logs=[report], include_terrain=False, today=pd.Timestamp(now[:10]))
    assert field(open_snap) and field(open_snap)[0]["level"] == "concern"
    done_snap = snap_mod.build_snapshot(s, pastures, logs=[{**report, "resolved_at": now, "resolved_by": "Luis"}],
                                        include_terrain=False, today=pd.Timestamp(now[:10]))
    assert field(done_snap) == []


def test_messenger_whole_ranch_and_direct_threads(client):
    owner = _login(client)
    code = client.post("/api/crew/invites", headers=owner).json()["code"]
    def join(name, email):
        r = client.post("/api/join", json={"code": code, "name": name, "email": email, "password": "HandPass123"}).json()
        client.cookies.clear()
        return {"Authorization": "Bearer " + r["token"]}
    luis, ana = join("Luis", "luis@example.com"), join("Ana", "ana@example.com")
    ids = {p["name"]: p["user_id"] for p in client.get("/api/messages", headers=owner).json()["people"]}
    assert set(ids) == {"Zach", "Luis", "Ana"}

    sent = client.post("/api/messages", headers=luis, json=[
        {"msg_id": "m1", "thread_id": "all", "text": "Gate on the county road is open", "sent_at": "2026-10-22T10:00:00Z"},
        {"msg_id": "m2", "to_user_id": ids["Zach"], "text": "Need more mineral at Mesa"},
        {"msg_id": "m3", "thread_id": "all", "text": "   "},
        {"msg_id": "m4", "to_user_id": "stranger", "text": "hi"}]).json()
    assert sent["saved"] == ["m1", "m2"] and [e["msg_id"] for e in sent["errors"]] == ["m3", "m4"]
    assert client.post("/api/messages", headers=luis, json={"msg_id": "m1", "thread_id": "all", "text": "dup"}).json()["saved"] == ["m1"]

    owner_view = client.get("/api/messages", headers=owner).json()
    dm = "dm:" + "|".join(sorted([ids["Luis"], ids["Zach"]]))
    assert [(m["msg_id"], m["thread_id"]) for m in owner_view["messages"]] == [("m1", "all"), ("m2", dm)]
    # Ana sees the ranch-wide message but not Luis's direct message to the owner, and can't post into it
    assert [m["msg_id"] for m in client.get("/api/messages", headers=ana).json()["messages"]] == ["m1"]
    assert client.post("/api/messages", headers=ana, json={"msg_id": "x", "thread_id": dm, "text": "hi"}).json()["errors"]
    # replies and "since": only what's new
    since = owner_view["now"]
    client.post("/api/messages", headers=owner, json={"msg_id": "m5", "thread_id": dm, "text": "I'll bring some Friday"})
    newer = client.get("/api/messages", headers=luis, params={"since": since}).json()["messages"]
    assert [m["msg_id"] for m in newer] == ["m5"] and newer[0]["from_name"] == "Zach"
    # read state: replying in a conversation marks it read for you
    store = client.store
    ws = client.user.workspace_id
    assert store.unread_count(ws, ids["Zach"]) == 1 and store.unread_count(ws, ids["Luis"]) == 1 and store.unread_count(ws, ids["Ana"]) == 1
    client.post("/api/messages/read", headers=owner, json={"thread_id": "all", "at": owner_view["messages"][0]["created_at"]})
    assert store.unread_count(ws, ids["Zach"]) == 0
    # delete: only your own (or the owner); deletions reach other phones through "since"
    assert client.delete("/api/messages/m1", headers=ana).status_code == 403
    assert client.delete("/api/messages/m1", headers=luis).json() == {"deleted": True}
    gone = client.get("/api/messages", headers=ana, params={"since": since}).json()["messages"]
    assert {"msg_id": "m1", "deleted": True} in [{k: m[k] for k in ("msg_id", "deleted") if k in m} for m in gone]
    assert "m1" not in [m["msg_id"] for m in client.get("/api/messages", headers=ana).json()["messages"]]


def test_push_subscriptions_and_sending(client):
    from ranch_ai.rancher import push

    owner = _login(client)
    key = client.get("/api/push/key", headers=owner).json()["key"]
    import base64
    raw = base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))
    assert len(raw) == 65 and raw[0] == 4                                     # uncompressed P-256 point
    assert client.get("/api/push/key", headers=owner).json()["key"] == key    # same key every time (kept in the database)
    assert client.post("/api/push/subscribe", headers=owner, json={"endpoint": "http://evil", "keys": {}}).status_code == 400
    sub = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "BPk", "auth": "xyz"}}
    assert client.post("/api/push/subscribe", headers=owner, json=sub).json() == {"ok": True}
    uid = client.user.user_id if hasattr(client.user, "user_id") else client.get("/api/me", headers=owner).json()["user_id"]
    got = []
    counts = push.send(client.store, [uid], {"title": "t", "body": "b"}, sender=lambda info, data, key: got.append(info) or 201)
    assert counts == {"sent": 1, "dropped": 0, "failed": 0} and got[0]["endpoint"] == sub["endpoint"]
    # an expired subscription is dropped
    assert push.send(client.store, [uid], {"title": "t"}, sender=lambda *a: 410)["dropped"] == 1
    assert client.store.push_subs_for([uid]) == []


def test_real_web_push_request_is_signed_and_encrypted(client, monkeypatch):
    """With pywebpush: the request carries a VAPID signature and an aes128gcm-encrypted body (nothing in clear)."""
    pytest.importorskip("pywebpush")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    import base64
    import requests
    from ranch_ai.rancher import push

    phone = ec.generate_private_key(ec.SECP256R1())
    p256dh = base64.urlsafe_b64encode(phone.public_key().public_bytes(serialization.Encoding.X962,
                                      serialization.PublicFormat.UncompressedPoint)).rstrip(b"=").decode()
    client.store.save_push_sub("u1", {"endpoint": "https://fcm.googleapis.com/fcm/send/abc",
                                      "keys": {"p256dh": p256dh, "auth": base64.urlsafe_b64encode(b"0123456789abcdef").rstrip(b"=").decode()}})
    seen = {}

    class Resp:                       # enough of a requests.Response for pywebpush 2.0-2.5
        status_code = 201
        text = ""
        headers: dict = {}
        content = b""
    def fake_post(self, url, data=None, headers=None, timeout=None, **kw):
        seen.update(url=url, data=data, headers=headers); return Resp()
    monkeypatch.setattr(requests.Session, "post", fake_post)
    monkeypatch.setattr(requests, "post", lambda url, **kw: fake_post(None, url, **kw))
    assert push.send(client.store, ["u1"], {"title": "Luis", "body": "Cattle out on the county road"})["sent"] == 1
    assert seen["url"].startswith("https://fcm.googleapis.com/") and seen["headers"]["Content-Encoding"] == "aes128gcm"
    assert seen["headers"]["Authorization"].startswith("vapid t=") and b"Cattle" not in seen["data"]


def test_message_ticks_sent_delivered_seen(client, monkeypatch):
    from ranch_ai.rancher import push

    owner = _login(client)
    code = client.post("/api/crew/invites", headers=owner).json()["code"]
    def join(name, email):
        r = client.post("/api/join", json={"code": code, "name": name, "email": email, "password": "HandPass123"}).json()
        client.cookies.clear()
        return {"Authorization": "Bearer " + r["token"]}
    luis, ana = join("Luis", "luis@example.com"), join("Ana", "ana@example.com")
    pushed = []
    monkeypatch.setattr(push, "send_in_background", lambda store, ids, payload: pushed.append((ids, payload)))
    ids = {p["name"]: p["user_id"] for p in client.get("/api/messages", headers=owner).json()["people"]}
    dm = "dm:" + "|".join(sorted([ids["Luis"], ids["Zach"]]))
    client.post("/api/messages", headers=luis, json=[{"msg_id": "a", "to_user_id": ids["Zach"], "text": "Cattle out at the county road"},
                                                     {"msg_id": "b", "thread_id": "all", "text": "Heading to the windmill"}])
    rec = lambda h: client.get("/api/messages", headers=h).json()["receipts"]   # noqa: E731
    msg = {m["msg_id"]: m for m in client.get("/api/messages", headers=luis).json()["messages"]}
    # sent only: Zach's phone hasn't fetched yet (Luis's own fetch doesn't count)
    assert rec(luis)[dm].get(ids["Zach"], {}).get("delivered", "") < msg["a"]["created_at"]
    # each recipient got their own push with a signed receipt; the service worker posts it -> delivered
    by_person = {tuple(i)[0]: p for i, p in pushed}
    assert set(by_person) == {ids["Zach"], ids["Ana"]} and all(p["receipt"] for p in by_person.values())
    assert client.post("/api/messages/delivered", json={"receipt": by_person[ids["Ana"]]["receipt"]}).json() == {"ok": True}
    assert client.post("/api/messages/delivered", json={"receipt": by_person[ids["Ana"]]["receipt"][:-2] + "00"}).status_code == 403
    assert rec(luis)["all"][ids["Ana"]]["delivered"] == msg["b"]["created_at"]
    # Zach opens the app: everything he fetched is delivered; then he reads the DM -> seen
    client.get("/api/messages", headers=owner)
    assert rec(luis)[dm][ids["Zach"]]["delivered"] >= msg["a"]["created_at"] and "read" not in rec(luis)[dm][ids["Zach"]]
    client.post("/api/messages/read", headers=owner, json={"thread_id": dm, "at": msg["a"]["created_at"]})
    assert rec(luis)[dm][ids["Zach"]]["read"] == msg["a"]["created_at"]
    # Ana can't see receipts of a direct conversation she isn't in
    assert dm not in rec(ana)


def test_profile_pictures_private_and_shown_to_the_crew(client, tmp_path, monkeypatch):
    monkeypatch.setenv("RANGEIQ_PHOTO_DIR", str(tmp_path / "photos"))
    owner = _login(client)
    code = client.post("/api/crew/invites", headers=owner).json()["code"]
    luis = {"Authorization": "Bearer " + client.post("/api/join", json={"code": code, "name": "Luis", "email": "luis@example.com",
                                                                        "password": "HandPass123"}).json()["token"]}
    client.cookies.clear()
    files = lambda data: {"photo": ("a.jpg", data, "image/jpeg")}   # noqa: E731
    assert client.post("/api/me/avatar", headers=luis, files=files(b"GIF89a")).status_code == 400
    assert client.post("/api/me/avatar", headers=luis, files=files(JPEG + b"0" * 400_000)).status_code == 413
    url = client.post("/api/me/avatar", headers=luis, files=files(JPEG)).json()["avatar_url"]
    assert url.startswith("/api/avatar/")
    people = {p["name"]: p for p in client.get("/api/messages", headers=owner).json()["people"]}
    assert people["Luis"]["avatar_url"] == url and people["Zach"]["avatar_url"] is None
    assert client.get(url).content == JPEG                                       # signed link works without sign-in (for <img>)
    assert client.get(url.replace("sig=", "sig=0")).status_code == 403           # but can't be guessed
    assert client.get("/api/me", headers=luis).json()["avatar_url"] == url
    # a new picture gets a new link (phones don't keep showing the old one)
    import time as _t; _t.sleep(1.1)
    url2 = client.post("/api/me/avatar", headers=luis, files=files(JPEG + b"x")).json()["avatar_url"]
    assert url2 != url
    assert client.delete("/api/me/avatar", headers=luis).json() == {"removed": True}
    assert client.get("/api/me", headers=luis).json()["avatar_url"] is None and client.get(url2).status_code == 404


def test_sos_alerts_everyone_tracks_location_and_closes(client, monkeypatch):
    from ranch_ai.rancher import push

    owner = _login(client)
    code = client.post("/api/crew/invites", headers=owner).json()["code"]
    def join(name, email):
        r = client.post("/api/join", json={"code": code, "name": name, "email": email, "password": "HandPass123"}).json()
        client.cookies.clear()
        return {"Authorization": "Bearer " + r["token"]}
    luis, ana = join("Luis", "luis@example.com"), join("Ana", "ana@example.com")
    pushed = []
    monkeypatch.setattr(push, "send_in_background", lambda store, ids, payload: pushed.append((sorted(ids), payload)))
    ids = {p["name"]: p["user_id"] for p in client.get("/api/messages", headers=owner).json()["people"]}

    # Luis holds SOS with no GPS fix yet, then the location arrives; a re-send (from the offline queue) is harmless
    r = client.post("/api/sos", headers=luis, json=[{"op": "create", "sos_id": "s1", "kind": "injury", "note": "Fell off the horse"},
                                                    {"op": "loc", "sos_id": "s1", "lat": 30.31, "lon": -103.69, "accuracy_m": 8}]).json()
    assert r["errors"] == [] and r["sos"][0]["lat"] == 30.31 and r["sos"][0]["resolved_at"] is None
    client.post("/api/sos", headers=luis, json={"op": "create", "sos_id": "s1", "kind": "injury"})
    urgent = [p for i, p in pushed if p.get("type") == "sos"]
    assert len(urgent) == 1 and pushed[0][0] == sorted([ids["Zach"], ids["Ana"]]) and urgent[0]["title"] == "🆘 SOS · Luis"
    # everyone sees it in the poll and in the Everyone chat
    poll = client.get("/api/messages", headers=ana).json()
    assert poll["sos"][0]["sos_id"] == "s1" and any(m["text"].startswith("🆘 SOS: Injury · Fell off the horse") for m in poll["messages"])
    # someone else can't move Luis's pin
    assert client.post("/api/sos", headers=ana, json={"op": "loc", "sos_id": "s1", "lat": 1, "lon": 1}).json()["errors"]
    # Zach is on the way: Luis is told, and it shows on the SOS
    client.post("/api/sos", headers=owner, json={"op": "ack", "sos_id": "s1"})
    assert [a["user_name"] for a in client.get("/api/sos", headers=luis).json()[0]["acks"]] == ["Zach"]
    assert any(i == [ids["Luis"]] and p["type"] == "sos-ack" for i, p in pushed)
    # Zach reaches him and closes it; the SOS stays in the list (for the Log) but isn't active
    client.post("/api/sos", headers=owner, json={"op": "resolve", "sos_id": "s1", "note": "Sprained wrist, driving him in"})
    s = client.get("/api/sos", headers=ana).json()[0]
    assert s["resolved_by"] == "Zach" and s["resolve_note"] == "Sprained wrist, driving him in"
    assert client.post("/api/sos", headers=luis, json={"op": "loc", "sos_id": "s1", "lat": 30.3, "lon": -103.6}).json()["errors"]
    texts = [m["text"] for m in client.get("/api/messages", headers=luis).json()["messages"]]
    assert any(t.startswith("✅ SOS over: Luis is OK") for t in texts) and any(t.startswith("🚙 On my way to Luis") for t in texts)


def test_every_place_kind_report_tag_and_water_feature_has_a_ranch_icon():
    import re
    from ranch_ai.rancher.status import TAG_LEVELS
    from ranch_ai.rancher.water_map import KIND_LABEL

    app = (Path(__file__).resolve().parents[1] / "web" / "app")
    icons = (app / "icons.js").read_text(encoding="utf-8")
    keys = set(re.findall(r'^\s+"([^"]+)":', icons, re.M)) | set(re.findall(r"^\s+([a-z_]+):", icons, re.M)) \
        | set(re.findall(r'I\["([^"]+)"\]\s*=', icons))
    kinds = re.findall(r"(\w+): \[T\(\"[^\"]+\"\), \"[^\"]+\", \"(?:water|hunting|ranch|sensors)\"\]", (app / "app.js").read_text(encoding="utf-8"))
    assert len(kinds) >= 20
    missing = [k for k in kinds if k not in keys] + [t for t in TAG_LEVELS if t not in keys] + \
              ["usgs_" + k for k in KIND_LABEL if "usgs_" + k not in keys]
    assert missing == []


# --- rain source: PRISM via ACIS, with plausibility checks --------------------------
class _Resp:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class _Session:
    def __init__(self, payload):
        self.payload, self.calls = payload, []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append((url, json))
        return _Resp(self.payload)


def test_prism_provider_parses_acis_and_converts_units():
    from ranch_ai.data.public_sources import AcisPrismHistoricalWeatherProvider

    payload = {"meta": {"ll": [-99.5, 32.5]}, "data": [
        ["2026-10-01", 25.4, 30.0, 15.0, 22.5], ["2026-10-02", 0.0, 28.0, 12.0, 20.0], ["2026-10-03", -999, -999, -999, -999]]}
    session = _Session(payload)
    frame = AcisPrismHistoricalWeatherProvider(session=session).get_daily_history(32.5, -99.5, "2026-10-01", "2026-10-03")
    url, body = session.calls[0]
    assert url == "https://data.rcc-acis.org/GridData" and body["grid"] == "21" and body["loc"] == "-99.5,32.5"
    assert body["elems"][0] == {"name": "pcpn", "interval": "dly", "units": "mm"}
    assert frame["public_precip_in"].tolist()[:2] == [1.0, 0.0] and np.isnan(frame["public_precip_in"].iloc[2])
    assert frame["public_temp_max_f"].iloc[0] == 86.0 and frame["source"].iloc[0] == "PRISM via ACIS GridData"


def test_prism_falls_back_to_nasa_outside_coverage_and_refuses_absurd_rain():
    from ranch_ai.data.public_sources import AcisPrismHistoricalWeatherProvider, precip_problem

    class Nasa:
        provider_name = "nasa_power"

        def get_daily_history(self, lat, lon, start, end):
            return pd.DataFrame({"date": pd.date_range(start, end), "public_precip_in": 0.1, "source": "NASA POWER Daily API"})

    empty = _Session({"meta": {}, "data": [["2026-10-01", -999, -999, -999, -999]]})
    prov = AcisPrismHistoricalWeatherProvider(session=empty, fallback=Nasa())
    frame = prov.get_daily_history(20.0, -100.0, "2026-10-01", "2026-10-03")
    assert prov.last_used == "nasa_power" and frame["source"].iloc[0].startswith("NASA")
    with pytest.raises(Exception):
        AcisPrismHistoricalWeatherProvider(session=_Session({"error": "bad loc"})).get_daily_history(1, 2, "2026-10-01", "2026-10-02")

    # The broken NASA POWER record seen in Oct 2026: a 1,165 mm day, and ~17,000 mm a year
    dates = pd.date_range("2016-07-15", "2026-10-23", freq="D")
    bad = pd.DataFrame({"date": dates, "public_precip_in": 1.9})
    assert "a year" in precip_problem(bad)
    spike = pd.DataFrame({"date": dates[:30], "public_precip_in": [0.0] * 29 + [45.9]})
    assert "one day" in precip_problem(spike)
    good = pd.DataFrame({"date": dates, "public_precip_in": 0.07})    # ~26 in a year: West Texas-ish
    assert precip_problem(good) is None
    assert rain_totals(bad) == {}                                    # an old bad cache shows nothing, not 107 in
    assert rain_totals(good)["rain_90d_in"] == pytest.approx(6.3, rel=0.02)


def test_accounts_on_nasa_power_are_moved_to_prism():
    from ranch_ai.config import Settings
    from ranch_ai.rancher.worker import usable_providers

    s = Settings()
    s.public_data.historical_weather.provider = "nasa_power"
    notes = usable_providers(s, env={})
    assert s.public_data.historical_weather.provider == "acis_prism" and any("acis_prism" in n for n in notes)


def test_notifications_reach_each_person_in_their_language(client, monkeypatch):
    from ranch_ai.rancher import push

    owner = _login(client)
    code = client.post("/api/crew/invites", headers=owner).json()["code"]
    r = client.post("/api/join", json={"code": code, "name": "Ana", "email": "ana@example.com", "password": "HandPass123"}).json()
    client.cookies.clear()
    ana = {"Authorization": "Bearer " + r["token"]}
    assert client.get("/api/me", headers=ana).json()["lang"] == "en"            # nobody picked yet: English
    assert client.post("/api/me/lang", headers=ana, json={"lang": "es"}).json() == {"lang": "es"}
    assert client.post("/api/me/lang", headers=owner, json={"lang": "fr"}).json() == {"lang": "en"}   # only en / es
    assert client.get("/api/me", headers=ana).json()["lang"] == "es"
    ids = {p["name"]: p["user_id"] for p in client.get("/api/messages", headers=owner).json()["people"]}
    pushed = []
    monkeypatch.setattr(push, "send_in_background", lambda store, who, payload: pushed.append((sorted(who), payload)))

    client.post("/api/messages", headers=owner, json=[{"msg_id": "m1", "thread_id": "all", "text": "Gate by the tank is open"}])
    to_ana = next(p for who, p in pushed if who == [ids["Ana"]])
    assert to_ana["title"].startswith("Zach → todos") and to_ana["body"] == "Gate by the tank is open"   # people's words stay as typed

    pushed.clear()
    client.post("/api/sos", headers=owner, json={"op": "create", "sos_id": "s9", "kind": "vehicle", "note": "Stuck in the draw"})
    sos = {tuple(who): p for who, p in pushed if p.get("type") == "sos"}
    assert sos[(ids["Ana"],)]["body"] == "Accidente o vehículo atascado · Stuck in the draw. Toca para ver dónde."
    client.post("/api/sos", headers=ana, json={"op": "ack", "sos_id": "s9"})
    ack = next(p for who, p in pushed if p.get("type") == "sos-ack")
    assert ack["title"] == "🚙 Ana is on the way"                              # Zach still reads English


# --- herd ledger -------------------------------------------------------------------------
def _at(day: int) -> str:
    return datetime(2026, 10, day, 12, tzinfo=timezone.utc).isoformat()


def test_herd_ledger_moves_from_several_pastures_counts_and_flags():
    from ranch_ai.rancher.herd import inventory

    logs = [
        {"client_id": "c1", "kind": "count", "pasture_id": "A", "counts": {"cows": 40, "calves": 38, "bulls": 2}, "logged_at": _at(1), "by": "Zach"},
        {"client_id": "c2", "kind": "count", "pasture_id": "B", "counts": {"heifers": 25}, "logged_at": _at(1)},
        # 2 cows from A and 3 heifers from B into X, in one move
        {"client_id": "m1", "kind": "move", "pasture_id": "X", "logged_at": _at(3),
         "lines": [{"from": "A", "counts": {"cows": 2}}, {"from": "B", "counts": {"heifers": 3}}]},
        {"client_id": "h1", "kind": "herd", "event": "born", "pasture_id": "X", "counts": {"calves": 2}, "logged_at": _at(4)},
        {"client_id": "h2", "kind": "herd", "event": "died", "pasture_id": "A", "counts": {"cows": 1}, "logged_at": _at(5)},
        # a stray found in X: from "not sure"
        {"client_id": "m2", "kind": "move", "pasture_id": "X", "logged_at": _at(6), "lines": [{"from": "unknown", "counts": {"steers": 1}}]},
        # more taken out of B than the ledger thinks is there: allowed, flagged
        {"client_id": "m3", "kind": "move", "pasture_id": "C", "logged_at": _at(7), "lines": [{"from": "B", "counts": {"heifers": 30}}]},
    ]
    inv = inventory(logs, today=datetime(2026, 10, 8, tzinfo=timezone.utc))
    P = inv["pastures"]
    assert P["A"]["counts"] == {"cows": 37, "calves": 38, "bulls": 2} and P["A"]["flags"] == []
    assert P["X"]["counts"] == {"cows": 2, "heifers": 3, "calves": 2, "steers": 1} and set(P["X"]["flags"]) == {"unknown_source", "not_counted"}
    assert P["B"]["total"] == 0 and "negative" in P["B"]["flags"]
    assert P["C"]["counts"] == {"heifers": 30}
    assert inv["head"] == 37 + 38 + 2 + 8 + 30

    # a count replaces what the ledger thought and says by how much it was off; the flags clear
    logs.append({"client_id": "c3", "kind": "count", "pasture_id": "B", "counts": {"heifers": 2}, "logged_at": _at(8)})
    logs.append({"client_id": "c4", "kind": "count", "pasture_id": "A", "counts": {"cows": 36, "calves": 38, "bulls": 2}, "logged_at": _at(8)})
    inv = inventory(logs, today=datetime(2026, 10, 9, tzinfo=timezone.utc))
    assert inv["pastures"]["B"]["flags"] == [] and inv["pastures"]["B"]["counts"] == {"heifers": 2}
    assert inv["count_diffs"]["c4"] == {"cows": -1}            # one cow unaccounted for since the last count
    # 40 days later A needs a recount
    assert "stale" in inventory(logs, today=datetime(2026, 11, 20, tzinfo=timezone.utc))["pastures"]["A"]["flags"]


def test_herd_ledger_move_all_weaning_and_order_of_offline_entries():
    from ranch_ai.rancher.herd import inventory

    logs = [
        # this count was logged in the field before the move, but reached the server after it (offline phone)
        {"client_id": "m1", "kind": "move", "pasture_id": "B", "logged_at": _at(5), "received_at": _at(5), "lines": [{"from": "A", "all": True, "counts": {"cows": 10}}]},
        {"client_id": "c1", "kind": "count", "pasture_id": "A", "counts": {"cows": 30, "calves": 28}, "logged_at": _at(2), "received_at": _at(6)},
        {"client_id": "w1", "kind": "herd", "event": "wean", "pasture_id": "B", "counts": {"heifers": 12, "steers": 14, "cows": 5}, "logged_at": _at(9)},
    ]
    P = inventory(logs)["pastures"]
    assert P["A"]["total"] == 0                                  # "All" moved what the ledger knew (30 + 28), not the 10 typed
    assert P["B"]["counts"] == {"cows": 30, "calves": 2, "heifers": 12, "steers": 14}


def test_herd_entries_are_checked_on_the_way_in(tmp_path):
    store = AppStore(tmp_path / "app.sqlite")
    ok = {"client_id": "m1", "kind": "move", "pasture_id": "X", "logged_at": _at(3), "lines": [{"from": "A", "counts": {"cows": "2", "goats": 4}}]}
    row, _ = store.add_log("ranch-a", ok)
    assert row["lines"] == [{"from": "A", "all": False, "counts": {"cows": 2}}]
    for bad in ({"lines": [{"from": "A", "counts": {}}]}, {"lines": [{"from": "X", "counts": {"cows": 1}}]}, {"lines": []},
                {"lines": [{"from": "A", "counts": {"cows": -1}}]}):
        with pytest.raises(ValueError):
            store.add_log("ranch-a", {"client_id": "bad", "kind": "move", "pasture_id": "X", **bad})
    with pytest.raises(ValueError):
        store.add_log("ranch-a", {"client_id": "bad", "kind": "herd", "event": "stolen", "pasture_id": "X", "counts": {"cows": 1}})
    store.add_log("ranch-a", {"client_id": "old", "kind": "move", "pasture_id": "X", "from_pasture_id": "A", "head": 30})   # older phones
    assert [l["client_id"] for l in store.herd_logs("ranch-a")] == ["m1", "old"] or len(store.herd_logs("ranch-a")) == 2


def test_rest_starts_only_when_a_counted_pasture_is_empty():
    now = datetime(2026, 10, 20, tzinfo=timezone.utc)
    logs = [
        {"kind": "count", "pasture_id": "A", "counts": {"cows": 40}, "logged_at": _at(1)},
        {"kind": "move", "pasture_id": "B", "logged_at": _at(10), "lines": [{"from": "A", "counts": {"cows": 2}}]},
    ]
    days = herd_days_by_pasture(logs, today=now)
    assert days["A"] == {"days_in": 18, "head": 38} and days["B"] == {"days_in": 9, "head": 2}
    logs.append({"kind": "move", "pasture_id": "B", "logged_at": _at(15), "lines": [{"from": "A", "all": True, "counts": {}}]})
    days = herd_days_by_pasture(logs, today=now)
    assert days["A"] == {"days_rested": 4} and days["B"]["head"] == 40


def test_herd_api_serves_the_ledger(client):
    owner = _login(client)
    client.post("/api/logs", headers=owner, json=[
        {"client_id": "c1", "kind": "count", "pasture_id": "P1", "counts": {"cows": 12}, "logged_at": _at(1)},
        {"client_id": "m1", "kind": "move", "pasture_id": "P2", "logged_at": _at(2), "lines": [{"from": "P1", "counts": {"cows": 5}}]}])
    inv = client.get("/api/herd", headers=owner).json()
    assert inv["pastures"]["P1"]["counts"] == {"cows": 7} and inv["pastures"]["P2"]["counts"] == {"cows": 5} and inv["head"] == 12
    client.delete("/api/logs/m1", headers=owner)                       # a deleted entry is out of the count straight away
    assert client.get("/api/herd", headers=owner).json()["pastures"]["P1"]["counts"] == {"cows": 12}
