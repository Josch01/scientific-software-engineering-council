from __future__ import annotations

import base64
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
import unittest
from unittest.mock import patch

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    QtCore = None
    QtGui = None
    QtWidgets = None

from scripts import scientific_workspace_qt_charts as charts
from scripts.scientific_ui_theme import CHART_SERIES_LINE_STYLES


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

    def test_chart_html_uses_scientific_dark_palette_and_reduced_motion(self):
        html = charts.build_scientific_chart_html(chart_payload()).lower()

        self.assertIn("#34323d", html)
        self.assertIn("#c6a7ff", html)
        self.assertIn("prefers-reduced-motion", html)
        self.assertIn("@keyframes", html)

    def test_chart_series_have_distinct_line_patterns_and_animated_entry(self):
        html = charts.build_scientific_chart_html(chart_payload()).lower()

        self.assertIn("stroke-dasharray", html)
        self.assertIn("data-line-style", html)
        self.assertIn("line-in", html)
        self.assertIn("aria-keyshortcuts", html)
        self.assertIn("arrowleft", html)
        self.assertNotIn("__ssec_", html)
        for style in CHART_SERIES_LINE_STYLES:
            self.assertIn(f'"{style}"', html)

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

    def test_data_table_rounds_display_only_and_preserves_exact_values(self):
        exact = 1.2345678912345
        payload = chart_payload()
        payload["series"][0]["y"][1] = exact

        table = charts._data_table(payload)
        self.addCleanup(table.close)
        cell = table.item(1, 1)

        self.assertEqual(cell.text(), "1.23457")
        self.assertEqual(cell.data(QtCore.Qt.ItemDataRole.UserRole), exact)
        self.assertEqual(float(cell.toolTip()), exact)

    def test_chart_widget_uses_native_fallback_when_webengine_is_unavailable(self):
        with patch.object(charts, "QWebEngineView", None):
            widget = charts.ScientificChartWidget(chart_payload())

        self.addCleanup(widget.close)
        self.assertIsNotNone(widget.findChild(QtWidgets.QFrame, "scientificChartFallback"))
        self.assertIsNotNone(widget.findChild(QtWidgets.QTableWidget, "scientificChartDataTable"))
        plot = widget.findChild(charts._ChartPainter)
        image = QtGui.QImage(420, 280, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtGui.QColor("transparent"))
        plot.resize(image.size())
        plot.render(image)
        self.assertEqual(image.pixelColor(5, 5).name(), charts.COLORS["surface"])
        self.assertEqual(
            plot._PEN_STYLES["dashdot"], QtCore.Qt.PenStyle.DashDotLine
        )

    def test_widget_falls_back_when_valid_chart_html_exceeds_page_budget(self):
        payload = chart_payload()
        with patch.object(charts, "MAX_CHART_HTML_BYTES", 1024):
            with patch.object(charts, "WEBENGINE_AVAILABLE", True):
                widget = charts.ScientificChartWidget(payload)

        self.addCleanup(widget.close)
        self.assertIsNotNone(widget.findChild(QtWidgets.QFrame, "scientificChartFallback"))

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
        rendered_theme = []
        view.page().runJavaScript(
            "JSON.stringify([getComputedStyle(document.body).backgroundColor, "
            "document.querySelector('path.series-line').getAttribute('stroke')])",
            lambda value: (rendered_theme.append(value), loop.quit()),
        )
        QtCore.QTimer.singleShot(5000, loop.quit)
        loop.exec()
        self.assertEqual(json.loads(rendered_theme[0]), ["rgb(52, 50, 61)", "#c6a7ff"])
        self.assertFalse(view.page().acceptNavigationRequest(
            QtCore.QUrl("https://example.invalid"),
            charts.QWebEnginePage.NavigationType.NavigationTypeLinkClicked,
            True,
        ))

    @unittest.skipUnless(charts.WEBENGINE_AVAILABLE, "Qt WebEngine is unavailable")
    def test_webengine_chart_arrow_navigation_reports_the_selected_data_point(self):
        widget = charts.ScientificChartWidget(chart_payload())
        self.addCleanup(widget.close)
        view = widget.findChild(charts.QWebEngineView, "scientificChartWebEngine")
        loop = QtCore.QEventLoop()
        view.loadFinished.connect(loop.quit)
        QtCore.QTimer.singleShot(5000, loop.quit)
        loop.exec()

        evaluated = []
        view.page().runJavaScript(
            "(()=>{const svg=document.querySelector('svg');svg.focus();"
            "svg.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',"
            "bubbles:true,cancelable:true}));"
            "return document.querySelector('#chart-tooltip').textContent;})()",
            lambda value: (evaluated.append(value), loop.quit()),
        )
        QtCore.QTimer.singleShot(5000, loop.quit)
        loop.exec()

        self.assertEqual(
            evaluated,
            ["Time · day: 1 · Observed: 8 · Simulated: 9"],
        )

    @unittest.skipUnless(charts.WEBENGINE_AVAILABLE, "Qt WebEngine is unavailable")
    def test_webengine_renders_series_beyond_javascript_argument_limit(self):
        point_count = 63_000
        x_values = [float(index) for index in range(point_count)]
        payload = chart_payload()
        payload["series"] = [
            {"name": "First", "x": x_values, "y": [1.0] * point_count},
            {"name": "Second", "x": x_values, "y": [2.0] * point_count},
        ]
        self.assertLessEqual(
            len(charts.build_scientific_chart_html(payload).encode("utf-8")),
            charts.MAX_WEBENGINE_DATA_URL_BYTES,
        )
        widget = charts.ScientificChartWidget(payload)
        self.addCleanup(widget.close)
        view = widget.findChild(charts.QWebEngineView, "scientificChartWebEngine")
        self.assertIsNotNone(view)

        loop = QtCore.QEventLoop()
        rendered_series = []

        deadline = time.monotonic() + 10

        def check_rendered_series(value):
            if value == 2 or time.monotonic() >= deadline:
                rendered_series.append(value)
                loop.quit()
            else:
                QtCore.QTimer.singleShot(50, query_series)

        def query_series():
            view.page().runJavaScript(
                "document.querySelectorAll('svg path[data-index]').length",
                check_rendered_series,
            )

        query_series()
        QtCore.QTimer.singleShot(10000, loop.quit)
        loop.exec()

        self.assertEqual(rendered_series, [2], "large local chart did not render both series")

    @unittest.skipUnless(charts.WEBENGINE_AVAILABLE, "Qt WebEngine is unavailable")
    def test_widget_falls_back_for_valid_payload_above_webengine_page_budget(self):
        point_count = charts.MAX_CHART_POINTS
        x_values = [float(index) for index in range(point_count)]
        payload = chart_payload()
        payload["series"] = [
            {"name": "First", "x": x_values, "y": [1.0] * point_count},
            {"name": "Second", "x": x_values, "y": [2.0] * point_count},
        ]

        widget = charts.ScientificChartWidget(payload)
        self.addCleanup(widget.close)

        self.assertIsNotNone(widget.findChild(QtWidgets.QFrame, "scientificChartFallback"))

    def test_fallback_paints_the_y_axis_label(self):
        def render(label):
            payload = chart_payload()
            payload["y_label"] = label
            widget = charts._ChartPainter(payload)
            widget.resize(700, 360)
            widget.show()
            self.app.processEvents()
            image = QtGui.QImage(widget.size(), QtGui.QImage.Format.Format_ARGB32)
            image.fill(QtGui.QColor("white"))
            painter = QtGui.QPainter(image)
            widget.render(painter, QtCore.QPoint())
            painter.end()
            widget.close()
            return image

        first = render("Unit alpha")
        second = render("Unit beta")
        differences = sum(
            first.pixelColor(x, y) != second.pixelColor(x, y)
            for y in range(first.height()) for x in range(first.width())
        )
        self.assertGreater(differences, 10, "changing y_label did not change the visible chart")

