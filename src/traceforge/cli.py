"""Command-line entry point for TraceForge's local investigation workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .langgraph_flow import analyze_case_with_langgraph
from .workflow import analyze_case


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Investigate an industrial AI reliability case with TraceForge."
    )
    parser.add_argument("--case", required=True, type=Path, help="Case directory containing case.json")
    parser.add_argument("--top-k", type=int, default=5, help="Number of maintenance evidence chunks")
    parser.add_argument("--langgraph", action="store_true", help="Use the optional LangGraph adapter")
    parser.add_argument("--output", type=Path, help="Write the complete JSON report to this path")
    parser.add_argument(
        "--report-dir",
        type=Path,
        help="For manufacturing cases, write incident_report.json, incident_report.md, and signal_summary.csv",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.langgraph:
        result = analyze_case_with_langgraph(args.case, top_k=args.top_k)
    else:
        result = analyze_case(args.case, top_k=args.top_k)

    print(f"Case: {result.case.id} ({result.case.asset_type})")
    print(f"Status: {result.status}")
    print(f"Anomalies: {len(result.anomalies)}")
    for anomaly in result.anomalies:
        print(f"- {anomaly.sensor}: {anomaly.severity.value} - {anomaly.explanation}")
    print(f"Model findings: {len(result.model_findings)}")
    for finding in result.model_findings:
        print(f"- {finding.severity.value} - {finding.title}: {finding.description}")
    print("Root-cause hypotheses:")
    for hypothesis in result.root_causes[:5]:
        print(
            f"- {hypothesis.score:.3f} {hypothesis.category.value}: {hypothesis.title}"
        )
        print(f"  Next check: {hypothesis.recommended_check}")
    for warning in result.warnings:
        print(f"Warning: {warning}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        print(f"JSON report: {args.output}")
    if args.report_dir:
        if result.case.domain == "cnc_manufacturing":
            from .manufacturing import write_reports

            write_reports(result, args.report_dir)
            print(f"Incident reports: {args.report_dir}")
        else:
            raise SystemExit("--report-dir is currently supported for cnc_manufacturing cases only")


if __name__ == "__main__":
    main()
