"""Pasture status from OBSERVED inputs only: Good / Watch / Act, in plain words.

Nothing here uses the synthetic forage score. Each rule looks at one measured
signal, says what it saw in rancher language, and rates it ok / watch / concern.
Missing or demo inputs are reported as "not available", never guessed.

The thresholds are starting points chosen to be conservative and explainable,
not calibrated values. Adjust them to the ranch as observations accumulate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# --- thresholds (starting points; tune per ranch) ---------------------------
RAIN_90D_CONCERN_PCT = 50.0   # under half of normal over 90 days
RAIN_90D_WATCH_PCT = 75.0
GRASS_CONCERN_PCT = -20.0     # NDVI 20 % or more below normal for the month
GRASS_WATCH_PCT = -10.0
DROUGHT_CONCERN = {"D2", "D3", "D4"}
DROUGHT_WATCH = {"D0", "D1"}
REST_WATCH_DAYS_GRAZED = 45   # herd in the same pasture this long -> check it

GOOD, WATCH, ACT = "good", "watch", "act"


@dataclass
class Signal:
    key: str
    label: str           # short heading, e.g. "Rain"
    level: str           # ok | watch | concern | unavailable
    text: str            # plain-words finding, e.g. "62 % of normal over 90 days"
    source: str | None = None
    as_of: str | None = None


@dataclass
class PastureStatus:
    status: str                      # good | watch | act | unknown
    headline: str                    # one line for the Today list
    signals: list[Signal] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "headline": self.headline, "signals": [asdict(s) for s in self.signals]}


def _fmt_in(value: float) -> str:
    return f"{value:.1f} in" if value >= 0.95 else f"{value:.2f} in"


def rain_signal(rain_90d_in: float | None, normal_90d_in: float | None, rain_30d_in: float | None,
                *, source: str | None, as_of: str | None) -> Signal:
    if rain_90d_in is None or normal_90d_in is None or normal_90d_in <= 0:
        return Signal("rain", "Rain", "unavailable", "Rain history not available right now.", source, as_of)
    pct = 100.0 * rain_90d_in / normal_90d_in
    month = f" Last 30 days: {_fmt_in(rain_30d_in)}." if rain_30d_in is not None else ""
    text = f"{_fmt_in(rain_90d_in)} of rain in the last 90 days, {pct:.0f}% of normal.{month}"
    if pct < RAIN_90D_CONCERN_PCT:
        level = "concern"
    elif pct < RAIN_90D_WATCH_PCT:
        level = "watch"
    else:
        level = "ok"
    return Signal("rain", "Rain", level, text, source, as_of)


def grass_signal(ndvi_anomaly_pct: float | None, *, source: str | None, as_of: str | None) -> Signal:
    if ndvi_anomaly_pct is None:
        return Signal("grass", "Grass greenness", "unavailable", "Satellite greenness not available right now.", source, as_of)
    if ndvi_anomaly_pct <= GRASS_CONCERN_PCT:
        level, words = "concern", f"well below normal for this time of year ({ndvi_anomaly_pct:+.0f}%)"
    elif ndvi_anomaly_pct <= GRASS_WATCH_PCT:
        level, words = "watch", f"below normal for this time of year ({ndvi_anomaly_pct:+.0f}%)"
    elif ndvi_anomaly_pct >= 10:
        level, words = "ok", f"greener than normal for this time of year ({ndvi_anomaly_pct:+.0f}%)"
    else:
        level, words = "ok", f"about normal for this time of year ({ndvi_anomaly_pct:+.0f}%)"
    return Signal("grass", "Grass greenness", level, f"Greenness is {words}.", source, as_of)


def drought_signal(category: str | None, *, source: str | None, as_of: str | None) -> Signal:
    if not category:
        return Signal("drought", "Drought", "unavailable", "Drought Monitor not available right now.", source, as_of)
    category = str(category).upper()
    names = {"NONE": "No drought", "D0": "Abnormally dry (D0)", "D1": "Moderate drought (D1)", "D2": "Severe drought (D2)",
             "D3": "Extreme drought (D3)", "D4": "Exceptional drought (D4)"}
    text = f"{names.get(category, category)} in the county."
    level = "concern" if category in DROUGHT_CONCERN else "watch" if category in DROUGHT_WATCH else "ok"
    return Signal("drought", "Drought", level, text, source, as_of)


def range_trend_signal(perennial_trend: str | None, bare_ground_trend: str | None, *, source: str | None, as_of: str | None) -> Signal:
    if not perennial_trend and not bare_ground_trend:
        return Signal("trend", "Long-term range", "unavailable", "Long-term range data not available right now.", source, as_of)
    worries = []
    if (perennial_trend or "").lower() == "declining":
        worries.append("perennial grass cover is declining")
    if (bare_ground_trend or "").lower() == "increasing":
        worries.append("bare ground is increasing")
    if worries:
        return Signal("trend", "Long-term range", "watch", "Over recent years " + " and ".join(worries) + ".", source, as_of)
    return Signal("trend", "Long-term range", "ok", "Perennial grass and bare ground are holding steady over recent years.", source, as_of)


def occupancy_signal(days_in_pasture: int | None, days_rested: int | None) -> Signal | None:
    if days_in_pasture is not None:
        level = "watch" if days_in_pasture >= REST_WATCH_DAYS_GRAZED else "ok"
        return Signal("herd", "Herd", level, f"Cattle have been in this pasture {days_in_pasture} days.", "Your log", None)
    if days_rested is not None:
        return Signal("herd", "Herd", "ok", f"Rested {days_rested} days since cattle were last moved out.", "Your log", None)
    return None


def combine(signals: list[Signal]) -> PastureStatus:
    usable = [s for s in signals if s.level != "unavailable"]
    if not usable:
        return PastureStatus("unknown", "Not enough data yet to judge this pasture.", signals)
    concerns = [s for s in usable if s.level == "concern"]
    watches = [s for s in usable if s.level == "watch"]
    if len(concerns) >= 2:
        status = ACT
    elif concerns or len(watches) >= 2:
        status = WATCH if not (concerns and watches) else ACT
    elif watches:
        status = WATCH
    else:
        status = GOOD
    lead = (concerns or watches or usable)[0]
    headlines = {
        ACT: f"Act: {lead.text}",
        WATCH: f"Watch: {lead.text}",
        GOOD: "Looks good. " + (lead.text if lead.key in {"grass", "rain"} else "No warning signs in the data."),
    }
    return PastureStatus(status, headlines[status], signals)
