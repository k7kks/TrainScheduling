from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "tools" / "export_cg_instance.py"

spec = importlib.util.spec_from_file_location("export_cg_instance", MODULE_PATH)
assert spec is not None and spec.loader is not None
export_cg_instance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export_cg_instance)


class ExportCgHeadwayWindowTests(unittest.TestCase):
    def test_filters_headway_options_to_plus_minus_ten_minutes(self) -> None:
        options = [
            {"shift_seconds": -900},
            {"shift_seconds": -600},
            {"shift_seconds": 0},
            {"shift_seconds": 600},
            {"shift_seconds": 901},
        ]

        bounded = export_cg_instance._headway_window_options(options)

        self.assertEqual([row["shift_seconds"] for row in bounded], [-600, 0, 600])

    def test_preserves_original_options_when_all_exceed_window(self) -> None:
        options = [
            {"shift_seconds": -901},
            {"shift_seconds": 901},
        ]

        bounded = export_cg_instance._headway_window_options(options)

        self.assertEqual(bounded, options)

    def test_bounded_headway_window_uses_intersection_when_available(self) -> None:
        target_gap = 400
        actual_gaps = [-100, 120, 780, 1300]

        min_gap, max_gap = export_cg_instance._bounded_headway_window(target_gap, actual_gaps)

        self.assertEqual((min_gap, max_gap), (120, 780))

    def test_bounded_headway_window_snaps_to_nearest_actual_gap_when_needed(self) -> None:
        target_gap = 400
        actual_gaps = [1201, 1210, 1500]

        min_gap, max_gap = export_cg_instance._bounded_headway_window(target_gap, actual_gaps)

        self.assertEqual((min_gap, max_gap), (1201, 1201))

    def test_bounded_headway_window_never_returns_negative_lower_bound(self) -> None:
        target_gap = 300
        actual_gaps = [-500, -100, 50]

        min_gap, max_gap = export_cg_instance._bounded_headway_window(target_gap, actual_gaps)

        self.assertEqual((min_gap, max_gap), (50, 50))


if __name__ == "__main__":
    unittest.main()
