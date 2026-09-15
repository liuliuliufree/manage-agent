"""Tests for the deterministic acts 1-3 mock dataset."""

from __future__ import annotations

import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "generate_demo_mock_data.py"
SPEC = importlib.util.spec_from_file_location("generate_demo_mock_data", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load generator from {SCRIPT_PATH}")
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


class DemoMockDataTests(unittest.TestCase):
    def test_repository_dataset_recomputes_confirmed_story_results(self) -> None:
        summary = GENERATOR.validate_dataset(GENERATOR.default_output_dir())

        self.assertEqual(summary["customer_count"], 120)
        self.assertEqual(summary["opportunities"]["family_ci_gap"], 86)
        self.assertEqual(summary["opportunities"]["policy_anniversary"], 50)
        self.assertEqual(summary["opportunities"]["medical_incomplete"], 25)
        self.assertEqual(summary["eligible_count"], 41)
        self.assertEqual(summary["priority_count"], 12)
        self.assertIn("C001", summary["priority_ids"])
        self.assertIn("C028", summary["priority_ids"])
        self.assertEqual(
            summary["exclusion_counts"],
            {
                "authorization": 14,
                "frequency": 9,
                "refusal": 7,
                "sensitive_status": 6,
                "suitability": 9,
            },
        )

    def test_generation_is_byte_for_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = Path(first_dir)
            second = Path(second_dir)
            tables, expectations = GENERATOR.build_tables()
            GENERATOR.write_dataset(first, tables, expectations)
            tables, expectations = GENERATOR.build_tables()
            GENERATOR.write_dataset(second, tables, expectations)

            first_hashes = self._hashes(first)
            second_hashes = self._hashes(second)
            self.assertEqual(first_hashes, second_hashes)
            self.assertEqual(len(first_hashes), 13)

    @staticmethod
    def _hashes(root: Path) -> dict[str, str]:
        return {
            path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*.csv"))
        }


if __name__ == "__main__":
    unittest.main()
