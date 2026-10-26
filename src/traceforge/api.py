"""Read-only FastAPI service for the Vercel TraceForge dashboard.

The Render deployment exposes the bundled synthetic manufacturing cases only.
It does not accept uploads or write to the ephemeral filesystem.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .dashboard_data import load_dashboard_case, numeric_telemetry_rows, prediction_chart_rows
from .ingest import load_case
from .manufacturing import incident_report


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _case_root() -> Path:
    """Find the bundled case directory across Render checkout layouts."""

    configured = Path(os.getenv("TRACEFORGE_CASE_ROOT", "demo"))
    if configured.is_absolute():
        return configured
    candidates = (
        PROJECT_ROOT / configured,
        Path.cwd() / configured,
        PROJECT_ROOT.parent / configured,
        Path(__file__).resolve().parents[3] / configured,
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    # Preserve the normal path in the error-free empty-list response so the
    # service still starts and its health endpoint remains available.
    return PROJECT_ROOT / configured


CASE_ROOT = _case_root()
DEFAULT_CASE_KEY = os.getenv("TRACEFORGE_DEFAULT_CASE_KEY", "cnc_vmc_07")
MAX_TOP_K = int(os.getenv("TRACEFORGE_MAX_TOP_K", "20"))
MAX_TELEMETRY_ROWS = int(os.getenv("TRACEFORGE_MAX_TELEMETRY_ROWS", "5000"))


def _allowed_origins() -> list[str]:
    # This is a public, read-only synthetic demo. A missing Render variable
    # should not make every browser request look like a network failure. Set an
    # exact comma-separated origin list for private deployments.
    configured = os.getenv("FRONTEND_ORIGINS", "*")
    return [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]


app = FastAPI(
    title="TraceForge API",
    version="0.1.0",
    description="Read-only industrial AI reliability analysis for the TraceForge dashboard.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "HEAD", "OPTIONS"],
    allow_headers=["Content-Type"],
)


def _error(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _case_dir(case_key: str) -> Path:
    """Resolve only a registered case key; never accept a filesystem path."""

    candidate = (CASE_ROOT / case_key).resolve()
    try:
        candidate.relative_to(CASE_ROOT.resolve())
    except ValueError as exc:
        raise _error("case_not_found", "Unknown case key", 404) from exc
    if not candidate.is_dir() or not (candidate / "case.json").is_file():
        raise _error("case_not_found", "Unknown case key", 404)
    return candidate


@lru_cache(maxsize=8)
def _dashboard_case(case_key: str, top_k: int):
    return load_dashboard_case(_case_dir(case_key), top_k=top_k)


def _case_metadata(case_key: str) -> dict[str, Any]:
    case = load_case(_case_dir(case_key))
    return {
        "case_key": case_key,
        "incident_id": case.id,
        "asset_id": case.asset_id,
        "asset_type": case.asset_type,
        "domain": case.domain,
        "problem_code": case.problem_code,
        "problem_label": case.problem_label,
        "description": case.description,
        "observed_at": case.observed_at,
    }


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "traceforge", "version": app.version}


@app.get("/api/v1/cases")
def list_cases() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    if CASE_ROOT.is_dir():
        for directory in sorted(CASE_ROOT.iterdir()):
            if directory.is_dir() and (directory / "case.json").is_file():
                key = directory.name
                try:
                    cases.append(_case_metadata(key))
                except Exception:
                    continue
    return {"cases": cases, "default_case_key": DEFAULT_CASE_KEY}


@app.get("/api/v1/cases/{case_key}/analysis")
def case_analysis(
    case_key: str,
    top_k: int = Query(default=5, ge=1, le=MAX_TOP_K),
) -> dict[str, Any]:
    data = _dashboard_case(case_key, top_k)
    return {
        "schema_version": "traceforge.reliability.v1",
        "case_key": case_key,
        "resolution_status": data.resolution_status,
        "manifest": data.manifest,
        "result": data.result.to_dict(),
    }


@app.get("/api/v1/cases/{case_key}/telemetry")
def case_telemetry(
    case_key: str,
    signals: str | None = None,
    limit: int = Query(default=1000, ge=1, le=MAX_TELEMETRY_ROWS),
) -> dict[str, Any]:
    data = _dashboard_case(case_key, 5)
    available = set(data.telemetry_rows[0]) if data.telemetry_rows else set()
    configured_signals = tuple(
        str(signal)
        for signal in (
            list(data.manifest.get("primary_signals", []))
            + list(data.manifest.get("context_signals", []))
        )
    )
    requested = (
        tuple(signal.strip() for signal in signals.split(",") if signal.strip())
        if signals
        else tuple(signal for signal in configured_signals if signal in available)
    )
    if not requested and not signals:
        requested = tuple(
            signal
            for signal in sorted(available)
            if signal not in {"ts_utc", "machine_id", "machine_state", "cycle_id", "operation_id", "program_id", "part_id", "tool_id", "material_code", "active_alarm_code", "sample_quality"}
        )
    unknown = sorted(set(requested) - available)
    if unknown:
        raise _error("unknown_signal", f"Unknown telemetry signal(s): {', '.join(unknown)}", 422)
    return {
        "case_key": case_key,
        "signals": list(requested),
        "rows": numeric_telemetry_rows(data, requested)[:limit],
        "total_rows": len(data.telemetry_rows),
        "incident_start_at": data.case.incident_start_at,
        "incident_end_at": data.case.incident_end_at,
    }


@app.get("/api/v1/cases/{case_key}/predictions")
def case_predictions(
    case_key: str,
    limit: int = Query(default=1000, ge=1, le=MAX_TELEMETRY_ROWS),
) -> dict[str, Any]:
    data = _dashboard_case(case_key, 5)
    return {"case_key": case_key, "rows": prediction_chart_rows(data)[:limit]}


@app.get("/api/v1/cases/{case_key}/report")
def case_report(case_key: str) -> dict[str, Any]:
    return incident_report(_dashboard_case(case_key, 5).result)


@app.get("/api/v1/cases/{case_key}/graph")
def case_graph(case_key: str) -> dict[str, Any]:
    graph = _dashboard_case(case_key, 5).result.graph
    return graph.to_dict() if graph is not None else {"nodes": [], "edges": []}
