"""
Support test datatype mapping engine for automated regression coverage.
Verifies migration parsing, validation, API, and AI behavior.
"""

import unittest

from business.validation.datatype_mapping_engine import (
    DatatypeMappingEngine,
    map_datatype,
    suggest_datatype_fix,
    validate_datatype,
)


class DatatypeMappingEngineTests(unittest.TestCase):
    """Encapsulates datatype mapping engine tests behavior for migration workflows."""

    def test_map_number_precision_scale(self) -> None:
        """Verify map number precision scale behavior."""

        mapped = map_datatype("NUMBER(18,6)")

        self.assertEqual("Decimal", mapped.idmc_type)
        self.assertEqual(18, mapped.precision)
        self.assertEqual(6, mapped.scale)

    def test_validate_varchar2(self) -> None:
        """Verify validate varchar2 behavior."""

        result = validate_datatype("VARCHAR2", precision=100, scale=0)

        self.assertTrue(result["valid"])
        self.assertEqual("String", result["mapped_type"])

    def test_suggest_decimal_fix(self) -> None:
        """Verify suggest decimal fix behavior."""

        self.assertEqual(
            "Retain original precision and scale.",
            suggest_datatype_fix("NUMBER", precision=18, scale=6),
        )

    def test_engine_reports_unknown_type(self) -> None:
        """Verify engine reports unknown type behavior."""

        engine = DatatypeMappingEngine()
        result = engine.validate_datatype("UNSUPPORTED_TYPE")

        self.assertFalse(result["valid"])
        self.assertTrue(result["issues"])


if __name__ == "__main__":
    unittest.main()
