from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from traceforge.audit import audit_model, load_model_report, load_prediction_rows
from traceforge.dashboard_data import (
    feature_coverage,
    load_dashboard_case,
    prediction_chart_rows,
    quality_before_after,
)
from traceforge.ingest import chunk_document, load_case, load_case_documents
from traceforge.manufacturing import analyze_cnc_case, incident_report, write_reports
from traceforge.models import RootCauseCategory
from traceforge.telemetry import detect_anomalies, load_telemetry


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = PROJECT_ROOT / "demo" / "cnc_vmc_07"
SPINDLE_CASE_DIR = PROJECT_ROOT / "demo" / "cnc_spindle_bearing_01"


class TraceForgeTests(unittest.TestCase):
    def test_cnc_case_detects_key_telemetry_anomalies(self) -> None:
        case = load_case(CASE_DIR)
        anomalies = detect_anomalies(load_telemetry(CASE_DIR / case.telemetry_file))
        sensors = {anomaly.sensor for anomaly in anomalies}
        self.assertIn("coolant_flow_l_min", sensors)
        self.assertIn("spindle_vibration_rms_mm_s", sensors)

    def test_model_audit_detects_leakage_and_late_warning(self) -> None:
        report = load_model_report(CASE_DIR / "model_manifest.json")
        predictions = (CASE_DIR / "predictions.csv").read_text(encoding="utf-8")
        self.assertIn("active_alarm_code", report["declared_features"])
        self.assertIn("PRED-0930", predictions)
        findings = audit_model(
            report,
            load_prediction_rows(CASE_DIR / "predictions.csv"),
            "2026-03-18T09:29:42Z",
        )
        ids = {finding.finding_id for finding in findings}
        self.assertIn("AUD-001", ids)
        self.assertIn("AUD-002", ids)
        self.assertIn("AUD-005", ids)
        self.assertIn("AUD-007", ids)

    def test_document_offsets_resolve_exactly(self) -> None:
        case = load_case(CASE_DIR)
        documents, _ = load_case_documents(CASE_DIR, case)
        for document in documents:
            for chunk in chunk_document(document):
                self.assertEqual(document.text[chunk.start_char : chunk.end_char], chunk.text)

    def test_full_cnc_case_confirms_filter_and_tool_findings(self) -> None:
        result = analyze_cnc_case(CASE_DIR)
        self.assertEqual(result.status, "CRITICAL")
        self.assertGreaterEqual(len(result.anomalies), 3)
        self.assertGreaterEqual(len(result.model_findings), 6)
        root = next(item for item in result.root_causes if item.role == "root_cause")
        self.assertEqual(root.status, "confirmed")
        self.assertIn("coolant", root.title.lower())
        self.assertTrue(any(item.role == "contributing_factor" for item in result.root_causes))
        self.assertTrue(any(item.role == "alternative" for item in result.root_causes))
        self.assertTrue(any(item.category is RootCauseCategory.DATA_PIPELINE for item in result.root_causes))

    def test_spindle_bearing_case_confirms_bearing_failure(self) -> None:
        case = load_case(SPINDLE_CASE_DIR)
        self.assertEqual(case.problem_code, "spindle_bearing_degradation")
        result = analyze_cnc_case(SPINDLE_CASE_DIR)
        self.assertEqual(result.status, "CRITICAL")
        self.assertGreaterEqual(len(result.anomalies), 3)
        root = next(item for item in result.root_causes if item.role == "root_cause")
        self.assertEqual(root.status, "confirmed")
        self.assertIn("bearing", root.title.lower())
        self.assertTrue(any(item.status == "ruled_out" for item in result.root_causes))

    def test_report_contract_and_outputs_are_reproducible(self) -> None:
        first = analyze_cnc_case(CASE_DIR)
        second = analyze_cnc_case(CASE_DIR)
        self.assertEqual(first.graph.to_dict(), second.graph.to_dict())
        report = incident_report(first)
        self.assertEqual(report["schema_version"], "traceforge.incident.v1")
        self.assertEqual(report["root_cause"]["failure_mode_code"], "coolant_starvation")
        self.assertTrue(report["signal_summary"])
        self.assertTrue(report["evidence_refs"])
        with tempfile.TemporaryDirectory() as directory:
            output_dir = write_reports(first, directory)
            self.assertTrue((output_dir / "incident_report.md").is_file())
            self.assertTrue((output_dir / "signal_summary.csv").is_file())
            written = json.loads((output_dir / "incident_report.json").read_text(encoding="utf-8"))
            self.assertEqual(written, report)
            headings = (output_dir / "incident_report.md").read_text(encoding="utf-8")
            self.assertIn("## Ranked failure modes", headings)
            self.assertIn("## Evidence index", headings)

    def test_invalid_case_reports_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError) as context:
                analyze_cnc_case(directory)
            self.assertIn("case.json", str(context.exception))

    def test_dashboard_view_model_supports_all_personas(self) -> None:
        dashboard_case = load_dashboard_case(CASE_DIR)
        self.assertEqual(dashboard_case.resolution_status, "VALIDATED")
        self.assertEqual(dashboard_case.result.status, "CRITICAL")
        self.assertEqual(len(prediction_chart_rows(dashboard_case)), 4)
        self.assertEqual(len(quality_before_after(dashboard_case)), 2)
        coverage = feature_coverage(dashboard_case)
        self.assertTrue(any(row["status"] == "Leakage risk" for row in coverage))
        self.assertTrue(any(row["status"] == "Missing from model" for row in coverage))


if __name__ == "__main__":
    unittest.main()
