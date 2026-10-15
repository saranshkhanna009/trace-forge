"""Stable graph representation for model-to-machine reliability evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ingest import stable_id
from .models import (
    Document,
    EvidenceHit,
    IncidentCase,
    ModelAuditFinding,
    RootCauseHypothesis,
    SensorAnomaly,
)


@dataclass(frozen=True)
class GraphNode:
    id: str
    kind: str
    properties: dict[str, Any]


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    relation: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReliabilityGraph:
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        self.edges.append(edge)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [
                {"id": n.id, "kind": n.kind, "properties": n.properties}
                for n in sorted(self.nodes.values(), key=lambda item: item.id)
            ],
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "relation": e.relation,
                    "properties": e.properties,
                }
                for e in sorted(self.edges, key=lambda item: (item.source, item.target, item.relation))
            ],
        }


def build_graph(
    case: IncidentCase,
    documents: list[Document],
    evidence_hits: list[EvidenceHit],
    anomalies: list[SensorAnomaly],
    findings: list[ModelAuditFinding],
    root_causes: list[RootCauseHypothesis],
) -> ReliabilityGraph:
    graph = ReliabilityGraph()
    case_id = stable_id("case", case.id)
    asset_id = stable_id("asset", case.asset_id)
    model_id = stable_id("model", case.id, case.asset_id)
    graph.add_node(
        GraphNode(
            case_id,
            "IncidentCase",
            {"id": case.id, "description": case.description, "observed_at": case.observed_at},
        )
    )
    graph.add_node(GraphNode(asset_id, "Asset", {"asset_id": case.asset_id, "asset_type": case.asset_type}))
    graph.add_node(GraphNode(model_id, "Model", {"case_id": case.id}))
    graph.add_edge(GraphEdge(case_id, asset_id, "INVOLVES_ASSET"))
    graph.add_edge(GraphEdge(asset_id, model_id, "MONITORED_BY_MODEL"))

    for document in documents:
        graph.add_node(GraphNode(document.id, "Document", {"path": document.path, "title": document.title}))
    for hit in evidence_hits:
        chunk = hit.chunk
        graph.add_node(
            GraphNode(
                chunk.id,
                "EvidenceSpan",
                {
                    "document_id": chunk.document_id,
                    "section": chunk.section,
                    "start_char": chunk.start_char,
                    "end_char": chunk.end_char,
                    "text": chunk.text,
                },
            )
        )
        graph.add_edge(GraphEdge(chunk.document_id, chunk.id, "DOCUMENT_CONTAINS_EVIDENCE"))
        graph.add_edge(
            GraphEdge(
                chunk.id,
                case_id,
                "EVIDENCE_RELEVANT_TO_CASE",
                {"retrieval_score": hit.score, "overlap_terms": list(hit.overlap_terms)},
            )
        )

    for anomaly in anomalies:
        anomaly_id = stable_id("anomaly", case.id, anomaly.sensor)
        sensor_id = stable_id("sensor", case.asset_id, anomaly.sensor)
        graph.add_node(
            GraphNode(
                sensor_id,
                "Sensor",
                {"asset_id": case.asset_id, "name": anomaly.sensor},
            )
        )
        graph.add_node(
            GraphNode(
                anomaly_id,
                "SensorAnomaly",
                {
                    "sensor": anomaly.sensor,
                    "latest_value": anomaly.latest_value,
                    "baseline_mean": anomaly.baseline_mean,
                    "relative_change": anomaly.relative_change,
                    "severity": anomaly.severity.value,
                },
            )
        )
        graph.add_edge(GraphEdge(asset_id, sensor_id, "HAS_SENSOR"))
        graph.add_edge(GraphEdge(sensor_id, anomaly_id, "PRODUCED_ANOMALY"))
        graph.add_edge(GraphEdge(anomaly_id, case_id, "OBSERVED_IN_CASE"))

    for finding in findings:
        finding_id = stable_id("finding", case.id, finding.title)
        graph.add_node(
            GraphNode(
                finding_id,
                "ModelAuditFinding",
                {
                    "category": finding.category.value,
                    "severity": finding.severity.value,
                    "finding_id": finding.finding_id,
                    "title": finding.title,
                    "description": finding.description,
                    "metric": finding.metric,
                    "disposition": finding.disposition,
                },
            )
        )
        graph.add_edge(GraphEdge(model_id, finding_id, "HAS_AUDIT_FINDING"))
        graph.add_edge(GraphEdge(finding_id, case_id, "RELEVANT_TO_CASE"))

    for root_cause in root_causes:
        cause_id = stable_id("cause", case.id, root_cause.category.value, root_cause.title)
        graph.add_node(
            GraphNode(
                cause_id,
                "RootCauseHypothesis",
                {
                    "category": root_cause.category.value,
                    "score": root_cause.score,
                    "title": root_cause.title,
                    "rationale": root_cause.rationale,
                    "recommended_check": root_cause.recommended_check,
                    "status": root_cause.status,
                    "role": root_cause.role,
                },
            )
        )
        graph.add_edge(GraphEdge(cause_id, case_id, "HYPOTHESIS_FOR_CASE", {"score": root_cause.score}))
    return graph
