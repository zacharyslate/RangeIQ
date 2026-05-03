from __future__ import annotations

import copy
from dataclasses import dataclass
import time
from typing import Any

import pandas as pd
import requests

from ranch_ai.vegetation.cache import _normalize_geojson_input


RAP_API_DOCS_URL = "https://rangelands.app/support/71-api-documentation"
RAP_COVER_URL = "https://us-central1-rap-data-365417.cloudfunctions.net/coverV3"
RAP_COVER_METEOROLOGY_URL = "https://us-central1-rap-data-365417.cloudfunctions.net/coverMeteorologyV3"
RAP_PRODUCTION_URL = "https://us-central1-rap-data-365417.cloudfunctions.net/productionV3"
RAP_PRODUCTION_16DAY_URL = "https://us-central1-rap-data-365417.cloudfunctions.net/production16dayV3"


def _build_frame_from_table(table: list[list[Any]], column_map: dict[str, str]) -> pd.DataFrame:
    if not isinstance(table, list) or len(table) < 2:
        return pd.DataFrame()

    headers = [str(value) for value in table[0]]
    rows = table[1:]
    frame = pd.DataFrame(rows, columns=headers)
    if frame.empty:
        return frame

    rename_map = {source: target for source, target in column_map.items() if source in frame.columns}
    frame = frame.rename(columns=rename_map)
    return frame


@dataclass
class RAPClient:
    timeout_seconds: int = 30
    retries: int = 2
    backoff_seconds: float = 0.5
    cover_url: str = RAP_COVER_URL
    cover_meteorology_url: str = RAP_COVER_METEOROLOGY_URL
    production_url: str = RAP_PRODUCTION_URL
    production_16day_url: str = RAP_PRODUCTION_16DAY_URL

    def __post_init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json", "Accept": "application/json"})

    def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self.session.post(url, json=payload, timeout=self.timeout_seconds)
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(self.backoff_seconds * (2**attempt))
        raise RuntimeError(f"RAP request failed for {url}: {last_exc}")

    @staticmethod
    def _build_payload(
        aoi_geojson: dict[str, Any],
        *,
        mask: bool = True,
        year: int | None = None,
    ) -> dict[str, Any]:
        feature = copy.deepcopy(_normalize_geojson_input(aoi_geojson))
        feature.setdefault("properties", {})
        feature["properties"]["mask"] = bool(mask)
        feature["properties"]["year"] = year
        return feature

    def get_cover_history(self, aoi_geojson: dict[str, Any], *, include_meteorology: bool = False) -> tuple[pd.DataFrame, dict[str, Any]]:
        payload = self._build_payload(aoi_geojson, mask=True, year=None)
        url = self.cover_meteorology_url if include_meteorology else self.cover_url
        response = self._post(url, payload)
        return self.parse_cover_response(response), response

    def get_cover_meteorology_history(self, aoi_geojson: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
        return self.get_cover_history(aoi_geojson, include_meteorology=True)

    def get_production_history(self, aoi_geojson: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
        payload = self._build_payload(aoi_geojson, mask=True, year=None)
        response = self._post(self.production_url, payload)
        return self.parse_production_response(response), response

    def get_production_16day_history(self, aoi_geojson: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
        payload = self._build_payload(aoi_geojson, mask=True, year=None)
        response = self._post(self.production_16day_url, payload)
        return self.parse_production_16day_response(response), response

    @staticmethod
    def parse_cover_response(payload: dict[str, Any]) -> pd.DataFrame:
        properties = payload.get("properties", {}) if isinstance(payload, dict) else {}
        frame = _build_frame_from_table(
            properties.get("cover", []),
            {
                "year": "year",
                "AFG": "rap_annual_grass_forb_cover_pct",
                "PFG": "rap_perennial_grass_forb_cover_pct",
                "SHR": "rap_shrub_cover_pct",
                "TRE": "rap_tree_cover_pct",
                "LTR": "rap_litter_cover_pct",
                "BGR": "rap_bare_ground_pct",
                "annualTemp": "rap_annual_temp_f",
                "AnnualTemp": "rap_annual_temp_f",
                "annualPrecip": "rap_annual_precip_in",
                "AnnualPrecip": "rap_annual_precip_in",
            },
        )
        if frame.empty:
            raise ValueError("RAP cover response did not include any cover rows.")

        frame["year"] = pd.to_numeric(frame["year"], errors="coerce").astype("Int64")
        for column in frame.columns:
            if column == "year":
                continue
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if "rap_total_vegetation_cover_pct" not in frame.columns:
            frame["rap_total_vegetation_cover_pct"] = frame[
                [
                    "rap_annual_grass_forb_cover_pct",
                    "rap_perennial_grass_forb_cover_pct",
                    "rap_shrub_cover_pct",
                    "rap_tree_cover_pct",
                    "rap_litter_cover_pct",
                ]
            ].sum(axis=1, min_count=1)
        frame["source"] = "Rangeland Analysis Platform coverV3"
        return frame.dropna(subset=["year"]).sort_values("year").reset_index(drop=True)

    @staticmethod
    def parse_production_response(payload: dict[str, Any]) -> pd.DataFrame:
        properties = payload.get("properties", {}) if isinstance(payload, dict) else {}
        frame = _build_frame_from_table(
            properties.get("production", []),
            {
                "year": "year",
                "AFG": "rap_annual_production_lb_ac",
                "PFG": "rap_perennial_production_lb_ac",
                "HER": "rap_total_herbaceous_production_lb_ac",
            },
        )
        if frame.empty:
            raise ValueError("RAP production response did not include any production rows.")

        frame["year"] = pd.to_numeric(frame["year"], errors="coerce").astype("Int64")
        for column in ["rap_annual_production_lb_ac", "rap_perennial_production_lb_ac", "rap_total_herbaceous_production_lb_ac"]:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame["source"] = "Rangeland Analysis Platform productionV3"
        return frame.dropna(subset=["year"]).sort_values("year").reset_index(drop=True)

    @staticmethod
    def parse_production_16day_response(payload: dict[str, Any]) -> pd.DataFrame:
        properties = payload.get("properties", {}) if isinstance(payload, dict) else {}
        frame = _build_frame_from_table(
            properties.get("production16day", []),
            {
                "date": "date",
                "year": "year",
                "doy": "doy",
                "AFG": "rap_annual_production_16day_lb_ac",
                "PFG": "rap_perennial_production_16day_lb_ac",
                "HER": "rap_total_herbaceous_16day_lb_ac",
            },
        )
        if frame.empty:
            raise ValueError("RAP 16-day production response did not include any rows.")

        frame["date"] = pd.to_datetime(frame["date"])
        frame["year"] = pd.to_numeric(frame["year"], errors="coerce").astype("Int64")
        frame["doy"] = pd.to_numeric(frame["doy"], errors="coerce").astype("Int64")
        for column in ["rap_annual_production_16day_lb_ac", "rap_perennial_production_16day_lb_ac", "rap_total_herbaceous_16day_lb_ac"]:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame["source"] = "Rangeland Analysis Platform production16dayV3"
        return frame.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
