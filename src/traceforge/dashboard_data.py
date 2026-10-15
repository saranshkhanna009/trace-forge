"""Normalized view model used by the TraceForge dashboard.

The dashboard should render one consistent case model instead of parsing CSV,
JSON, and graph objects independently in every widget. This module keeps the
Streamlit layer thin and remains dependency-free so it can be tested locally.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .audit import load_json_object, load_prediction_rows
from .ingest import load_case, load_csv_rows
from .manufacturing import analyze_cnc_case
from .models import ReliabilityResult


@dataclass(frozen=True)
class DashboardCase:
    """All data needed to render one incident dashboard."""

    case_dir: Path
    result: ReliabilityResult
    telemetry_rows: tuple[dict[str, str], ...]
    prediction_rows: tuple[dict[str, str], ...]
    manifest: dict[str, Any]

    @property
    def case(self):
        return self.result.case

    @property
    def primary_root_cause(self):
        return next(
            (item for item in self.result.root_causes if item.role == "root_cause"),
            None,
        )

    @property
    def resolution_status(self) -> str:
        """Separate current resolution from historical incident severity."""

        has_pass = any(row.get("quality_status") == "pass" for row in self.result.quality_records)
        has_validation = any(row.get("status") == "validated" for row in self.result.maintenance_evidence)
        if has_pass and has_validation:
            return "VALIDATED"
        if self.result.maintenance_evidence:
            return "IN_REVIEW"
        return "UNKNOWN"

    @property
    def model_status(self) -> str:
        return self.result.model_audit_status or "NOT_EVALUATED"

    @property
    def evidence_by_id(self) -> dict[str, dict[str, Any]]:
        return {
            hit.chunk.id: {
                "document": hit.chunk.document_id,
                "section": hit.chunk.section,
                "text": hit.chunk.text,
                "start_char": hit.chunk.start_char,
                "end_char": hit.chunk.end_char,
                "score": hit.score,
            }
            for hit in self.result.evidence_hits
        }


def _manifest_path(root: Path) -> Path:
    return root / "manifest.json"


def load_dashboard_case(case_dir: str | Path, top_k: int = 5) -> DashboardCase:
    """Load and analyze a case for all dashboard personas."""

    root = Path(case_dir).expanduser().resolve()
    case = load_case(root)
    telemetry_path = root / case.telemetry_file
    telemetry_rows = load_csv_rows(telemetry_path)
    prediction_rows = (
        load_prediction_rows(root / case.predictions_file)
        if case.predictions_file and (root / case.predictions_file).is_file()
        else []
    )
    manifest = load_json_object(_manifest_path(root)) if _manifest_path(root).is_file() else {}
    if case.model_manifest_file:
        model_manifest_path = root / case.model_manifest_file
        if model_manifest_path.is_file():
            # Keep bundle metadata and model contract in one normalized view.
            manifest = {**manifest, **load_json_object(model_manifest_path)}
    result = analyze_cnc_case(root, top_k=top_k)
    return DashboardCase(
        case_dir=root,
        result=result,
        telemetry_rows=tuple(telemetry_rows),
        prediction_rows=tuple(prediction_rows),
        manifest=manifest,
    )


def numeric_telemetry_rows(
    dashboard_case: DashboardCase,
    signals: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Return chart-ready rows while preserving missing values as ``None``."""

    rows: list[dict[str, Any]] = []
    for row in dashboard_case.telemetry_rows:
        chart_row: dict[str, Any] = {"timestamp": row.get("ts_utc")}
        for signal in signals:
            raw = row.get(signal)
            try:
                chart_row[signal] = None if raw in (None, "") else float(raw)
            except (TypeError, ValueError):
                chart_row[signal] = None
        rows.append(chart_row)
    return rows


def prediction_chart_rows(dashboard_case: DashboardCase) -> list[dict[str, Any]]:
    """Return validated point-in-time prediction rows for the ML view."""

    rows: list[dict[str, Any]] = []
    for row in dashboard_case.prediction_rows:
        try:
            score = float(row["score"])
            threshold = float(row.get("decision_threshold", "0.65"))
        except (KeyError, TypeError, ValueError):
            continue
        rows.append(
            {
                "timestamp": row.get("predicted_at_utc"),
                "score": score,
                "threshold": threshold,
                "class": row.get("predicted_class"),
                "prediction_id": row.get("prediction_id"),
            }
        )
    return rows


def feature_coverage(dashboard_case: DashboardCase) -> list[dict[str, str]]:
    """Compare declared model features with observed telemetry fields."""

    declared = dashboard_case.manifest.get("declared_features", [])
    observed = set(dashboard_case.telemetry_rows[0]) if dashboard_case.telemetry_rows else set()
    rows: list[dict[str, str]] = []
    for feature in declared:
        status = "Observed"
        if feature not in observed:
            status = "Not observed"
        if feature == "active_alarm_code":
            status = "Leakage risk"
        rows.append({"feature": feature, "status": status})
    for feature in sorted({"coolant_flow_l_min", "coolant_pressure_bar"} - set(declared)):
        rows.append({"feature": feature, "status": "Missing from model"})
    return rows


def quality_before_after(dashboard_case: DashboardCase) -> list[dict[str, Any]]:
    """Return the failed and validation quality measurements."""

    rows: list[dict[str, Any]] = []
    for record in dashboard_case.result.quality_records:
        try:
            value = float(record["surface_finish_ra_um"])
            limit = float(record["surface_finish_limit_um"])
        except (KeyError, TypeError, ValueError):
            continue
        rows.append(
            {
                "timestamp": record.get("inspected_at_utc"),
                "label": record.get("quality_status", "unknown").upper(),
                "surface_finish_ra_um": value,
                "limit": limit,
            }
        )
    return rows
