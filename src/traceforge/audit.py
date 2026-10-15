"""Deterministic model-health and point-in-time checks for TraceForge cases."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .ingest import load_csv_rows
from .models import ModelAuditFinding, RiskLevel, RootCauseCategory


def load_json_object(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"JSON file does not exist: {file_path}")
    try:
        value = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {file_path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON file must contain an object: {file_path}")
    return value


def load_model_report(path: str | Path) -> dict[str, Any]:
    return load_json_object(path)


def load_prediction_rows(path: str | Path) -> list[dict[str, str]]:
    return load_csv_rows(path)


def _parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _finding(
    finding_id: str,
    category: RootCauseCategory,
    severity: RiskLevel,
    title: str,
    description: str,
    *,
    metric: float | None = None,
    evidence: tuple[str, ...] = (),
    disposition: str = "review",
) -> ModelAuditFinding:
    return ModelAuditFinding(
        finding_id=finding_id,
        category=category,
        severity=severity,
        title=title,
        description=description,
        metric=metric,
        evidence=evidence,
        disposition=disposition,
    )


def audit_model(
    report: dict[str, Any],
    predictions: list[dict[str, str]] | None = None,
    incident_start_at: str | None = None,
) -> list[ModelAuditFinding]:
    """Audit declared features, quality metadata, drift, and early warning.

    This is intentionally a conservative baseline. Predictions after the
    incident begins cannot be counted as actionable early warning evidence.
    """

    findings: list[ModelAuditFinding] = []
    declared_features = set(report.get("declared_features", []))
    if report.get("train_test_overlap") is True:
        findings.append(
            _finding(
                "AUD-003",
                RootCauseCategory.DATA_PIPELINE,
                RiskLevel.HIGH,
                "Possible train/test overlap",
                "The model report marks training and evaluation records as overlapping.",
                evidence=("model_report.train_test_overlap",),
                disposition="remove_overlap_and_rerun",
            )
        )

    if "active_alarm_code" in declared_features:
        findings.append(
            _finding(
                "AUD-001",
                RootCauseCategory.DATA_PIPELINE,
                RiskLevel.HIGH,
                "Alarm feature can leak the target event",
                "active_alarm_code begins when the machine is already in an alarm state and cannot provide early warning.",
                evidence=("model_manifest.declared_features.active_alarm_code",),
                disposition="remove_from_training_and_inference",
            )
        )

    missing_physical_signals = sorted(
        {"coolant_flow_l_min", "coolant_pressure_bar"} - declared_features
    )
    if missing_physical_signals:
        findings.append(
            _finding(
                "AUD-002",
                RootCauseCategory.MODEL,
                RiskLevel.HIGH,
                "Primary coolant restriction signals are absent",
                "The model does not declare the coolant flow and pressure signals needed to detect the incident's physical precursor.",
                evidence=tuple(f"model_manifest.missing_feature.{name}" for name in missing_physical_signals),
                disposition="add_features_and_retrain",
            )
        )

    calibration_error = report.get("calibration_error", report.get("expected_calibration_error"))
    if isinstance(calibration_error, (int, float)) and calibration_error > 0.1:
        findings.append(
            _finding(
                "AUD-004",
                RootCauseCategory.MODEL,
                RiskLevel.MEDIUM,
                "Model calibration error exceeds review threshold",
                "Predicted risk may not match observed failure frequency on the operational evaluation window.",
                metric=float(calibration_error),
                evidence=("model_report.calibration_error",),
                disposition="recalibrate_before_thresholding",
            )
        )

    drift = report.get("feature_drift", {})
    if isinstance(drift, dict):
        for feature, value in sorted(drift.items()):
            if isinstance(value, (int, float)) and value > 0.2:
                findings.append(
                    _finding(
                        f"AUD-DRIFT-{feature}",
                        RootCauseCategory.DRIFT,
                        RiskLevel.MEDIUM,
                        f"Feature drift: {feature}",
                        f"Feature distribution shift is {float(value):.1%}.",
                        metric=float(value),
                        evidence=(f"model_report.feature_drift.{feature}",),
                    )
                )

    reproducibility = report.get("reproducibility")
    if not isinstance(reproducibility, dict) or not reproducibility.get("data_version"):
        findings.append(
            _finding(
                "AUD-006",
                RootCauseCategory.CONFIGURATION,
                RiskLevel.LOW,
                "Missing reproducibility metadata",
                "A versioned training-data identifier is not recorded.",
                evidence=("model_report.reproducibility.data_version",),
                disposition="record_training_data_version",
            )
        )

    if predictions and incident_start_at:
        incident_start = _parse_timestamp(incident_start_at)
        threshold = float(report.get("decision_threshold", 0.65))
        cutoff = incident_start - timedelta(minutes=10)
        actionable_scores: list[float] = []
        late_alerts: list[dict[str, str]] = []
        for row in predictions:
            try:
                predicted_at = _parse_timestamp(row["predicted_at_utc"])
                score = float(row["score"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid prediction row: {row}") from exc
            if predicted_at <= cutoff:
                actionable_scores.append(score)
            if predicted_at >= incident_start and score >= threshold:
                late_alerts.append(row)
        max_actionable = max(actionable_scores, default=0.0)
        if max_actionable < threshold:
            findings.append(
                _finding(
                    "AUD-005",
                    RootCauseCategory.MODEL,
                    RiskLevel.MEDIUM,
                    "No actionable early warning before the incident",
                    f"The highest score at least ten minutes before the incident was {max_actionable:.2f}, below the {threshold:.2f} threshold.",
                    metric=max_actionable,
                    evidence=("predictions.csv.actionable_window",),
                    disposition="re-estimate_threshold_for_lead_time",
                )
            )
        if late_alerts:
            findings.append(
                _finding(
                    "AUD-007",
                    RootCauseCategory.MODEL,
                    RiskLevel.MEDIUM,
                    "Alert was emitted after the incident had started",
                    "A threshold-crossing prediction was late and must not be reported as preventive warning.",
                    metric=max(float(row["score"]) for row in late_alerts),
                    evidence=("predictions.csv.late_alert",),
                    disposition="separate_detection_from_early_warning",
                )
            )
    return findings
