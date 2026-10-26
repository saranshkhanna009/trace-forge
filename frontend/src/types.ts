export type Persona = "Operations" | "ML Engineering" | "Management" | "Reliability";

export interface RootCause {
  category: string;
  score: number;
  title: string;
  rationale: string;
  recommended_check: string;
  evidence_refs: string[];
  status: string;
  role: string;
}

export interface ModelFinding {
  finding_id: string;
  category: string;
  severity: string;
  title: string;
  description: string;
  metric: number | null;
  evidence: string[];
  disposition: string;
}

export interface SignalSummary {
  signal_name: string;
  baseline_median: number;
  incident_median: number;
  absolute_change: number;
  percent_change: number | null;
  trend_direction: string;
  first_abnormal_at_utc: string | null;
  evidence_refs: string[];
}

export interface TimelineEvent {
  timestamp: string;
  type: string;
  code: string | null;
  message: string | null;
  source: string | null;
}

export interface TelemetryRow {
  timestamp: string;
  [key: string]: string | number | null;
}

export interface PredictionRow {
  timestamp: string;
  score: number;
  threshold: number;
  class: string;
  prediction_id: string;
}

export interface QualityRecord {
  quality_id?: string;
  inspected_at_utc?: string;
  surface_finish_ra_um?: string;
  surface_finish_limit_um?: string;
  quality_status?: string;
  failure_code?: string;
  inspector_source?: string;
  [key: string]: string | undefined;
}

export interface MaintenanceRecord {
  maintenance_event_id?: string;
  component?: string;
  action_type?: string;
  status?: string;
  measurement_before?: string;
  measurement_after?: string;
  measurement_unit?: string;
  observation?: string;
  evidence_ref?: string;
  [key: string]: string | undefined;
}

export interface EvidenceSpan {
  chunk_id: string;
  document_id: string;
  section: string;
  start_char: number;
  end_char: number;
  text: string;
  retrieval_score: number;
}

export interface GraphNode {
  id: string;
  kind: string;
  properties: Record<string, unknown>;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
  properties: Record<string, unknown>;
}

export interface ReliabilityGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface CaseResult {
  case: {
    id: string;
    asset_id: string;
    asset_type: string;
    problem_code?: string | null;
    problem_label?: string | null;
    description: string;
    observed_at: string;
    domain: string;
    baseline_end_at: string | null;
    incident_start_at: string | null;
    incident_end_at: string | null;
  };
  status: string;
  anomalies: Array<{
    sensor: string;
    baseline_mean: number;
    latest_value: number;
    relative_change: number;
    z_score: number | null;
    severity: string;
    explanation: string;
  }>;
  model_findings: ModelFinding[];
  evidence: EvidenceSpan[];
  root_causes: RootCause[];
  timeline: TimelineEvent[];
  signal_summary: SignalSummary[];
  maintenance_evidence: MaintenanceRecord[];
  quality_records: QualityRecord[];
  model_audit_status: string;
  data_quality: Record<string, unknown>;
  warnings: string[];
  graph: ReliabilityGraph;
}

export interface AnalysisResponse {
  schema_version: string;
  case_key: string;
  resolution_status: string;
  manifest: Record<string, unknown>;
  result: CaseResult;
}

export interface CaseMetadata {
  case_key: string;
  incident_id: string;
  asset_id: string;
  asset_type: string;
  domain: string;
  problem_code?: string | null;
  problem_label?: string | null;
  description: string;
  observed_at: string;
}

export interface TelemetryResponse {
  case_key: string;
  signals: string[];
  rows: TelemetryRow[];
  total_rows: number;
  incident_start_at: string | null;
  incident_end_at: string | null;
}

export interface PredictionsResponse {
  case_key: string;
  rows: PredictionRow[];
}

export interface ApiErrorShape {
  detail?: { code?: string; message?: string } | string;
}
