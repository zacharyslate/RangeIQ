"""Spanish for the phone app: every English string the app shows has a Spanish entry in web/app/es.js, and the text
the server writes (pasture status, fire, alerts, SOS lines, errors) is matched by an exact entry or a pattern.

tx() below is a copy of tx() in web/app/i18n.js, so the server's own sentences are checked here, next to the code
that writes them."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "web" / "app"


def load_es() -> dict:
    text = (APP / "es.js").read_text(encoding="utf-8")
    body = text[text.index("window.RANGEIQ_ES = ") + len("window.RANGEIQ_ES = "):].strip()
    return json.loads(body.rstrip(";"))


ES = load_es()
NORM = lambda s: " ".join(str(s).split())  # noqa: E731
DICT = {NORM(k): v for k, v in ES["t"].items()}
LOWER = {k.lower(): v for k, v in DICT.items()}
PATS = [(re.compile(p["re"]), p["es"], p.get("g", "")) for p in ES["patterns"]]


def tx(text: str, group: str = "", missing: list | None = None) -> str:
    """Same as tx() in web/app/i18n.js."""
    k = NORM(text)
    if not re.search(r"[A-Za-z]", k):
        return text
    if group:
        gk = group + ":" + k
        if gk in DICT:
            return DICT[gk]
        if gk.lower() in LOWER:
            return LOWER[gk.lower()]
    if k in DICT:
        return DICT[k]
    if k.lower() in LOWER:
        v = LOWER[k.lower()]
        return v[0].lower() + v[1:] if re.match(r"^[a-z]", k) else v
    for rx, es, g in PATS:
        if g != group:
            continue
        m = rx.match(k)
        if m:
            def sub(mm, m=m):
                g_ = m.group(int(mm.group(2))) or ""
                return tx(g_, group, missing) if mm.group(1) else g_
            return re.sub(r"\{(t?)(\d)\}", sub, es)
    if missing is not None:
        missing.append(k)
    return text


def translated(text: str, group: str = "") -> str:
    missing: list[str] = []
    out = tx(text, group, missing)
    assert not missing, f"no Spanish for {missing!r} (from {text!r})"
    return out


# --- the dictionary itself --------------------------------------------------------------------
def test_es_js_entries_keep_placeholders_and_markup():
    for k, v in ES["t"].items():
        assert v.strip(), k
        assert sorted(re.findall(r"\{(\w+)\}", k)) == sorted(re.findall(r"\{(\w+)\}", v)), k
        assert sorted(re.findall(r"</?\w+>", k)) == sorted(re.findall(r"</?\w+>", v)), k
    for p in ES["patterns"]:
        re.compile(p["re"])
        groups = re.compile(p["re"]).groups
        assert all(int(n) <= groups for n in re.findall(r"\{t?(\d)\}", p["es"])), p


def test_entries_that_differ_only_by_case_agree():
    """tx() matches server text ignoring case, so "today" and "Today" must say the same thing."""
    seen: dict[str, str] = {}
    for k, v in ES["t"].items():
        low = NORM(k).lower()
        assert low not in seen or seen[low].lower() == v.lower(), (k, v, seen.get(low))
        seen[low] = v


def _t_keys(source: str) -> set[str]:
    """String literals in the first argument of every T( ... ) call (handles T(n === 1 ? "a" : "b", {...}))."""
    keys = set()
    for m in re.finditer(r"(?<![\w$.])T\(", source):
        i, depth, cur, arg_done = m.end(), 1, "", False
        while i < len(source) and depth:
            c = source[i]
            if c in "\"'`":
                q, j = c, i + 1
                while source[j] != q:
                    j += 2 if source[j] == "\\" else 1
                lit = source[i + 1:j]
                if not arg_done and q != "`":
                    keys.add(json.loads('"' + lit.replace('"', '\\"').replace("\\'", "'") + '"') if q == "'" else json.loads(q + lit + q))
                i = j + 1
                continue
            if c in "([{":
                depth += 1
            elif c in ")]}":
                depth -= 1
            elif c == "," and depth == 1:
                arg_done = True
            i += 1
    return keys


@pytest.mark.parametrize("name", ["app.js", "terrain3d.js"])
def test_every_app_string_has_spanish(name):
    keys = _t_keys((APP / name).read_text(encoding="utf-8"))
    assert len(keys) > (300 if name == "app.js" else 0)
    missing = sorted(k for k in keys if NORM(k) not in DICT)
    assert not missing, missing


def test_report_tags_and_groups_have_spanish():
    from ranch_ai.rancher.status import TAG_LEVELS

    app = (APP / "app.js").read_text(encoding="utf-8")
    groups = re.findall(r'"group": "([^"]+)"', app)
    for word in [*TAG_LEVELS, *groups, "Good", "Watch", "Act"]:
        assert NORM(word) in DICT, word
    for k in ["Check waters", "Fix fence", "Check cattle", "Put out mineral / salt", "Check windmill", "Grade road", "Spray weeds"]:
        assert k in DICT, k


def test_index_html_fixed_words_have_spanish():
    html = (APP / "index.html").read_text(encoding="utf-8")
    body = html[html.index("<body>"):]
    keys: list[str] = []

    class Walk(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.skip, self.whole, self.buf = 0, 0, []

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag in ("script", "style"):
                self.skip += 1
            if self.whole:
                self.whole += 1
                self.buf.append(self.get_starttag_text())
            elif "data-i18n" in a:
                self.whole, self.buf = 1, []
            for k in ("aria-label", "placeholder", "title", "alt"):
                if a.get(k) and re.search(r"[A-Za-z]{2}", a[k]):
                    keys.append(a[k])

        def handle_endtag(self, tag):
            if tag in ("script", "style"):
                self.skip -= 1
            if self.whole:
                self.whole -= 1
                if self.whole:
                    self.buf.append(f"</{tag}>")
                else:
                    keys.append("".join(self.buf).replace("&", "&amp;"))

        def handle_data(self, d):
            if self.skip:
                return
            if self.whole:
                self.buf.append(d)
            elif re.search(r"[A-Za-z]{2}", d):
                keys.append(d)

    Walk().feed(body)
    missing = sorted({NORM(k) for k in keys} - set(DICT))
    assert not missing, missing


# --- what the server writes ---------------------------------------------------------------------
def test_pasture_status_sentences_translate():
    from ranch_ai.rancher import status as st

    samples = [
        st.rain_signal(2.3, 8.1, 1.2, source="PRISM", as_of="2026-10-21"), st.rain_signal(0.45, 8.1, None, source=None, as_of=None),
        st.rain_signal(None, None, None, source=None, as_of=None), st.rain_signal(9.2, 8.0, 0.1, source=None, as_of=None),
        *(st.grass_signal(v, source=None, as_of=None) for v in (-25, -12, 15, 3, None)),
        *(st.drought_signal(c, source=None, as_of=None) for c in ("NONE", "D0", "D1", "D2", "D3", "D4", None)),
        st.range_trend_signal("declining", "increasing", source=None, as_of=None), st.range_trend_signal("declining", None, source=None, as_of=None),
        st.range_trend_signal(None, "increasing", source=None, as_of=None), st.range_trend_signal("stable", "stable", source=None, as_of=None),
        st.range_trend_signal(None, None, source=None, as_of=None),
        st.occupancy_signal(12, None), st.occupancy_signal(None, 40),
        st.field_report_signal([{"tags": ["Fence down"], "by": "Juan", "logged_at": "2026-10-20T10:00:00Z"}],
                               today=st.datetime(2026, 10, 21, tzinfo=st.timezone.utc)),
        st.field_report_signal([{"tags": ["Water low"], "logged_at": "2026-10-20T10:00:00Z"}], today=st.datetime(2026, 10, 21, tzinfo=st.timezone.utc)),
        st.field_report_signal([{"tags": ["Good grass"], "logged_at": "2026-10-20T10:00:00Z"}], today=st.datetime(2026, 10, 21, tzinfo=st.timezone.utc)),
    ]
    for sig in samples:
        out = translated(sig.text)
        assert out != sig.text, sig.text
        translated(sig.label)
        if sig.source in ("Your log", "Your crew"):
            translated(sig.source)
    combos = [samples[1:2], samples[4:6], samples[0:1], [], samples[-3:-2], samples[7:8] + samples[5:6]]
    for sigs in combos:
        head = st.combine(sigs).headline
        assert translated(head) != head
    assert translated("Act: Fence down reported by Juan.") == "Actuar: Cerca caída, reportado por Juan."
    assert translated("Recent report: good grass.") == "Reporte reciente: buen pasto."
    assert translated("2.3 in of rain in the last 90 days, 28% of normal. Last 30 days: 1.2 in.").startswith("2.3 pulg de lluvia")


def test_fire_and_alert_wording_translates():
    from ranch_ai.rancher.snapshot import PROVIDER_NAMES  # noqa: F401  (provider names are proper names, shown as is)
    from ranch_ai.services.alert_service import interpret_alert
    from ranch_ai.services.fire_risk_service import assess_fire_risk

    for event in ["Red Flag Warning", "Fire Weather Watch", "Heat Advisory", "Excessive Heat Warning", "Severe Thunderstorm Warning",
                  "High Wind Warning", "Wind Advisory", "Flash Flood Warning", "Flood Watch", "Freeze Warning", "Winter Storm Warning",
                  "Tornado Watch", "Tornado Warning", "Special Weather Statement"]:
        translated(event)
        translated(interpret_alert({"event": event}))
    for level in ["LOW", "MODERATE", "HIGH", "VERY HIGH", "EXTREME"]:
        translated(level)
    import pandas as pd

    from ranch_ai.config import Settings

    alerts = pd.DataFrame([{"event": "Red Flag Warning", "is_fire_weather": True, "severity": "Severe"}])
    result = assess_fire_risk(current_weather={"temperature_f": 101, "humidity_pct": 8, "wind_speed_mph": 30, "wind_gust_mph": 45},
                              alerts_df=alerts, latest_snapshot=pd.DataFrame(), sensor_status_df=pd.DataFrame(), app_settings=Settings())
    for text in [*result.main_drivers, *result.recommended_actions]:
        if "sensor" in text.lower():
            continue                                  # dropped by the snapshot before it reaches the app
        translated(text)


def test_snapshot_sources_and_messages_translate():
    for name in ["Weather forecast", "Weather alerts", "Rain history", "U.S. Drought Monitor", "Satellite greenness (Sentinel-2)",
                 "Rangeland Analysis Platform", "USGS 3DEP lidar elevation"]:
        translated(name)
    src = Path(__file__).resolve().parents[1] / "src" / "ranch_ai" / "rancher"
    for msg in re.findall(r'"message": "([^"]+)"', (src / "worker.py").read_text() + (src / "api.py").read_text()):
        translated(msg)


def test_weather_words_translate():
    for label in ["Sunny", "Mostly Sunny", "Partly Cloudy", "Chance Showers And Thunderstorms", "Slight Chance Rain Showers then Mostly Sunny",
                  "Showers And Thunderstorms Likely", "Isolated Showers And Thunderstorms", "Patchy Fog", "Areas Of Blowing Dust",
                  "Mostly Cloudy and Breezy", "Light Rain", "Rain Showers", "Overcast", "Fair", "Thunderstorm", "Storm Hail"]:
        out = translated(label, "wx")
        assert not re.search(r"\b(Chance|Showers|Thunderstorms|Sunny|Cloudy|then|And)\b", out), (label, out)
    from ranch_ai.data.weather import WMO_WEATHER_CODES

    for label in WMO_WEATHER_CODES.values():
        translated(label, "wx")


def test_sos_chat_lines_and_server_errors_translate():
    assert translated("🆘 SOS: Injury · Fell by the tank. Where: 30.12345, -103.54321 (±6 m)") == \
        "🆘 SOS: Herida · Fell by the tank. Dónde: 30.12345, -103.54321 (±6 m)"
    assert translated("🆘 SOS: Fire. Where: location not known yet") == "🆘 SOS: Incendio. Dónde: todavía no se sabe la ubicación"
    assert translated("🚙 On my way to Ana.") == "🚙 Voy en camino con Ana."
    assert translated("✅ SOS over: I’m OK · all good") == "✅ SOS terminado: estoy bien · all good"
    assert translated("✅ SOS over: Ana is OK") == "✅ SOS terminado: Ana está bien"
    src = Path(__file__).resolve().parents[1] / "src" / "ranch_ai" / "rancher"
    text = (src / "api.py").read_text() + (src / "store.py").read_text() + (src / "setup.py").read_text()
    shown = re.findall(r'(?:detail|PermissionError\(|ValueError\()="?([A-Z][^"{]+[.?)])"', text)
    shown += re.findall(r'(?:PermissionError|ValueError)\("([A-Z][^"{]+[.?)])"\)', text)
    technical = {"Bad photo details.", "Bad receipt.", "Receipt expired.", "Bad subscription.", "Points must be [longitude, latitude] pairs."}
    for msg in sorted(set(shown) - technical):
        if msg.startswith(("Send a list", "Send at most")):
            continue                                      # only a broken or very old phone sends that much
        translated(msg)
