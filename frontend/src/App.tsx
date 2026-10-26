import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { apiBaseUrl, getAnalysis, getCases, getPredictions, getTelemetry } from "./api";
import type {
  AnalysisResponse,
  CaseMetadata,
  CaseResult,
  GraphNode,
  PredictionRow,
  TelemetryRow,
  TimelineEvent,
} from "./types";
import type { Persona } from "./types";

const defaultCaseKey = import.meta.env.VITE_DEFAULT_CASE_KEY || "cnc_vmc_07";

const personaOptions: Array<{ id: Persona; label: string; caption: string }> = [
  { id: "Operations", label: "Operations", caption: "What happened and what should I inspect?" },
  { id: "ML Engineering", label: "ML Engineering", caption: "Can the model be trusted?" },
  { id: "Management", label: "Management", caption: "What decisions matter now?" },
  { id: "Reliability", label: "Reliability", caption: "How do the layers and evidence connect?" },
];

type ManufacturingProblem = {
  id: string;
  label: string;
  family: string;
  description: string;
  caseKey?: string;
};

const manufacturingProblems: ManufacturingProblem[] = [
  {
    id: "spindle-bearing",
    label: "Spindle bearing",
    family: "CNC",
    description: "Bearing degradation, heat, and vibration",
    caseKey: "cnc_spindle_bearing_01",
  },
  { id: "tool-wear", label: "Tool wear / breakage", family: "CNC", description: "Tool-life and cutting-condition failure", caseKey: "cnc_tool_wear_01" },
  { id: "robot-joint", label: "Robotic-arm joint wear", family: "Robotics", description: "Joint backlash and position error", caseKey: "robot_arm_joint_01" },
  { id: "conveyor-motor", label: "Conveyor motor overheating", family: "Material handling", description: "Motor friction, overload, and stoppage", caseKey: "conveyor_motor_01" },
  { id: "conveyor-alignment", label: "Conveyor-belt misalignment", family: "Material handling", description: "Tracking error and belt damage", caseKey: "conveyor_belt_alignment_01" },
  { id: "hydraulic-press", label: "Hydraulic-press pressure loss", family: "Forming", description: "Pressure loss and defective forming", caseKey: "hydraulic_press_01" },
  { id: "welding-quality", label: "Welding-quality degradation", family: "Welding", description: "Arc or gas instability and weak welds", caseKey: "welding_quality_01" },
  { id: "injection-molding", label: "Injection-molding drift", family: "Polymer", description: "Temperature, pressure, and part-quality drift", caseKey: "injection_molding_01" },
  { id: "compressor", label: "Compressor surge / overheating", family: "Utilities", description: "Airflow restriction and compressor trips", caseKey: "air_compressor_01" },
];

const currentCaseTab: ManufacturingProblem = {
  id: "current-cnc-case",
  label: "Coolant starvation",
  family: "Current case",
  description: "Bundled CNC-VMC-07 investigation",
  caseKey: "cnc_vmc_07",
};

function formatPercent(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${(value * 100).toFixed(0)}%`;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "Not available";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function titleCase(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function severityClass(value: string): string {
  const upper = value.toUpperCase();
  if (upper === "CRITICAL" || upper === "HIGH") return "badge badge-danger";
  if (upper === "MEDIUM" || upper === "NEEDS_REVIEW") return "badge badge-warning";
  if (upper === "VALIDATED" || upper === "LOW" || upper === "CONFIRMED") return "badge badge-success";
  return "badge badge-neutral";
}

function isSpindleBearingCase(data: AnalysisResponse): boolean {
  return data.result.case.problem_code === "spindle_bearing_degradation";
}

function ProblemTabs({
  caseKey,
  availableCases,
  onSelect,
}: {
  caseKey: string;
  availableCases: CaseMetadata[];
  onSelect: (nextCaseKey: string) => void;
}) {
  const availableKeys = new Set(availableCases.map((item) => item.case_key));
  const options = [currentCaseTab, ...manufacturingProblems];
  return (
    <section className="problem-tabs" aria-label="Manufacturing problems">
      <div className="problem-tabs-heading">
        <div>
          <span className="eyebrow">Manufacturing problem library</span>
          <strong>Choose an investigation</strong>
        </div>
        <small>{availableCases.length} case{availableCases.length === 1 ? "" : "s"} available</small>
      </div>
      <div className="problem-tabs-list">
        {options.map((problem) => {
          const available = Boolean(problem.caseKey && availableKeys.has(problem.caseKey));
          const active = problem.caseKey === caseKey;
          return (
            <button
              className={`problem-tab ${active ? "active" : ""}`}
              disabled={!available}
              key={problem.id}
              onClick={() => problem.caseKey && onSelect(problem.caseKey)}
              title={available ? problem.description : `${problem.description} · Coming soon`}
              type="button"
            >
              <span className="problem-tab-family">{problem.family}</span>
              <strong>{problem.label}</strong>
              <small>{available ? "Open case" : "Coming soon"}</small>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function Metric({ label, value, detail, tone = "default" }: { label: string; value: string; detail?: string; tone?: string }) {
  return (
    <div className={`metric-card metric-${tone}`}>
      <span className="metric-label">{label}</span>
      <strong>{value}</strong>
      {detail && <span className="metric-detail">{detail}</span>}
    </div>
  );
}

function SectionHeader({ eyebrow, title, children }: { eyebrow?: string; title: string; children?: ReactNode }) {
  return (
    <div className="section-header">
      <div>
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h2>{title}</h2>
      </div>
      {children}
    </div>
  );
}

function EvidenceList({ result, refs }: { result: CaseResult; refs: string[] }) {
  const evidence = refs.map((ref) => result.evidence.find((item) => item.chunk_id === ref)).filter(Boolean);
  if (!evidence.length) return <div className="empty-note">No retrieved document span is linked to this item.</div>;
  return (
    <div className="evidence-list">
      {evidence.map((item) => item && (
        <details className="evidence-item" key={item.chunk_id}>
          <summary>{item.section} · {item.document_id}</summary>
          <small>{item.chunk_id} · characters {item.start_char}–{item.end_char} · score {item.retrieval_score.toFixed(2)}</small>
          <p>{item.text}</p>
        </details>
      ))}
    </div>
  );
}

function ChartCard({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <section className="panel chart-card">
      <div className="chart-heading"><div><h3>{title}</h3>{subtitle && <span>{subtitle}</span>}</div></div>
      <div className="chart-wrap">{children}</div>
    </section>
  );
}

function useChartTooltip() {
  return {
    contentStyle: { background: "#ffffff", border: "1px solid #cbd7e2", borderRadius: 10, color: "#172b43", boxShadow: "0 8px 24px rgba(35, 56, 78, .14)" },
    labelStyle: { color: "#74869a" },
  };
}

function signalLabel(signal: string): string {
  return titleCase(signal).replace(/\bMm S\b/g, "mm/s").replace(/\bPct\b/g, "%");
}

function qualityMetric(record: CaseResult["quality_records"][number]): { value: number; unit: string } | null {
  const raw = record.quality_measurement ?? record.quality_value ?? record.surface_finish_ra_um;
  if (raw === undefined) return null;
  const value = Number(raw);
  return Number.isFinite(value) ? { value, unit: record.quality_unit || (record.surface_finish_ra_um ? "µm" : "") } : null;
}

function TelemetryChart({
  telemetry,
  signals,
  title,
  subtitle,
}: {
  telemetry: TelemetryRow[];
  signals: string[];
  title: string;
  subtitle: string;
}) {
  const tooltip = useChartTooltip();
  const rows = telemetry.map((row) => {
    const chartRow: Record<string, string | number | null> = { timestamp: formatDate(row.timestamp) };
    signals.forEach((signal) => { chartRow[signal] = row[signal] ?? null; });
    return chartRow;
  });
  const colors = ["#d94f61", "#3269d6", "#d99a2d", "#0d9c8e", "#7650b5"];
  return (
    <ChartCard title={title} subtitle={subtitle}>
      {signals.length && rows.length ? (
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 12, right: 12, bottom: 8, left: 0 }}>
            <CartesianGrid stroke="#e2e9ef" vertical={false} />
            <XAxis dataKey="timestamp" stroke="#74869a" />
            <YAxis stroke="#74869a" />
            <Tooltip {...tooltip} />
            {signals.map((signal, index) => (
              <Line key={signal} type="monotone" dataKey={signal} name={signalLabel(signal)} stroke={colors[index % colors.length]} strokeWidth={2.5} dot={{ r: 3 }} connectNulls={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      ) : <div className="empty-note">Telemetry signals are unavailable.</div>}
    </ChartCard>
  );
}

function OperationsView({ data, telemetry }: { data: AnalysisResponse; telemetry: TelemetryRow[] }) {
  const result = data.result;
  const root = result.root_causes.find((item) => item.role === "root_cause");
  const spindleBearing = isSpindleBearingCase(data);
  const quality = result.quality_records.map((record) => {
    const metric = qualityMetric(record);
    return { label: (record.quality_status || "unknown").toUpperCase(), value: metric?.value ?? 0, unit: metric?.unit || "" };
  });
  const defaultPrimary = spindleBearing
    ? ["spindle_bearing_temp_c", "spindle_vibration_rms_mm_s", "spindle_motor_current_a"]
    : ["coolant_flow_l_min", "coolant_pressure_bar", "spindle_bearing_temp_c"];
  const defaultContext = spindleBearing
    ? ["spindle_load_pct", "spindle_motor_current_a", "feed_rate_mm_min"]
    : ["coolant_pump_current_a", "spindle_vibration_rms_mm_s", "spindle_load_pct"];
  const primarySignals = Array.isArray(data.manifest.primary_signals) ? data.manifest.primary_signals.map(String) : defaultPrimary;
  const contextSignals = Array.isArray(data.manifest.context_signals) ? data.manifest.context_signals.map(String) : defaultContext;
  return (
    <>
      <div className="summary-grid summary-grid-4">
        <Metric label="Incident severity" value={result.status} tone="danger" detail="Historical incident state" />
        <Metric label="Primary cause" value={root ? formatPercent(root.score) : "—"} tone="success" detail={root?.title || "No confirmed cause"} />
        <Metric label="Resolution" value={data.resolution_status} tone="success" detail="Based on maintenance + validation" />
        <Metric label="Quality recovery" value={quality.length > 1 ? `${quality[0].value.toFixed(1)} → ${quality.at(-1)?.value.toFixed(1)} ${quality.at(-1)?.unit}` : "—"} detail={quality[0]?.unit ? `Quality metric (${quality[0].unit})` : "Quality metric"} />
      </div>
      <div className="split-grid">
        <div className="panel story-panel">
          <span className="eyebrow">Investigation readout</span>
          <h3>{root?.title || "No root-cause hypothesis"}</h3>
          <p>{root?.rationale || "The available data is not sufficient to support a conclusion."}</p>
          <div className="next-action"><span>Recommended next check</span><strong>{root?.recommended_check || "Add independent evidence."}</strong></div>
          {root && <EvidenceList result={result} refs={root.evidence_refs} />}
        </div>
        <ChartCard title="Quality recovery" subtitle="Failed part versus validation cut">
          {quality.length ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={quality} margin={{ top: 12, right: 12, bottom: 8, left: 0 }}>
                <CartesianGrid stroke="#e2e9ef" vertical={false} />
                <XAxis dataKey="label" stroke="#74869a" />
                <YAxis stroke="#74869a" />
               <Tooltip {...useChartTooltip()} />
                 <Bar dataKey="value" name={`Quality ${quality[0]?.unit || "value"}`} radius={[5, 5, 0, 0]}>
                  {quality.map((item) => <Cell key={item.label} fill={item.label === "FAIL" ? "#d94f61" : "#0d9c8e"} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : <div className="empty-note">Product quality is unavailable.</div>}
        </ChartCard>
      </div>
      <div className="split-grid">
        <TelemetryChart telemetry={telemetry} signals={primarySignals} title="Primary condition signals" subtitle="Signals selected for this manufacturing problem" />
        <TelemetryChart telemetry={telemetry} signals={contextSignals} title="Operating context" subtitle="Load and process context during the incident" />
      </div>
      <SectionHeader eyebrow="Sequence of events" title="Incident timeline" />
      <Timeline events={result.timeline} />
      <SectionHeader eyebrow="Work order evidence" title="Corrective actions" />
      <MaintenanceTable records={result.maintenance_evidence} />
    </>
  );
}

function Timeline({ events }: { events: TimelineEvent[] }) {
  if (!events.length) return <div className="panel empty-note">No event, quality, or maintenance timeline records are available.</div>;
  return (
    <div className="timeline panel">
      {events.map((event, index) => (
        <div className="timeline-row" key={`${event.timestamp}-${event.code}-${index}`}>
          <div className="timeline-time">{formatDate(event.timestamp)}</div>
          <div className={`timeline-dot timeline-${event.type}`} />
          <div><div className="timeline-title"><strong>{titleCase(event.code || event.type)}</strong><span className="badge badge-neutral">{event.type}</span></div><p>{event.message || "No description"}</p><small>{event.source || "source unavailable"}</small></div>
        </div>
      ))}
    </div>
  );
}

function MaintenanceTable({ records }: { records: CaseResult["maintenance_evidence"] }) {
  if (!records.length) return <div className="panel empty-note">Physical causes remain suspected. Add a work order or independent measurement.</div>;
  return (
    <div className="panel table-scroll"><table><thead><tr><th>Action</th><th>Component</th><th>Status</th><th>Before</th><th>After</th><th>Evidence</th></tr></thead><tbody>
      {records.map((row, index) => <tr key={`${row.maintenance_event_id}-${index}`}><td>{titleCase(row.action_type || "—")}</td><td>{row.component || "—"}</td><td><span className={severityClass(row.status || "")}>{titleCase(row.status || "unknown")}</span></td><td>{row.measurement_before || "—"} {row.measurement_unit || ""}</td><td>{row.measurement_after || "—"} {row.measurement_unit || ""}</td><td className="mono">{row.evidence_ref || "—"}</td></tr>)}
    </tbody></table></div>
  );
}

function MlEngineeringView({ data, predictions }: { data: AnalysisResponse; predictions: PredictionRow[] }) {
  const result = data.result;
  const manifest = data.manifest;
  const spindleBearing = isSpindleBearingCase(data);
  const findings = [...result.model_findings].sort((a, b) => ({ HIGH: 0, MEDIUM: 1, LOW: 2 }[a.severity] ?? 3) - ({ HIGH: 0, MEDIUM: 1, LOW: 2 }[b.severity] ?? 3));
  const maxActionable = Math.max(0, ...predictions.filter((item) => data.result.case.incident_start_at && item.timestamp < data.result.case.incident_start_at).map((item) => item.score));
  const threshold = predictions[0]?.threshold ?? Number(manifest.decision_threshold || 0.65);
  const predictionRows = predictions.map((item) => ({ ...item, timestampLabel: formatDate(item.timestamp) }));
  const driftEntries = Object.entries((manifest.feature_drift || {}) as Record<string, number>);
  const tooltip = useChartTooltip();
  return (
    <>
      <div className="summary-grid summary-grid-4">
        <Metric label="Model" value={String(manifest.model_id || "Not available")} detail={`Version ${String(manifest.model_version || "—")}`} />
        <Metric label="Decision threshold" value={threshold.toFixed(2)} detail="Risk score probability" />
        <Metric label="Max actionable score" value={maxActionable.toFixed(2)} tone={maxActionable < threshold ? "warning" : "success"} detail="Before incident start" />
        <Metric label="Audit status" value={data.result.model_audit_status} tone="warning" detail={`${findings.length} findings`} />
      </div>
      <ChartCard title="Prediction timing" subtitle="Late detection is not preventive warning">
        {predictionRows.length ? <ResponsiveContainer width="100%" height="100%"><ComposedChart data={predictionRows} margin={{ top: 16, right: 20, bottom: 8, left: 0 }}>
          <CartesianGrid stroke="#e2e9ef" vertical={false} /><XAxis dataKey="timestampLabel" stroke="#74869a" /><YAxis domain={[0, 1]} stroke="#74869a" /><Tooltip {...tooltip} /><ReferenceLine y={threshold} stroke="#d99a2d" strokeDasharray="5 5" label={{ value: `threshold ${threshold}`, fill: "#aa7110" }} />
          <Line type="monotone" dataKey="score" name="Risk score" stroke="#0d9c8e" strokeWidth={3} dot={{ r: 6, fill: "#0d9c8e" }} />
        </ComposedChart></ResponsiveContainer> : <div className="empty-note">Early-warning performance was not evaluated.</div>}
      </ChartCard>
      <SectionHeader eyebrow="Prioritized remediation" title="Audit findings queue" />
      <div className="panel table-scroll"><table><thead><tr><th>ID</th><th>Severity</th><th>Category</th><th>Finding</th><th>Metric</th><th>Remediation</th></tr></thead><tbody>
        {findings.map((finding) => <tr key={finding.finding_id}><td className="mono">{finding.finding_id}</td><td><span className={severityClass(finding.severity)}>{finding.severity}</span></td><td>{titleCase(finding.category)}</td><td><strong>{finding.title}</strong><br /><small>{finding.description}</small></td><td>{finding.metric === null ? "—" : finding.metric.toFixed(2)}</td><td>{titleCase(finding.disposition)}</td></tr>)}
      </tbody></table></div>
      <div className="split-grid">
        <ChartCard title="Feature drift" subtitle="Review threshold at 20%">
          {driftEntries.length ? <ResponsiveContainer width="100%" height="100%"><BarChart data={driftEntries.map(([feature, value]) => ({ feature, value }))} layout="vertical" margin={{ top: 8, right: 28, bottom: 8, left: 10 }}><CartesianGrid stroke="#e2e9ef" horizontal={false} /><XAxis type="number" domain={[0, 0.6]} tickFormatter={(value) => `${Math.round(value * 100)}%`} stroke="#74869a" /><YAxis dataKey="feature" type="category" width={150} tick={{ fill: "#52677d", fontSize: 11 }} /><Tooltip {...tooltip} formatter={(value: number) => `${(value * 100).toFixed(0)}%`} /><ReferenceLine x={0.2} stroke="#d99a2d" strokeDasharray="5 5" /><Bar dataKey="value" fill="#7650b5" radius={[0, 5, 5, 0]} /></BarChart></ResponsiveContainer> : <div className="empty-note">Drift not reported.</div>}
        </ChartCard>
        <FeatureCoverage manifest={manifest} telemetry={data.result.data_quality} />
      </div>
      <div className="panel chain-panel"><span className="eyebrow">Model-to-outcome chain</span><div className="chain"><span>Features</span><i>→</i><span>Prediction</span><i>→</i><span>Alert timing</span><i>→</i><span>Machine event</span><i>→</i><span>Quality label</span></div><p>{spindleBearing ? "The model crossed its threshold after bearing degradation had started and omitted motor current from its declared physical signals." : "The current model crossed its threshold after the incident began and did not use the primary coolant precursor signals."}</p></div>
    </>
  );
}

function FeatureCoverage({ manifest, telemetry }: { manifest: Record<string, unknown>; telemetry: Record<string, unknown> }) {
  const declared = Array.isArray(manifest.declared_features) ? manifest.declared_features.map(String) : [];
  const observed = new Set(Array.isArray(telemetry.telemetry_fields) ? telemetry.telemetry_fields.map(String) : []);
  const rows = declared.map((feature) => ({
    feature,
    status: feature === "active_alarm_code" ? "Leakage risk" : observed.size && !observed.has(feature) ? "Not observed" : "Observed",
  }));
  const required = Array.isArray(manifest.required_physical_signals)
    ? manifest.required_physical_signals.map(String)
    : ["coolant_flow_l_min", "coolant_pressure_bar"];
  const missing = required.filter((feature) => !declared.includes(feature));
  rows.push(...missing.map((feature) => ({ feature, status: "Missing from model" })));
  return <section className="panel"><div className="chart-heading"><div><h3>Feature coverage</h3><span>{Number(telemetry.telemetry_rows || 0)} telemetry rows observed</span></div></div><div className="coverage-list">{rows.map((row) => <div className="coverage-row" key={row.feature}><span className="mono">{row.feature}</span><span className={severityClass(row.status)}>{row.status}</span></div>)}</div></section>;
}

function ManagementView({ data }: { data: AnalysisResponse }) {
  const result = data.result;
  const spindleBearing = isSpindleBearingCase(data);
  const root = result.root_causes.find((item) => item.role === "root_cause");
  const quality = result.quality_records.map((record) => qualityMetric(record)?.value || 0);
  const decisions = spindleBearing ? [
    ["Inspect bearing health before release", "SB-001", "Confirm lubrication, vibration, and temperature are stable during the validation cycle."],
    ["Add motor current to the model", "AUD-002", "Capture the electrical precursor that rose with bearing friction."],
    ["Rebuild the evaluation split", "AUD-003", "Remove overlap and separate late detection from preventive warning."],
  ] : [
    ["Remove alarm leakage", "AUD-001", "Prevent post-event signals from inflating model quality."],
    ["Add coolant features", "AUD-002", "Capture the physical precursor that appeared before failure."],
    ["Rebuild evaluation", "AUD-003", "Use time- and machine-grouped holdouts without overlap."],
  ];
  const causalSteps = Array.isArray(data.manifest.causal_chain)
    ? data.manifest.causal_chain.map(String)
    : spindleBearing
    ? ["Lubrication breakdown", "Bearing friction", "Heat + vibration", "Spindle trip", "Quality failure"]
    : ["Filter restriction", "Low flow / pressure", "Heat + vibration", "Chatter + tool wear", "Quality failure"];
  return <>
    <div className="panel executive-panel"><span className="eyebrow">Executive summary</span><h2>{root?.title || "Insufficient evidence"}</h2><p>{root ? `${root.rationale} The corrective work was validated, but the predictive model requires remediation.` : "The available case data does not support an executive conclusion."}</p></div>
    <div className="summary-grid summary-grid-4"><Metric label="Incident severity" value={result.status} tone="danger" /><Metric label="Confirmed cause" value={root ? formatPercent(root.score) : "—"} tone="success" /><Metric label="Validation" value={data.resolution_status} tone="success" /><Metric label="Actions required" value={String(result.model_findings.length)} tone="warning" /></div>
    <div className="split-grid"><ChartCard title="Before / after quality" subtitle="Production quality measurement"><ResponsiveContainer width="100%" height="100%"><BarChart data={quality.map((value, index) => ({ label: index === 0 ? "Failed part" : "Validation cut", value }))} margin={{ top: 16, right: 18, bottom: 8, left: 0 }}><CartesianGrid stroke="#e2e9ef" vertical={false} /><XAxis dataKey="label" stroke="#74869a" /><YAxis stroke="#74869a" /><Tooltip {...useChartTooltip()} /><Bar dataKey="value" name="Quality value" radius={[5, 5, 0, 0]}>{quality.map((_, index) => <Cell key={index} fill={index === 0 ? "#d94f61" : "#0d9c8e"} />)}</Bar></BarChart></ResponsiveContainer></ChartCard><div className="panel causal-panel"><span className="eyebrow">Causal story</span><div className="causal-chain">{causalSteps.map((step, index) => <div key={step} className="causal-step"><span>0{index + 1}</span><strong>{step}</strong>{index < 4 && <i>→</i>}</div>)}</div><p>{spindleBearing ? "Bearing service restored temperature and vibration, and the validation cut passed the dimensional and surface-finish limits." : "Correction restored the machine condition and produced a passing validation result."}</p></div></div>
    <SectionHeader eyebrow="Decisions" title="Corrective actions" /><div className="panel table-scroll"><table><thead><tr><th>Priority</th><th>Decision</th><th>Finding</th><th>Why it matters</th></tr></thead><tbody>{decisions.map(([decision, finding, reason], index) => <tr key={finding}><td><span className="priority">0{index + 1}</span></td><td><strong>{decision}</strong></td><td className="mono">{finding}</td><td>{reason}</td></tr>)}</tbody></table></div><p className="muted-note">Business cost, downtime, throughput, and fleet trends are not quantified in this single-case fixture.</p>
  </>;
}

function ReliabilityView({ data }: { data: AnalysisResponse }) {
  const result = data.result;
  const groupedNodes = result.graph.nodes.reduce<Record<string, GraphNode[]>>((groups, node) => { (groups[node.kind] ||= []).push(node); return groups; }, {});
  const layers = [
    ["Machine", true, "Asset observed"],
    ["Sensor", result.anomalies.length > 0, `${result.anomalies.length} anomalies`],
    ["Data", Number(result.data_quality.telemetry_rows || 0) > 0, `${result.data_quality.telemetry_rows || 0} rows`],
    ["Features", result.model_findings.length > 0, `${result.model_findings.length} findings`],
    ["Model", Boolean(data.manifest.model_id), data.manifest.model_id ? String(data.manifest.model_id) : "Not observed"],
    ["Alert", Number(result.data_quality.prediction_count || 0) > 0, `${result.data_quality.prediction_count || 0} scores`],
    ["Outcome", result.quality_records.length > 0, `${result.quality_records.length} quality records`],
  ] as const;
  return <>
    <div className="panel graph-panel"><SectionHeader eyebrow="Evidence graph" title="Model-to-machine reliability chain"><span className="badge badge-neutral">{result.graph.nodes.length} nodes · {result.graph.edges.length} edges</span></SectionHeader><div className="graph-lanes">{Object.entries(groupedNodes).map(([kind, nodes]) => <div className="graph-lane" key={kind}><span className="graph-kind">{titleCase(kind)}</span><div className="graph-nodes">{nodes.slice(0, 6).map((node) => <div className="graph-node" key={node.id} title={node.id}><strong>{String(node.properties.title || node.properties.name || node.kind)}</strong><small>{node.id.slice(0, 18)}</small></div>)}</div></div>)}</div></div>
    <SectionHeader eyebrow="Competing explanations" title="Ranked hypotheses" />
    <div className="panel table-scroll"><table><thead><tr><th>Score</th><th>Role</th><th>Status</th><th>Hypothesis</th><th>Recommended check</th></tr></thead><tbody>{result.root_causes.map((item) => <tr key={item.title}><td><strong>{formatPercent(item.score)}</strong></td><td>{titleCase(item.role)}</td><td><span className={severityClass(item.status)}>{titleCase(item.status)}</span></td><td><strong>{item.title}</strong><br /><small>{item.rationale}</small></td><td>{item.recommended_check}</td></tr>)}</tbody></table></div>
    <div className="section-header"><div><span className="eyebrow">Coverage</span><h2>Reliability chain</h2></div></div><div className="layer-grid">{layers.map(([label, present, detail]) => <div className={`layer-card ${present ? "layer-present" : "layer-missing"}`} key={label}><span>{label}</span><strong>{present ? "Observed" : "Not observed"}</strong><small>{detail}</small></div>)}</div>
    <div className="panel"><SectionHeader eyebrow="Reproducibility" title="Provenance and data quality" /><pre className="json-block">{JSON.stringify({ schema_version: data.schema_version, data_quality: result.data_quality, warnings: result.warnings }, null, 2)}</pre></div>
  </>;
}

function App() {
  const [persona, setPersona] = useState<Persona>("Operations");
  const [caseKey, setCaseKey] = useState(defaultCaseKey);
  const [caseKeys, setCaseKeys] = useState<CaseMetadata[]>([]);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [telemetry, setTelemetry] = useState<TelemetryRow[]>([]);
  const [predictions, setPredictions] = useState<PredictionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [casesReady, setCasesReady] = useState(false);

  useEffect(() => {
    let active = true;
    getCases().then((response) => {
      if (!active) return;
      setCaseKeys(response.cases);
      if (!response.cases.length) {
        setError("The API is reachable, but it published no cases. Verify that demo/cnc_vmc_07 is included in the Render deployment.");
        setLoading(false);
        return;
      }
      const selected = response.cases.find((item) => item.case_key === defaultCaseKey)?.case_key
        || response.default_case_key
        || response.cases[0].case_key;
      setCaseKey(selected);
      setCasesReady(true);
    }).catch((reason: Error) => {
      if (!active) return;
      setError(reason.message);
      setLoading(false);
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!casesReady || !caseKey) return;
    let active = true;
    setLoading(true);
    setError(null);
    Promise.all([getAnalysis(caseKey), getTelemetry(caseKey), getPredictions(caseKey)])
      .then(([nextAnalysis, nextTelemetry, nextPredictions]) => {
        if (!active) return;
        setAnalysis(nextAnalysis);
        setTelemetry(nextTelemetry.rows);
        setPredictions(nextPredictions.rows);
      })
      .catch((reason: Error) => { if (active) setError(reason.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [caseKey, casesReady]);

  const activePersona = useMemo(() => personaOptions.find((item) => item.id === persona) || personaOptions[0], [persona]);

  const selectCase = (nextCaseKey: string) => {
    if (nextCaseKey === caseKey) return;
    setCaseKey(nextCaseKey);
    setAnalysis(null);
    setTelemetry([]);
    setPredictions([]);
    setLoading(true);
    setError(null);
  };

  if (loading && !analysis) return <div className="app-shell loading-screen"><div className="brand-mark">TF</div><h1>TraceForge</h1><p>Loading evidence graph and telemetry…</p><div className="loader" /></div>;
  if (error && !analysis) return <div className="app-shell loading-screen"><div className="brand-mark">TF</div><h1>TraceForge</h1><div className="error-card"><h2>{error.includes("no cases") ? "No cases published" : "Backend unavailable"}</h2><p>{error}</p><code>{apiBaseUrl()}</code><p>{error.includes("no cases") ? "Redeploy the Render service from the repository root so the demo/cnc_vmc_07 fixture is included." : "Start FastAPI locally or set VITE_API_BASE_URL to the Render service URL."}</p></div></div>;
  if (!analysis) return null;
  const { result } = analysis;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark">TF</div><div><strong>TraceForge</strong><small>Industrial AI reliability</small></div></div>
         <div className="sidebar-section"><span className="eyebrow">Workspace</span><label htmlFor="case-select">Case</label><select id="case-select" value={caseKey} onChange={(event) => selectCase(event.target.value)}>{caseKeys.length ? caseKeys.map((item) => <option key={item.case_key} value={item.case_key}>{item.asset_id} · {item.case_key}</option>) : <option value={caseKey}>{caseKey}</option>}</select></div>
        <div className="sidebar-section persona-nav"><span className="eyebrow">View for</span>{personaOptions.map((option) => <button className={option.id === persona ? "persona active" : "persona"} onClick={() => setPersona(option.id)} key={option.id}><span className="persona-icon">{option.id === "Operations" ? "◉" : option.id === "ML Engineering" ? "⌁" : option.id === "Management" ? "◫" : "◈"}</span><span><strong>{option.label}</strong><small>{option.caption}</small></span></button>)}</div>
        <div className="sidebar-footer"><span className="status-pip" /> API connected<br /><small>{apiBaseUrl()}</small></div>
      </aside>
       <main className="main-content">
         <header className="topbar"><div><span className="eyebrow">Industrial AI reliability workspace</span><h1>{result.case.asset_id} <span>·</span> {result.case.problem_label || "incident investigation"}</h1><p>{result.case.description}</p></div><div className="topbar-actions"><span className={severityClass(result.status)}>{result.status}</span><span className={severityClass(analysis.resolution_status)}>{analysis.resolution_status}</span><a className="icon-button" href={`${apiBaseUrl()}/api/v1/cases/${encodeURIComponent(caseKey)}/report`} target="_blank" rel="noreferrer">Export report ↗</a></div></header>
         <div className="case-meta"><span>Incident <strong>{result.case.id}</strong></span><span>Observed {formatDate(result.case.observed_at)}</span><span>{result.case.asset_type}</span><span className="persona-label">{activePersona.label}: {activePersona.caption}</span></div>
         <ProblemTabs caseKey={caseKey} availableCases={caseKeys} onSelect={selectCase} />
        {error && <div className="inline-error">{error} · Showing the last available analysis.</div>}
        {persona === "Operations" && <OperationsView data={analysis} telemetry={telemetry} />}
        {persona === "ML Engineering" && <MlEngineeringView data={analysis} predictions={predictions} />}
        {persona === "Management" && <ManagementView data={analysis} />}
        {persona === "Reliability" && <ReliabilityView data={analysis} />}
        <footer className="app-footer"><span>TraceForge decision support · validate conclusions through approved manufacturing procedures.</span><span>Schema {analysis.schema_version}</span></footer>
      </main>
    </div>
  );
}

export default App;
