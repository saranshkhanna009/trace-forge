"""Dependency-free domain types for the TraceForge reliability workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RootCauseCategory(str, Enum):
    PHYSICAL_ASSET = "PHYSICAL_ASSET"
    SENSOR = "SENSOR"
    DATA_PIPELINE = "DATA_PIPELINE"
    MODEL = "MODEL"
    DRIFT = "DRIFT"
    CONFIGURATION = "CONFIGURATION"
    CROSS_LAYER = "CROSS_LAYER"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Document:
    id: str
    path: str
    title: str
    text: str


@dataclass(frozen=True)
class EvidenceChunk:
    id: str
    document_id: str
    section: str
    start_char: int
    end_char: int
    text: str


@dataclass(frozen=True)
class EvidenceHit:
    chunk: EvidenceChunk
    score: float
    overlap_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class TelemetryPoint:
    timestamp: str
    values: dict[str, float]


@dataclass(frozen=True)
class SensorAnomaly:
    sensor: str
    baseline_mean: float
    latest_value: float
    relative_change: float
    z_score: float | None
    severity: RiskLevel
    explanation: str


@dataclass(frozen=True)
class ModelAuditFinding:
    category: RootCauseCategory
    severity: RiskLevel
    title: str
    description: str
    finding_id: str = ""
    metric: float | None = None
    evidence: tuple[str, ...] = ()
    disposition: str = "review"


@dataclass(frozen=True)
class RootCauseHypothesis:
    category: RootCauseCategory
    score: float
    title: str
    rationale: str
    recommended_check: str
    evidence_refs: tuple[str, ...] = ()
    status: str = "suspected"
    role: str = "hypothesis"


@dataclass(frozen=True)
class IncidentCase:
    id: str
    asset_id: str
    asset_type: str
    description: str
    observed_at: str
    telemetry_file: str
    model_report_file: str
    documents_dir: str
    domain: str = "industrial"
    baseline_end_at: str | None = None
    incident_start_at: str | None = None
    incident_end_at: str | None = None
    events_file: str | None = None
    production_quality_file: str | None = None
    maintenance_file: str | None = None
    predictions_file: str | None = None
    labels_file: str | None = None
    model_manifest_file: str | None = None


@dataclass
class ReliabilityResult:
    case: IncidentCase
    status: str
    anomalies: list[SensorAnomaly] = field(default_factory=list)
    model_findings: list[ModelAuditFinding] = field(default_factory=list)
    evidence_hits: list[EvidenceHit] = field(default_factory=list)
    root_causes: list[RootCauseHypothesis] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    signal_summary: list[dict[str, Any]] = field(default_factory=list)
    maintenance_evidence: list[dict[str, Any]] = field(default_factory=list)
    quality_records: list[dict[str, Any]] = field(default_factory=list)
    model_audit_status: str | None = None
    data_quality: dict[str, Any] = field(default_factory=dict)
    graph: Any = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        def anomaly_dict(item: SensorAnomaly) -> dict[str, Any]:
            return {
                "sensor": item.sensor,
                "baseline_mean": round(item.baseline_mean, 6),
                "latest_value": round(item.latest_value, 6),
                "relative_change": round(item.relative_change, 6),
                "z_score": None if item.z_score is None else round(item.z_score, 6),
                "severity": item.severity.value,
                "explanation": item.explanation,
            }

        def finding_dict(item: ModelAuditFinding) -> dict[str, Any]:
            return {
                "finding_id": item.finding_id,
                "category": item.category.value,
                "severity": item.severity.value,
                "title": item.title,
                "description": item.description,
                "metric": item.metric,
                "evidence": list(item.evidence),
                "disposition": item.disposition,
            }

        def cause_dict(item: RootCauseHypothesis) -> dict[str, Any]:
            return {
                "category": item.category.value,
                "score": round(item.score, 6),
                "title": item.title,
                "rationale": item.rationale,
                "recommended_check": item.recommended_check,
                "evidence_refs": list(item.evidence_refs),
                "status": item.status,
                "role": item.role,
            }

        output: dict[str, Any] = {
            "case": {
                "id": self.case.id,
                "asset_id": self.case.asset_id,
                "asset_type": self.case.asset_type,
                "description": self.case.description,
                "observed_at": self.case.observed_at,
                "domain": self.case.domain,
                "baseline_end_at": self.case.baseline_end_at,
                "incident_start_at": self.case.incident_start_at,
                "incident_end_at": self.case.incident_end_at,
            },
            "status": self.status,
            "anomalies": [anomaly_dict(item) for item in self.anomalies],
            "model_findings": [finding_dict(item) for item in self.model_findings],
            "evidence": [
                {
                    "chunk_id": hit.chunk.id,
                    "document_id": hit.chunk.document_id,
                    "section": hit.chunk.section,
                    "start_char": hit.chunk.start_char,
                    "end_char": hit.chunk.end_char,
                    "text": hit.chunk.text,
                    "retrieval_score": round(hit.score, 6),
                }
                for hit in self.evidence_hits
            ],
            "root_causes": [cause_dict(item) for item in self.root_causes],
            "timeline": list(self.timeline),
            "signal_summary": list(self.signal_summary),
            "maintenance_evidence": list(self.maintenance_evidence),
            "quality_records": list(self.quality_records),
            "model_audit_status": self.model_audit_status,
            "data_quality": dict(self.data_quality),
            "warnings": list(self.warnings),
        }
        if self.graph is not None:
            output["graph"] = self.graph.to_dict()
        return output
