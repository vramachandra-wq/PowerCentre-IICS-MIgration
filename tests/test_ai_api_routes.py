import csv
import unittest


try:
    from fastapi.testclient import TestClient

    from api.dependencies import get_logger, get_repository
    from app import create_app
    from automation.evaluation_matrix import ReportRepository
except ModuleNotFoundError:  # pragma: no cover - exercised only in lean local environments.
    TestClient = None


class NullLogger:
    def info(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass


@unittest.skipIf(TestClient is None, "FastAPI is not installed")
class AIAPIRoutesTests(unittest.TestCase):
    def test_recommendation_endpoint_returns_strict_columns(self) -> None:
        from pathlib import Path
        from uuid import uuid4

        root = Path.cwd() / ".test_tmp" / f"ai_route_{uuid4().hex}"
        output = root / "output"
        metadata = output / "metadata_tables"
        metadata.mkdir(parents=True, exist_ok=True)
        self._write_csv(metadata / "mappings.csv", ["file_name", "mapping_name"], [{"file_name": "customer.XML", "mapping_name": "M_CUSTOMER"}])
        self._write_csv(metadata / "workflows.csv", ["file_name", "workflow_name"], [{"file_name": "customer.XML", "workflow_name": "WF_CUSTOMER"}])
        self._write_csv(metadata / "sessions.csv", ["file_name", "session_name", "mapping_name"], [{"file_name": "customer.XML", "session_name": "S_CUSTOMER", "mapping_name": "M_CUSTOMER"}])
        self._write_csv(metadata / "transformations.csv", ["file_name", "mapping_name", "transformation_name", "transformation_type"], [{"file_name": "customer.XML", "mapping_name": "M_CUSTOMER", "transformation_name": "MPL_CUSTOMER", "transformation_type": "Mapplet"}])
        self._write_csv(output / "complexity_classification_report.csv", ["XML", "Mapping"], [{"XML": "customer.XML", "Mapping": "M_CUSTOMER"}])
        self._write_csv(
            output / "validation_report.csv",
            ["Issue", "Severity", "Recommendation", "Auto Fixed", "Status", "Rule ID", "Asset", "Source File"],
            [{"Issue": "Mapplet Nesting detected.", "Severity": "HIGH", "Recommendation": "Flatten mapplet logic.", "Auto Fixed": "False", "Status": "Open", "Rule ID": "VAL-028", "Asset": "MPL_CUSTOMER", "Source File": "customer.XML"}],
        )
        self._write_csv(
            output / "remediation_report.csv",
            ["Issue", "Severity", "Recommendation", "Auto Fixed", "Fix Applied", "Before Value", "After Value", "Status", "Asset", "Manual Remediation Required", "Approval Required"],
            [{"Issue": "mapplet_nesting", "Severity": "HIGH", "Recommendation": "Flatten mapplet logic.", "Auto Fixed": "False", "Fix Applied": "", "Before Value": "MPL_CUSTOMER", "After Value": "MPL_CUSTOMER", "Status": "Manual Remediation Required", "Asset": "MPL_CUSTOMER", "Manual Remediation Required": "True", "Approval Required": "False"}],
        )
        app = create_app()
        app.dependency_overrides[get_repository] = lambda: ReportRepository(output, root / "automation")
        app.dependency_overrides[get_logger] = lambda: NullLogger()

        response = TestClient(app).post("/api/v1/ai/recommendation", json={"Max Records": 1})

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            ["Workflow", "Failures", "Root Cause", "AI Recommendation", "Priority", "AI Summary"],
            list(response.json()[0].keys()),
        )

    def test_evaluation_endpoint_returns_strict_matrix(self) -> None:
        import json
        from pathlib import Path
        from uuid import uuid4

        root = Path.cwd() / ".test_tmp" / f"ai_route_{uuid4().hex}"
        reports = root / "automation"
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "ai_evaluation_summary.json").write_text(
            json.dumps(
                {
                    "matrix": {
                        "Average Confidence": 80,
                        "F1 Score": 70,
                        "Accuracy": 90,
                        "Precision": 85,
                        "Model Call Success Rate": 100,
                        "Recall": 60,
                        "Total Rules": 4,
                    }
                }
            ),
            encoding="utf-8",
        )
        app = create_app()
        app.dependency_overrides[get_repository] = lambda: ReportRepository(root / "output", reports)
        app.dependency_overrides[get_logger] = lambda: NullLogger()

        response = TestClient(app).post("/api/v1/ai/evaluation", json={})

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {
                "matrix": {
                    "Average Confidence": 80,
                    "F1 Score": 70,
                    "ML Accuracy": 90,
                    "ML Precision": 85,
                    "Model Success Rate": 100,
                    "Recall": 60,
                    "Total Evaluations": 4,
                }
            },
            response.json(),
        )

    @staticmethod
    def _write_csv(path, fieldnames, rows) -> None:
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
