from __future__ import annotations

import unittest

from zephyr.forecast.gefs import find_precip_variable, inches_to_mm, _is_cumulative_matrix


class GEFSPrecipTests(unittest.TestCase):
    def test_find_precip_variable_prefers_apcpsfc(self) -> None:
        dds_text = """
        Dataset {
            Float32 apcpsfc[ens][time][lat][lon];
            Float32 prate[ens][time][lat][lon];
        } gefs;
        """
        self.assertEqual(find_precip_variable(dds_text), "apcpsfc")

    def test_is_cumulative_matrix(self) -> None:
        cumulative = [
            [0.0, 0.2, 0.3],
            [0.0, 0.0, 0.1],
        ]
        incremental = [
            [0.2, 0.0, 0.1],
            [0.0, 0.1, 0.0],
        ]
        self.assertTrue(_is_cumulative_matrix(cumulative))
        self.assertFalse(_is_cumulative_matrix(incremental))

    def test_inches_to_mm(self) -> None:
        self.assertAlmostEqual(inches_to_mm(1.0), 25.4)


if __name__ == "__main__":
    unittest.main()
