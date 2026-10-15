# TraceForge

**TraceForge** is an evidence-based industrial AI reliability platform.

It investigates failures across the complete chain:

```text
Machine → Sensor → Data Pipeline → Features → ML Model → Alert → Outcome
```

The central question is:

> Did the machine fail, did the sensor or data pipeline fail, did the model
> fail, or did several layers interact—and what evidence supports that answer?

TraceForge combines two capabilities that are usually built separately:

1. **ModelProof:** audits datasets, features, models, metrics, drift,
   calibration, leakage, and reproducibility.
2. **Industrial Root-Cause Investigation:** detects telemetry anomalies,
   retrieves maintenance evidence, finds similar incidents, and ranks the next
   diagnostic actions.

It is deliberately not a generic maintenance chatbot. Its output is a
replayable reliability report with evidence, confidence, uncertainty, and a
graph of the model-to-machine chain.

## What TraceForge produces

Given an industrial incident case containing telemetry, a model report, and
maintenance documents, TraceForge produces:

- sensor anomalies and baseline comparisons;
- ML audit findings such as leakage, drift, poor calibration, and missing
  reproducibility metadata;
- ranked root-cause hypotheses across physical, sensor, data, and model
  layers;
- recommended next diagnostic checks;
- retrieved source passages with stable document offsets;
- a JSON reliability graph connecting assets, sensors, findings, models, and
  evidence;
- a conservative status such as `NO_FINDINGS`, `NEEDS_REVIEW`, or `CRITICAL`.

The first local slice is deterministic and requires no API key. Its interfaces
are intentionally designed for later BM25/vector retrieval, transformer
models, LangChain components, LangGraph branching, and a graph database.

## Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│ Case inputs                                                     │
│ telemetry.csv · model_report.json · manuals · incident reports │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                    Ingestion and normalization
                                │
             ┌──────────────────┴──────────────────┐
             │                                     │
   Time-series analysis                    ML artifact audit
   baseline + anomalies                    leakage + drift +
   change detection                        calibration + repro
             │                                     │
             └──────────────────┬──────────────────┘
                                │
                       Hybrid evidence RAG
                  manuals · logs · prior incidents
                                │
                                ▼
                    Unified reliability evidence graph
                                │
                                ▼
                    Root-cause correlation layer
                                │
                                ▼
             Evidence-backed report and next diagnostic step
```

### Planned production workflow

```text
Receive incident
    ↓
Load case artifacts and validate provenance
    ↓
┌──────────────────┬──────────────────┬──────────────────┐
│ Telemetry branch │ Model audit      │ Document RAG     │
│ anomaly model    │ leakage/drift    │ manuals/incidents│
└──────────────────┴──────────────────┴──────────────────┘
    ↓
Correlate sensor, data, model, and document evidence
    ↓
Rank root-cause hypotheses
    ↓
Critic/reviewer checks unsupported conclusions
    ↓
Generate report, graph, confidence, and next check
```

### Technology mapping

| Layer | Initial implementation | Planned extension |
|---|---|---|
| Ingestion | Python standard library, CSV, JSON, Markdown | PDF, tables, object storage |
| Retrieval | Deterministic lexical retrieval | BM25 + vector search + reranker |
| Evidence | Stable source offsets and graph edges | Neo4j or another graph store |
| Orchestration | Typed Python workflow | LangGraph branches, retries, checkpoints |
| LLM integration | Provider-independent interfaces | LangChain loaders, retrievers, structured output |
| Deep learning | Replaceable anomaly/audit interfaces | TCN, temporal transformer, NLI, GNN |
| Interface | CLI, JSON report, and Streamlit dashboard | FastAPI + React investigation console |

## Repository layout

```text
src/traceforge/
  audit.py          # ML artifact checks
  cli.py            # local case-analysis command
  graph.py          # reliability graph and serialization
  ingest.py         # case, document, and provenance ingestion
  langgraph_flow.py # optional LangGraph orchestration
  models.py         # industrial reliability domain model
  retrieval.py      # evidence retrieval baseline
  manufacturing.py  # CNC incident correlation and report writers
  telemetry.py      # CSV loading and anomaly detection
  workflow.py       # first end-to-end case workflow
tests/
  test_traceforge.py
demo/cnc_vmc_07/
  manifest.json             # bundle schema and relative file inventory
  case.json
  telemetry.csv
  events.csv
  production_quality.csv
  maintenance.csv
  predictions.csv
  labels.csv
  model_manifest.json
  documents/
    maintenance-evidence.md
```

## Quick start

The initial case path uses only Python's standard library.

```powershell
cd C:\Users\saransh\verigraph
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
python -m traceforge.cli --case demo/cnc_vmc_07
python -m traceforge.cli `
  --case demo/cnc_vmc_07 `
  --report-dir artifacts/cnc-vmc-07
```

The optional LangGraph adapter is available after installing the orchestration
extra:

```powershell
python -m pip install -e ".[orchestration]"
python -m traceforge.cli --case demo/cnc_vmc_07 --langgraph
```

The first command is the reproducible default. The second command exercises
the same domain workflow through explicit LangGraph state transitions.

## Deployable dashboard

TraceForge includes a local-first Streamlit dashboard at:

```text
src/traceforge/dashboard.py
```

It uses a normalized dashboard view model and provides four audience-specific
views without requiring a database, API key, or network service:

- **Operations / Maintenance:** signal charts, incident timeline, quality
  recovery, corrective actions, and source evidence;
- **ML Engineering:** model contract, prediction timing, leakage, drift,
  calibration, feature coverage, and remediation queue;
- **Management:** executive summary, before/after outcome, causal story, and
  prioritized decisions;
- **Engineering / Reliability:** interactive evidence graph, competing
  hypotheses, reliability-chain coverage, and provenance/data quality.

The dashboard keeps these concepts separate:

```text
Incident severity  ≠  Root-cause confidence  ≠  Resolution status
```

For example, a historical incident can remain `CRITICAL` while its current
resolution is `VALIDATED` after a passing validation cut.

Run locally:

```powershell
python -m pip install -e ".[dashboard]"
python -m streamlit run dashboard.py
```

Then open `http://localhost:8501`. The default CNC case is bundled, and the
sidebar also accepts another case directory that follows the same `case.json`
contract. Use the export buttons in the footer to share JSON, Markdown, or
graph artifacts with maintenance, ML, management, and reliability personnel.

The dashboard entry point also bootstraps the local `src` path when Streamlit
executes it as a script, so this command works from the repository root even
before an editable package install, provided Streamlit and Plotly are already
available:

```powershell
python -m streamlit run dashboard.py
```

Build a portable deployment image:

```powershell
docker build -t traceforge-api .
docker run --rm -p 8000:8000 -e FRONTEND_ORIGINS=http://localhost:5173 traceforge-api
```

The Streamlit dashboard remains available as a local fallback, but it is not
the recommended multi-user deployment. The production dashboard path is now
**React/Vite on Vercel** and **FastAPI on Render**:

```text
frontend/             # React/Vite dashboard for Vercel
render.yaml           # Render FastAPI web-service blueprint
src/traceforge/api.py # read-only API consumed by the frontend
DEPLOYMENT.md         # exact deployment sequence and environment variables
```

Use `DEPLOYMENT.md` for the Vercel and Render setup. The frontend uses
`VITE_API_BASE_URL` to call Render, while the API uses `FRONTEND_ORIGINS` to
allow configured browser origins. CORS is not authentication; add auth before
serving private industrial data.

## Case format

```text
demo/cnc_vmc_07/
  case.json                 # incident metadata and relative file paths
  telemetry.csv             # CNC state, tool, spindle, coolant, and alarm signals
  events.csv                # controller alarms and operator observations
  production_quality.csv   # surface finish and dimensional inspection
  maintenance.csv          # work-order observations and corrective actions
  predictions.csv          # point-in-time model scores
  labels.csv               # post-incident ground truth
  model_manifest.json      # model contract, feature list, drift, and calibration
  documents/
    maintenance-evidence.md
```

Every evidence citation keeps the source document ID, section, character
offsets, and exact source text. The graph is content-addressed so a repeated
run over the same inputs produces stable topology.

## Industrial domain choices

The project can eventually support several domains. We chose a CNC machining
case as the current learning and evaluation boundary because it connects
machine health, model behavior, and product quality in one incident.

### 1. Industrial pumps

Pumps move liquids through manufacturing plants, water systems, chemical
facilities, and energy infrastructure. Common signals include vibration,
temperature, pressure, flow rate, motor current, and rotational speed.

Typical failures:

- bearing wear;
- cavitation;
- seal leakage;
- blockage or filter obstruction;
- overheating;
- misalignment;
- loss of prime.

Why it remains a useful future domain:

- sensor features are understandable;
- failure modes can be explained clearly;
- a small synthetic case can demonstrate the complete architecture;
- the same workflow applies to many industries;
- there is less operational complexity than a full plant or aircraft engine.

### 2. Turbines and turbofan engines

Turbines have many interacting sensors and long degradation cycles. Turbofan
datasets are useful for remaining-useful-life prediction and expose realistic
multivariate time-series problems.

Typical signals include temperatures, pressures, fan speeds, and efficiency
measurements. The ML work is richer, but the domain requires more careful
feature interpretation and longer-running sequences.

Best for demonstrating:

- temporal transformers;
- remaining-useful-life prediction;
- multivariate drift;
- uncertainty over long horizons.

### 3. Manufacturing machines — current domain

Manufacturing equipment includes CNC machines, robotic arms, presses, welding
systems, and assembly lines. Failures can affect production quality as well as
machine uptime.

Typical data includes vibration, spindle load, acoustic signals, current,
cycle time, product quality, and operator events.

Best for demonstrating:

- anomaly detection tied to quality defects;
- computer vision or acoustic deep learning;
- scheduling and maintenance recommendations;
- multiple assets interacting in a production line.

Our first fixture is a 3-axis CNC vertical machining center, `CNC-VMC-07`,
machining an aluminum finishing operation with tool `T12`. Coolant starvation
from a clogged filter causes rising temperature and vibration, tool wear,
chatter, and an out-of-spec surface finish. This lets TraceForge test both
physical root-cause reasoning and model audit logic.

The key manufacturing-specific chain is:

```text
Coolant restriction → thermal escalation → tool wear/chatter
→ surface-finish failure → model early-warning review
```

### 4. Chemical and process plants

Process plants contain pumps, reactors, heat exchangers, tanks, valves, and
controllers connected in a process network. A local fault can propagate through
the process.

Typical data includes pressure, flow, temperature, level, composition, valve
state, and control-loop values.

Best for demonstrating:

- graph-based fault propagation;
- process-state estimation;
- causal hypotheses;
- safety-aware diagnostic workflows.

This is the most compelling graph use case, but also the highest-risk domain.
TraceForge must present ranked hypotheses and recommended checks, never
autonomous control commands.

### 5. Wind turbines

Wind turbines combine mechanical, electrical, weather, and environmental
signals. Wind conditions make normal behavior highly variable.

Typical data includes wind speed, rotor speed, pitch angle, generator
temperature, gearbox vibration, power output, and yaw position.

Best for demonstrating:

- context-aware anomaly detection;
- weather-conditioned baselines;
- remaining-useful-life prediction;
- maintenance planning across a fleet.

The main challenge is distinguishing a true fault from a legitimate change in
wind or operating conditions.

## What is in the current manufacturing slice

The CNC demo intentionally includes both sides of the product:

- coolant-flow, pressure, pump-current, temperature, vibration, and spindle-load trends;
- a failed quality inspection and a passing validation cut;
- maintenance records confirming a clogged filter and worn tool;
- a model manifest with an alarm leakage feature, omitted coolant features,
  drift, calibration error, and missing data version;
- point-in-time predictions that distinguish late detection from actionable
  early warning;
- ranked root causes with `confirmed`, `contributing_factor`, `ruled_out`,
  and `model_risk` roles;
- JSON, Markdown, CSV, and graph-backed report output.

It is an evidence and reasoning foundation, not yet a production safety system.
The anomaly detector is a transparent baseline; deep models will be evaluated
against it rather than silently replacing it.

## Acceptance criteria

- A user can run one local command against a case directory and receive a
  reliability report.
- Telemetry anomalies include the sensor, baseline, latest value, change, and
  severity.
- Model findings identify the checked artifact and the relevant metric or
  missing field.
- Root-cause hypotheses combine telemetry, model, and document signals without
  claiming certainty.
- Every retrieved citation resolves to its original source text and offsets.
- The graph contains asset, sensor, model, finding, root-cause, and evidence
  relationships.
- The same case produces stable IDs and graph topology on repeated runs.
- Empty or malformed case inputs fail with an actionable error.

## Safety and scope boundary

TraceForge is a decision-support and investigation system. It does not issue
commands to industrial controllers, bypass safety systems, or establish causal
truth automatically. A root-cause result is a ranked hypothesis that an
engineer should validate through approved procedures.
