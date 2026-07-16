"""Tests for IICS success benchmark profiles and gold reference packages."""

from __future__ import annotations

import unittest
from pathlib import Path

from business.iics.iics_success_benchmark import IICSSuccessBenchmark


class IICSSuccessBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.benchmark = IICSSuccessBenchmark(project_root=cls.root)

    def test_multi_session_reference_package_exists(self) -> None:
        package = self.benchmark.reference_package("multi_session")
        self.assertIsNotNone(package)
        assert package is not None
        self.assertTrue(package.exists())

    def test_single_session_reference_package_exists(self) -> None:
        package = self.benchmark.reference_package("single_session")
        self.assertIsNotNone(package)
        assert package is not None
        self.assertTrue(package.exists())

    def test_multi_session_gold_package_passes_profile(self) -> None:
        package = self.benchmark.reference_package("multi_session")
        assert package is not None
        result = self.benchmark.validate_package(package, profile="multi_session")
        failed = [check for check in result.checks if not check.passed]
        self.assertTrue(result.passed, msg=str(failed))
        self.assertGreaterEqual(result.checks[0].actual, 1)

    def test_single_session_gold_package_passes_profile(self) -> None:
        package = self.benchmark.reference_package("single_session")
        assert package is not None
        result = self.benchmark.validate_package(package, profile="single_session")
        failed = [check for check in result.checks if not check.passed]
        self.assertTrue(result.passed, msg=str(failed))

    def test_multi_session_fingerprint_has_parallel_taskflow(self) -> None:
        package = self.benchmark.reference_package("multi_session")
        assert package is not None
        fingerprint = self.benchmark.fingerprint_package(package, profile="multi_session")
        self.assertEqual("multi_session", fingerprint.profile)
        self.assertGreaterEqual(fingerprint.mtt_count, 2)
        self.assertTrue(fingerprint.taskflows[0].has_parallel)
        self.assertGreaterEqual(fingerprint.taskflows[0].mtt_guid_count, 2)

    def test_single_session_fingerprint_has_one_primary_guid(self) -> None:
        package = self.benchmark.reference_package("single_session")
        assert package is not None
        fingerprint = self.benchmark.fingerprint_package(package, profile="single_session")
        self.assertEqual("single_session", fingerprint.profile)
        self.assertEqual(1, fingerprint.mtt_count)
        self.assertFalse(fingerprint.taskflows[0].has_parallel)
        self.assertGreaterEqual(fingerprint.taskflows[0].mtt_guid_count, 1)

    def test_training_context_includes_both_profiles(self) -> None:
        context = self.benchmark.training_context()
        self.assertIn("multi_session", context["profiles"])
        self.assertIn("single_session", context["profiles"])


if __name__ == "__main__":
    unittest.main()
