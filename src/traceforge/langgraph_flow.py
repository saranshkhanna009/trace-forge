"""Optional LangGraph orchestration for TraceForge's investigation flow."""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from .audit import audit_model
from .graph import build_graph
from .ingest import load_case_documents
from .models import (
    Document,
    EvidenceChunk,
    EvidenceHit,
    IncidentCase,
    ModelAuditFinding,
    ReliabilityResult,
    RootCauseHypothesis,
    SensorAnomaly,
    TelemetryPoint,
)
from .retrieval import retrieve
from .telemetry import detect_anomalies
from .workflow import _status, load_model_report, load_telemetry, load_case, rank_root_causes


class TraceForgeState(TypedDict, total=False):
    case_dir: str
    top_k: int
    case: IncidentCase
    telemetry: list[TelemetryPoint]
    model_report: dict[str, Any]
    documents: list[Document]
    chunks: list[EvidenceChunk]
    anomalies: list[SensorAnomaly]
    findings: list[ModelAuditFinding]
    evidence_hits: list[EvidenceHit]
    root_causes: list[RootCauseHypothesis]
    result: ReliabilityResult


def analyze_case_with_langgraph(case_dir: str | Path, top_k: int = 5) -> ReliabilityResult:
    """Run explicit load, analysis, retrieval, and correlation nodes."""

    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError(
            "LangGraph is optional. Install it with "
            '`python -m pip install -e ".[orchestration]"`.'
        ) from exc

    configured_case = load_case(case_dir)
    if configured_case.domain == "cnc_manufacturing":
        # The manufacturing workflow already owns the richer CSV contracts
        # (events, quality, maintenance, labels, and point-in-time scores).
        # Keep it behind a LangGraph node so the optional adapter cannot
        # silently fall back to the older generic industrial path.
        from .manufacturing import analyze_cnc_case

        class ManufacturingState(TypedDict, total=False):
            case_dir: str
            top_k: int
            result: ReliabilityResult

        def investigate_manufacturing(state: ManufacturingState) -> dict[str, object]:
            return {"result": analyze_cnc_case(state["case_dir"], top_k=state.get("top_k", 5))}

        manufacturing_graph = StateGraph(ManufacturingState)
        manufacturing_graph.add_node("investigate_cnc_case", investigate_manufacturing)
        manufacturing_graph.add_edge(START, "investigate_cnc_case")
        manufacturing_graph.add_edge("investigate_cnc_case", END)
        return manufacturing_graph.compile().invoke(
            {"case_dir": str(case_dir), "top_k": top_k}
        )["result"]

    def load_context(state: TraceForgeState) -> dict[str, object]:
        root = Path(state["case_dir"])
        case = load_case(root)
        documents, chunks = load_case_documents(root, case)
        return {
            "case": case,
            "telemetry": load_telemetry(root / case.telemetry_file),
            "model_report": load_model_report(root / case.model_report_file),
            "documents": documents,
            "chunks": chunks,
        }

    def inspect_telemetry(state: TraceForgeState) -> dict[str, object]:
        return {"anomalies": detect_anomalies(state.get("telemetry", []))}

    def audit_model_node(state: TraceForgeState) -> dict[str, object]:
        return {"findings": audit_model(state.get("model_report", {}))}

    def retrieve_evidence(state: TraceForgeState) -> dict[str, object]:
        case = state["case"]
        query_parts = [case.description]
        query_parts.extend(anomaly.sensor for anomaly in state.get("anomalies", []))
        query_parts.extend(finding.title for finding in state.get("findings", []))
        return {
            "evidence_hits": retrieve(
                " ".join(query_parts), state.get("chunks", []), top_k=state.get("top_k", 5)
            )
        }

    def correlate(state: TraceForgeState) -> dict[str, object]:
        case = state["case"]
        anomalies = state.get("anomalies", [])
        findings = state.get("findings", [])
        evidence_hits = state.get("evidence_hits", [])
        root_causes = rank_root_causes(case, anomalies, findings, evidence_hits)
        warnings: list[str] = []
        if not state.get("documents"):
            warnings.append("The case has no .md or .txt maintenance documents.")
        if not evidence_hits:
            warnings.append("No relevant document evidence was retrieved for this case.")
        return {
            "root_causes": root_causes,
            "result": ReliabilityResult(
                case=case,
                status=_status(anomalies, findings),
                anomalies=anomalies,
                model_findings=findings,
                evidence_hits=evidence_hits,
                root_causes=root_causes,
                graph=build_graph(
                    case,
                    state.get("documents", []),
                    evidence_hits,
                    anomalies,
                    findings,
                    root_causes,
                ),
                warnings=warnings,
            ),
        }

    builder = StateGraph(TraceForgeState)
    builder.add_node("load_context", load_context)
    builder.add_node("inspect_telemetry", inspect_telemetry)
    builder.add_node("audit_model", audit_model_node)
    builder.add_node("retrieve_evidence", retrieve_evidence)
    builder.add_node("correlate_findings", correlate)
    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "inspect_telemetry")
    builder.add_edge("load_context", "audit_model")
    builder.add_edge("load_context", "retrieve_evidence")
    builder.add_edge("inspect_telemetry", "correlate_findings")
    builder.add_edge("audit_model", "correlate_findings")
    builder.add_edge("retrieve_evidence", "correlate_findings")
    builder.add_edge("correlate_findings", END)
    return builder.compile().invoke({"case_dir": str(case_dir), "top_k": top_k})["result"]
