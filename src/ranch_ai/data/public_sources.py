from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np
import pandas as pd
import requests

from ranch_ai.data.weather import celsius_to_fahrenheit, mm_to_inches, ms_to_mph


NASA_POWER_CITATION_URL = "https://power.larc.nasa.gov/docs/services/api/"
USDA_SDA_CITATION_URL = "https://sdmdataaccess.nrcs.usda.gov/"
USDM_CITATION_URL = "https://www.drought.gov/data-maps-tools/us-drought-monitor"
CENSUS_GEOCODER_CITATION_URL = "https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.html"
VEGETATION_CITATION_URL = "synthetic vegetation history"


def _normalize_start_end(start_date: str | pd.Timestamp, end_date: str | pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    if end < start:
        raise ValueError("end_date must be on or after start_date")
    return start, end


def _week_starts_between(start_date: str | pd.Timestamp, end_date: str | pd.Timestamp) -> pd.DatetimeIndex:
    start, end = _normalize_start_end(start_date, end_date)
    first_week = start - pd.to_timedelta(start.weekday(), unit="D")
    last_week = end - pd.to_timedelta(end.weekday(), unit="D")
    return pd.date_range(start=first_week, end=last_week, freq="W-MON")


def _month_starts_between(start_date: str | pd.Timestamp, end_date: str | pd.Timestamp) -> pd.DatetimeIndex:
    start, end = _normalize_start_end(start_date, end_date)
    return pd.date_range(start=start.to_period("M").to_timestamp(), end=end.to_period("M").to_timestamp(), freq="MS")


def _clean_power_value(value: Any) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if numeric <= -900:
        return None
    return numeric


def _format_usdm_date(value: str | pd.Timestamp) -> str:
    timestamp = pd.Timestamp(value)
    return f"{timestamp.month}/{timestamp.day}/{timestamp.year}"


def _pick_first(payload: dict[str, Any], keys: list[str]) -> Any:
    lowered = {str(key).lower(): value for key, value in payload.items()}
    for key in keys:
        if key.lower() in lowered:
            return lowered[key.lower()]
    return None


def _extract_record_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        if all(not isinstance(value, (dict, list)) for value in payload.values()):
            return [payload]
        for value in payload.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value
    raise ValueError("Unexpected service payload format.")


def _parse_sda_json_table(payload: Any) -> pd.DataFrame:
    table = payload.get("Table") if isinstance(payload, dict) else None
    if not table or not isinstance(table, list):
        return pd.DataFrame()

    if table and isinstance(table[0], list):
        headers = [str(value) for value in table[0]]
        rows = table[1:]
        return pd.DataFrame(rows, columns=headers)

    return pd.DataFrame(table)


def _resolve_county_from_census(lat: float, lon: float, timeout_seconds: int) -> tuple[str, str]:
    response = requests.get(
        "https://geocoding.geo.census.gov/geocoder/geographies/coordinates",
        params={
            "x": lon,
            "y": lat,
            "benchmark": "Public_AR_Current",
            "vintage": "Current_Current",
            "format": "json",
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    counties = payload.get("result", {}).get("geographies", {}).get("Counties", [])
    if not counties:
        raise ValueError("Census geocoder returned no county for this location.")

    county = counties[0]
    geoid = str(county.get("GEOID") or county.get("COUNTY") or "").strip()
    name = str(county.get("NAME") or county.get("BASENAME") or geoid).strip()
    if not geoid:
        raise ValueError("Census geocoder did not return a county GEOID.")
    return geoid, name


class HistoricalWeatherProvider(ABC):
    provider_name = "base"
    citation_url = NASA_POWER_CITATION_URL

    @abstractmethod
    def get_daily_history(
        self,
        lat: float,
        lon: float,
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
    ) -> pd.DataFrame:
        raise NotImplementedError


class SoilProfileProvider(ABC):
    provider_name = "base"
    citation_url = USDA_SDA_CITATION_URL

    @abstractmethod
    def get_pasture_soils(self, pastures: pd.DataFrame) -> pd.DataFrame:
        raise NotImplementedError


class DroughtHistoryProvider(ABC):
    provider_name = "base"
    citation_url = USDM_CITATION_URL

    @abstractmethod
    def get_weekly_drought(
        self,
        lat: float,
        lon: float,
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
    ) -> pd.DataFrame:
        raise NotImplementedError


class VegetationHistoryProvider(ABC):
    provider_name = "base"
    citation_url = VEGETATION_CITATION_URL

    @abstractmethod
    def get_monthly_vegetation(
        self,
        pastures: pd.DataFrame,
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
    ) -> pd.DataFrame:
        raise NotImplementedError


class MockHistoricalWeatherProvider(HistoricalWeatherProvider):
    provider_name = "mock"

    def __init__(self, seed: int = 42):
        self.seed = seed

    def get_daily_history(
        self,
        lat: float,
        lon: float,
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
    ) -> pd.DataFrame:
        start, end = _normalize_start_end(start_date, end_date)
        index = pd.date_range(start=start, end=end, freq="D")
        rng_seed = int(abs(lat * 1000) + abs(lon * 1000) + self.seed)
        rng = np.random.default_rng(rng_seed)
        rows: list[dict[str, object]] = []

        for timestamp in index:
            day_of_year = timestamp.dayofyear
            seasonal_temp = 72 + 18 * np.sin(((day_of_year - 110) / 365) * 2 * np.pi)
            seasonal_rain = 0.05 + max(0, np.sin(((day_of_year - 60) / 365) * 2 * np.pi)) * 0.12
            humidity = np.clip(48 + rng.normal(0, 8) - max(0, seasonal_temp - 90) * 0.4, 12, 95)
            wind = np.clip(9 + rng.normal(0, 2.2) + max(0, seasonal_temp - 85) * 0.07, 2, 28)
            precip = max(0.0, seasonal_rain + rng.gamma(1.1, 0.04) - 0.03)
            temp_mean = seasonal_temp + rng.normal(0, 4)
            temp_max = temp_mean + rng.uniform(8, 18)
            temp_min = temp_mean - rng.uniform(8, 18)

            rows.append(
                {
                    "date": timestamp,
                    "public_temp_mean_f": round(float(temp_mean), 1),
                    "public_temp_max_f": round(float(temp_max), 1),
                    "public_temp_min_f": round(float(temp_min), 1),
                    "public_precip_in": round(float(precip), 3),
                    "public_humidity_pct": round(float(humidity), 1),
                    "public_wind_speed_mph": round(float(wind), 1),
                    "source": "Mock historical weather",
                }
            )

        return pd.DataFrame(rows)


class NasaPowerHistoricalWeatherProvider(HistoricalWeatherProvider):
    provider_name = "nasa_power"

    def __init__(self, timeout_seconds: int = 20):
        self.timeout_seconds = timeout_seconds

    def get_daily_history(
        self,
        lat: float,
        lon: float,
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
    ) -> pd.DataFrame:
        start, end = _normalize_start_end(start_date, end_date)
        response = requests.get(
            "https://power.larc.nasa.gov/api/temporal/daily/point",
            params={
                "parameters": "T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,RH2M,WS2M",
                "community": "AG",
                "latitude": lat,
                "longitude": lon,
                "start": start.strftime("%Y%m%d"),
                "end": end.strftime("%Y%m%d"),
                "format": "JSON",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        parameters = payload.get("properties", {}).get("parameter", {})
        if not parameters:
            raise ValueError("NASA POWER returned no parameter payload.")

        rows: list[dict[str, object]] = []
        for raw_date, temp_mean in parameters.get("T2M", {}).items():
            date = pd.to_datetime(raw_date, format="%Y%m%d")
            temp_mean_f = celsius_to_fahrenheit(_clean_power_value(temp_mean))
            temp_max_f = celsius_to_fahrenheit(_clean_power_value(parameters.get("T2M_MAX", {}).get(raw_date)))
            temp_min_f = celsius_to_fahrenheit(_clean_power_value(parameters.get("T2M_MIN", {}).get(raw_date)))
            precip_in = mm_to_inches(_clean_power_value(parameters.get("PRECTOTCORR", {}).get(raw_date)))
            humidity_pct = _clean_power_value(parameters.get("RH2M", {}).get(raw_date))
            wind_speed_mph = ms_to_mph(_clean_power_value(parameters.get("WS2M", {}).get(raw_date)))
            rows.append(
                {
                    "date": date,
                    "public_temp_mean_f": round(temp_mean_f, 1) if temp_mean_f is not None else np.nan,
                    "public_temp_max_f": round(temp_max_f, 1) if temp_max_f is not None else np.nan,
                    "public_temp_min_f": round(temp_min_f, 1) if temp_min_f is not None else np.nan,
                    "public_precip_in": round(precip_in, 3) if precip_in is not None else np.nan,
                    "public_humidity_pct": humidity_pct,
                    "public_wind_speed_mph": round(wind_speed_mph, 1) if wind_speed_mph is not None else np.nan,
                    "source": "NASA POWER Daily API",
                }
            )

        frame = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
        if frame.empty:
            raise ValueError("NASA POWER returned an empty daily history.")
        return frame


class MockSoilProfileProvider(SoilProfileProvider):
    provider_name = "mock"

    def __init__(self, seed: int = 42):
        self.seed = seed

    def get_pasture_soils(self, pastures: pd.DataFrame) -> pd.DataFrame:
        rng = np.random.default_rng(self.seed + 211)
        rows: list[dict[str, object]] = []
        drainage_classes = ["Well drained", "Moderately well drained", "Somewhat excessively drained"]
        soil_types = ["Sandy loam", "Clay loam", "Gravelly loam", "Loam"]

        for pasture in pastures.itertuples(index=False):
            rows.append(
                {
                    "pasture_id": pasture.pasture_id,
                    "public_soil_type": soil_types[rng.integers(0, len(soil_types))],
                    "public_available_water_capacity_in": round(float(rng.uniform(4.2, 9.8)), 2),
                    "public_range_prod_index": round(float(rng.uniform(42, 86)), 1),
                    "public_soil_drainage_class": drainage_classes[rng.integers(0, len(drainage_classes))],
                    "source": "Mock soil profile",
                }
            )

        return pd.DataFrame(rows)


class USDASoilDataAccessProvider(SoilProfileProvider):
    provider_name = "usda_sda"

    def __init__(self, timeout_seconds: int = 20):
        self.timeout_seconds = timeout_seconds

    def get_pasture_soils(self, pastures: pd.DataFrame) -> pd.DataFrame:
        rows: list[dict[str, object]] = []

        for pasture in pastures.itertuples(index=False):
            lat = float(getattr(pasture, "centroid_lat"))
            lon = float(getattr(pasture, "centroid_lon"))
            query = f"""
SELECT TOP 1
    mu.mukey,
    mu.muname,
    co.compname,
    co.drainagecl,
    muagg.aws0100wta
FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('point({lon} {lat})') AS s
INNER JOIN mapunit AS mu ON mu.mukey = s.mukey
LEFT JOIN muaggatt AS muagg ON muagg.mukey = mu.mukey
LEFT JOIN component AS co ON co.mukey = mu.mukey
WHERE co.comppct_r = (
    SELECT MAX(c2.comppct_r)
    FROM component AS c2
    WHERE c2.mukey = mu.mukey
)
ORDER BY co.comppct_r DESC, mu.mukey
""".strip()

            response = requests.post(
                "https://sdmdataaccess.nrcs.usda.gov/Tabular/post.rest",
                data={"query": query, "format": "JSON+COLUMNNAME"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            table = _parse_sda_json_table(response.json())
            if table.empty:
                raise ValueError(f"USDA Soil Data Access returned no rows for pasture {pasture.pasture_id}.")

            record = table.iloc[0].to_dict()
            awc_cm = pd.to_numeric(record.get("aws0100wta"), errors="coerce")
            rows.append(
                {
                    "pasture_id": pasture.pasture_id,
                    "public_soil_type": record.get("compname") or record.get("muname"),
                    "public_available_water_capacity_in": round(float(awc_cm) / 2.54, 2) if pd.notna(awc_cm) else None,
                    "public_range_prod_index": None,
                    "public_soil_drainage_class": record.get("drainagecl"),
                    "source": "USDA Soil Data Access",
                }
            )

        return pd.DataFrame(rows)


class MockDroughtHistoryProvider(DroughtHistoryProvider):
    provider_name = "mock"

    def __init__(self, seed: int = 42):
        self.seed = seed

    def get_weekly_drought(
        self,
        lat: float,
        lon: float,
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
    ) -> pd.DataFrame:
        week_index = _week_starts_between(start_date, end_date)
        rng_seed = int(abs(lat * 100) + abs(lon * 100) + self.seed + 401)
        rng = np.random.default_rng(rng_seed)
        categories = ["None", "D0", "D1", "D2", "D3"]
        weights = np.array([0.22, 0.26, 0.24, 0.18, 0.10], dtype=float)
        rows = []

        for week_start in week_index:
            category = str(rng.choice(categories, p=weights))
            category_score = {"None": 0, "D0": 1, "D1": 2, "D2": 3, "D3": 4}.get(category, 0)
            drought_coverage_pct = 0.0 if category == "None" else round(float(rng.uniform(18, 96)), 2)
            max_intensity_pct = 0.0 if category == "None" else round(float(rng.uniform(8, drought_coverage_pct)), 2)
            rows.append(
                {
                    "week_start": pd.Timestamp(week_start),
                    "public_usdm_category": category,
                    "public_usdm_score": category_score,
                    "public_usdm_none_pct": round(100.0 - drought_coverage_pct, 2),
                    "public_usdm_drought_coverage_pct": drought_coverage_pct,
                    "public_usdm_max_intensity_pct": max_intensity_pct,
                    "public_usdm_county_fips": None,
                    "public_usdm_county_name": "Mock County",
                    "source": "Mock drought history",
                }
            )

        return pd.DataFrame(rows)


class USDroughtMonitorProvider(DroughtHistoryProvider):
    provider_name = "usdm"

    def __init__(self, timeout_seconds: int = 20):
        self.timeout_seconds = timeout_seconds

    def get_weekly_drought(
        self,
        lat: float,
        lon: float,
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
    ) -> pd.DataFrame:
        county_fips, county_name = _resolve_county_from_census(lat, lon, timeout_seconds=self.timeout_seconds)
        response = requests.get(
            "https://usdmdataservices.unl.edu/api/CountyStatistics/GetDroughtSeverityStatisticsByAreaPercent",
            params={
                "aoi": county_fips,
                "startdate": _format_usdm_date(start_date),
                "enddate": _format_usdm_date(end_date),
                "statisticsType": 2,
            },
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        records = _extract_record_list(response.json())
        rows: list[dict[str, object]] = []

        for record in records:
            raw_date = _pick_first(record, ["MapDate", "Date", "ValidDate", "Releasedate", "ReleaseDate"])
            if raw_date is None:
                continue

            none_pct = pd.to_numeric(_pick_first(record, ["None"]), errors="coerce")
            d0_pct = pd.to_numeric(_pick_first(record, ["D0"]), errors="coerce")
            d1_pct = pd.to_numeric(_pick_first(record, ["D1"]), errors="coerce")
            d2_pct = pd.to_numeric(_pick_first(record, ["D2"]), errors="coerce")
            d3_pct = pd.to_numeric(_pick_first(record, ["D3"]), errors="coerce")
            d4_pct = pd.to_numeric(_pick_first(record, ["D4"]), errors="coerce")

            category_values = {
                "D4": 0.0 if pd.isna(d4_pct) else float(d4_pct),
                "D3": 0.0 if pd.isna(d3_pct) else float(d3_pct),
                "D2": 0.0 if pd.isna(d2_pct) else float(d2_pct),
                "D1": 0.0 if pd.isna(d1_pct) else float(d1_pct),
                "D0": 0.0 if pd.isna(d0_pct) else float(d0_pct),
            }
            active_category = "None"
            for category, pct in category_values.items():
                if pct > 0:
                    active_category = category
                    break

            drought_coverage_pct = sum(category_values.values())
            max_intensity_pct = category_values.get(active_category, 0.0) if active_category != "None" else 0.0
            rows.append(
                {
                    "week_start": pd.Timestamp(raw_date) - pd.to_timedelta(pd.Timestamp(raw_date).weekday(), unit="D"),
                    "public_usdm_category": active_category,
                    "public_usdm_score": {"None": 0, "D0": 1, "D1": 2, "D2": 3, "D3": 4, "D4": 5}.get(active_category, 0),
                    "public_usdm_none_pct": 0.0 if pd.isna(none_pct) else float(none_pct),
                    "public_usdm_drought_coverage_pct": round(float(drought_coverage_pct), 2),
                    "public_usdm_max_intensity_pct": round(float(max_intensity_pct), 2),
                    "public_usdm_county_fips": county_fips,
                    "public_usdm_county_name": county_name,
                    "source": "U.S. Drought Monitor county statistics",
                }
            )

        frame = pd.DataFrame(rows).sort_values("week_start").drop_duplicates("week_start", keep="last").reset_index(drop=True)
        if frame.empty:
            raise ValueError("U.S. Drought Monitor returned no drought history rows.")
        return frame


class MockVegetationHistoryProvider(VegetationHistoryProvider):
    provider_name = "mock"
    citation_url = VEGETATION_CITATION_URL

    def __init__(self, seed: int = 42):
        self.seed = seed

    def get_monthly_vegetation(
        self,
        pastures: pd.DataFrame,
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
    ) -> pd.DataFrame:
        month_index = _month_starts_between(start_date, end_date)
        rng = np.random.default_rng(self.seed + 611)
        rows: list[dict[str, object]] = []

        for pasture_idx, pasture in enumerate(pastures.itertuples(index=False)):
            for month_start in month_index:
                seasonal = 0.34 + 0.12 * np.sin(((month_start.month - 3) / 12) * 2 * np.pi)
                ndvi_mean = np.clip(seasonal + rng.normal(0, 0.04) + pasture_idx * 0.01, 0.08, 0.84)
                ndvi_anomaly = np.clip(rng.normal(0, 0.05), -0.22, 0.22)
                fractional_cover = np.clip(ndvi_mean * 0.9 + rng.normal(0, 0.03), 0.05, 0.95)
                rows.append(
                    {
                        "pasture_id": pasture.pasture_id,
                        "month_start": pd.Timestamp(month_start),
                        "public_ndvi_mean": round(float(ndvi_mean), 3),
                        "public_ndvi_anomaly": round(float(ndvi_anomaly), 3),
                        "public_fractional_cover": round(float(fractional_cover), 3),
                        "source": "Mock vegetation history",
                    }
                )

        return pd.DataFrame(rows)
