from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pandas as pd


class RanchType(str, Enum):
    ROTATIONAL_CATTLE = "rotational cattle ranch"
    CONTINUOUS_CATTLE = "continuous grazing cattle ranch"
    HORSE_PROPERTY = "horse property"
    GOAT_OPERATION = "goat operation"
    SHEEP_OPERATION = "sheep operation"
    MIXED_LIVESTOCK = "mixed livestock ranch"
    HAY_FORAGE = "hay / forage fields"
    CONSERVATION = "conservation or restoration land"
    HOBBY = "small hobby ranch"
    COMMERCIAL = "large commercial ranch"
    LAND_MONITORING_ONLY = "land monitoring only"
    OTHER = "other"


class ManagementStyle(str, Enum):
    ROTATIONAL_GRAZING = "rotational grazing"
    CONTINUOUS_GRAZING = "continuous grazing"
    ADAPTIVE_GRAZING = "adaptive grazing"
    SEASONAL_GRAZING = "seasonal grazing"
    SET_STOCKING = "set stocking"
    HORSE_TURNOUT = "horse turnout"
    GOAT_SHEEP_BROWSING = "goat/sheep browsing"
    HAY_FORAGE_PRODUCTION = "hay/forage production"
    CONSERVATION_MONITORING = "conservation/restoration monitoring"
    LAND_MONITORING_ONLY = "land monitoring only"
    MIXED_USE = "mixed use"
    NOT_SURE = "not sure"


class RanchGoal(str, Enum):
    MONITOR_FORAGE = "monitor forage condition"
    MOVE_ANIMALS = "decide when to move animals"
    REDUCE_OVERGRAZING = "reduce overgrazing"
    MONITOR_DROUGHT = "monitor drought stress"
    MANAGE_HORSE_TURNOUT = "manage horse turnout"
    MANAGE_BROWSE = "manage goat/sheep browse"
    MONITOR_BARE_GROUND = "monitor bare ground"
    MONITOR_BRUSH = "monitor brush/shrub encroachment"
    MONITOR_WATER_RISK = "monitor water risk"
    MONITOR_FIRE_RISK = "monitor fire risk"
    TRACK_RESTORATION = "track restoration progress"
    GENERATE_REPORTS = "generate reports/maps"
    GENERAL_MONITORING = "general land monitoring"


class LivestockSpecies(str, Enum):
    CATTLE = "cattle"
    HORSES = "horses"
    GOATS = "goats"
    SHEEP = "sheep"
    MIXED = "mixed livestock"
    WILDLIFE = "wildlife/no livestock"
    OTHER = "other"


class ManagementUnitType(str, Enum):
    PASTURE = "pasture"
    PADDOCK = "paddock"
    HAY_FIELD = "hay field"
    HORSE_TURNOUT = "horse turnout"
    GOAT_BROWSE_ZONE = "goat browse zone"
    SHEEP_GRAZING_BLOCK = "sheep grazing block"
    RIPARIAN_AREA = "riparian area"
    CONSERVATION_ZONE = "conservation zone"
    RESTORATION_ZONE = "restoration zone"
    WINTER_LOT = "winter lot"
    DRY_LOT = "dry lot"
    LEASED_LAND = "leased land"
    EXCLUSION_REST_AREA = "exclusion/rest area"
    OTHER = "other"


class UnitActivityType(str, Enum):
    GRAZING = "grazing / occupancy"
    BROWSING = "targeted browsing"
    TURNOUT = "horse turnout"
    REST = "rest / recovery"
    HAYING = "haying / harvest"
    MONITORING = "monitoring / scouting"
    RESTORATION = "restoration work"
    WATER_INFRASTRUCTURE = "water / infrastructure work"
    FIRE_READINESS = "fire readiness"
    OTHER = "other"


UNIT_TERM_OPTIONS = [
    "management unit",
    "pasture",
    "paddock",
    "field",
    "turnout",
    "block",
]

RANCH_TYPE_OPTIONS = [item.value for item in RanchType]
MANAGEMENT_STYLE_OPTIONS = [item.value for item in ManagementStyle]
RANCH_GOAL_OPTIONS = [item.value for item in RanchGoal]
LIVESTOCK_SPECIES_OPTIONS = [item.value for item in LivestockSpecies]
MANAGEMENT_UNIT_TYPE_OPTIONS = [item.value for item in ManagementUnitType]
UNIT_ACTIVITY_TYPE_OPTIONS = [item.value for item in UnitActivityType]


@dataclass
class RanchProfile:
    ranch_type: str = RanchType.MIXED_LIVESTOCK.value
    management_style: str = ManagementStyle.NOT_SURE.value
    primary_goals: list[str] = field(default_factory=lambda: [RanchGoal.GENERAL_MONITORING.value])
    rotates_animals: bool = False
    preferred_unit_term: str = "management unit"
    default_unit_type: str = ManagementUnitType.PASTURE.value
    livestock_species: list[str] = field(default_factory=lambda: [LivestockSpecies.CATTLE.value])
    notes: str = ""


@dataclass
class LivestockGroup:
    group_id: str
    group_name: str
    species: str
    animal_count: int | None = None
    class_type: str = ""
    average_weight: float | None = None
    assigned_unit_id: str | None = None
    notes: str = ""


@dataclass
class UnitActivityEvent:
    event_id: str
    unit_id: str
    activity_type: str
    livestock_group_id: str | None = None
    start_date: str = ""
    end_date: str | None = None
    notes: str = ""


@dataclass
class UnitConditionSummary:
    forage_condition_score: float
    vegetation_anomaly_percent: float | None
    vegetation_status: str
    drought_category: str
    grazing_pressure: float
    water_risk_score: float
    attention_score: float
    attention_level: str
    recommendation_code: str
    recommendation_label: str
    recommendation_summary: str


@dataclass
class ManagementUnit:
    unit_id: str
    name: str
    unit_type: str
    acres: float
    centroid_lat: float
    centroid_lon: float
    geometry: list[list[float]]
    assigned_group_ids: list[str] = field(default_factory=list)
    assigned_livestock: list[str] = field(default_factory=list)
    notes: str = ""
    condition: UnitConditionSummary | None = None


@dataclass
class ManagementUnitOverride:
    unit_id: str
    display_name: str = ""
    unit_type: str = ManagementUnitType.PASTURE.value
    assigned_group_ids: list[str] = field(default_factory=list)
    assigned_livestock: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class UnitActivitySummary:
    unit_id: str
    status_label: str = "No Activity"
    current_activity: str = "No activity logged"
    current_group_label: str = ""
    current_window: str = ""
    recent_activity: str = "No activity logged"
    recent_group_label: str = ""
    recent_window: str = ""
    active_event_count: int = 0


@dataclass
class LivestockGroupLoadSummary:
    group_id: str
    group_name: str
    species: str
    current_unit_name: str = "Unassigned"
    current_activity: str = "No activity logged"
    current_window: str = ""
    recent_activity: str = "No activity logged"
    recent_window: str = ""
    occupied_units_30: int = 0
    occupancy_days_30: int = 0
    animal_unit_days_30: float = 0.0
    active_head_count: int = 0


@dataclass
class UnitUtilizationSummary:
    unit_id: str
    active_group_labels: list[str] = field(default_factory=list)
    active_head_count: int = 0
    occupancy_days_30: int = 0
    animal_unit_days_30: float = 0.0
    utilization_per_acre_30: float = 0.0
    utilization_label: str = "Resting"
    rest_days_since_occupancy: int | None = None


@dataclass
class OperationPlannerSuggestion:
    unit_id: str
    unit_name: str
    unit_type: str
    suggested_activity_type: str
    suggested_group_id: str | None = None
    suggested_group_label: str = ""
    start_date: str = ""
    end_date: str | None = None
    urgency: str = "Watch"
    rationale: str = ""


def unit_term(profile: RanchProfile, *, plural: bool = False, title: bool = False) -> str:
    singular = str(profile.preferred_unit_term or "management unit").strip().lower() or "management unit"
    label = singular
    if plural:
        if singular == "pasture":
            label = "pastures"
        elif singular == "paddock":
            label = "paddocks"
        elif singular == "field":
            label = "fields"
        elif singular == "turnout":
            label = "turnouts"
        elif singular == "block":
            label = "blocks"
        else:
            label = "management units"
    if title:
        return label.title()
    return label


def default_unit_type_for_profile(profile: RanchProfile) -> str:
    ranch_type = str(profile.ranch_type or "")
    style = str(profile.management_style or "")
    if ranch_type == RanchType.HORSE_PROPERTY.value or style == ManagementStyle.HORSE_TURNOUT.value:
        return ManagementUnitType.HORSE_TURNOUT.value
    if ranch_type == RanchType.GOAT_OPERATION.value:
        return ManagementUnitType.GOAT_BROWSE_ZONE.value
    if ranch_type == RanchType.SHEEP_OPERATION.value:
        return ManagementUnitType.SHEEP_GRAZING_BLOCK.value
    if ranch_type == RanchType.HAY_FORAGE.value or style == ManagementStyle.HAY_FORAGE_PRODUCTION.value:
        return ManagementUnitType.HAY_FIELD.value
    if ranch_type == RanchType.CONSERVATION.value or style in {
        ManagementStyle.CONSERVATION_MONITORING.value,
        ManagementStyle.LAND_MONITORING_ONLY.value,
    }:
        return ManagementUnitType.CONSERVATION_ZONE.value
    return str(profile.default_unit_type or ManagementUnitType.PASTURE.value)


def primary_livestock_group(profile: RanchProfile) -> LivestockGroup | None:
    species_values = [value for value in profile.livestock_species if value and value != LivestockSpecies.WILDLIFE.value]
    if not species_values:
        return None
    species_label = species_values[0] if len(species_values) == 1 else LivestockSpecies.MIXED.value
    return LivestockGroup(
        group_id="primary-group",
        group_name="Primary Livestock Group",
        species=species_label,
        assigned_unit_id=None,
        notes=str(profile.notes or "").strip(),
    )


def friendly_condition_label(score: float) -> str:
    if score >= 80:
        return "Strong"
    if score >= 65:
        return "Stable"
    if score >= 50:
        return "Watch"
    return "Needs attention"


def _attention_level(score: float) -> str:
    if score >= 80:
        return "High"
    if score >= 60:
        return "Elevated"
    if score >= 35:
        return "Watch"
    return "Low"


def _attention_score(row: pd.Series, vegetation_row: pd.Series | None) -> float:
    condition_score = float(pd.to_numeric(row.get("pasture_condition_score"), errors="coerce") or 0.0)
    water_risk = float(pd.to_numeric(row.get("water_risk_score"), errors="coerce") or 0.0)
    stocking_risk = float(pd.to_numeric(row.get("stocking_risk_score"), errors="coerce") or 0.0)
    anomaly_value = None
    if vegetation_row is not None:
        raw_anomaly = pd.to_numeric(vegetation_row.get("ndvi_anomaly_percent"), errors="coerce")
        if not pd.isna(raw_anomaly):
            anomaly_value = abs(float(raw_anomaly))
    anomaly_component = min((anomaly_value or 0.0) * 1.4, 100.0)
    recommendation_code = str(row.get("recommendation") or "").upper()
    recommendation_component = {
        "GRAZE": 25.0,
        "REST": 38.0,
        "SUPPLEMENT": 62.0,
        "REDUCE STOCKING": 76.0,
        "DESTOCK WARNING": 92.0,
    }.get(recommendation_code, 40.0)
    return round(max(100.0 - condition_score, water_risk, stocking_risk, anomaly_component, recommendation_component), 1)


def management_recommendation_summary(
    row: pd.Series,
    profile: RanchProfile,
    *,
    unit_label: str,
    unit_type: str,
    vegetation_status: str,
) -> str:
    recommendation_code = str(row.get("recommendation") or "WATCH").upper()
    condition_score = float(pd.to_numeric(row.get("pasture_condition_score"), errors="coerce") or 0.0)
    drought_category = str(row.get("drought_category") or "Unknown")
    base_clause = f"{unit_label.title()} condition is {friendly_condition_label(condition_score).lower()} with {vegetation_status.lower()} vegetation and drought status {drought_category}."
    style = str(profile.management_style or ManagementStyle.NOT_SURE.value)
    species_values = {value.lower() for value in profile.livestock_species}

    if style in {
        ManagementStyle.ROTATIONAL_GRAZING.value,
        ManagementStyle.ADAPTIVE_GRAZING.value,
        ManagementStyle.SEASONAL_GRAZING.value,
    }:
        mapping = {
            "GRAZE": f"This {unit_type} appears close to ready for the next rotation window.",
            "REST": f"Keep this {unit_type} in recovery a bit longer before re-entry.",
            "SUPPLEMENT": f"Plan for extra feed or shorter occupancy if animals enter this {unit_type}.",
            "REDUCE STOCKING": f"Ease grazing pressure here before the next rotation to protect recovery.",
            "DESTOCK WARNING": f"This {unit_type} is showing high strain; defer use or remove grazing pressure quickly.",
        }
    elif style in {ManagementStyle.CONTINUOUS_GRAZING.value, ManagementStyle.SET_STOCKING.value}:
        mapping = {
            "GRAZE": f"This area is currently coping well under ongoing use, but keep monitoring pressure.",
            "REST": f"This area would benefit from a rest window or lighter occupancy if possible.",
            "SUPPLEMENT": f"Conditions suggest supplementing or redistributing pressure across the ranch.",
            "REDUCE STOCKING": f"This area may be under sustained pressure; consider reducing use intensity.",
            "DESTOCK WARNING": f"This area is showing high sustained stress and may need urgent pressure reduction.",
        }
    elif style == ManagementStyle.HORSE_TURNOUT.value or LivestockSpecies.HORSES.value in species_values:
        mapping = {
            "GRAZE": f"This turnout looks usable now, but keep an eye on hoof impact and bare-ground formation.",
            "REST": f"Give this turnout more recovery time before putting horses back in it.",
            "SUPPLEMENT": f"This turnout may need shorter sessions and feed support to limit wear.",
            "REDUCE STOCKING": f"This turnout is vulnerable to surface damage; reduce turnout duration or stocking.",
            "DESTOCK WARNING": f"This turnout shows high wear risk; rest it and shift horses elsewhere if possible.",
        }
    elif style == ManagementStyle.GOAT_SHEEP_BROWSING.value or {
        LivestockSpecies.GOATS.value,
        LivestockSpecies.SHEEP.value,
    } & species_values:
        mapping = {
            "GRAZE": f"This unit may be suitable for near-term grazing or targeted browsing.",
            "REST": f"This unit would benefit from recovery before more browsing pressure.",
            "SUPPLEMENT": f"Use this unit cautiously and pair with feed support or a lighter browse window.",
            "REDUCE STOCKING": f"Browsing pressure may be outrunning recovery here; back off if conditions keep falling.",
            "DESTOCK WARNING": f"This unit looks over-pressured for current conditions and needs a quick reset.",
        }
    elif style == ManagementStyle.HAY_FORAGE_PRODUCTION.value:
        mapping = {
            "GRAZE": f"This field is trending toward a workable forage window.",
            "REST": f"Give this field more regrowth time before cutting or reuse.",
            "SUPPLEMENT": f"Forage outlook here is moderate; plan around a lighter yield window.",
            "REDUCE STOCKING": f"This field is underperforming and may need lower traffic or a different harvest plan.",
            "DESTOCK WARNING": f"This field is under significant stress and may need a conservative recovery period.",
        }
    elif style in {
        ManagementStyle.CONSERVATION_MONITORING.value,
        ManagementStyle.LAND_MONITORING_ONLY.value,
    }:
        mapping = {
            "GRAZE": f"This monitoring area is holding up well relative to current conditions.",
            "REST": f"This monitoring area is below its recent baseline and should stay under observation.",
            "SUPPLEMENT": f"Conditions are softening here; flag it for closer follow-up on the next update.",
            "REDUCE STOCKING": f"This area is trending the wrong direction and may need intervention planning.",
            "DESTOCK WARNING": f"This area is showing high concern and should move to your priority watchlist.",
        }
    else:
        mapping = {
            "GRAZE": f"This {unit_label} looks usable now with normal caution.",
            "REST": f"This {unit_label} would benefit from more recovery time.",
            "SUPPLEMENT": f"This {unit_label} may need extra support or lighter use.",
            "REDUCE STOCKING": f"This {unit_label} is showing elevated pressure and may need lower use intensity.",
            "DESTOCK WARNING": f"This {unit_label} is showing high stress and needs attention soon.",
        }
    return f"{mapping.get(recommendation_code, mapping['REST'])} {base_clause}"


def build_management_units(
    latest_snapshot: pd.DataFrame,
    vegetation_summary_df: pd.DataFrame,
    profile: RanchProfile,
    overrides: dict[str, ManagementUnitOverride] | None = None,
    livestock_groups: dict[str, LivestockGroup] | None = None,
) -> list[ManagementUnit]:
    vegetation_lookup: dict[str, pd.Series] = {}
    if not vegetation_summary_df.empty and "pasture_id" in vegetation_summary_df.columns:
        vegetation_lookup = {
            str(row["pasture_id"]): row for _, row in vegetation_summary_df.set_index("pasture_id", drop=False).iterrows()
        }

    units: list[ManagementUnit] = []
    default_unit_type = default_unit_type_for_profile(profile)
    default_assigned_livestock = [value for value in profile.livestock_species if value]
    override_lookup = overrides or {}
    group_lookup = livestock_groups or {}
    for _, row in latest_snapshot.iterrows():
        unit_id = str(row.get("pasture_id") or "")
        override = override_lookup.get(unit_id)
        assigned_group_ids = list(override.assigned_group_ids) if override is not None else []
        assigned_groups = [group_lookup[group_id] for group_id in assigned_group_ids if group_id in group_lookup]
        assigned_livestock = (
            [f"{group.group_name} ({group.species})" for group in assigned_groups]
            if assigned_groups
            else (
                list(override.assigned_livestock)
                if override is not None and override.assigned_livestock
                else default_assigned_livestock
            )
        )
        vegetation_row = vegetation_lookup.get(unit_id)
        vegetation_status = "Near normal"
        vegetation_anomaly = None
        if vegetation_row is not None:
            vegetation_status = str(vegetation_row.get("ndvi_status") or vegetation_status)
            raw_anomaly = pd.to_numeric(vegetation_row.get("ndvi_anomaly_percent"), errors="coerce")
            if not pd.isna(raw_anomaly):
                vegetation_anomaly = float(raw_anomaly)
        attention_score = _attention_score(row, vegetation_row)
        recommendation_code = str(row.get("recommendation") or "REST").upper()
        condition = UnitConditionSummary(
            forage_condition_score=float(pd.to_numeric(row.get("pasture_condition_score"), errors="coerce") or 0.0),
            vegetation_anomaly_percent=vegetation_anomaly,
            vegetation_status=vegetation_status,
            drought_category=str(row.get("drought_category") or "Unknown"),
            grazing_pressure=float(pd.to_numeric(row.get("grazing_pressure"), errors="coerce") or 0.0),
            water_risk_score=float(pd.to_numeric(row.get("water_risk_score"), errors="coerce") or 0.0),
            attention_score=attention_score,
            attention_level=_attention_level(attention_score),
            recommendation_code=recommendation_code,
            recommendation_label=friendly_condition_label(float(pd.to_numeric(row.get('pasture_condition_score'), errors='coerce') or 0.0)),
            recommendation_summary=management_recommendation_summary(
                row,
                profile,
                unit_label=unit_term(profile),
                unit_type=default_unit_type,
                vegetation_status=vegetation_status,
            ),
        )
        units.append(
            ManagementUnit(
                unit_id=unit_id,
                name=(override.display_name.strip() if override is not None and override.display_name.strip() else str(row.get("name") or unit_id)),
                unit_type=(override.unit_type if override is not None and override.unit_type else default_unit_type),
                acres=float(pd.to_numeric(row.get("acres"), errors="coerce") or 0.0),
                centroid_lat=float(pd.to_numeric(row.get("centroid_lat"), errors="coerce") or 0.0),
                centroid_lon=float(pd.to_numeric(row.get("centroid_lon"), errors="coerce") or 0.0),
                geometry=row.get("geometry") or [],
                assigned_group_ids=assigned_group_ids,
                assigned_livestock=assigned_livestock,
                notes=(override.notes if override is not None and override.notes else str(row.get("notes") or "")),
                condition=condition,
            )
        )
    return sorted(units, key=lambda item: item.condition.attention_score if item.condition else 0.0, reverse=True)


def management_units_frame(units: list[ManagementUnit]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for unit in units:
        condition = unit.condition
        activity_summary = None
        if hasattr(unit, "activity_summary"):
            activity_summary = getattr(unit, "activity_summary")
        utilization_summary = None
        if hasattr(unit, "utilization_summary"):
            utilization_summary = getattr(unit, "utilization_summary")
        rows.append(
            {
                "unit_id": unit.unit_id,
                "name": unit.name,
                "unit_type": unit.unit_type,
                "acres": unit.acres,
                "assigned_groups": ", ".join(unit.assigned_group_ids) if unit.assigned_group_ids else "none assigned",
                "assigned_livestock": ", ".join(unit.assigned_livestock) if unit.assigned_livestock else "none assigned",
                "notes": unit.notes,
                "current_activity": "No activity logged"
                if activity_summary is None
                else activity_summary.current_activity,
                "current_status": "No Activity"
                if activity_summary is None
                else activity_summary.status_label,
                "recent_activity": "No activity logged"
                if activity_summary is None
                else activity_summary.recent_activity,
                "active_head_count": 0
                if utilization_summary is None
                else utilization_summary.active_head_count,
                "occupancy_days_30": 0
                if utilization_summary is None
                else utilization_summary.occupancy_days_30,
                "animal_unit_days_30": 0.0
                if utilization_summary is None
                else utilization_summary.animal_unit_days_30,
                "utilization_per_acre_30": 0.0
                if utilization_summary is None
                else utilization_summary.utilization_per_acre_30,
                "utilization_label": "Resting"
                if utilization_summary is None
                else utilization_summary.utilization_label,
                "rest_days_since_occupancy": None
                if utilization_summary is None
                else utilization_summary.rest_days_since_occupancy,
                "condition_score": None if condition is None else condition.forage_condition_score,
                "vegetation_status": None if condition is None else condition.vegetation_status,
                "drought_category": None if condition is None else condition.drought_category,
                "attention_score": None if condition is None else condition.attention_score,
                "attention_level": None if condition is None else condition.attention_level,
                "recommendation": None if condition is None else condition.recommendation_code,
            }
        )
    return pd.DataFrame(rows)


def coerce_management_unit_overrides(raw_value: Any) -> dict[str, ManagementUnitOverride]:
    if not isinstance(raw_value, dict):
        return {}
    overrides: dict[str, ManagementUnitOverride] = {}
    for unit_id, payload in raw_value.items():
        if not isinstance(payload, dict):
            continue
        normalized_unit_id = str(unit_id or payload.get("unit_id") or "").strip()
        if not normalized_unit_id:
            continue
        assigned_livestock = payload.get("assigned_livestock", [])
        if not isinstance(assigned_livestock, list):
            assigned_livestock = []
        assigned_group_ids = payload.get("assigned_group_ids", [])
        if not isinstance(assigned_group_ids, list):
            assigned_group_ids = []
        overrides[normalized_unit_id] = ManagementUnitOverride(
            unit_id=normalized_unit_id,
            display_name=str(payload.get("display_name", "") or ""),
            unit_type=str(payload.get("unit_type", ManagementUnitType.PASTURE.value) or ManagementUnitType.PASTURE.value),
            assigned_group_ids=[str(value) for value in assigned_group_ids if str(value).strip()],
            assigned_livestock=[str(value) for value in assigned_livestock if str(value).strip()],
            notes=str(payload.get("notes", "") or ""),
        )
    return overrides


def serialize_management_unit_overrides(
    overrides: dict[str, ManagementUnitOverride],
) -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}
    for unit_id, override in overrides.items():
        payload[str(unit_id)] = {
            "unit_id": override.unit_id,
            "display_name": override.display_name,
            "unit_type": override.unit_type,
            "assigned_group_ids": list(override.assigned_group_ids),
            "assigned_livestock": list(override.assigned_livestock),
            "notes": override.notes,
        }
    return payload


def coerce_livestock_groups(raw_value: Any) -> dict[str, LivestockGroup]:
    if not isinstance(raw_value, (dict, list)):
        return {}
    groups: dict[str, LivestockGroup] = {}
    items = raw_value.items() if isinstance(raw_value, dict) else enumerate(raw_value)
    for key, payload in items:
        if not isinstance(payload, dict):
            continue
        group_id = str(payload.get("group_id") or key or "").strip()
        if not group_id:
            continue
        raw_count = payload.get("animal_count")
        animal_count = int(raw_count) if str(raw_count).strip() not in {"", "None", "none"} else None
        raw_weight = payload.get("average_weight")
        average_weight = float(raw_weight) if str(raw_weight).strip() not in {"", "None", "none"} else None
        groups[group_id] = LivestockGroup(
            group_id=group_id,
            group_name=str(payload.get("group_name", "") or group_id),
            species=str(payload.get("species", LivestockSpecies.OTHER.value) or LivestockSpecies.OTHER.value),
            animal_count=animal_count,
            class_type=str(payload.get("class_type", "") or ""),
            average_weight=average_weight,
            assigned_unit_id=str(payload.get("assigned_unit_id", "") or "") or None,
            notes=str(payload.get("notes", "") or ""),
        )
    return groups


def serialize_livestock_groups(groups: dict[str, LivestockGroup]) -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}
    for group_id, group in groups.items():
        payload[str(group_id)] = {
            "group_id": group.group_id,
            "group_name": group.group_name,
            "species": group.species,
            "animal_count": group.animal_count,
            "class_type": group.class_type,
            "average_weight": group.average_weight,
            "assigned_unit_id": group.assigned_unit_id,
            "notes": group.notes,
        }
    return payload


def _normalize_date_string(raw_value: Any) -> str:
    if raw_value is None or str(raw_value).strip() in {"", "None", "none"}:
        return ""
    timestamp = pd.to_datetime(raw_value, errors="coerce")
    if pd.isna(timestamp):
        return ""
    return timestamp.date().isoformat()


def _parse_activity_date(raw_value: str | None) -> pd.Timestamp | None:
    if raw_value is None or str(raw_value).strip() == "":
        return None
    timestamp = pd.to_datetime(raw_value, errors="coerce")
    if pd.isna(timestamp):
        return None
    if getattr(timestamp, "tzinfo", None) is not None:
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    return timestamp.normalize()


def coerce_unit_activity_events(raw_value: Any) -> dict[str, UnitActivityEvent]:
    if not isinstance(raw_value, (dict, list)):
        return {}
    events: dict[str, UnitActivityEvent] = {}
    items = raw_value.items() if isinstance(raw_value, dict) else enumerate(raw_value)
    for key, payload in items:
        if not isinstance(payload, dict):
            continue
        event_id = str(payload.get("event_id") or key or "").strip()
        unit_id = str(payload.get("unit_id") or "").strip()
        if not event_id or not unit_id:
            continue
        events[event_id] = UnitActivityEvent(
            event_id=event_id,
            unit_id=unit_id,
            activity_type=str(payload.get("activity_type", UnitActivityType.OTHER.value) or UnitActivityType.OTHER.value),
            livestock_group_id=(str(payload.get("livestock_group_id", "") or "").strip() or None),
            start_date=_normalize_date_string(payload.get("start_date")),
            end_date=(_normalize_date_string(payload.get("end_date")) or None),
            notes=str(payload.get("notes", "") or ""),
        )
    return events


def serialize_unit_activity_events(events: dict[str, UnitActivityEvent]) -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}
    for event_id, event in events.items():
        payload[str(event_id)] = {
            "event_id": event.event_id,
            "unit_id": event.unit_id,
            "activity_type": event.activity_type,
            "livestock_group_id": event.livestock_group_id,
            "start_date": event.start_date,
            "end_date": event.end_date,
            "notes": event.notes,
        }
    return payload


def _activity_type_label(activity_type: str) -> str:
    value = str(activity_type or UnitActivityType.OTHER.value)
    return value.title()


def _activity_group_label(event: UnitActivityEvent, groups: dict[str, LivestockGroup]) -> str:
    if not event.livestock_group_id:
        return ""
    group = groups.get(event.livestock_group_id)
    if group is None:
        return event.livestock_group_id
    return f"{group.group_name} ({group.species})"


def _activity_window_label(event: UnitActivityEvent) -> str:
    start_value = _parse_activity_date(event.start_date)
    end_value = _parse_activity_date(event.end_date)
    if start_value is None and end_value is None:
        return ""
    if start_value is None and end_value is not None:
        return f"Until {end_value.strftime('%b %d, %Y')}"
    if start_value is not None and end_value is None:
        return f"Since {start_value.strftime('%b %d, %Y')}"
    assert start_value is not None
    assert end_value is not None
    if start_value == end_value:
        return start_value.strftime("%b %d, %Y")
    return f"{start_value.strftime('%b %d, %Y')} to {end_value.strftime('%b %d, %Y')}"


def _activity_status(event: UnitActivityEvent, as_of: pd.Timestamp) -> str:
    start_value = _parse_activity_date(event.start_date)
    end_value = _parse_activity_date(event.end_date)
    if start_value is not None and start_value > as_of:
        return "Scheduled"
    if start_value is not None and start_value <= as_of and (end_value is None or end_value >= as_of):
        return "Active"
    return "Completed"


def _is_occupancy_activity(activity_type: str) -> bool:
    return str(activity_type or "").strip().lower() in {
        UnitActivityType.GRAZING.value,
        UnitActivityType.BROWSING.value,
        UnitActivityType.TURNOUT.value,
    }


def _species_default_animal_unit_equivalent(species: str) -> float:
    normalized = str(species or LivestockSpecies.OTHER.value).strip().lower()
    if normalized in {LivestockSpecies.CATTLE.value, LivestockSpecies.HORSES.value}:
        return 1.0
    if normalized in {LivestockSpecies.GOATS.value, LivestockSpecies.SHEEP.value}:
        return 0.2
    if normalized == LivestockSpecies.MIXED.value:
        return 0.75
    if normalized == LivestockSpecies.WILDLIFE.value:
        return 0.0
    return 1.0


def _animal_unit_equivalent(group: LivestockGroup | None) -> float:
    if group is None:
        return 1.0
    if group.average_weight is not None and group.average_weight > 0:
        return round(float(group.average_weight) / 1000.0, 3)
    return _species_default_animal_unit_equivalent(group.species)


def _event_overlap_days(
    event: UnitActivityEvent,
    *,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> int:
    start_value = _parse_activity_date(event.start_date)
    if start_value is None:
        return 0
    end_value = _parse_activity_date(event.end_date) or window_end
    overlap_start = max(start_value, window_start)
    overlap_end = min(end_value, window_end)
    if overlap_end < overlap_start:
        return 0
    return int((overlap_end - overlap_start).days) + 1


def _utilization_label(value: float) -> str:
    if value <= 0:
        return "Resting"
    if value < 0.5:
        return "Light"
    if value < 1.5:
        return "Moderate"
    if value < 3.0:
        return "Elevated"
    return "Heavy"


def build_unit_activity_summary_lookup(
    events: dict[str, UnitActivityEvent],
    groups: dict[str, LivestockGroup],
    units: list[ManagementUnit],
    *,
    as_of: pd.Timestamp | None = None,
) -> dict[str, UnitActivitySummary]:
    effective_now = as_of or pd.Timestamp.utcnow().normalize()
    unit_lookup = {unit.unit_id: unit for unit in units}
    grouped_events: dict[str, list[UnitActivityEvent]] = {unit.unit_id: [] for unit in units}
    for event in events.values():
        if event.unit_id in grouped_events:
            grouped_events[event.unit_id].append(event)

    summary_lookup: dict[str, UnitActivitySummary] = {}
    for unit_id in unit_lookup:
        unit_events = grouped_events.get(unit_id, [])
        sorted_events = sorted(
            unit_events,
            key=lambda event: (
                _parse_activity_date(event.start_date) or pd.Timestamp.min,
                _parse_activity_date(event.end_date) or pd.Timestamp.min,
            ),
            reverse=True,
        )
        active_events = [event for event in sorted_events if _activity_status(event, effective_now) == "Active"]
        scheduled_events = sorted(
            [event for event in sorted_events if _activity_status(event, effective_now) == "Scheduled"],
            key=lambda event: _parse_activity_date(event.start_date) or pd.Timestamp.max,
        )
        current_event = active_events[0] if active_events else (scheduled_events[0] if scheduled_events else None)
        latest_event = sorted_events[0] if sorted_events else None
        status_label = "No Activity"
        if current_event is not None:
            status_label = _activity_status(current_event, effective_now)
        elif latest_event is not None:
            status_label = "Recent"
        summary_lookup[unit_id] = UnitActivitySummary(
            unit_id=unit_id,
            status_label=status_label,
            current_activity="No activity logged"
            if current_event is None
            else _activity_type_label(current_event.activity_type),
            current_group_label=""
            if current_event is None
            else _activity_group_label(current_event, groups),
            current_window=""
            if current_event is None
            else _activity_window_label(current_event),
            recent_activity="No activity logged"
            if latest_event is None
            else _activity_type_label(latest_event.activity_type),
            recent_group_label=""
            if latest_event is None
            else _activity_group_label(latest_event, groups),
            recent_window=""
            if latest_event is None
            else _activity_window_label(latest_event),
            active_event_count=len(active_events),
        )
    return summary_lookup


def attach_activity_summaries(
    units: list[ManagementUnit],
    activity_summaries: dict[str, UnitActivitySummary],
) -> list[ManagementUnit]:
    for unit in units:
        setattr(unit, "activity_summary", activity_summaries.get(unit.unit_id))
    return units


def build_livestock_group_load_summaries(
    groups: dict[str, LivestockGroup],
    events: dict[str, UnitActivityEvent],
    units: list[ManagementUnit],
    *,
    as_of: pd.Timestamp | None = None,
    lookback_days: int = 30,
) -> dict[str, LivestockGroupLoadSummary]:
    effective_now = (as_of or pd.Timestamp.utcnow()).normalize()
    window_start = effective_now - pd.Timedelta(days=max(lookback_days - 1, 0))
    unit_lookup = {unit.unit_id: unit.name for unit in units}
    summary_lookup: dict[str, LivestockGroupLoadSummary] = {}
    for group_id, group in groups.items():
        group_events = [event for event in events.values() if event.livestock_group_id == group_id]
        sorted_events = sorted(
            group_events,
            key=lambda event: (
                _parse_activity_date(event.start_date) or pd.Timestamp.min,
                _parse_activity_date(event.end_date) or pd.Timestamp.min,
            ),
            reverse=True,
        )
        current_event = next((event for event in sorted_events if _activity_status(event, effective_now) == "Active"), None)
        latest_event = sorted_events[0] if sorted_events else None
        occupancy_events = [event for event in group_events if _is_occupancy_activity(event.activity_type)]
        occupied_units: set[str] = set()
        occupancy_days_30 = 0
        animal_unit_days_30 = 0.0
        for event in occupancy_events:
            overlap_days = _event_overlap_days(event, window_start=window_start, window_end=effective_now)
            if overlap_days <= 0:
                continue
            occupied_units.add(event.unit_id)
            occupancy_days_30 += overlap_days
            head_count = group.animal_count or 0
            animal_unit_days_30 += overlap_days * head_count * _animal_unit_equivalent(group)
        summary_lookup[group_id] = LivestockGroupLoadSummary(
            group_id=group.group_id,
            group_name=group.group_name,
            species=group.species,
            current_unit_name="Unassigned"
            if current_event is None
            else unit_lookup.get(current_event.unit_id, current_event.unit_id),
            current_activity="No activity logged"
            if current_event is None
            else _activity_type_label(current_event.activity_type),
            current_window=""
            if current_event is None
            else _activity_window_label(current_event),
            recent_activity="No activity logged"
            if latest_event is None
            else _activity_type_label(latest_event.activity_type),
            recent_window=""
            if latest_event is None
            else _activity_window_label(latest_event),
            occupied_units_30=len(occupied_units),
            occupancy_days_30=occupancy_days_30,
            animal_unit_days_30=round(animal_unit_days_30, 1),
            active_head_count=(group.animal_count or 0) if current_event is not None else 0,
        )
    return summary_lookup


def livestock_group_load_frame(summaries: dict[str, LivestockGroupLoadSummary]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for summary in summaries.values():
        rows.append(
            {
                "group_id": summary.group_id,
                "group_name": summary.group_name,
                "species": summary.species,
                "current_unit_name": summary.current_unit_name,
                "current_activity": summary.current_activity,
                "active_head_count": summary.active_head_count,
                "occupied_units_30": summary.occupied_units_30,
                "occupancy_days_30": summary.occupancy_days_30,
                "animal_unit_days_30": summary.animal_unit_days_30,
                "recent_activity": summary.recent_activity,
                "recent_window": summary.recent_window,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(["active_head_count", "animal_unit_days_30", "group_name"], ascending=[False, False, True]).reset_index(drop=True)


def build_unit_utilization_summaries(
    units: list[ManagementUnit],
    groups: dict[str, LivestockGroup],
    events: dict[str, UnitActivityEvent],
    *,
    as_of: pd.Timestamp | None = None,
    lookback_days: int = 30,
) -> dict[str, UnitUtilizationSummary]:
    effective_now = (as_of or pd.Timestamp.utcnow()).normalize()
    window_start = effective_now - pd.Timedelta(days=max(lookback_days - 1, 0))
    summaries: dict[str, UnitUtilizationSummary] = {}
    for unit in units:
        unit_events = [event for event in events.values() if event.unit_id == unit.unit_id and _is_occupancy_activity(event.activity_type)]
        active_events = [event for event in unit_events if _activity_status(event, effective_now) == "Active"]
        active_group_labels: list[str] = []
        active_head_count = 0
        seen_active_groups: set[str] = set()
        for event in active_events:
            group = groups.get(event.livestock_group_id or "")
            label = _activity_group_label(event, groups) or "Unnamed Group"
            if label not in active_group_labels:
                active_group_labels.append(label)
            group_key = event.livestock_group_id or f"event:{event.event_id}"
            if group_key not in seen_active_groups:
                active_head_count += 0 if group is None or group.animal_count is None else int(group.animal_count)
                seen_active_groups.add(group_key)
        occupancy_days_30 = 0
        animal_unit_days_30 = 0.0
        latest_end: pd.Timestamp | None = None
        for event in unit_events:
            overlap_days = _event_overlap_days(event, window_start=window_start, window_end=effective_now)
            if overlap_days > 0:
                group = groups.get(event.livestock_group_id or "")
                head_count = 0 if group is None or group.animal_count is None else int(group.animal_count)
                occupancy_days_30 += overlap_days
                animal_unit_days_30 += overlap_days * head_count * _animal_unit_equivalent(group)
            end_value = _parse_activity_date(event.end_date)
            if end_value is not None and end_value <= effective_now and (latest_end is None or end_value > latest_end):
                latest_end = end_value
        utilization_per_acre_30 = 0.0 if unit.acres <= 0 else round(animal_unit_days_30 / unit.acres, 2)
        rest_days_since_occupancy = None
        if not active_events and latest_end is not None:
            rest_days_since_occupancy = int((effective_now - latest_end).days)
        summaries[unit.unit_id] = UnitUtilizationSummary(
            unit_id=unit.unit_id,
            active_group_labels=active_group_labels,
            active_head_count=active_head_count,
            occupancy_days_30=occupancy_days_30,
            animal_unit_days_30=round(animal_unit_days_30, 1),
            utilization_per_acre_30=utilization_per_acre_30,
            utilization_label=_utilization_label(utilization_per_acre_30),
            rest_days_since_occupancy=rest_days_since_occupancy,
        )
    return summaries


def attach_utilization_summaries(
    units: list[ManagementUnit],
    utilization_summaries: dict[str, UnitUtilizationSummary],
) -> list[ManagementUnit]:
    for unit in units:
        setattr(unit, "utilization_summary", utilization_summaries.get(unit.unit_id))
    return units


def unit_utilization_frame(summaries: dict[str, UnitUtilizationSummary], units: list[ManagementUnit]) -> pd.DataFrame:
    unit_lookup = {unit.unit_id: unit.name for unit in units}
    rows: list[dict[str, Any]] = []
    for summary in summaries.values():
        rows.append(
            {
                "unit_id": summary.unit_id,
                "unit_name": unit_lookup.get(summary.unit_id, summary.unit_id),
                "active_groups": ", ".join(summary.active_group_labels) if summary.active_group_labels else "none active",
                "active_head_count": summary.active_head_count,
                "occupancy_days_30": summary.occupancy_days_30,
                "animal_unit_days_30": summary.animal_unit_days_30,
                "utilization_per_acre_30": summary.utilization_per_acre_30,
                "utilization_label": summary.utilization_label,
                "rest_days_since_occupancy": summary.rest_days_since_occupancy,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(["utilization_per_acre_30", "active_head_count", "unit_name"], ascending=[False, False, True]).reset_index(drop=True)


def _planner_group(unit: ManagementUnit, groups: dict[str, LivestockGroup]) -> tuple[str | None, str]:
    group_id = unit.assigned_group_ids[0] if unit.assigned_group_ids else None
    if not group_id:
        return None, ""
    group = groups.get(group_id)
    if group is None:
        return group_id, group_id
    return group_id, f"{group.group_name} ({group.species})"


def _planner_window(start_date: pd.Timestamp, duration_days: int) -> tuple[str, str | None]:
    normalized_start = start_date.normalize()
    if duration_days <= 1:
        return normalized_start.date().isoformat(), normalized_start.date().isoformat()
    end_date = normalized_start + pd.Timedelta(days=duration_days - 1)
    return normalized_start.date().isoformat(), end_date.date().isoformat()


def build_operation_planner_suggestions(
    units: list[ManagementUnit],
    profile: RanchProfile,
    groups: dict[str, LivestockGroup],
    *,
    as_of: pd.Timestamp | None = None,
) -> list[OperationPlannerSuggestion]:
    effective_now = (as_of or pd.Timestamp.utcnow()).normalize()
    suggestions: list[OperationPlannerSuggestion] = []
    style = str(profile.management_style or ManagementStyle.NOT_SURE.value)
    for unit in units:
        condition = unit.condition
        if condition is None:
            continue
        activity_summary = getattr(unit, "activity_summary", None)
        utilization_summary = getattr(unit, "utilization_summary", None)
        if activity_summary is None or utilization_summary is None:
            continue
        group_id, group_label = _planner_group(unit, groups)
        start_date = effective_now + pd.Timedelta(days=1)
        suggested_activity_type = UnitActivityType.MONITORING.value
        duration_days = 1
        urgency = condition.attention_level
        rationale = condition.recommendation_summary
        current_active = activity_summary.status_label == "Active"
        resting = utilization_summary.utilization_label == "Resting"
        heavy_pressure = utilization_summary.utilization_label in {"Elevated", "Heavy"} or condition.attention_level in {"High", "Elevated"}
        ready_window = (
            not current_active
            and condition.forage_condition_score >= 65
            and condition.attention_level in {"Low", "Watch"}
            and (utilization_summary.rest_days_since_occupancy is None or utilization_summary.rest_days_since_occupancy >= 5)
        )

        if style in {
            ManagementStyle.ROTATIONAL_GRAZING.value,
            ManagementStyle.ADAPTIVE_GRAZING.value,
            ManagementStyle.SEASONAL_GRAZING.value,
        }:
            if current_active and heavy_pressure:
                suggested_activity_type = UnitActivityType.REST.value
                duration_days = 10 if condition.attention_level == "High" else 7
                rationale = "Pressure and attention indicators suggest ending the current grazing window and protecting recovery."
            elif ready_window:
                suggested_activity_type = UnitActivityType.GRAZING.value
                duration_days = 5 if condition.forage_condition_score >= 80 else 3
                rationale = "This unit looks ready for a short grazing window based on condition, recovery, and recent use."
            else:
                suggested_activity_type = UnitActivityType.MONITORING.value
                duration_days = 1
                rationale = "Hold this unit in the watch queue and re-check before scheduling the next move."
        elif style in {ManagementStyle.CONTINUOUS_GRAZING.value, ManagementStyle.SET_STOCKING.value}:
            if heavy_pressure:
                suggested_activity_type = UnitActivityType.MONITORING.value
                duration_days = 1
                rationale = "This area may be under sustained pressure; flag it for a field check and be ready to redistribute use."
            elif resting:
                suggested_activity_type = UnitActivityType.REST.value
                duration_days = 7
                rationale = "Keep this area in recovery and verify that condition improves before bringing more pressure back."
            else:
                suggested_activity_type = UnitActivityType.MONITORING.value
                duration_days = 1
                rationale = "Maintain a normal scouting rhythm and watch for persistent decline."
        elif style == ManagementStyle.HORSE_TURNOUT.value:
            if current_active and heavy_pressure:
                suggested_activity_type = UnitActivityType.REST.value
                duration_days = 7
                rationale = "Turnout pressure is elevated; schedule recovery time before horses return."
            elif ready_window:
                suggested_activity_type = UnitActivityType.TURNOUT.value
                duration_days = 2
                rationale = "Conditions support a short turnout window if you want to rotate horses back in."
            else:
                suggested_activity_type = UnitActivityType.MONITORING.value
                duration_days = 1
                rationale = "Use this turnout cautiously and keep monitoring bare ground and hoof impact."
        elif style == ManagementStyle.GOAT_SHEEP_BROWSING.value:
            if ready_window:
                suggested_activity_type = UnitActivityType.BROWSING.value
                duration_days = 3
                rationale = "This unit appears suitable for a targeted browse window based on current condition."
            elif heavy_pressure:
                suggested_activity_type = UnitActivityType.REST.value
                duration_days = 7
                rationale = "Give this unit more recovery before adding more grazing or browsing pressure."
            else:
                suggested_activity_type = UnitActivityType.MONITORING.value
                duration_days = 1
                rationale = "Monitor browse response and vegetation condition before the next pass."
        elif style == ManagementStyle.HAY_FORAGE_PRODUCTION.value:
            if condition.forage_condition_score >= 70 and condition.attention_level in {"Low", "Watch"}:
                suggested_activity_type = UnitActivityType.HAYING.value
                duration_days = 2
                rationale = "This field looks close to a workable harvest window based on current condition."
            else:
                suggested_activity_type = UnitActivityType.MONITORING.value
                duration_days = 1
                rationale = "Watch this field a bit longer before committing to harvest or traffic."
        elif style in {
            ManagementStyle.CONSERVATION_MONITORING.value,
            ManagementStyle.LAND_MONITORING_ONLY.value,
        }:
            if condition.attention_level in {"High", "Elevated"}:
                suggested_activity_type = UnitActivityType.RESTORATION.value
                duration_days = 1
                rationale = "This unit should move into a closer restoration/response workflow because recent indicators are deteriorating."
            else:
                suggested_activity_type = UnitActivityType.MONITORING.value
                duration_days = 1
                rationale = "Keep this area on the monitoring calendar and re-check after the next data refresh."
        else:
            if heavy_pressure:
                suggested_activity_type = UnitActivityType.REST.value
                duration_days = 7
                rationale = "Conditions suggest a temporary reset or lighter use window."
            elif ready_window:
                suggested_activity_type = UnitActivityType.GRAZING.value
                duration_days = 3
                rationale = "Conditions support a cautious near-term use window."
            else:
                suggested_activity_type = UnitActivityType.MONITORING.value
                duration_days = 1
                rationale = "Keep this unit under observation until conditions become clearer."

        window_start, window_end = _planner_window(start_date, duration_days)
        suggestions.append(
            OperationPlannerSuggestion(
                unit_id=unit.unit_id,
                unit_name=unit.name,
                unit_type=unit.unit_type,
                suggested_activity_type=suggested_activity_type,
                suggested_group_id=group_id,
                suggested_group_label=group_label,
                start_date=window_start,
                end_date=window_end,
                urgency=urgency,
                rationale=rationale,
            )
        )
    urgency_rank = {"High": 0, "Elevated": 1, "Watch": 2, "Low": 3}
    return sorted(
        suggestions,
        key=lambda item: (
            urgency_rank.get(item.urgency, 9),
            item.start_date,
            item.unit_name,
        ),
    )


def operation_planner_frame(suggestions: list[OperationPlannerSuggestion]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for suggestion in suggestions:
        rows.append(
            {
                "unit_id": suggestion.unit_id,
                "unit_name": suggestion.unit_name,
                "unit_type": suggestion.unit_type,
                "suggested_activity_type": suggestion.suggested_activity_type.title(),
                "suggested_group": suggestion.suggested_group_label or "No group assigned",
                "start_date": suggestion.start_date,
                "end_date": suggestion.end_date or "",
                "urgency": suggestion.urgency,
                "rationale": suggestion.rationale,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame


def unit_activity_frame(
    events: dict[str, UnitActivityEvent],
    groups: dict[str, LivestockGroup],
    units: list[ManagementUnit],
    *,
    as_of: pd.Timestamp | None = None,
) -> pd.DataFrame:
    effective_now = as_of or pd.Timestamp.utcnow().normalize()
    unit_lookup = {unit.unit_id: unit.name for unit in units}
    rows: list[dict[str, Any]] = []
    for event in events.values():
        rows.append(
            {
                "event_id": event.event_id,
                "unit_id": event.unit_id,
                "unit_name": unit_lookup.get(event.unit_id, event.unit_id),
                "activity_type": _activity_type_label(event.activity_type),
                "livestock_group": _activity_group_label(event, groups) or "No group assigned",
                "start_date": event.start_date or "",
                "end_date": event.end_date or "",
                "status": _activity_status(event, effective_now),
                "notes": event.notes,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(["status", "start_date", "unit_name"], ascending=[True, False, True]).reset_index(drop=True)


def livestock_groups_frame(groups: dict[str, LivestockGroup], units: list[ManagementUnit]) -> pd.DataFrame:
    unit_lookup = {unit.unit_id: unit.name for unit in units}
    rows: list[dict[str, Any]] = []
    for group in groups.values():
        rows.append(
            {
                "group_id": group.group_id,
                "group_name": group.group_name,
                "species": group.species,
                "animal_count": group.animal_count,
                "class_type": group.class_type,
                "average_weight": group.average_weight,
                "assigned_unit": unit_lookup.get(group.assigned_unit_id or "", group.assigned_unit_id or "unassigned"),
                "notes": group.notes,
            }
        )
    return pd.DataFrame(rows)
