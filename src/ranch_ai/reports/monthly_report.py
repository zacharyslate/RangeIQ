from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class MonthlyReportArtifacts:
    report_table: pd.DataFrame
    markdown: str


def build_monthly_ranch_report(
    latest_snapshot: pd.DataFrame,
    ranch_name: str,
    ranch_address: str,
) -> MonthlyReportArtifacts:
    report_rows = latest_snapshot[
        [
            "pasture_id",
            "name",
            "acres",
            "pasture_condition_score",
            "predicted_forage_score",
            "rainfall_deficit_30d",
            "drought_category",
            "grazing_pressure",
            "water_risk_score",
            "stocking_risk_score",
            "recommendation",
            "recommendation_reason",
        ]
    ].copy()

    report_rows = report_rows.sort_values(["water_risk_score", "stocking_risk_score"], ascending=[False, False]).reset_index(
        drop=True
    )

    report_date = pd.Timestamp(latest_snapshot["week_start"].max()).strftime("%B %Y")
    avg_condition = report_rows["pasture_condition_score"].mean()
    avg_water_risk = report_rows["water_risk_score"].mean()
    avg_stocking_risk = report_rows["stocking_risk_score"].mean()
    action_count = int(report_rows["recommendation"].isin(["SUPPLEMENT", "REDUCE STOCKING", "DESTOCK WARNING"]).sum())

    top_concern = report_rows.iloc[0]
    markdown = "\n".join(
        [
            f"# RangeIQ Monthly Report - {report_date}",
            "",
            f"**Ranch:** {ranch_name}",
            f"**Address:** {ranch_address}",
            "",
            "## Ranch Summary",
            f"- Average pasture condition score: {avg_condition:.1f}",
            f"- Average water risk score: {avg_water_risk:.1f}",
            f"- Average stocking risk score: {avg_stocking_risk:.1f}",
            f"- Pastures needing action this month: {action_count}",
            "",
            "## Priority Pasture",
            f"- {top_concern['pasture_id']} {top_concern['name']}",
            f"- Recommendation: {top_concern['recommendation']}",
            f"- Reason: {top_concern['recommendation_reason']}",
            "",
            "## Notes",
            "- This report uses synthetic weather, synthetic satellite indicators, and synthetic management data in the MVP.",
            "- Replace the starter corner-derived boundary with surveyed geometry if you need legal or engineering precision.",
        ]
    )

    return MonthlyReportArtifacts(report_table=report_rows, markdown=markdown)
