"""Shared charcoal and violet design tokens for the Qt scientific workspace."""
from __future__ import annotations

import os


COLORS = {
    "background": "#202027",
    "sidebar": "#24232b",
    "surface": "#292830",
    "surface_raised": "#32313b",
    "surface_hover": "#3a3744",
    "border": "#484550",
    "text": "#f2eef7",
    "muted": "#c2bdcc",
    "accent": "#aa8bf2",
    "accent_hover": "#bea5ff",
    "accent_pressed": "#5b487d",
    "focus": "#d8caff",
    "success": "#70ddbd",
    "warning": "#ffd27d",
    "danger": "#ff929e",
}

CHART_SERIES_COLORS = (
    "#b89bff", "#61d6c1", "#ff9b81", "#79c7ff", "#f4c96d", "#ed94c6",
)


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
        QToolBar {{ background: {c['sidebar']}; border: 0; spacing: 12px; padding: 10px 16px; }}
        QToolBar QLabel {{ color: {c['text']}; font-size: 15px; font-weight: 650; }}
        QStatusBar {{ background: {c['sidebar']}; color: {c['muted']}; border-top: 1px solid {c['border']}; }}
        QListWidget {{ background: {c['sidebar']}; color: {c['muted']}; border: 0; padding: 14px 10px; outline: 0; }}
        QListWidget::item {{ min-height: 38px; padding: 5px 12px; border-radius: 7px; margin: 2px 0; }}
        QListWidget::item:hover {{ background: {c['surface_hover']}; color: {c['text']}; }}
        QListWidget::item:selected {{ background: {c['accent_pressed']}; color: {c['text']}; font-weight: 650; border-left: 3px solid {c['accent']}; }}
        QGroupBox {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 10px; margin-top: 14px; padding: 16px 12px 12px; font-weight: 600; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 5px; }}
        QTabWidget::pane {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; top: -1px; }}
        QTabBar::tab {{ background: {c['sidebar']}; color: {c['muted']}; padding: 9px 15px; margin-right: 4px; border: 1px solid {c['border']}; border-bottom: 0; border-top-left-radius: 7px; border-top-right-radius: 7px; }}
        QTabBar::tab:selected {{ background: {c['surface_raised']}; color: {c['text']}; border-top: 2px solid {c['accent']}; }}
        QPushButton {{ background: {c['accent_pressed']}; color: {c['text']}; border: 1px solid {c['accent']}; border-radius: 7px; padding: 8px 14px; min-height: 22px; }}
        QPushButton:hover {{ background: {c['accent']}; color: {c['background']}; }}
        QPushButton:pressed {{ background: {c['accent_pressed']}; }}
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
        QLabel#controlCenterPageHeading, QLabel#workspaceHeading {{ color: {c['text']}; font-size: 22px; font-weight: 700; }}
        QLabel#activeProjectLabel {{ color: {c['muted']}; background: {c['surface_raised']}; border: 1px solid {c['border']}; border-radius: 12px; padding: 5px 10px; }}
        QLabel#workspaceDigestStatus, QLabel[state="success"] {{ background: #253b37; color: {c['success']}; border: 1px solid #42695f; border-radius: 6px; padding: 8px; font-weight: 600; }}
        QLabel#scientificNotice, QLabel[state="warning"] {{ color: {c['warning']}; background: #39342a; border: 1px solid #71603d; border-radius: 6px; padding: 8px; }}
        QLabel#scientificActionWarning {{ color: {c['danger']}; }}
        QToolTip {{ background: {c['surface_raised']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 5px; }}
        QPushButton:focus, QListWidget:focus, QTabBar::tab:focus, QTableWidget:focus, QPlainTextEdit:focus, QLineEdit:focus, QComboBox:focus {{ border: 2px solid {c['focus']}; }}
    """
