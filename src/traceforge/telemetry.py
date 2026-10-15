"""Transparent time-series loading and anomaly baseline."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path

from .ingest import load_csv_rows
from .models import RiskLevel, SensorAnomaly, TelemetryPoint


def load_telemetry(path: str | Path) -> list[TelemetryPoint]:
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Telemetry file does not exist: {file_path}")
    rows = load_csv_rows(file_path)
    timestamp_key = "ts_utc" if rows and "ts_utc" in rows[0] else "timestamp"
    if not rows or timestamp_key not in rows[0]:
        raise ValueError("Telemetry CSV must contain a timestamp or ts_utc column")
    points: list[TelemetryPoint] = []
    for row_number, row in enumerate(rows, start=2):
        values: dict[str, float] = {}
        for sensor, raw_value in row.items():
            if sensor == timestamp_key or raw_value in (None, ""):
                continue
            try:
                values[sensor] = float(raw_value)
            except (TypeError, ValueError):
                # Manufacturing telemetry includes categorical context such as
                # machine_state and tool_id. Those fields are retained by the
                # case CSV but are not numeric anomaly inputs.
                continue
        if not values:
            raise ValueError(f"No numeric telemetry values at row {row_number}")
        points.append(TelemetryPoint(timestamp=row[timestamp_key], values=values))
    if len(points) < 2:
        raise ValueError("Telemetry CSV must contain at least two data rows")
    return points


def _sample_standard_deviation(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def detect_anomalies(
    points: list[TelemetryPoint],
    relative_change_threshold: float = 0.2,
    baseline_end_at: str | None = None,
) -> list[SensorAnomaly]:
    """Compare the latest observation with the historical baseline.

    This is a transparent baseline, not the final deep-learning detector. It
    is useful for validating the end-to-end evidence and root-cause flow before
    introducing a TCN or temporal transformer.
    """

    if not points:
        return []
    sensors = sorted(points[0].values)
    if baseline_end_at:
        baseline_end = datetime.fromisoformat(baseline_end_at.replace("Z", "+00:00"))
        if baseline_end.tzinfo is None:
            baseline_end = baseline_end.replace(tzinfo=timezone.utc)
        baseline_points = [
            point
            for point in points
            if datetime.fromisoformat(point.timestamp.replace("Z", "+00:00")) <= baseline_end
        ]
    else:
        baseline_points = points[:-1]
    if not baseline_points:
        baseline_points = points[:-1]
    anomalies: list[SensorAnomaly] = []
    for sensor in sensors:
        baseline = [point.values[sensor] for point in baseline_points if sensor in point.values]
        latest = points[-1].values.get(sensor)
        if not baseline or latest is None:
            continue
        baseline_mean = sum(baseline) / len(baseline)
        denominator = max(abs(baseline_mean), 1.0)
        relative_change = abs(latest - baseline_mean) / denominator
        std = _sample_standard_deviation(baseline)
        z_score = None if std == 0 else abs(latest - baseline_mean) / std
        if relative_change < relative_change_threshold:
            continue
        severity = RiskLevel.HIGH if relative_change >= 0.5 else RiskLevel.MEDIUM
        direction = "increased" if latest > baseline_mean else "decreased"
        anomalies.append(
            SensorAnomaly(
                sensor=sensor,
                baseline_mean=baseline_mean,
                latest_value=latest,
                relative_change=relative_change,
                z_score=z_score,
                severity=severity,
                explanation=(
                    f"{sensor} {direction} by {relative_change:.1%} relative to its "
                    f"historical baseline."
                ),
            )
        )
    return anomalies
