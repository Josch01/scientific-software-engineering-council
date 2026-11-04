from __future__ import annotations

import base64
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from unittest.mock import patch

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    QtCore = None
    QtWidgets = None

from scripts import scientific_workspace_qt_charts as charts


def chart_payload():
    return {
        "title": "Observed and simulated values",
        "x_label": "Time · day",
        "y_label": "Count · person",
        "series": [
            {"name": "Observed", "x": [0.0, 1.0, 2.0], "y": [10.0, 8.0, 6.0]},
            {"name": "Simulated", "x": [0.0, 1.0, 2.0], "y": [10.0, 9.0, 7.0]},
        ],
    }


class ScientificChartHtmlTests(unittest.TestCase):
    def test_chart_html_uses_csp_and_has_no_remote_url_or_bridge(self):
        html = charts.build_scientific_chart_html(chart_payload())

        self.assertIn("Content-Security-Policy", html)
        self.assertIn("connect-src 'none'", html)
        self.assertNotIn("http://", html.lower().replace("http://www.w3.org/2000/svg", ""))
        self.assertNotIn("https://", html.lower())
        self.assertNotIn("file://", html.lower())
        self.assertNotIn("qwebchannel", html.lower())
        self.assertNotIn("<script src", html.lower())

    def test_hostile_labels_are_transported_as_data_not_html(self):
        payload = chart_payload()
        hostile = "</script><img src=x onerror=alert(1)>"
        payload["title"] = hostile
        payload["series"][0]["name"] = hostile

        html = charts.build_scientific_chart_html(payload)
        encoded = html.split('data-payload="', 1)[1].split('"', 1)[0]
        decoded = json.loads(base64.b64decode(encoded).decode("utf-8"))

        self.assertEqual(decoded["title"], hostile)
        self.assertEqual(decoded["series"][0]["name"], hostile)
        self.assertNotIn(hostile, html)
        self.assertIn("textContent", html)

    def test_chart_rejects_unbounded_series_points_and_nonfinite_data(self):
        too_many = chart_payload()
        too_many["series"] = [
            {"name": f"s{index}", "x": [0.0], "y": [1.0]}
            for index in range(charts.MAX_CHART_SERIES + 1)
        ]
        with self.assertRaisesRegex(ValueError, "series limit"):
            charts.build_scientific_chart_html(too_many)

        nonfinite = chart_payload()
        nonfinite["series"][0]["y"][0] = float("inf")
        with self.assertRaisesRegex(ValueError, "finite"):
            charts.build_scientific_chart_html(nonfinite)

        with patch.object(charts, "MAX_CHART_POINTS", 2):
            with self.assertRaisesRegex(ValueError, "point limit"):
                charts.build_scientific_chart_html(chart_payload())


@unittest.skipIf(QtWidgets is None, "PySide6 is not installed")
class ScientificChartWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_chart_widget_uses_native_fallback_when_webengine_is_unavailable(self):
        with patch.object(charts, "QWebEngineView", None):
            widget = charts.ScientificChartWidget(chart_payload())

        self.addCleanup(widget.close)
        self.assertIsNotNone(widget.findChild(QtWidgets.QFrame, "scientificChartFallback"))
        self.assertIsNotNone(widget.findChild(QtWidgets.QTableWidget, "scientificChartDataTable"))

    @unittest.skipUnless(charts.WEBENGINE_AVAILABLE, "Qt WebEngine is unavailable")
    def test_webengine_widget_uses_local_content_without_remote_file_access(self):
        widget = charts.ScientificChartWidget(chart_payload())
        self.addCleanup(widget.close)
        view = widget.findChild(charts.QWebEngineView, "scientificChartWebEngine")

        self.assertIsNotNone(view)
        settings = view.settings()
        self.assertFalse(settings.testAttribute(
            charts.QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls
        ))
        self.assertFalse(settings.testAttribute(
            charts.QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls
        ))
        self.assertIsInstance(view.page(), charts._ScientificChartPage)

        loop = QtCore.QEventLoop()
        view.loadFinished.connect(loop.quit)
        QtCore.QTimer.singleShot(5000, loop.quit)
        loop.exec()
        evaluated = []
        view.page().runJavaScript(
            "document.querySelectorAll('svg path').length",
            lambda value: (evaluated.append(value), loop.quit()),
        )
        QtCore.QTimer.singleShot(5000, loop.quit)
        loop.exec()

        self.assertTrue(evaluated, "local chart script did not finish")
        self.assertGreater(evaluated[0], 0, "local SVG chart was not rendered")
        self.assertFalse(view.page().acceptNavigationRequest(
            QtCore.QUrl("https://example.invalid"),
            charts.QWebEnginePage.NavigationType.NavigationTypeLinkClicked,
            True,
        ))

