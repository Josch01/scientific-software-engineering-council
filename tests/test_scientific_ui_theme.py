from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from scripts.scientific_ui_theme import (
    CHART_SERIES_COLORS,
    COLORS,
    chart_line_style,
    motion_enabled,
    qt_stylesheet,
)


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
              for value in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class ScientificUiThemeTests(unittest.TestCase):
    def test_theme_uses_the_requested_moderate_charcoal_and_violet_palette(self):
        self.assertEqual(COLORS["background"], "#27262e")
        self.assertEqual(COLORS["sidebar"], "#2d2b35")
        self.assertEqual(COLORS["surface"], "#34323d")
        self.assertEqual(COLORS["surface_raised"], "#3d3b47")
        self.assertEqual(COLORS["accent"], "#b99aff")

    def test_text_and_chart_colors_keep_contrast_on_their_surfaces(self):
        surfaces = ("background", "sidebar", "surface", "surface_raised", "surface_hover")
        for surface in surfaces:
            with self.subTest(surface=surface):
                self.assertGreaterEqual(_contrast(COLORS["text"], COLORS[surface]), 4.5)
                self.assertGreaterEqual(_contrast(COLORS["muted"], COLORS[surface]), 4.5)
        for color in CHART_SERIES_COLORS:
            with self.subTest(series=color):
                self.assertGreaterEqual(_contrast(color, COLORS["surface"]), 3.0)

    def test_native_controls_expose_focus_and_distinct_interaction_states(self):
        style = qt_stylesheet()

        self.assertIn("QPushButton:focus", style)
        self.assertIn("QPushButton:hover", style)
        self.assertIn("QPushButton:pressed", style)
        self.assertIn("QPushButton:disabled", style)
        self.assertIn("QListWidget::item:selected", style)

    def test_reduced_motion_setting_disables_qt_transitions(self):
        with patch.dict(os.environ, {"SSEC_REDUCED_MOTION": "1"}):
            self.assertFalse(motion_enabled())

    def test_native_and_web_charts_share_six_line_style_tokens(self):
        self.assertEqual(
            [chart_line_style(index) for index in range(6)],
            ["solid", "dashed", "dotted", "dashdot", "longdash", "shortdash"],
        )
        self.assertEqual(chart_line_style(6), "solid")


if __name__ == "__main__":
    unittest.main()
