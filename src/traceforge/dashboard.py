"""Deployable Streamlit dashboard for TraceForge manufacturing incidents."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Streamlit may execute this file as a script or import it as
# ``traceforge.dashboard`` depending on the host. Always make the local
# ``src`` package discoverable before choosing the matching import style. This
# keeps both direct checkout launches and installed-package deployments valid.
_src_root = str(Path(__file__).resolve().parents[1])
if _src_root not in sys.path:
    sys.path.insert(0, _src_root)

try:
    import plotly.graph_objects as go
    import streamlit as st
except ImportError as exc:  # pragma: no cover - exercised by the runtime, not unit tests
    raise RuntimeError(
        "The dashboard requires the optional UI dependencies. Install them with "
        '`python -m pip install -e ".[dashboard]"`.'
    ) from exc

if __package__ in (None, ""):
    from traceforge.dashboard_data import (
        DashboardCase,
        feature_coverage,
        load_dashboard_case,
        numeric_telemetry_rows,
        prediction_chart_rows,
        quality_before_after,
    )
    from traceforge.manufacturing import incident_report
else:
    from .dashboard_data import (
        DashboardCase,
        feature_coverage,
        load_dashboard_case,
        numeric_telemetry_rows,
        prediction_chart_rows,
        quality_before_after,
    )
    from .manufacturing import incident_report


DEFAULT_CASE = Path(__file__).resolve().parents[2] / "demo" / "cnc_vmc_07"
SIGNAL_LABELS = {
    "coolant_flow_l_min": ("Coolant flow", "L/min"),
    "coolant_pressure_bar": ("Coolant pressure", "bar"),
    "coolant_pump_current_a": ("Pump current", "A"),
    "spindle_bearing_temp_c": ("Spindle temperature", "°C"),
    "spindle_vibration_rms_mm_s": ("Spindle vibration", "mm/s"),
    "spindle_load_pct": ("Spindle load", "%"),
}


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root { --ink: #e8eef7; --muted: #91a2b8; --panel: #111b2a; --line: #24354a; }
        .stApp { background: #08111f; color: var(--ink); }
        [data-testid="stSidebar"] { background: #0b1626; border-right: 1px solid var(--line); }
        .block-container { max-width: 1500px; padding-top: 2rem; padding-bottom: 3rem; }
        .tf-brand { display:flex; align-items:center; gap: .8rem; margin-bottom: .3rem; }
        .tf-mark { width: 2.4rem; height: 2.4rem; border-radius: .8rem; display:flex;
          align-items:center; justify-content:center; background: linear-gradient(135deg,#18b6a4,#3967ff);
          color:white; font-weight:800; letter-spacing:-.06em; box-shadow: 0 8px 26px #18b6a433; }
        .tf-title { font-size: 1.55rem; font-weight: 750; letter-spacing: -.03em; }
        .tf-subtitle { color: var(--muted); font-size: .85rem; margin-bottom: 1.25rem; }
        .tf-kicker { color:#5fe4d1; text-transform:uppercase; letter-spacing:.13em; font-size:.7rem; font-weight:700; }
        .tf-hero { background: linear-gradient(120deg,#112844,#102032 55%,#171c36); border:1px solid #294460;
          padding:1.25rem 1.45rem; border-radius:1rem; margin-bottom:1.1rem; }
        .tf-hero h1 { margin:.25rem 0 .35rem; font-size:2rem; letter-spacing:-.045em; }
        .tf-hero p { color:#b4c2d5; margin:0; max-width: 70rem; }
        .tf-badge { display:inline-block; border-radius:999px; padding:.25rem .65rem; font-size:.72rem;
          font-weight:750; letter-spacing:.06em; margin-right:.35rem; }
        .tf-critical { color:#ffdfe1; background:#8e2632; border:1px solid #d95762; }
        .tf-warning { color:#ffe9ba; background:#714d17; border:1px solid #c6973d; }
        .tf-success { color:#d4fff6; background:#155c58; border:1px solid #2ebfae; }
        .tf-neutral { color:#d3deed; background:#27364a; border:1px solid #52657f; }
        .tf-section { margin-top: 1.5rem; margin-bottom: .6rem; font-size:1.15rem; font-weight:700; }
        .tf-muted { color: var(--muted); font-size: .86rem; }
        .tf-story { background:#101d2d; border:1px solid #27415a; border-radius:.9rem; padding:1rem 1.1rem;
          min-height:5.5rem; }
        .tf-story strong { color:#eef5ff; }
        div[data-testid="stMetric"] { background:#101c2c; border:1px solid #253b53; padding:.8rem 1rem; border-radius:.8rem; }
        div[data-testid="stMetricLabel"] { color:#99abc0; }
        .stTabs [data-baseweb="tab-list"] { gap: .3rem; }
        .stTabs [data-baseweb="tab"] { padding: .7rem 1rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def badge(text: str, kind: str = "neutral") -> str:
    return f'<span class="tf-badge tf-{kind}">{text}</span>'


def severity_kind(value: str) -> str:
    return {"CRITICAL": "critical", "HIGH": "critical", "MEDIUM": "warning", "LOW": "success"}.get(
        value.upper(), "neutral"
    )


def safe_text(value: Any, fallback: str = "Not available") -> str:
    return fallback if value in (None, "") else str(value)


@st.cache_data(show_spinner=False)
def cached_case(case_dir: str) -> DashboardCase:
    return load_dashboard_case(case_dir)


def render_sidebar() -> tuple[str, str]:
    with st.sidebar:
        st.markdown('<div class="tf-kicker">TraceForge control room</div>', unsafe_allow_html=True)
        st.markdown("## Investigation workspace")
        default_path = str(DEFAULT_CASE)
        case_path = st.text_input("Case directory", value=default_path, help="Path containing case.json")
        persona = st.radio(
            "View for",
            ["Operations / Maintenance", "ML Engineering", "Management", "Engineering / Reliability"],
            index=0,
        )
        st.divider()
        st.caption("Local-first demo • no credentials • deterministic case analysis")
        st.caption("Use the report buttons in the header to share artifacts with other personnel.")
    return case_path, persona


def render_header(data: DashboardCase) -> None:
    result = data.result
    root = data.primary_root_cause
    severity = result.status.upper()
    st.markdown(
        f"""
        <div class="tf-hero">
          <div class="tf-kicker">Industrial AI reliability workspace</div>
          <h1>{data.case.asset_id} · CNC incident investigation</h1>
          <p>{data.case.description}</p>
          <div style="margin-top:.8rem">
            {badge(severity, severity_kind(severity))}
            {badge(f"RESOLUTION · {data.resolution_status}", "success" if data.resolution_status == "VALIDATED" else "warning")}
            {badge(f"MODEL · {data.model_status}", "warning" if data.model_status != "not_evaluated" else "neutral")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    left, middle, right = st.columns([2, 2, 1])
    with left:
        st.caption(f"Incident {data.case.id}")
        st.caption(f"Observed {safe_text(data.case.observed_at)} · {data.case.asset_type}")
    with middle:
        if root:
            st.caption(f"Primary hypothesis: {root.title}")
            st.caption(f"Confidence {root.score:.0%} · {root.status.replace('_', ' ')}")
        else:
            st.caption("Primary hypothesis: not available")
    with right:
        report = incident_report(result)
        st.download_button(
            "Download JSON",
            data=json.dumps(report, indent=2),
            file_name=f"{data.case.id}.json",
            mime="application/json",
            use_container_width=True,
        )


def metric_row(data: DashboardCase) -> None:
    root = data.primary_root_cause
    quality = quality_before_after(data)
    before = next((item for item in quality if item["label"] == "FAIL"), None)
    after = next((item for item in quality if item["label"] == "PASS"), None)
    cols = st.columns(5)
    with cols[0]:
        st.metric("Incident severity", data.result.status)
    with cols[1]:
        st.metric("Root-cause confidence", f"{root.score:.0%}" if root else "N/A")
    with cols[2]:
        st.metric("Quality result", f"{before['surface_finish_ra_um']:.1f} → {after['surface_finish_ra_um']:.1f} µm" if before and after else "Unavailable")
    with cols[3]:
        st.metric("Resolution", data.resolution_status)
    with cols[4]:
        st.metric("Audit findings", len(data.result.model_findings))


def chart_layout(title: str, y_title: str, height: int = 310) -> dict[str, Any]:
    return {
        "title": {"text": title, "font": {"size": 15, "color": "#e8eef7"}},
        "height": height,
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "#0e1a29",
        "font": {"color": "#b8c5d6"},
        "margin": {"l": 45, "r": 20, "t": 48, "b": 42},
        "xaxis": {"gridcolor": "#213249", "linecolor": "#304860"},
        "yaxis": {"title": y_title, "gridcolor": "#213249", "linecolor": "#304860"},
        "legend": {"orientation": "h", "y": 1.08, "x": 0},
        "hovermode": "x unified",
    }


def add_incident_markers(fig: go.Figure, data: DashboardCase) -> None:
    start = data.case.incident_start_at
    end = data.case.incident_end_at
    if start:
        fig.add_vline(x=start, line_dash="dash", line_color="#ef6a73", annotation_text="incident start")
    if end:
        fig.add_vline(x=end, line_dash="dot", line_color="#d99943", annotation_text="cycle abort")


def telemetry_figure(data: DashboardCase, signals: tuple[str, ...], title: str, y_title: str) -> go.Figure:
    rows = numeric_telemetry_rows(data, signals)
    fig = go.Figure()
    for signal in signals:
        label, unit = SIGNAL_LABELS.get(signal, (signal, ""))
        fig.add_trace(
            go.Scatter(
                x=[row["timestamp"] for row in rows],
                y=[row.get(signal) for row in rows],
                mode="lines+markers",
                name=f"{label} ({unit})",
                connectgaps=False,
                line={"width": 2.3},
                marker={"size": 7},
            )
        )
    add_incident_markers(fig, data)
    fig.update_layout(**chart_layout(title, y_title))
    return fig


def render_evidence(data: DashboardCase, refs: list[str] | tuple[str, ...], title: str = "Evidence drawer") -> None:
    valid_refs = [ref for ref in refs if ref in data.evidence_by_id]
    with st.expander(f"{title} · {len(valid_refs)} source-backed spans", expanded=False):
        if not valid_refs:
            st.info("No retrieved document span is linked to this item. Do not promote it to a confirmed conclusion.")
            return
        for ref in valid_refs:
            item = data.evidence_by_id[ref]
            st.markdown(f"**{item['document']} · {item['section']}** · `{ref}`")
            st.caption(f"Characters {item['start_char']}–{item['end_char']} · retrieval {item['score']:.2f}")
            st.code(item["text"], language="text")


def render_operations(data: DashboardCase) -> None:
    st.markdown('<div class="tf-section">Operations / Maintenance</div>', unsafe_allow_html=True)
    st.caption("Answering: what happened, what should be inspected, and did the correction work?")
    metric_row(data)
    root = data.primary_root_cause
    left, right = st.columns([1.2, 1])
    with left:
        st.markdown("### Investigation readout")
        if root:
            st.markdown(
                f'<div class="tf-story"><strong>{root.title}</strong><br>{root.rationale}<br><br>'
                f'<span class="tf-muted">Next check: {root.recommended_check}</span></div>',
                unsafe_allow_html=True,
            )
            render_evidence(data, root.evidence_refs, "Primary hypothesis evidence")
        else:
            st.warning("No root-cause hypothesis was generated from the available evidence.")
    with right:
        st.markdown("### Quality recovery")
        quality = quality_before_after(data)
        if quality:
            fig = go.Figure()
            fig.add_trace(go.Bar(x=[item["label"] for item in quality], y=[item["surface_finish_ra_um"] for item in quality], name="Ra µm", marker_color=["#ef6a73" if item["label"] == "FAIL" else "#2ebfae" for item in quality]))
            limit = quality[0]["limit"]
            fig.add_hline(y=limit, line_dash="dash", line_color="#d99943", annotation_text=f"limit {limit:g}")
            fig.update_layout(**chart_layout("Surface finish before and after", "Ra (µm)", 260), showlegend=False)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Product quality is unavailable; validation status cannot be determined.")

    st.markdown("### Signal condition")
    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.plotly_chart(
            telemetry_figure(data, ("coolant_flow_l_min", "coolant_pressure_bar", "coolant_pump_current_a"), "Coolant circuit", "Value (native units)"),
            use_container_width=True,
            config={"displayModeBar": False},
        )
    with chart_right:
        st.plotly_chart(
            telemetry_figure(data, ("spindle_bearing_temp_c", "spindle_vibration_rms_mm_s", "spindle_load_pct"), "Spindle condition", "Value (native units)"),
            use_container_width=True,
            config={"displayModeBar": False},
        )

    st.markdown("### Incident timeline")
    timeline_rows = [
        {"timestamp": item["timestamp"], "type": item["type"], "code": item["code"], "message": item["message"], "source": item["source"]}
        for item in data.result.timeline
    ]
    if timeline_rows:
        st.dataframe(timeline_rows, use_container_width=True, hide_index=True)
    else:
        st.info("No event, quality, or maintenance timeline records are available.")

    st.markdown("### Corrective actions")
    actions = data.result.maintenance_evidence
    if actions:
        st.dataframe(
            [
                {
                    "Action": row.get("action_type"),
                    "Component": row.get("component"),
                    "Status": row.get("status"),
                    "Before": row.get("measurement_before"),
                    "After": row.get("measurement_after"),
                    "Evidence": row.get("evidence_ref"),
                }
                for row in actions
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.warning("Physical causes remain suspected. Add a work order or independent measurement.")


def render_ml_engineering(data: DashboardCase) -> None:
    st.markdown('<div class="tf-section">ML Engineering</div>', unsafe_allow_html=True)
    st.caption("Answering: is the model valid, was the alert actionable, and what should be remediated?")
    manifest = data.manifest
    if not manifest:
        st.error("Model audit unavailable. Provide model_manifest.json.")
        return
    contract_cols = st.columns(4)
    contract = [
        ("Model", safe_text(manifest.get("model_id"))),
        ("Version", safe_text(manifest.get("model_version"))),
        ("Target", safe_text(manifest.get("target_name"))),
        ("Threshold", safe_text(manifest.get("decision_threshold"))),
    ]
    for column, (label, value) in zip(contract_cols, contract):
        with column:
            st.metric(label, value)
    st.markdown("### Prediction timing")
    prediction_rows = prediction_chart_rows(data)
    if prediction_rows:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=[row["timestamp"] for row in prediction_rows],
            y=[row["score"] for row in prediction_rows],
            mode="lines+markers",
            name="risk score",
            line={"color": "#5fe4d1", "width": 3},
            marker={"size": 9, "color": ["#ef6a73" if row["class"] == "alert" else "#5fe4d1" for row in prediction_rows]},
            text=[row["prediction_id"] for row in prediction_rows],
            hovertemplate="%{x}<br>score %{y:.2f}<br>%{text}<extra></extra>",
        ))
        threshold = prediction_rows[0]["threshold"]
        fig.add_hline(y=threshold, line_dash="dash", line_color="#d99943", annotation_text=f"threshold {threshold:.2f}")
        add_incident_markers(fig, data)
        prediction_layout = chart_layout("Point-in-time model score", "Probability", 350)
        prediction_layout["yaxis"] = {"range": [0, 1], "title": "Probability", "gridcolor": "#213249"}
        fig.update_layout(**prediction_layout)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        actionable = [row for row in prediction_rows if data.case.incident_start_at and row["timestamp"] < data.case.incident_start_at]
        late = [row for row in prediction_rows if data.case.incident_start_at and row["timestamp"] >= data.case.incident_start_at and row["score"] >= row["threshold"]]
        a, b, c = st.columns(3)
        with a:
            st.metric("Max pre-incident score", f"{max((row['score'] for row in actionable), default=0):.2f}")
        with b:
            st.metric("Decision threshold", f"{threshold:.2f}")
        with c:
            st.metric("Late alerts", len(late))
        st.caption("Scores at or after incident start are shown as detection, not preventive warning.")
    else:
        st.info("Early-warning performance not evaluated because predictions.csv is absent or invalid.")

    st.markdown("### Audit findings queue")
    findings = sorted(
        data.result.model_findings,
        key=lambda item: ({"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(item.severity.value, 3), item.finding_id),
    )
    if findings:
        st.dataframe(
            [
                {
                    "ID": item.finding_id,
                    "Severity": item.severity.value,
                    "Category": item.category.value,
                    "Finding": item.title,
                    "Metric": item.metric,
                    "Remediation": item.disposition.replace("_", " "),
                }
                for item in findings
            ],
            use_container_width=True,
            hide_index=True,
        )
        selected = st.selectbox("Inspect finding", [item.finding_id for item in findings])
        finding = next(item for item in findings if item.finding_id == selected)
        st.markdown(f"**{finding.title}** · {finding.description}")
        st.caption(f"Disposition: {finding.disposition.replace('_', ' ')}")
        render_evidence(data, finding.evidence, f"Evidence for {finding.finding_id}")
    else:
        st.success("No model findings were generated.")

    st.markdown("### Drift and feature coverage")
    drift = manifest.get("feature_drift", {})
    left, right = st.columns([1, 1.15])
    with left:
        if drift:
            fig = go.Figure(go.Bar(
                x=[float(value) for value in drift.values()],
                y=list(drift.keys()),
                orientation="h",
                marker_color=["#ef6a73" if float(value) > 0.2 else "#5fe4d1" for value in drift.values()],
                text=[f"{float(value):.0%}" for value in drift.values()],
                textposition="outside",
            ))
            fig.add_vline(x=0.2, line_dash="dash", line_color="#d99943", annotation_text="review 20%")
            drift_layout = chart_layout("Feature drift", "", 280)
            drift_layout["xaxis"] = {"range": [0, max(0.55, max(float(value) for value in drift.values()) + 0.08)], "tickformat": ".0%", "gridcolor": "#213249"}
            fig.update_layout(**drift_layout, showlegend=False)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Drift not reported; this is different from no drift.")
    with right:
        coverage = feature_coverage(data)
        if coverage:
            st.dataframe(coverage, use_container_width=True, hide_index=True)
        else:
            st.info("Feature coverage is not available without a model manifest.")

    st.markdown("### Model-to-outcome chain")
    st.markdown(
        '<div class="tf-story"><strong>Features → prediction → alert timing → machine event → quality label</strong><br>'
        '<span class="tf-muted">The current model score crossed its threshold after the incident started and did not use the primary coolant precursor signals.</span></div>',
        unsafe_allow_html=True,
    )


def render_management(data: DashboardCase) -> None:
    st.markdown('<div class="tf-section">Management</div>', unsafe_allow_html=True)
    st.caption("Answering: what happened, what was validated, and which decisions require attention?")
    root = data.primary_root_cause
    quality = quality_before_after(data)
    failed = next((item for item in quality if item["label"] == "FAIL"), None)
    passed = next((item for item in quality if item["label"] == "PASS"), None)
    narrative = (
        f"A {root.title.lower()} caused the incident. "
        "The evidence shows a machine-side precursor, a model that did not provide actionable early warning, "
        "and a successful corrective validation."
        if root
        else "The case does not contain enough evidence for an executive conclusion."
    )
    st.markdown(f'<div class="tf-story"><strong>Executive summary</strong><br>{narrative}</div>', unsafe_allow_html=True)
    cols = st.columns(5)
    with cols[0]:
        st.metric("Incident", data.result.status)
    with cols[1]:
        st.metric("Confirmed cause", f"{root.score:.0%}" if root and root.status == "confirmed" else "Provisional")
    with cols[2]:
        st.metric("Quality recovery", f"{failed['surface_finish_ra_um']:.1f} → {passed['surface_finish_ra_um']:.1f} µm" if failed and passed else "Unknown")
    with cols[3]:
        st.metric("Validation", data.resolution_status)
    with cols[4]:
        st.metric("Remediation items", len(data.result.model_findings))

    st.markdown("### Before / after outcome")
    if quality:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=[item["label"] for item in quality],
            y=[item["surface_finish_ra_um"] for item in quality],
            marker_color=["#ef6a73" if item["label"] == "FAIL" else "#2ebfae" for item in quality],
            text=[f"{item['surface_finish_ra_um']:.1f} µm" for item in quality],
            textposition="outside",
        ))
        fig.add_hline(y=quality[0]["limit"], line_dash="dash", line_color="#d99943", annotation_text=f"limit {quality[0]['limit']:.1f} µm")
        fig.update_layout(**chart_layout("Surface finish recovery", "Ra (µm)", 290), showlegend=False)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("Business/product outcome is not quantified in this case.")

    st.markdown("### Causal story")
    story_cols = st.columns(5)
    steps = [
        ("01", "Filter restriction", "Confirmed", "critical"),
        ("02", "Low flow / pressure", "Telemetry", "warning"),
        ("03", "Heat + vibration", "Telemetry", "warning"),
        ("04", "Chatter + tool wear", "Contributing", "warning"),
        ("05", "Quality failure", "Validated recovery", "success"),
    ]
    for column, (number, title, label, kind) in zip(story_cols, steps):
        with column:
            st.markdown(
                f'<div class="tf-story"><span class="tf-kicker">{number}</span><br><strong>{title}</strong><br>{badge(label, kind)}</div>',
                unsafe_allow_html=True,
            )

    st.markdown("### Decisions and corrective actions")
    actions = [
        ("Remove alarm leakage", "AUD-001", "Do not count post-event alarms as preventive features."),
        ("Add coolant signals", "AUD-002", "Add flow, pressure, and pump-current features."),
        ("Rebuild evaluation", "AUD-003", "Use time- and machine-grouped holdouts without overlap."),
    ]
    st.dataframe(
        [{"Priority": index + 1, "Decision": title, "Evidence": evidence, "Why it matters": reason} for index, (title, evidence, reason) in enumerate(actions)],
        use_container_width=True,
        hide_index=True,
    )
    st.caption("Business cost, downtime, throughput, and fleet trends are not invented because they are not in this single-case fixture.")


def graph_figure(data: DashboardCase) -> go.Figure | None:
    graph = data.result.graph
    if graph is None or not graph.nodes:
        return None
    groups = {
        "IncidentCase": 0,
        "Asset": 1,
        "Sensor": 2,
        "SensorAnomaly": 3,
        "Model": 2,
        "ModelAuditFinding": 3,
        "RootCauseHypothesis": 4,
        "Document": 3,
        "EvidenceSpan": 5,
    }
    nodes = sorted(graph.nodes.values(), key=lambda node: (groups.get(node.kind, 6), node.id))
    positions: dict[str, tuple[float, float]] = {}
    for x in sorted(set(groups.get(node.kind, 6) for node in nodes)):
        lane = [node for node in nodes if groups.get(node.kind, 6) == x]
        for index, node in enumerate(lane):
            positions[node.id] = (float(x), float(-index))
    edge_x: list[float | None] = []
    edge_y: list[float | None] = []
    for edge in graph.edges:
        if edge.source not in positions or edge.target not in positions:
            continue
        edge_x.extend([positions[edge.source][0], positions[edge.target][0], None])
        edge_y.extend([positions[edge.source][1], positions[edge.target][1], None])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=edge_x, y=edge_y, mode="lines", line={"width": 1, "color": "#3b536e"}, hoverinfo="none", showlegend=False))
    palette = {
        "IncidentCase": "#ef6a73", "Asset": "#8b9ef5", "Sensor": "#5fe4d1", "SensorAnomaly": "#e9b45b",
        "Model": "#b68cff", "ModelAuditFinding": "#f28c9b", "RootCauseHypothesis": "#46d39b",
        "Document": "#6da5d9", "EvidenceSpan": "#7290ad",
    }
    for kind in sorted({node.kind for node in nodes}):
        lane = [node for node in nodes if node.kind == kind]
        fig.add_trace(go.Scatter(
            x=[positions[node.id][0] for node in lane],
            y=[positions[node.id][1] for node in lane],
            mode="markers+text",
            name=kind,
            text=[node.properties.get("title", node.properties.get("name", node.id))[:28] for node in lane],
            textposition="top center",
            marker={"size": 15, "color": palette.get(kind, "#91a2b8"), "line": {"width": 1, "color": "#edf5ff"}},
            customdata=[node.id for node in lane],
            hovertemplate="%{text}<br>%{customdata}<extra>" + kind + "</extra>",
        ))
    graph_layout = chart_layout("Reliability evidence graph", "", 560)
    graph_layout["xaxis"] = {"visible": False}
    graph_layout["yaxis"] = {"visible": False}
    graph_layout["legend"] = {"orientation": "h", "y": -0.05}
    fig.update_layout(**graph_layout, showlegend=True)
    return fig


def render_reliability(data: DashboardCase) -> None:
    st.markdown('<div class="tf-section">Engineering / Reliability</div>', unsafe_allow_html=True)
    st.caption("Answering: how do the evidence, competing hypotheses, and system layers connect?")
    fig = graph_figure(data)
    if fig:
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.warning("Graph unavailable. Showing ranked tables and provenance instead.")
    st.markdown("### Ranked hypotheses")
    if data.result.root_causes:
        st.dataframe(
            [
                {
                    "Score": f"{item.score:.0%}",
                    "Role": item.role,
                    "Status": item.status,
                    "Category": item.category.value,
                    "Hypothesis": item.title,
                    "Recommended check": item.recommended_check,
                }
                for item in data.result.root_causes
            ],
            use_container_width=True,
            hide_index=True,
        )
        selected = st.selectbox("Inspect hypothesis", [item.title for item in data.result.root_causes], key="reliability_hypothesis")
        hypothesis = next(item for item in data.result.root_causes if item.title == selected)
        st.markdown(f"**{hypothesis.title}** · {hypothesis.rationale}")
        render_evidence(data, hypothesis.evidence_refs, "Hypothesis evidence")
    else:
        st.info("No ranked hypothesis was generated from the available evidence.")

    st.markdown("### Reliability chain coverage")
    layers = [
        ("Machine", "Observed", True),
        ("Sensor", f"{len(data.result.anomalies)} anomalies", bool(data.result.anomalies)),
        ("Data", f"{data.result.data_quality.get('telemetry_rows', 0)} rows", bool(data.result.telemetry_rows if hasattr(data.result, "telemetry_rows") else data.telemetry_rows)),
        ("Features", "Audit findings", bool(data.result.model_findings)),
        ("Model", data.model_status, bool(data.manifest)),
        ("Alert", f"{len(data.prediction_rows)} scores", bool(data.prediction_rows)),
        ("Outcome", f"{len(data.result.quality_records)} quality records", bool(data.result.quality_records)),
    ]
    layer_cols = st.columns(len(layers))
    for column, (title, value, present) in zip(layer_cols, layers):
        with column:
            st.markdown(f'<div class="tf-story"><strong>{title}</strong><br>{badge(value, "success" if present else "neutral")}</div>', unsafe_allow_html=True)
    st.markdown("### Provenance and data quality")
    st.json({
        "schema_version": data.manifest.get("schema_version", "traceforge.incident.v1"),
        "input_directory": str(data.case_dir),
        "data_quality": data.result.data_quality,
        "warnings": data.result.warnings,
    })


def markdown_export(data: DashboardCase) -> str:
    report = incident_report(data.result)
    primary = report.get("root_cause")
    lines = [
        f"# TraceForge Incident {report['incident_id']}",
        "",
        "## Executive summary",
        "",
        f"- Machine: `{report['machine_id']}`",
        f"- Severity: `{report['severity']}`",
        f"- Resolution: `{data.resolution_status}`",
        f"- Primary root cause: `{primary['failure_mode_code'] if primary else 'unconfirmed'}`",
        "",
        "## Root-cause conclusion",
        "",
        json.dumps(primary, indent=2) if primary else "No root cause was confirmed.",
        "",
        "## Ranked failure modes",
        "",
    ]
    lines.extend(
        f"- **{item['score']:.0%}** {item['title']} — {item['status']} ({item['role']})"
        for item in report["ranked_failure_modes"]
    )
    lines.extend(["", "## Model audit findings", ""])
    lines.extend(
        f"- `{item['finding_id']}` · {item['severity']} · {item['title']} — {item['disposition']}"
        for item in report["model_audit_summary"]["findings"]
    )
    lines.extend(["", "## Data-quality limitations", "", "```json", json.dumps(report["data_quality"], indent=2), "```", ""])
    return "\n".join(lines)


def render_footer(data: DashboardCase) -> None:
    st.divider()
    st.caption("TraceForge is decision support. A ranked hypothesis must be validated through approved manufacturing procedures.")
    left, middle, right = st.columns(3)
    with left:
        st.download_button(
            "Export incident JSON",
            data=json.dumps(incident_report(data.result), indent=2),
            file_name=f"{data.case.id}-incident.json",
            mime="application/json",
            use_container_width=True,
        )
    with middle:
        st.download_button(
            "Export summary Markdown",
            data=markdown_export(data),
            file_name=f"{data.case.id}-summary.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with right:
        st.download_button(
            "Export graph JSON",
            data=json.dumps(data.result.graph.to_dict() if data.result.graph else {}, indent=2),
            file_name=f"{data.case.id}-graph.json",
            mime="application/json",
            use_container_width=True,
        )


def main() -> None:
    st.set_page_config(
        page_title="TraceForge · Industrial AI Reliability",
        page_icon="🛠️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_styles()
    st.markdown(
        '<div class="tf-brand"><div class="tf-mark">TF</div><div class="tf-title">TraceForge</div></div>'
        '<div class="tf-subtitle">Industrial AI reliability · evidence-backed root-cause investigation</div>',
        unsafe_allow_html=True,
    )
    case_path, persona = render_sidebar()
    try:
        data = cached_case(case_path)
    except Exception as exc:  # noqa: BLE001 - dashboard must show actionable section-level failure
        st.error(f"Could not load this case: {exc}")
        st.info("Choose a directory containing case.json, telemetry.csv, model_manifest.json, and the referenced evidence files.")
        return
    render_header(data)
    metric_row(data)
    st.divider()
    if persona == "Operations / Maintenance":
        render_operations(data)
    elif persona == "ML Engineering":
        render_ml_engineering(data)
    elif persona == "Management":
        render_management(data)
    else:
        render_reliability(data)
    render_footer(data)


if __name__ == "__main__":
    main()
