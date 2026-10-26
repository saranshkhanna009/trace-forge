"""CNC manufacturing investigation logic and deterministic report writers."""

from __future__ import annotations

import csv
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audit import audit_model, load_json_object, load_prediction_rows
from .graph import build_graph
from .ingest import load_case, load_case_documents, load_csv_rows
from .models import (
    EvidenceHit,
    IncidentCase,
    ReliabilityResult,
    RiskLevel,
    RootCauseCategory,
    RootCauseHypothesis,
    SensorAnomaly,
)
from .retrieval import retrieve
from .telemetry import detect_anomalies, load_telemetry


KEY_SIGNALS = (
    "coolant_flow_l_min",
    "coolant_pressure_bar",
    "coolant_pump_current_a",
    "spindle_bearing_temp_c",
    "spindle_vibration_rms_mm_s",
    "spindle_load_pct",
)

SPINDLE_BEARING_SIGNALS = (
    "spindle_bearing_temp_c",
    "spindle_vibration_rms_mm_s",
    "spindle_motor_current_a",
    "spindle_load_pct",
)

GENERIC_PROBLEM_CONFIG: dict[str, dict[str, Any]] = {
    "cnc_tool_wear": {
        "signals": ("tool_runtime_min", "spindle_load_pct", "cutting_force_n", "tool_vibration_rms_mm_s"),
        "query": "tool wear cutting force vibration acoustic insert inspection maintenance",
        "title": "CNC tool wear and edge failure",
        "rationale": "Tool runtime, cutting force, and vibration increased together; maintenance confirmed edge degradation and the replacement restored the validation part.",
        "check": "Inspect the tool edge, compare runtime against the approved tool-life limit, and verify the next validation part.",
        "symptom": "Cutting force and vibration escalation caused the quality failure",
    },
    "robot_arm_joint_wear": {
        "signals": ("joint_3_torque_nm", "joint_3_position_error_mm", "servo_current_a", "joint_3_temp_c"),
        "query": "robot joint gearbox backlash lubrication torque position error servo maintenance",
        "title": "Robot Joint 3 gearbox wear",
        "rationale": "Joint torque, position error, and servo current increased during repeated assembly cycles; maintenance found gearbox lubrication loss and validated accuracy after service.",
        "check": "Inspect Joint 3 lubrication and backlash, then run a calibrated positional-accuracy validation across repeated assembly cycles.",
        "symptom": "Joint position error caused assembly misalignment",
    },
    "conveyor_motor_overheating": {
        "signals": ("motor_current_a", "motor_temp_c", "motor_vibration_mm_s", "belt_speed_m_s"),
        "query": "conveyor motor overheating bearing friction overload vibration maintenance",
        "title": "Conveyor drive-motor overheating",
        "rationale": "Drive current, motor temperature, and vibration rose while belt speed fell; maintenance found a seized drive bearing and validated normal operation after replacement.",
        "check": "Inspect drive bearings and belt loading, measure motor temperature under a controlled load, and confirm stable speed.",
        "symptom": "Motor thermal overload caused conveyor stoppage",
    },
    "conveyor_belt_misalignment": {
        "signals": ("belt_offset_mm", "drive_current_a", "roller_vibration_mm_s", "belt_speed_m_s"),
        "query": "conveyor belt tracking misalignment roller friction edge damage maintenance",
        "title": "Conveyor belt tracking misalignment",
        "rationale": "Belt offset and roller vibration increased while drive current rose; maintenance found a skewed tracking roller and validated alignment after correction.",
        "check": "Check tracking rollers and belt tension, then run the conveyor at production load while measuring edge offset.",
        "symptom": "Belt tracking error caused edge contact and line interruption",
    },
    "hydraulic_press_pressure_loss": {
        "signals": ("hydraulic_pressure_bar", "ram_force_kn", "oil_temp_c", "pump_current_a"),
        "query": "hydraulic press pressure loss seal leakage pump force forming defect maintenance",
        "title": "Hydraulic-press pressure loss from seal leakage",
        "rationale": "Hydraulic pressure and ram force declined while oil temperature and pump current rose; maintenance confirmed a leaking seal and validated forming force after repair.",
        "check": "Inspect cylinder seals and hydraulic oil condition, then verify pressure and ram force through a controlled forming cycle.",
        "symptom": "Insufficient forming force caused dimensional defects",
    },
    "welding_quality_degradation": {
        "signals": ("weld_current_a", "arc_voltage_v", "shielding_gas_flow_l_min", "torch_temp_c"),
        "query": "welding arc gas flow porosity weld quality torch maintenance",
        "title": "Welding arc instability from shielding-gas restriction",
        "rationale": "Shielding-gas flow fell while arc voltage and torch temperature became unstable; maintenance found a restricted regulator and validated weld quality after service.",
        "check": "Inspect the gas regulator and torch path, verify flow at the nozzle, and complete a destructive or approved weld-quality validation.",
        "symptom": "Arc instability caused porosity in the weld inspection",
    },
    "injection_molding_drift": {
        "signals": ("melt_temp_c", "mold_temp_c", "injection_pressure_bar", "cycle_time_s"),
        "query": "injection molding heater temperature pressure flash warping quality maintenance",
        "title": "Injection-molding thermal-process drift",
        "rationale": "Melt temperature and injection pressure drifted beyond the validated recipe window; maintenance found a heater-control fault and the validation parts passed after repair.",
        "check": "Calibrate the temperature loop, inspect heater zones, and validate fill pressure and part dimensions across consecutive cycles.",
        "symptom": "Thermal and pressure drift caused warped parts",
    },
    "compressor_surge_overheating": {
        "signals": ("discharge_pressure_bar", "airflow_m3_min", "discharge_temp_c", "motor_current_a"),
        "query": "air compressor surge overheating filter lubrication pressure airflow maintenance",
        "title": "Air-compressor overheating from airflow restriction",
        "rationale": "Airflow fell while discharge pressure, temperature, and motor current rose; maintenance found a blocked intake filter and validated stable compressor operation after replacement.",
        "check": "Inspect the intake filter and lubrication circuit, then verify pressure, airflow, and discharge temperature under production demand.",
        "symptom": "Reduced airflow caused compressor thermal trip",
    },
}


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _number(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _case_file(root: Path, relative_path: str | None) -> Path | None:
    return None if not relative_path else root / relative_path


def _load_optional_rows(root: Path, relative_path: str | None) -> list[dict[str, str]]:
    path = _case_file(root, relative_path)
    return [] if path is None else load_csv_rows(path)


def _median(rows: list[dict[str, str]], field: str) -> float | None:
    values = [value for value in (_number(row.get(field)) for row in rows) if value is not None]
    return None if not values else statistics.median(values)


def build_signal_summary(
    telemetry_rows: list[dict[str, str]],
    case: IncidentCase,
    signals: tuple[str, ...] = KEY_SIGNALS,
) -> list[dict[str, Any]]:
    """Compare a stable baseline with the incident window for case signals."""

    if not case.incident_start_at:
        return []
    incident_start = _parse_timestamp(case.incident_start_at)
    incident_end = _parse_timestamp(case.incident_end_at) if case.incident_end_at else incident_start
    baseline_end = (
        _parse_timestamp(case.baseline_end_at)
        if getattr(case, "baseline_end_at", None)
        else incident_start
    )
    baseline_rows = [
        row for row in telemetry_rows if _parse_timestamp(row["ts_utc"]) <= baseline_end
    ]
    incident_rows = [
        row
        for row in telemetry_rows
        if incident_start <= _parse_timestamp(row["ts_utc"]) <= incident_end
    ]
    if not incident_rows:
        before_start = [
            row for row in telemetry_rows if _parse_timestamp(row["ts_utc"]) <= incident_start
        ]
        incident_rows = before_start[-1:] or telemetry_rows[-1:]
    summary: list[dict[str, Any]] = []
    for signal in signals:
        baseline = _median(baseline_rows, signal)
        incident = _median(incident_rows, signal)
        if baseline is None or incident is None:
            continue
        absolute_change = incident - baseline
        percent_change = None if baseline == 0 else absolute_change / abs(baseline) * 100
        direction = "stable"
        if absolute_change > 0:
            direction = "increasing"
        elif absolute_change < 0:
            direction = "decreasing"
        first_abnormal = None
        denominator = max(abs(baseline), 1.0)
        for row in telemetry_rows:
            value = _number(row.get(signal))
            if value is not None and abs(value - baseline) / denominator >= 0.2:
                first_abnormal = row["ts_utc"]
                break
        summary.append(
            {
                "signal_name": signal,
                "baseline_median": round(baseline, 6),
                "incident_median": round(incident, 6),
                "absolute_change": round(absolute_change, 6),
                "percent_change": None if percent_change is None else round(percent_change, 6),
                "trend_direction": direction,
                "first_abnormal_at_utc": first_abnormal,
                "evidence_refs": [f"telemetry.csv#{signal}"],
            }
        )
    return summary


def _timeline(
    events: list[dict[str, str]],
    quality: list[dict[str, str]],
    maintenance: list[dict[str, str]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for row in events:
        entries.append(
            {
                "timestamp": row.get("ts_start_utc"),
                "type": row.get("event_type", "event"),
                "code": row.get("event_code"),
                "message": row.get("message"),
                "source": row.get("source"),
            }
        )
    for row in quality:
        measurement = row.get("quality_measurement", row.get("surface_finish_ra_um", "—"))
        limit = row.get("quality_limit", row.get("surface_finish_limit_um", "—"))
        unit = row.get("quality_unit", "µm" if row.get("surface_finish_ra_um") else "")
        label = row.get("quality_label", "Quality metric")
        entries.append(
            {
                "timestamp": row.get("inspected_at_utc"),
                "type": "quality",
                "code": row.get("failure_code"),
                "message": f"{label} {measurement} {unit} (limit {limit}); status {row.get('quality_status')}",
                "source": row.get("inspector_source"),
            }
        )
    for row in maintenance:
        entries.append(
            {
                "timestamp": row.get("ts_utc"),
                "type": "maintenance",
                "code": row.get("failure_mode_code"),
                "message": row.get("observation", row.get("action_type")),
                "source": row.get("evidence_ref"),
            }
        )
    entries.sort(key=lambda item: item.get("timestamp") or "")
    return entries


def _refs_for_hits(evidence_hits: list[EvidenceHit]) -> tuple[str, ...]:
    return tuple(hit.chunk.id for hit in evidence_hits[:3])


def _maintenance_refs(rows: list[dict[str, str]], mode: str) -> tuple[str, ...]:
    return tuple(
        row.get("evidence_ref", "")
        for row in rows
        if row.get("failure_mode_code") == mode and row.get("evidence_ref")
    )


def rank_cnc_root_causes(
    anomalies: list[SensorAnomaly],
    findings: list,
    evidence_hits: list[EvidenceHit],
    maintenance: list[dict[str, str]],
) -> list[RootCauseHypothesis]:
    """Rank CNC failure modes using telemetry plus independent maintenance proof."""

    hit_refs = _refs_for_hits(evidence_hits)
    coolant_refs = _maintenance_refs(maintenance, "coolant_starvation")
    tool_refs = _maintenance_refs(maintenance, "tool_wear")
    bearing_refs = _maintenance_refs(maintenance, "spindle_bearing_degradation")
    telemetry_ref = "telemetry.csv#coolant_flow_l_min"
    causes: list[RootCauseHypothesis] = []

    if coolant_refs:
        causes.append(
            RootCauseHypothesis(
                category=RootCauseCategory.PHYSICAL_ASSET,
                score=0.94,
                title="Coolant starvation from a clogged filter",
                rationale="Coolant flow and pressure fell while pump current rose; maintenance measured restriction and confirmed recovery after filter replacement.",
                recommended_check="Inspect the coolant filter and flush the coolant line before the next production cycle.",
                evidence_refs=(telemetry_ref, *coolant_refs, *hit_refs),
                status="confirmed",
                role="root_cause",
            )
        )
    else:
        causes.append(
            RootCauseHypothesis(
                category=RootCauseCategory.PHYSICAL_ASSET,
                score=0.58,
                title="Possible coolant starvation",
                rationale="Coolant signals are abnormal, but independent maintenance confirmation is not available in this case.",
                recommended_check="Perform an independent coolant-flow test and inspect the filter.",
                evidence_refs=(telemetry_ref, *hit_refs),
                status="suspected",
                role="root_cause",
            )
        )

    if tool_refs:
        causes.append(
            RootCauseHypothesis(
                category=RootCauseCategory.PHYSICAL_ASSET,
                score=0.78,
                title="Tool T12 wear contributed to chatter",
                rationale="The tool was near its runtime limit and maintenance found edge wear and chipping; replacing it restored the validation cut.",
                recommended_check="Replace or inspect T12 at the planned runtime interval and verify the next surface-finish result.",
                evidence_refs=("telemetry.csv#tool_runtime_min", *tool_refs, *hit_refs),
                status="confirmed",
                role="contributing_factor",
            )
        )

    causes.append(
        RootCauseHypothesis(
            category=RootCauseCategory.PHYSICAL_ASSET,
            score=0.91 if any("chatter" in (row.get("message") or "").lower() for row in maintenance) else 0.72,
            title="Cutting chatter caused the surface-finish failure",
            rationale="Vibration increased during the finishing pass and the produced surface roughness exceeded its limit.",
            recommended_check="Run a validation cut after coolant and tool correction and inspect vibration during the finishing pass.",
            evidence_refs=("telemetry.csv#spindle_vibration_rms_mm_s", *hit_refs),
            status="confirmed" if hit_refs else "suspected",
            role="symptom",
        )
    )

    if bearing_refs:
        causes.append(
            RootCauseHypothesis(
                category=RootCauseCategory.PHYSICAL_ASSET,
                score=0.18,
                title="Spindle-bearing degradation not confirmed",
                rationale="Temperature and vibration rose, but inspection found no bearing or lubrication defect and post-repair vibration normalized.",
                recommended_check="Continue scheduled spindle monitoring; do not replace the bearing based on this incident alone.",
                evidence_refs=("telemetry.csv#spindle_vibration_rms_mm_s", *bearing_refs),
                status="ruled_out",
                role="alternative",
            )
        )

    for finding in findings:
        causes.append(
            RootCauseHypothesis(
                category=finding.category,
                score=0.92 if finding.severity is RiskLevel.HIGH else 0.7,
                title=finding.title,
                rationale=finding.description,
                recommended_check=finding.disposition.replace("_", " ").capitalize(),
                evidence_refs=tuple(finding.evidence),
                status="needs_remediation",
                role="model_risk",
            )
        )
    causes.sort(key=lambda item: (-item.score, item.title))
    return causes


def rank_spindle_bearing_root_causes(
    anomalies: list[SensorAnomaly],
    findings: list,
    evidence_hits: list[EvidenceHit],
    maintenance: list[dict[str, str]],
) -> list[RootCauseHypothesis]:
    """Rank spindle-bearing failure modes using condition and work-order evidence."""

    hit_refs = _refs_for_hits(evidence_hits)
    bearing_refs = _maintenance_refs(maintenance, "spindle_bearing_degradation")
    tool_refs = _maintenance_refs(maintenance, "tool_wear")
    temperature_ref = "telemetry.csv#spindle_bearing_temp_c"
    vibration_ref = "telemetry.csv#spindle_vibration_rms_mm_s"
    current_ref = "telemetry.csv#spindle_motor_current_a"
    causes: list[RootCauseHypothesis] = []

    if bearing_refs:
        causes.append(
            RootCauseHypothesis(
                category=RootCauseCategory.PHYSICAL_ASSET,
                score=0.95,
                title="Spindle-bearing degradation from lubrication breakdown",
                rationale="Bearing temperature, vibration, and motor current rose together; maintenance found grease breakdown and race damage, then validated recovery after bearing service.",
                recommended_check="Inspect spindle-bearing lubrication and vibration before returning the machine to production; repeat the validation cut after service.",
                evidence_refs=(temperature_ref, vibration_ref, current_ref, *bearing_refs, *hit_refs),
                status="confirmed",
                role="root_cause",
            )
        )
    else:
        causes.append(
            RootCauseHypothesis(
                category=RootCauseCategory.PHYSICAL_ASSET,
                score=0.64,
                title="Possible spindle-bearing degradation",
                rationale="Temperature, vibration, and current moved above baseline, but independent bearing inspection evidence is not available.",
                recommended_check="Inspect bearing lubrication, radial play, and vibration spectrum before the next production cycle.",
                evidence_refs=(temperature_ref, vibration_ref, current_ref, *hit_refs),
                status="suspected",
                role="root_cause",
            )
        )

    causes.append(
        RootCauseHypothesis(
            category=RootCauseCategory.PHYSICAL_ASSET,
            score=0.88 if any(item.sensor == "spindle_vibration_rms_mm_s" for item in anomalies) else 0.7,
            title="Spindle thermal and vibration escalation",
            rationale="The condition signals escalated during the finishing cycle and coincided with a failed dimensional and surface-quality inspection.",
            recommended_check="Trend bearing temperature, vibration, and motor current together during a controlled validation cycle.",
            evidence_refs=(temperature_ref, vibration_ref, *hit_refs),
            status="confirmed" if anomalies else "suspected",
            role="symptom",
        )
    )

    if tool_refs:
        causes.append(
            RootCauseHypothesis(
                category=RootCauseCategory.PHYSICAL_ASSET,
                score=0.2,
                title="Tool wear was not the primary cause",
                rationale="The tool was inspected without a failure consistent with the temperature and vibration escalation; the bearing service restored the validation result.",
                recommended_check="Continue the normal tool-life check, but do not replace the tool as the primary corrective action for this incident.",
                evidence_refs=(*tool_refs, *hit_refs),
                status="ruled_out",
                role="alternative",
            )
        )

    for finding in findings:
        causes.append(
            RootCauseHypothesis(
                category=finding.category,
                score=0.92 if finding.severity is RiskLevel.HIGH else 0.7,
                title=finding.title,
                rationale=finding.description,
                recommended_check=finding.disposition.replace("_", " ").capitalize(),
                evidence_refs=tuple(finding.evidence),
                status="needs_remediation",
                role="model_risk",
            )
        )
    causes.sort(key=lambda item: (-item.score, item.title))
    return causes


def rank_generic_root_causes(
    case: IncidentCase,
    anomalies: list[SensorAnomaly],
    findings: list,
    evidence_hits: list[EvidenceHit],
    maintenance: list[dict[str, str]],
) -> list[RootCauseHypothesis]:
    """Rank the configured manufacturing problem using shared evidence contracts."""

    config = GENERIC_PROBLEM_CONFIG[case.problem_code or ""]
    mode = case.problem_code or "unknown"
    hit_refs = _refs_for_hits(evidence_hits)
    maintenance_refs = _maintenance_refs(maintenance, mode)
    signal_refs = tuple(f"telemetry.csv#{signal}" for signal in config["signals"])
    causes: list[RootCauseHypothesis] = []
    confirmed = bool(maintenance_refs)
    causes.append(
        RootCauseHypothesis(
            category=RootCauseCategory.PHYSICAL_ASSET,
            score=0.95 if confirmed else 0.62,
            title=config["title"] if confirmed else f"Possible {config['title'].lower()}",
            rationale=config["rationale"] if confirmed else f"{config['rationale']} Independent maintenance confirmation is not available.",
            recommended_check=config["check"],
            evidence_refs=(*signal_refs, *maintenance_refs, *hit_refs),
            status="confirmed" if confirmed else "suspected",
            role="root_cause",
        )
    )
    causes.append(
        RootCauseHypothesis(
            category=RootCauseCategory.PHYSICAL_ASSET,
            score=0.86 if anomalies else 0.7,
            title=config["symptom"],
            rationale="The primary condition signals moved outside their baseline during the incident window and coincided with the failed production-quality check.",
            recommended_check="Trend the primary condition signals together during a controlled validation cycle.",
            evidence_refs=(*signal_refs[:3], *hit_refs),
            status="confirmed" if anomalies else "suspected",
            role="symptom",
        )
    )
    for finding in findings:
        causes.append(
            RootCauseHypothesis(
                category=finding.category,
                score=0.92 if finding.severity is RiskLevel.HIGH else 0.7,
                title=finding.title,
                rationale=finding.description,
                recommended_check=finding.disposition.replace("_", " ").capitalize(),
                evidence_refs=tuple(finding.evidence),
                status="needs_remediation",
                role="model_risk",
            )
        )
    causes.sort(key=lambda item: (-item.score, item.title))
    return causes


def analyze_cnc_case(case_dir: str | Path, top_k: int = 5) -> ReliabilityResult:
    root = Path(case_dir)
    case = load_case(root)
    manifest_path = root / "manifest.json"
    manifest = load_json_object(manifest_path) if manifest_path.is_file() else {}
    if manifest and manifest.get("machine_id") not in (None, case.asset_id):
        raise ValueError(
            f"Manifest machine_id {manifest.get('machine_id')!r} does not match case asset_id {case.asset_id!r}"
        )
    telemetry_path = root / case.telemetry_file
    telemetry_rows = load_csv_rows(telemetry_path)
    telemetry = load_telemetry(telemetry_path)
    report_path = root / (case.model_manifest_file or case.model_report_file)
    model_report = load_json_object(report_path)
    predictions = _load_optional_rows(root, case.predictions_file)
    labels = _load_optional_rows(root, case.labels_file)
    events = _load_optional_rows(root, case.events_file)
    quality = _load_optional_rows(root, case.production_quality_file)
    maintenance = _load_optional_rows(root, case.maintenance_file)
    documents, chunks = load_case_documents(root, case)

    generic_config = GENERIC_PROBLEM_CONFIG.get(case.problem_code or "")
    case_signals = (
        SPINDLE_BEARING_SIGNALS
        if case.problem_code == "spindle_bearing_degradation"
        else generic_config["signals"]
        if generic_config
        else KEY_SIGNALS
    )
    anomalies = [
        anomaly
        for anomaly in detect_anomalies(telemetry, baseline_end_at=case.baseline_end_at)
        if anomaly.sensor in case_signals
    ]
    findings = audit_model(model_report, predictions, case.incident_start_at)
    query = (
        "spindle bearing lubrication grease vibration temperature motor current inspection maintenance incident"
        if case.problem_code == "spindle_bearing_degradation"
        else generic_config["query"]
        if generic_config
        else "coolant filter pressure flow vibration chatter tool wear spindle maintenance incident"
    )
    evidence_hits = retrieve(query, chunks, top_k=top_k)
    root_causes = (
        rank_spindle_bearing_root_causes(anomalies, findings, evidence_hits, maintenance)
        if case.problem_code == "spindle_bearing_degradation"
        else rank_generic_root_causes(case, anomalies, findings, evidence_hits, maintenance)
        if generic_config
        else rank_cnc_root_causes(anomalies, findings, evidence_hits, maintenance)
    )
    timeline = _timeline(events, quality, maintenance)
    signal_summary = build_signal_summary(telemetry_rows, case, signals=case_signals)
    data_quality = {
        "telemetry_rows": len(telemetry_rows),
        "telemetry_fields": sorted(telemetry_rows[0]) if telemetry_rows else [],
        "telemetry_missing_fields": sorted(
            {
                field
                for row in telemetry_rows
                for field, value in row.items()
                if value in (None, "")
            }
        ),
        "document_count": len(documents),
        "maintenance_count": len(maintenance),
        "prediction_count": len(predictions),
        "label_count": len(labels),
        "manifest_schema_version": manifest.get("schema_version"),
    }
    warnings: list[str] = []
    if not maintenance:
        warnings.append("Maintenance evidence is absent; physical root causes remain suspected.")
    if not evidence_hits:
        warnings.append("No maintenance-document evidence was retrieved.")
    if not predictions:
        warnings.append("Predictions are absent; early-warning audit is incomplete.")
    status = "CRITICAL" if any(item.severity is RiskLevel.HIGH for item in anomalies + findings) else "NEEDS_REVIEW"
    return ReliabilityResult(
        case=case,
        status=status,
        anomalies=anomalies,
        model_findings=findings,
        evidence_hits=evidence_hits,
        root_causes=root_causes,
        timeline=timeline,
        signal_summary=signal_summary,
        maintenance_evidence=maintenance,
        quality_records=quality,
        model_audit_status="needs_remediation" if findings else "not_evaluated",
        data_quality=data_quality,
        graph=build_graph(case, documents, evidence_hits, anomalies, findings, root_causes),
        warnings=warnings,
    )


def incident_report(result: ReliabilityResult) -> dict[str, Any]:
    """Build the stable JSON report contract for manufacturing incidents."""

    primary = next((cause for cause in result.root_causes if cause.role == "root_cause"), None)
    contributing = [cause for cause in result.root_causes if cause.role == "contributing_factor"]
    return {
        "schema_version": "traceforge.incident.v1",
        "incident_id": result.case.id,
        "machine_id": result.case.asset_id,
        "incident_start_utc": result.case.incident_start_at,
        "incident_end_utc": result.case.incident_end_at,
        "severity": result.status.lower(),
        "root_cause": None if primary is None else {
            "failure_mode_code": result.case.problem_code or ("coolant_starvation" if "coolant" in primary.title.lower() else primary.title),
            "status": primary.status,
            "confidence": primary.score,
            "role": primary.role,
            "evidence_refs": list(primary.evidence_refs),
        },
        "contributing_factors": [
            {"title": item.title, "status": item.status, "confidence": item.score, "evidence_refs": list(item.evidence_refs)}
            for item in contributing
        ],
        "timeline": result.timeline,
        "signal_summary": result.signal_summary,
        "ranked_failure_modes": result.to_dict()["root_causes"],
        "maintenance_evidence": result.maintenance_evidence,
        "model_audit_summary": {
            "status": result.model_audit_status,
            "findings": result.to_dict()["model_findings"],
            "max_actionable_score": next(
                (finding["metric"] for finding in result.to_dict()["model_findings"] if finding["finding_id"] == "AUD-005"),
                None,
            ),
        },
        "data_quality": result.data_quality,
        "evidence_refs": [item["chunk_id"] for item in result.to_dict()["evidence"]],
    }


def write_reports(result: ReliabilityResult, report_dir: str | Path) -> Path:
    """Write JSON, Markdown, and signal CSV artifacts for a manufacturing case."""

    import json

    directory = Path(report_dir)
    directory.mkdir(parents=True, exist_ok=True)
    report = incident_report(result)
    (directory / "incident_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    headings = [
        "Executive summary",
        "Asset and operating context",
        "Incident timeline",
        "Signal comparison",
        "Ranked failure modes",
        "Maintenance evidence",
        "Model behavior",
        "Model audit findings",
        "Root-cause conclusion",
        "Recommended corrective actions",
        "Data-quality limitations",
        "Evidence index",
    ]
    primary = report["root_cause"]
    lines = [f"# Incident {result.case.id}", "", "## Executive summary", ""]
    lines.append(f"Status: **{result.status}**. Primary hypothesis: **{primary['failure_mode_code'] if primary else 'unconfirmed'}**.")
    for heading in headings[1:]:
        lines.extend(["", f"## {heading}", ""])
        if heading == "Root-cause conclusion":
            lines.append(json.dumps(primary, indent=2) if primary else "No root cause was confirmed.")
        elif heading == "Ranked failure modes":
            lines.extend(f"- {item['score']:.2f}: {item['title']} ({item['status']})" for item in report["ranked_failure_modes"])
        elif heading == "Recommended corrective actions":
            lines.extend(f"- {item.recommended_check}" for item in result.root_causes[:5])
        elif heading == "Model audit findings":
            lines.extend(f"- {item['finding_id']}: {item['title']} ({item['severity']})" for item in report["model_audit_summary"]["findings"])
        elif heading == "Data-quality limitations":
            lines.append(json.dumps(result.data_quality, indent=2))
        elif heading == "Evidence index":
            lines.extend(f"- {item['chunk_id']}: {item['text']}" for item in result.to_dict()["evidence"])
        else:
            lines.append("See incident_report.json for the structured data.")
    (directory / "incident_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with (directory / "signal_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "incident_id", "signal_name", "baseline_median", "incident_median",
            "absolute_change", "percent_change", "trend_direction", "first_abnormal_at_utc",
            "evidence_refs",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in result.signal_summary:
            writer.writerow({**item, "incident_id": result.case.id, "evidence_refs": ";".join(item["evidence_refs"])})
    return directory
