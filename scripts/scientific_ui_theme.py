"""Shared charcoal and violet design tokens for the Qt scientific workspace."""
from __future__ import annotations

import os


COLORS = {
    "background": "#27262e",
    "sidebar": "#2d2b35",
    "surface": "#34323d",
    "surface_raised": "#3d3b47",
    "surface_hover": "#484550",
    "border": "#585561",
    "text": "#f5f2fa",
    "muted": "#cdc8d5",
    "accent": "#b99aff",
    "accent_hover": "#d0baff",
    "accent_pressed": "#69558f",
    "focus": "#e6d8ff",
    "success": "#7be0c3",
    "warning": "#ffd68a",
    "danger": "#ffa1ab",
}

CHART_SERIES_COLORS = (
    "#c6a7ff", "#66dec6", "#ffa48e", "#7dd3fc", "#ffd166", "#f29bcb",
)
CHART_SERIES_LINE_STYLES = (
    "solid", "dashed", "dotted", "dashdot", "longdash", "shortdash",
)
CHART_SERIES_DASH_PATTERNS = ("", "9 5", "2 4", "12 4 2 4", "14 5", "5 3")


def chart_line_style(index: int) -> str:
    """Return the shared color-independent line style for a chart series."""
    if not isinstance(index, int) or index < 0:
        raise ValueError("chart series index must be a non-negative integer")
    return CHART_SERIES_LINE_STYLES[index % len(CHART_SERIES_LINE_STYLES)]


def motion_enabled() -> bool:
    """Respect an explicit accessibility opt-out for Qt transitions."""
    return os.environ.get("SSEC_REDUCED_MOTION", "").strip().lower() not in {
        "1", "true", "yes", "on",
    }


def qt_stylesheet() -> str:
    """Return the shared dark stylesheet for the control center and workspace."""
    c = COLORS
    return f"""
        QMainWindow, QDialog, QProgressDialog {{ background: {c['background']}; color: {c['text']}; }}
        QWidget {{ color: {c['text']}; font-family: "Segoe UI", "Arial", sans-serif; font-size: 13px; }}
        QToolBar {{ background: {c['sidebar']}; border: 0; border-bottom: 1px solid {c['border']}; spacing: 14px; padding: 11px 22px; }}
        QToolBar QLabel {{ color: {c['text']}; font-size: 15px; font-weight: 650; }}
        QStatusBar {{ background: {c['sidebar']}; color: {c['muted']}; border-top: 1px solid {c['border']}; }}
        QListWidget {{ background: {c['sidebar']}; color: {c['muted']}; border: 0; border-right: 1px solid {c['border']}; padding: 18px 12px; outline: 0; }}
        QListWidget::item {{ min-height: 42px; padding: 7px 13px; border-radius: 8px; margin: 3px 0; }}
        QListWidget::item:hover {{ background: {c['surface_hover']}; color: {c['text']}; }}
        QListWidget::item:selected {{ background: {c['accent_pressed']}; color: {c['text']}; font-weight: 650; border-left: 3px solid {c['accent']}; }}
        QGroupBox {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 12px; margin-top: 15px; padding: 18px 14px 14px; font-weight: 600; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 6px; color: {c['accent_hover']}; }}
        QTabWidget::pane {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; top: -1px; }}
        QTabBar::tab {{ background: {c['sidebar']}; color: {c['muted']}; padding: 10px 16px; margin-right: 5px; border: 1px solid {c['border']}; border-bottom: 0; border-top-left-radius: 8px; border-top-right-radius: 8px; }}
        QTabBar::tab:selected {{ background: {c['surface_raised']}; color: {c['text']}; border-top: 2px solid {c['accent']}; font-weight: 650; }}
        QPushButton {{ background: {c['surface_raised']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 9px 15px; min-height: 24px; }}
        QPushButton:hover {{ background: {c['surface_hover']}; border-color: {c['accent']}; }}
        QPushButton:pressed {{ background: {c['accent_pressed']}; border-color: {c['accent_pressed']}; }}
        QPushButton#openProjectButton, QPushButton#proposeWorkspaceButton, QPushButton#runThesisSirButton {{ background: {c['accent_pressed']}; border-color: {c['accent']}; font-weight: 650; }}
        QPushButton#openProjectButton:hover, QPushButton#proposeWorkspaceButton:hover, QPushButton#runThesisSirButton:hover {{ background: {c['accent']}; color: {c['background']}; }}
        QPushButton:disabled {{ background: {c['surface_raised']}; color: {c['muted']}; border-color: {c['border']}; }}
        QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 7px; selection-background-color: {c['accent_pressed']}; }}
        QComboBox QAbstractItemView {{ background: {c['surface_raised']}; color: {c['text']}; selection-background-color: {c['accent_pressed']}; border: 1px solid {c['border']}; }}
        QTableWidget, QTableView {{ background: {c['surface']}; color: {c['text']}; alternate-background-color: {c['surface_raised']}; gridline-color: {c['border']}; selection-background-color: {c['accent_pressed']}; selection-color: {c['text']}; border: 1px solid {c['border']}; border-radius: 6px; }}
        QHeaderView::section {{ background: {c['surface_raised']}; color: {c['muted']}; padding: 7px; border: 0; border-right: 1px solid {c['border']}; border-bottom: 1px solid {c['border']}; }}
        QProgressBar {{ background: {c['surface_raised']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 5px; min-height: 9px; max-height: 9px; }}
        QProgressBar::chunk {{ background: {c['accent']}; border-radius: 4px; }}
        QScrollArea, QScrollArea > QWidget > QWidget {{ background: {c['background']}; }}
        QScrollBar:vertical {{ background: {c['sidebar']}; width: 12px; margin: 2px; }}
        QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 5px; min-height: 30px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QLabel#controlCenterPageHeading, QLabel#workspaceHeading {{ color: {c['text']}; font-size: 24px; font-weight: 700; padding-bottom: 2px; }}
        QLabel#activeProjectLabel {{ color: {c['muted']}; background: {c['surface_raised']}; border: 1px solid {c['border']}; border-radius: 12px; padding: 5px 10px; }}
        QLabel#workspaceDigestStatus, QLabel[state="success"] {{ background: #253b37; color: {c['success']}; border: 1px solid #42695f; border-radius: 6px; padding: 8px; font-weight: 600; }}
        QLabel#scientificNotice, QLabel[state="warning"] {{ color: {c['warning']}; background: #39342a; border: 1px solid #71603d; border-radius: 6px; padding: 8px; }}
        QLabel#scientificActionWarning {{ color: {c['danger']}; }}
        QFrame#thesisSirHeroCard, QFrame#thesisSirSetupPanel, QFrame#thesisSirResultsPanel {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px; }}
        QFrame#thesisSirFactCard {{ background: {c['surface_raised']}; border: 1px solid {c['border']}; border-radius: 9px; }}
        QLabel#thesisSirPageTitle {{ color: {c['text']}; font-size: 23px; font-weight: 700; }}
        QLabel#thesisSirKicker {{ color: {c['accent_hover']}; font-size: 10px; font-weight: 700; letter-spacing: 1px; }}
        QLabel#thesisSirEquationSummary {{ background: {c['background']}; color: {c['text']}; border-left: 3px solid {c['accent']}; border-radius: 5px; padding: 10px 12px; font-size: 14px; }}
        QLabel#thesisSirModelProvenance, QLabel#thesisSirDataDigest {{ color: {c['muted']}; font-size: 11px; }}
        QLabel#thesisSirFactLabel {{ color: {c['muted']}; font-size: 10px; font-weight: 700; }}
        QLabel#thesisSirFactValue {{ color: {c['text']}; font-size: 12px; font-weight: 600; }}
        QLabel#thesisSirPanelTitle {{ color: {c['text']}; font-size: 17px; font-weight: 650; }}
        QLabel#thesisSirHelperText {{ color: {c['muted']}; font-size: 11px; }}
        QLabel#thesisSirDataStatus {{ color: {c['muted']}; font-weight: 650; }}
        QLabel#thesisSirDataStatus[state="info"], QLabel#thesisSirRunStatus[state="info"] {{ color: {c['success']}; background: #253b37; border: 1px solid #42695f; border-radius: 7px; padding: 8px; }}
        QLabel#thesisSirRunStatus {{ color: {c['muted']}; background: {c['surface_raised']}; border: 1px solid {c['border']}; border-radius: 7px; padding: 9px; }}
        QLabel#thesisSirRunStatus[state="warning"] {{ color: {c['warning']}; background: #39342a; border-color: #71603d; }}
        QLabel#thesisSirRunStatus[state="active"] {{ color: {c['accent_hover']}; background: {c['surface_raised']}; border-color: {c['accent']}; }}
        QLabel#thesisSirRunStatus[state="computed"] {{ color: {c['accent_hover']}; background: #312b3d; border-color: {c['accent']}; }}
        QLabel#thesisSirRunStatus[state="error"] {{ color: {c['danger']}; background: #3a292e; border-color: #80535b; }}
        QLabel#thesisSirEmptyState {{ color: {c['muted']}; background: {c['surface_raised']}; border: 1px dashed {c['border']}; border-radius: 9px; padding: 24px; line-height: 1.45; }}
        QSplitter#thesisSirWorkspaceSplitter::handle {{ background: {c['background']}; }}
        QSplitter#thesisSirWorkspaceSplitter::handle:horizontal {{ width: 8px; }}
        QSplitter#thesisSirWorkspaceSplitter::handle:vertical {{ height: 8px; }}
        QToolTip {{ background: {c['surface_raised']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 5px; }}
        QListWidget:focus {{ border-right: 1px solid {c['border']}; }}
        QPushButton:focus, QListWidget::item:focus, QTabBar::tab:focus, QTableWidget:focus, QPlainTextEdit:focus, QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border: 2px solid {c['focus']}; }}
    """
