"""
Regression tests for business-oriented migration REST APIs.
"""

from __future__ import annotations

import unittest

try:
    from fastapi.testclient import TestClient

    from api.dependencies import get_logger, get_migration_orchestrator
    from app import create_app
except ModuleNotFoundError:  # pragma: no cover
    TestClient = None


class NullLogger:
    """Logger stub for route tests."""

    def info(self, *args, **kwargs):
        """Accept info calls."""

    def error(self, *args, **kwargs):
        """Accept error calls."""

    def warning(self, *args, **kwargs):
        """Accept warning calls."""

    def exception(self, *args, **kwargs):
        """Accept exception calls."""


class FakeMigrationOrchestrator:
    """Small orchestrator fake that keeps route tests fast."""

    def __init__(self) -> None:
        self.job_id = ""

    def run(self, *, job_id: str, uploaded_xml_name=None, uploaded_xml_content=None, persist_to_mysql=False, progress=None):
        """Return a representative migration response."""

        self.job_id = job_id
        if progress:
            progress(50, "Halfway")
        return {
            "job_id": job_id,
            "status": "Completed",
            "readiness_score": 98.5,
            "validation_summary": {
                "total_issues": 2,
                "open_issues": 0,
                "resolved_issues": 2,
                "severity_counts": {"HIGH": 1, "LOW": 1},
            },
            "auto_fix_accuracy": 100.0,
            "generated_report_locations": {
                "validation_report": "output/validation_report.csv",
                "dashboard_dataset_json": "output/automation/dashboard_dataset.json",
            },
            "iics_deployment": {"provider": "MockIICSProvider", "status": {"state": "COMPLETED"}},
        }

    def generated_reports(self):
        """Return report locations."""

        return {"validation_report": "output/validation_report.csv"}

    def dashboard_dataset(self):
        """Return dashboard rows."""

        return [{"mapping_name": "M_CUSTOMER", "overall_health_score": 100}], "output/automation/dashboard_dataset.json"


@unittest.skipIf(TestClient is None, "FastAPI is not installed")
class MigrationAPIRoutesTests(unittest.TestCase):
    """Validate migration REST route behavior."""

    def test_migrate_tracks_job_and_returns_summary(self) -> None:
        """POST /migrate returns the migration summary and creates a retrievable job."""

        fake = FakeMigrationOrchestrator()
        app = create_app()
        app.dependency_overrides[get_migration_orchestrator] = lambda: fake
        app.dependency_overrides[get_logger] = lambda: NullLogger()
        client = TestClient(app)

        response = client.post("/api/v1/migrate", json={})

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("Completed", payload["status"])
        self.assertEqual(98.5, payload["readiness_score"])
        self.assertEqual("MockIICSProvider", payload["iics_deployment"]["provider"])

        job_response = client.get(f"/api/v1/jobs/{payload['job_id']}")
        self.assertEqual(200, job_response.status_code)
        self.assertEqual("Completed", job_response.json()["status"])

    def test_reports_dashboard_and_health(self) -> None:
        """GET endpoints expose reports, dashboard data, and health."""

        fake = FakeMigrationOrchestrator()
        app = create_app()
        app.dependency_overrides[get_migration_orchestrator] = lambda: fake
        app.dependency_overrides[get_logger] = lambda: NullLogger()
        client = TestClient(app)
        job_id = client.post("/api/v1/migrate", json={}).json()["job_id"]

        reports = client.get(f"/api/v1/reports/{job_id}")
        dashboard = client.get(f"/api/v1/dashboard/{job_id}")
        health = client.get("/api/v1/health")

        self.assertEqual(200, reports.status_code)
        self.assertEqual({"validation_report": "output/validation_report.csv"}, reports.json()["reports"])
        self.assertEqual(200, dashboard.status_code)
        self.assertEqual("M_CUSTOMER", dashboard.json()["dataset"][0]["mapping_name"])
        self.assertEqual({"status": "UP", "service": "PowerCenter to IDMC Migration Accelerator API", "version": "1.0.0"}, health.json())


if __name__ == "__main__":
    unittest.main()
