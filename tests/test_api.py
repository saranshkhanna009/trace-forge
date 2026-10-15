from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from traceforge.api import app


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_health_endpoint(self) -> None:
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_case_list_and_analysis(self) -> None:
        cases = self.client.get("/api/v1/cases")
        self.assertEqual(cases.status_code, 200)
        self.assertIn("cnc_vmc_07", {item["case_key"] for item in cases.json()["cases"]})

        analysis = self.client.get("/api/v1/cases/cnc_vmc_07/analysis")
        self.assertEqual(analysis.status_code, 200)
        body = analysis.json()
        self.assertEqual(body["resolution_status"], "VALIDATED")
        self.assertEqual(body["result"]["status"], "CRITICAL")
        self.assertTrue(any("coolant" in item["title"].lower() for item in body["result"]["root_causes"]))

    def test_chart_endpoints_return_bounded_data(self) -> None:
        telemetry = self.client.get(
            "/api/v1/cases/cnc_vmc_07/telemetry?signals=coolant_flow_l_min,spindle_vibration_rms_mm_s&limit=2"
        )
        self.assertEqual(telemetry.status_code, 200)
        self.assertEqual(len(telemetry.json()["rows"]), 2)
        self.assertEqual(telemetry.json()["signals"], ["coolant_flow_l_min", "spindle_vibration_rms_mm_s"])

        predictions = self.client.get("/api/v1/cases/cnc_vmc_07/predictions?limit=2")
        self.assertEqual(predictions.status_code, 200)
        self.assertEqual(len(predictions.json()["rows"]), 2)

    def test_unknown_case_and_signal_are_actionable_errors(self) -> None:
        missing = self.client.get("/api/v1/cases/not-a-real-case/analysis")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["detail"]["code"], "case_not_found")

        unknown_signal = self.client.get(
            "/api/v1/cases/cnc_vmc_07/telemetry?signals=not_a_signal"
        )
        self.assertEqual(unknown_signal.status_code, 422)
        self.assertEqual(unknown_signal.json()["detail"]["code"], "unknown_signal")


if __name__ == "__main__":
    unittest.main()
