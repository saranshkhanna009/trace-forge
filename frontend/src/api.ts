import type {
  AnalysisResponse,
  ApiErrorShape,
  CaseMetadata,
  PredictionsResponse,
  TelemetryResponse,
} from "./types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    let body: ApiErrorShape = {};
    try {
      body = (await response.json()) as ApiErrorShape;
    } catch {
      // Preserve the HTTP status when the backend did not return JSON.
    }
    const detail = typeof body.detail === "object" ? body.detail?.message : body.detail;
    throw new Error(detail || `TraceForge API returned HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export function apiBaseUrl(): string {
  return API_BASE_URL;
}

export function getCases(): Promise<{ cases: CaseMetadata[]; default_case_key: string }> {
  return request("/api/v1/cases");
}

export function getAnalysis(caseKey: string): Promise<AnalysisResponse> {
  return request(`/api/v1/cases/${encodeURIComponent(caseKey)}/analysis?top_k=8`);
}

export function getTelemetry(caseKey: string): Promise<TelemetryResponse> {
  return request(`/api/v1/cases/${encodeURIComponent(caseKey)}/telemetry?limit=5000`);
}

export function getPredictions(caseKey: string): Promise<PredictionsResponse> {
  return request(`/api/v1/cases/${encodeURIComponent(caseKey)}/predictions?limit=5000`);
}
