import pandas as pd

from ranch_ai.models.ranch_domain import (
    UnitFeedbackLabel,
    LivestockGroup,
    coerce_unit_feedback_labels,
    attach_utilization_summaries,
    build_operation_planner_suggestions,
    build_livestock_group_load_summaries,
    ManagementUnitOverride,
    RanchProfile,
    UnitActivityEvent,
    attach_activity_summaries,
    build_management_units,
    build_unit_activity_summary_lookup,
    build_unit_utilization_summaries,
    coerce_livestock_groups,
    coerce_management_unit_overrides,
    coerce_unit_activity_events,
    livestock_group_load_frame,
    management_units_frame,
    serialize_unit_feedback_labels,
    serialize_unit_activity_events,
    serialize_livestock_groups,
    serialize_management_unit_overrides,
    unit_utilization_frame,
    unit_feedback_frame,
)


def test_management_unit_overrides_are_applied_to_units():
    latest_snapshot = pd.DataFrame(
        [
            {
                "pasture_id": "P-001",
                "name": "North Pasture",
                "acres": 120.0,
                "centroid_lat": 32.1,
                "centroid_lon": -99.4,
                "geometry": [[[-99.4, 32.1], [-99.39, 32.1], [-99.39, 32.11], [-99.4, 32.1]]][0],
                "pasture_condition_score": 58.0,
                "drought_category": "D1",
                "grazing_pressure": 0.42,
                "water_risk_score": 35.0,
                "stocking_risk_score": 41.0,
                "recommendation": "REST",
                "notes": "Source notes",
            }
        ]
    )
    vegetation_summary = pd.DataFrame(
        [
            {
                "pasture_id": "P-001",
                "ndvi_status": "Below normal",
                "ndvi_anomaly_percent": -12.5,
            }
        ]
    )
    profile = RanchProfile(
        ranch_type="horse property",
        management_style="horse turnout",
        livestock_species=["horses"],
    )
    overrides = {
        "P-001": ManagementUnitOverride(
            unit_id="P-001",
            display_name="Arena Turnout",
            unit_type="horse turnout",
            assigned_group_ids=["mares"],
            assigned_livestock=["horses"],
            notes="Rotate only for short sessions.",
        )
    }
    livestock_groups = {
        "mares": LivestockGroup(
            group_id="mares",
            group_name="Broodmares",
            species="horses",
            animal_count=12,
            assigned_unit_id="P-001",
        )
    }

    units = build_management_units(
        latest_snapshot,
        vegetation_summary,
        profile,
        overrides=overrides,
        livestock_groups=livestock_groups,
    )

    assert len(units) == 1
    assert units[0].name == "Arena Turnout"
    assert units[0].unit_type == "horse turnout"
    assert units[0].assigned_group_ids == ["mares"]
    assert units[0].assigned_livestock == ["Broodmares (horses)"]
    assert units[0].notes == "Rotate only for short sessions."


def test_management_unit_override_serialization_round_trip():
    overrides = {
        "P-001": ManagementUnitOverride(
            unit_id="P-001",
            display_name="North Unit",
            unit_type="pasture",
            assigned_group_ids=["cow-calf"],
            assigned_livestock=["cattle", "goats"],
            notes="Priority recovery area.",
        )
    }

    payload = serialize_management_unit_overrides(overrides)
    reloaded = coerce_management_unit_overrides(payload)

    assert reloaded["P-001"].display_name == "North Unit"
    assert reloaded["P-001"].unit_type == "pasture"
    assert reloaded["P-001"].assigned_group_ids == ["cow-calf"]
    assert reloaded["P-001"].assigned_livestock == ["cattle", "goats"]
    assert reloaded["P-001"].notes == "Priority recovery area."


def test_livestock_group_serialization_round_trip():
    groups = {
        "cow-calf": LivestockGroup(
            group_id="cow-calf",
            group_name="Cow-Calf Pairs",
            species="cattle",
            animal_count=85,
            class_type="cow-calf pairs",
            average_weight=1150.0,
            assigned_unit_id="P-001",
            notes="Spring herd",
        )
    }

    payload = serialize_livestock_groups(groups)
    reloaded = coerce_livestock_groups(payload)

    assert reloaded["cow-calf"].group_name == "Cow-Calf Pairs"
    assert reloaded["cow-calf"].animal_count == 85
    assert reloaded["cow-calf"].average_weight == 1150.0
    assert reloaded["cow-calf"].assigned_unit_id == "P-001"


def test_unit_activity_serialization_round_trip():
    events = {
        "activity-1": UnitActivityEvent(
            event_id="activity-1",
            unit_id="P-001",
            activity_type="rest / recovery",
            livestock_group_id="cow-calf",
            start_date="2026-05-01",
            end_date="2026-05-14",
            notes="Rest after spring grazing.",
        )
    }

    payload = serialize_unit_activity_events(events)
    reloaded = coerce_unit_activity_events(payload)

    assert reloaded["activity-1"].unit_id == "P-001"
    assert reloaded["activity-1"].activity_type == "rest / recovery"
    assert reloaded["activity-1"].livestock_group_id == "cow-calf"
    assert reloaded["activity-1"].start_date == "2026-05-01"
    assert reloaded["activity-1"].end_date == "2026-05-14"


def test_unit_feedback_label_serialization_round_trip():
    labels = {
        "feedback-1": UnitFeedbackLabel(
            label_id="feedback-1",
            unit_id="P-001",
            label_type="forage / vegetation condition",
            label_value="stressed",
            observed_on="2026-05-04",
            confidence="high",
            notes="Greenness fell off after the last dry week.",
        )
    }

    payload = serialize_unit_feedback_labels(labels)
    reloaded = coerce_unit_feedback_labels(payload)

    assert reloaded["feedback-1"].unit_id == "P-001"
    assert reloaded["feedback-1"].label_type == "forage / vegetation condition"
    assert reloaded["feedback-1"].label_value == "stressed"
    assert reloaded["feedback-1"].confidence == "high"


def test_unit_feedback_frame_uses_unit_names_and_sorts_latest_first():
    management_units = build_management_units(
        pd.DataFrame(
            [
                {
                    "pasture_id": "P-001",
                    "name": "North Pasture",
                    "acres": 120.0,
                    "centroid_lat": 32.1,
                    "centroid_lon": -99.4,
                    "geometry": [[[-99.4, 32.1], [-99.39, 32.1], [-99.39, 32.11], [-99.4, 32.1]]][0],
                    "pasture_condition_score": 58.0,
                    "drought_category": "D1",
                    "grazing_pressure": 0.42,
                    "water_risk_score": 35.0,
                    "stocking_risk_score": 41.0,
                    "recommendation": "REST",
                    "notes": "Source notes",
                }
            ]
        ),
        pd.DataFrame(
            [
                {
                    "pasture_id": "P-001",
                    "ndvi_status": "Below normal",
                    "ndvi_anomaly_percent": -12.5,
                }
            ]
        ),
        RanchProfile(),
    )
    labels = {
        "feedback-older": UnitFeedbackLabel(
            label_id="feedback-older",
            unit_id="P-001",
            label_type="general observation",
            label_value="mixed",
            observed_on="2026-05-01",
            confidence="medium",
            notes="Earlier note.",
        ),
        "feedback-latest": UnitFeedbackLabel(
            label_id="feedback-latest",
            unit_id="P-001",
            label_type="move / turnout readiness",
            label_value="hold",
            observed_on="2026-05-05",
            confidence="high",
            notes="Recent note.",
        ),
    }

    frame = unit_feedback_frame(labels, management_units)

    assert frame.loc[0, "unit_name"] == "North Pasture"
    assert frame.loc[0, "label_id"] == "feedback-latest"
    assert frame.loc[1, "label_id"] == "feedback-older"


def test_unit_activity_summary_marks_active_operations():
    latest_snapshot = pd.DataFrame(
        [
            {
                "pasture_id": "P-001",
                "name": "North Pasture",
                "acres": 120.0,
                "centroid_lat": 32.1,
                "centroid_lon": -99.4,
                "geometry": [[[-99.4, 32.1], [-99.39, 32.1], [-99.39, 32.11], [-99.4, 32.1]]][0],
                "pasture_condition_score": 58.0,
                "drought_category": "D1",
                "grazing_pressure": 0.42,
                "water_risk_score": 35.0,
                "stocking_risk_score": 41.0,
                "recommendation": "REST",
                "notes": "Source notes",
            }
        ]
    )
    vegetation_summary = pd.DataFrame(
        [
            {
                "pasture_id": "P-001",
                "ndvi_status": "Below normal",
                "ndvi_anomaly_percent": -12.5,
            }
        ]
    )
    profile = RanchProfile(
        ranch_type="horse property",
        management_style="horse turnout",
        livestock_species=["horses"],
    )
    livestock_groups = {
        "mares": LivestockGroup(
            group_id="mares",
            group_name="Broodmares",
            species="horses",
            animal_count=12,
            assigned_unit_id="P-001",
        )
    }
    units = build_management_units(
        latest_snapshot,
        vegetation_summary,
        profile,
        livestock_groups=livestock_groups,
    )
    events = {
        "activity-1": UnitActivityEvent(
            event_id="activity-1",
            unit_id="P-001",
            activity_type="horse turnout",
            livestock_group_id="mares",
            start_date="2026-05-01",
            end_date="2026-05-10",
            notes="Morning turnout block.",
        )
    }

    activity_summary = build_unit_activity_summary_lookup(
        events,
        livestock_groups,
        units,
        as_of=pd.Timestamp("2026-05-04"),
    )
    units = attach_activity_summaries(units, activity_summary)
    frame = management_units_frame(units)

    assert activity_summary["P-001"].status_label == "Active"
    assert activity_summary["P-001"].current_activity == "Horse Turnout"
    assert activity_summary["P-001"].current_group_label == "Broodmares (horses)"
    assert frame.loc[0, "current_status"] == "Active"
    assert frame.loc[0, "current_activity"] == "Horse Turnout"


def test_group_load_and_unit_utilization_summaries():
    latest_snapshot = pd.DataFrame(
        [
            {
                "pasture_id": "P-001",
                "name": "North Pasture",
                "acres": 100.0,
                "centroid_lat": 32.1,
                "centroid_lon": -99.4,
                "geometry": [[[-99.4, 32.1], [-99.39, 32.1], [-99.39, 32.11], [-99.4, 32.1]]][0],
                "pasture_condition_score": 58.0,
                "drought_category": "D1",
                "grazing_pressure": 0.42,
                "water_risk_score": 35.0,
                "stocking_risk_score": 41.0,
                "recommendation": "REST",
                "notes": "Source notes",
            }
        ]
    )
    vegetation_summary = pd.DataFrame(
        [
            {
                "pasture_id": "P-001",
                "ndvi_status": "Below normal",
                "ndvi_anomaly_percent": -12.5,
            }
        ]
    )
    profile = RanchProfile(
        ranch_type="rotational cattle ranch",
        management_style="rotational grazing",
        livestock_species=["cattle"],
    )
    livestock_groups = {
        "cow-calf": LivestockGroup(
            group_id="cow-calf",
            group_name="Cow-Calf Pairs",
            species="cattle",
            animal_count=50,
            average_weight=1000.0,
            assigned_unit_id="P-001",
        )
    }
    units = build_management_units(
        latest_snapshot,
        vegetation_summary,
        profile,
        livestock_groups=livestock_groups,
    )
    events = {
        "activity-1": UnitActivityEvent(
            event_id="activity-1",
            unit_id="P-001",
            activity_type="grazing / occupancy",
            livestock_group_id="cow-calf",
            start_date="2026-05-01",
            end_date="2026-05-05",
            notes="Short rotation pass.",
        )
    }

    group_load = build_livestock_group_load_summaries(
        livestock_groups,
        events,
        units,
        as_of=pd.Timestamp("2026-05-10"),
        lookback_days=30,
    )
    utilization = build_unit_utilization_summaries(
        units,
        livestock_groups,
        events,
        as_of=pd.Timestamp("2026-05-10"),
        lookback_days=30,
    )
    units = attach_utilization_summaries(units, utilization)
    unit_frame = management_units_frame(units)
    group_frame = livestock_group_load_frame(group_load)
    utilization_frame = unit_utilization_frame(utilization, units)

    assert group_load["cow-calf"].occupancy_days_30 == 5
    assert group_load["cow-calf"].animal_unit_days_30 == 250.0
    assert group_load["cow-calf"].occupied_units_30 == 1
    assert utilization["P-001"].occupancy_days_30 == 5
    assert utilization["P-001"].animal_unit_days_30 == 250.0
    assert utilization["P-001"].utilization_per_acre_30 == 2.5
    assert utilization["P-001"].utilization_label == "Elevated"
    assert utilization["P-001"].rest_days_since_occupancy == 5
    assert unit_frame.loc[0, "utilization_label"] == "Elevated"
    assert group_frame.loc[0, "animal_unit_days_30"] == 250.0
    assert utilization_frame.loc[0, "utilization_per_acre_30"] == 2.5


def test_operation_planner_suggests_rest_for_high_pressure_active_unit():
    latest_snapshot = pd.DataFrame(
        [
            {
                "pasture_id": "P-001",
                "name": "North Pasture",
                "acres": 100.0,
                "centroid_lat": 32.1,
                "centroid_lon": -99.4,
                "geometry": [[[-99.4, 32.1], [-99.39, 32.1], [-99.39, 32.11], [-99.4, 32.1]]][0],
                "pasture_condition_score": 42.0,
                "drought_category": "D2",
                "grazing_pressure": 0.68,
                "water_risk_score": 61.0,
                "stocking_risk_score": 74.0,
                "recommendation": "REDUCE STOCKING",
                "notes": "Source notes",
            }
        ]
    )
    vegetation_summary = pd.DataFrame(
        [{"pasture_id": "P-001", "ndvi_status": "Below normal", "ndvi_anomaly_percent": -18.0}]
    )
    profile = RanchProfile(
        ranch_type="rotational cattle ranch",
        management_style="rotational grazing",
        livestock_species=["cattle"],
    )
    livestock_groups = {
        "cow-calf": LivestockGroup(
            group_id="cow-calf",
            group_name="Cow-Calf Pairs",
            species="cattle",
            animal_count=50,
            average_weight=1000.0,
            assigned_unit_id="P-001",
        )
    }
    units = build_management_units(
        latest_snapshot,
        vegetation_summary,
        profile,
        overrides={"P-001": ManagementUnitOverride(unit_id="P-001", assigned_group_ids=["cow-calf"])},
        livestock_groups=livestock_groups,
    )
    events = {
        "activity-1": UnitActivityEvent(
            event_id="activity-1",
            unit_id="P-001",
            activity_type="grazing / occupancy",
            livestock_group_id="cow-calf",
            start_date="2026-05-01",
            end_date="2026-05-06",
            notes="Current rotation pass.",
        )
    }
    activity_summary = build_unit_activity_summary_lookup(events, livestock_groups, units, as_of=pd.Timestamp("2026-05-04"))
    utilization = build_unit_utilization_summaries(units, livestock_groups, events, as_of=pd.Timestamp("2026-05-04"))
    units = attach_activity_summaries(units, activity_summary)
    units = attach_utilization_summaries(units, utilization)

    suggestions = build_operation_planner_suggestions(units, profile, livestock_groups, as_of=pd.Timestamp("2026-05-04"))

    assert suggestions[0].suggested_activity_type == "rest / recovery"
    assert suggestions[0].urgency in {"High", "Elevated"}


def test_operation_planner_suggests_grazing_for_recovered_rotational_unit():
    latest_snapshot = pd.DataFrame(
        [
            {
                "pasture_id": "P-001",
                "name": "North Pasture",
                "acres": 100.0,
                "centroid_lat": 32.1,
                "centroid_lon": -99.4,
                "geometry": [[[-99.4, 32.1], [-99.39, 32.1], [-99.39, 32.11], [-99.4, 32.1]]][0],
                "pasture_condition_score": 81.0,
                "drought_category": "D0",
                "grazing_pressure": 0.18,
                "water_risk_score": 18.0,
                "stocking_risk_score": 24.0,
                "recommendation": "GRAZE",
                "notes": "Source notes",
            }
        ]
    )
    vegetation_summary = pd.DataFrame(
        [{"pasture_id": "P-001", "ndvi_status": "Near normal", "ndvi_anomaly_percent": 4.0}]
    )
    profile = RanchProfile(
        ranch_type="rotational cattle ranch",
        management_style="rotational grazing",
        livestock_species=["cattle"],
    )
    livestock_groups = {
        "cow-calf": LivestockGroup(
            group_id="cow-calf",
            group_name="Cow-Calf Pairs",
            species="cattle",
            animal_count=50,
            average_weight=1000.0,
            assigned_unit_id="P-001",
        )
    }
    units = build_management_units(
        latest_snapshot,
        vegetation_summary,
        profile,
        overrides={"P-001": ManagementUnitOverride(unit_id="P-001", assigned_group_ids=["cow-calf"])},
        livestock_groups=livestock_groups,
    )
    events = {
        "activity-1": UnitActivityEvent(
            event_id="activity-1",
            unit_id="P-001",
            activity_type="rest / recovery",
            livestock_group_id="cow-calf",
            start_date="2026-04-20",
            end_date="2026-04-27",
            notes="Prior rest block.",
        )
    }
    activity_summary = build_unit_activity_summary_lookup(events, livestock_groups, units, as_of=pd.Timestamp("2026-05-04"))
    utilization = build_unit_utilization_summaries(units, livestock_groups, events, as_of=pd.Timestamp("2026-05-04"))
    units = attach_activity_summaries(units, activity_summary)
    units = attach_utilization_summaries(units, utilization)

    suggestions = build_operation_planner_suggestions(units, profile, livestock_groups, as_of=pd.Timestamp("2026-05-04"))

    assert suggestions[0].suggested_activity_type == "grazing / occupancy"
    assert suggestions[0].suggested_group_id == "cow-calf"
