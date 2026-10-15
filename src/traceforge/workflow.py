"""First end-to-end TraceForge case-analysis workflow."""

from __future__ import annotations

from pathlib import Path

from .audit import audit_model, load_model_report
from .graph import build_graph
from .ingest import load_case, load_case_documents
from .models import (
    EvidenceHit,
    IncidentCase,
    ModelAuditFinding,
    ReliabilityResult,
    RiskLevel,
    RootCauseCategory,
    RootCauseHypothesis,
    SensorAnomaly,
    TelemetryPoint,
)
from .retrieval import retrieve
from .telemetry import detect_anomalies, load_telemetry


def _risk_score(level: RiskLevel) -> float:
    return {RiskLevel.LOW: 0.45, RiskLevel.MEDIUM: 0.7, RiskLevel.HIGH: 0.92}[level]


def rank_root_causes(
    case: IncidentCase,
    anomalies: list[SensorAnomaly],
    findings: list[ModelAuditFinding],
    evidence_hits: list[EvidenceHit],
) -> list[RootCauseHypothesis]:
    """Turn independent signals into ranked, engineer-reviewable hypotheses."""

    evidence_refs = tuple(hit.chunk.id for hit in evidence_hits[:3])
    hypotheses: list[RootCauseHypothesis] = []
    for anomaly in anomalies:
        score = min(0.95, 0.55 + anomaly.relative_change / 2)
        hypotheses.append(
            RootCauseHypothesis(
                category=RootCauseCategory.SENSOR,
                score=round(score, 6),
                title=f"Abnormal sensor behavior: {anomaly.sensor}",
                rationale=(
                    f"The latest {anomaly.sensor} reading differs from baseline by "
                    f"{anomaly.relative_change:.1%}. This may reflect a sensor fault "
                    "or a physical change that the sensor is detecting."
                ),
                recommended_check=f"Inspect, calibrate, and compare the {anomaly.sensor} sensor with an independent reading.",
                evidence_refs=evidence_refs,
            )
        )

    for finding in findings:
        hypotheses.append(
            RootCauseHypothesis(
                category=finding.category,
                score=round(_risk_score(finding.severity), 6),
                title=finding.title,
                rationale=finding.description,
                recommended_check=(
                    "Rebuild the evaluation split and rerun the audit."
                    if finding.category is RootCauseCategory.DATA_PIPELINE
                    else "Re-evaluate the model on current telemetry and inspect the flagged artifact."
                ),
                evidence_refs=evidence_refs,
            )
        )

    if anomalies and findings:
        max_anomaly = max(anomaly.relative_change for anomaly in anomalies)
        max_finding = max(_risk_score(finding.severity) for finding in findings)
        hypotheses.append(
            RootCauseHypothesis(
                category=RootCauseCategory.CROSS_LAYER,
                score=round(min(0.98, max(max_anomaly, max_finding) + 0.05), 6),
                title="Cross-layer reliability issue",
                rationale=(
                    "Telemetry anomalies coincide with model-health findings. The "
                    "incident may involve both changed machine behavior and a model "
                    "or data pipeline that is not reliable under that behavior."
                ),
                recommended_check=(
                    "Replay the model against the incident window, validate sensor health, "
                    "and compare predictions before and after the detected drift."
                ),
                evidence_refs=evidence_refs,
            )
        )

    hypotheses.sort(key=lambda item: (-item.score, item.category.value, item.title))
    return hypotheses


def _status(anomalies: list[SensorAnomaly], findings: list[ModelAuditFinding]) -> str:
    high_risk = any(item.severity is RiskLevel.HIGH for item in anomalies + findings)
    if high_risk:
        return "CRITICAL"
    if anomalies or findings:
        return "NEEDS_REVIEW"
    return "NO_FINDINGS"


def prepare_case(case_dir: str | Path) -> tuple[IncidentCase, list[TelemetryPoint], dict, list, list]:
    """Load all case inputs; kept public for the optional LangGraph adapter."""

    root = Path(case_dir)
    case = load_case(root)
    telemetry = load_telemetry(root / case.telemetry_file)
    model_report = load_model_report(root / case.model_report_file)
    documents, chunks = load_case_documents(root, case)
    return case, telemetry, model_report, documents, chunks


def analyze_case(case_dir: str | Path, top_k: int = 5) -> ReliabilityResult:
    """Analyze one incident case without requiring a hosted model or API key."""

    case_config = load_case(case_dir)
    if case_config.domain == "cnc_manufacturing" or case_config.events_file:
        from .manufacturing import analyze_cnc_case

        return analyze_cnc_case(case_dir, top_k=top_k)

    case, telemetry, model_report, documents, chunks = prepare_case(case_dir)
    anomalies = detect_anomalies(telemetry)
    findings = audit_model(model_report)
    query_parts = [case.description]
    query_parts.extend(anomaly.sensor for anomaly in anomalies)
    query_parts.extend(finding.title for finding in findings)
    evidence_hits = retrieve(" ".join(query_parts), chunks, top_k=top_k)
    root_causes = rank_root_causes(case, anomalies, findings, evidence_hits)
    warnings: list[str] = []
    if not documents:
        warnings.append("The case has no .md or .txt maintenance documents.")
    if not evidence_hits:
        warnings.append("No relevant document evidence was retrieved for this case.")
    if not anomalies and not findings:
        warnings.append("No baseline anomaly or model-audit finding was detected.")
    graph = build_graph(case, documents, evidence_hits, anomalies, findings, root_causes)
    return ReliabilityResult(
        case=case,
        status=_status(anomalies, findings),
        anomalies=anomalies,
        model_findings=findings,
        evidence_hits=evidence_hits,
        root_causes=root_causes,
        graph=graph,
        warnings=warnings,
    )
