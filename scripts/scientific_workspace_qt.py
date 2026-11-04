"""Optional PySide6 desktop frontend for verified scientific workspaces.

The module consumes the safe loader and bounded presentation models. Project
files remain inert; only host-registered actions may execute after confirmation.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
import json
import math
import os
from pathlib import Path
import sys
from typing import Any

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:  # Keep this optional frontend importable without Qt installed.
    QtCore = QtGui = QtWidgets = None

try:
    from .scientific_workspace_actions import (
        ApprovedSimulationRun,
        request_approved_simulation,
        run_approved_simulation,
        sir_simulation_actions_for_workspace,
    )
    from .scientific_workspace_loader import LoadedWorkspace, load_scientific_workspace
    from .scientific_workspace_view import (
        ComponentView,
        ResourceView,
        SirEquationView,
        SirParameterView,
        WorkspaceViewModel,
        build_workspace_view_model,
        sanitize_display_text,
    )
except ImportError:  # Direct execution from the scripts directory.
    from scientific_workspace_actions import (
        ApprovedSimulationRun,
        request_approved_simulation,
        run_approved_simulation,
        sir_simulation_actions_for_workspace,
    )
    from scientific_workspace_loader import LoadedWorkspace, load_scientific_workspace
    from scientific_workspace_view import (
        ComponentView,
        ResourceView,
        SirEquationView,
        SirParameterView,
        WorkspaceViewModel,
        build_workspace_view_model,
        sanitize_display_text,
    )


def _plain(value: object) -> object:
    """Convert bounded immutable view data to plain JSON-safe display values."""
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _plain(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return sanitize_display_text(str(value))


def _display_json(value: object) -> str:
    try:
        return json.dumps(_plain(value), ensure_ascii=False, indent=2, allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        return sanitize_display_text(str(value))


if QtWidgets is not None:

    class _SimulationThread(QtCore.QThread):
        completed = QtCore.Signal(str, int, object)
        failed = QtCore.Signal(str, int, str)

        def __init__(
            self,
            component_id: str,
            generation: int,
            ticket: ApprovedSimulationRun,
            parent=None,
        ):
            super().__init__(parent)
            self._component_id = component_id
            self._generation = generation
            self._ticket = ticket

        @property
        def component_id(self) -> str:
            return self._component_id

        def run(self) -> None:
            try:
                result = run_approved_simulation(self._ticket)
            except Exception as exc:  # Surface action failure; never convert it to success.
                self.failed.emit(
                    self._component_id,
                    self._generation,
                    sanitize_display_text(str(exc))[:1000],
                )
            else:
                self.completed.emit(self._component_id, self._generation, result)


    class _TrajectoryPlot(QtWidgets.QFrame):
        """Small native Qt plot for the verified time series already in memory."""

        _COLORS = ("#176b87", "#c76732", "#3b7e58", "#7856a5", "#a14355")

        def __init__(self, content: Mapping[str, object], parent=None):
            super().__init__(parent)
            self._content = content
            self.setObjectName("trajectoryPlot")
            self.setMinimumHeight(230)
            self.setAccessibleName("Gráfica de trayectoria de simulación")
            self.setAccessibleDescription(
                "Representación de las series seleccionadas a partir de valores numéricos verificados."
            )
            self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)

        def paintEvent(self, event) -> None:
            del event
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            painter.fillRect(self.rect(), QtGui.QColor("#ffffff"))
            rect = self.rect().adjusted(54, 20, -20, -44)
            times = self._content.get("times", ())
            values = self._content.get("values", ())
            names = self._content.get("series_names", ())
            indices = self._content.get("series_indices", ())
            if not times or not values or not names or not indices:
                painter.setPen(QtGui.QColor("#536273"))
                painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter, "No hay datos para graficar")
                return

            x_min, x_max = float(times[0]), float(times[-1])
            selected = [float(row[index]) for row in values for index in indices]
            y_min, y_max = min(selected), max(selected)
            if math.isclose(y_min, y_max):
                padding = max(abs(y_min) * 0.05, 1.0)
                y_min, y_max = y_min - padding, y_max + padding
            else:
                padding = (y_max - y_min) * 0.06
                y_min, y_max = y_min - padding, y_max + padding

            axis_pen = QtGui.QPen(QtGui.QColor("#9aa8b5"), 1)
            painter.setPen(axis_pen)
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())
            painter.drawLine(rect.bottomLeft(), rect.topLeft())
            painter.setPen(QtGui.QColor("#536273"))
            painter.drawText(4, rect.top() + 8, f"{y_max:.4g}")
            painter.drawText(4, rect.bottom(), f"{y_min:.4g}")
            painter.drawText(rect.left(), rect.bottom() + 27, f"{x_min:.4g}")
            painter.drawText(rect.right() - 48, rect.bottom() + 27, f"{x_max:.4g}")
            painter.drawText(
                rect.left(), self.height() - 8, f"Tiempo · {self._content.get('time_unit') or 'unidad no indicada'}"
            )

            count = len(times)
            stride = max(1, math.ceil(count / 2000))
            for series_number, (name, index) in enumerate(zip(names, indices)):
                color = QtGui.QColor(self._COLORS[series_number % len(self._COLORS)])
                painter.setPen(QtGui.QPen(color, 2))
                path = QtGui.QPainterPath()
                sampled = list(range(0, count, stride))
                if sampled[-1] != count - 1:
                    sampled.append(count - 1)
                for point_number, row_index in enumerate(sampled):
                    x = rect.left() + (float(times[row_index]) - x_min) / (x_max - x_min) * rect.width()
                    y = rect.bottom() - (float(values[row_index][index]) - y_min) / (y_max - y_min) * rect.height()
                    point = QtCore.QPointF(x, y)
                    if point_number == 0:
                        path.moveTo(point)
                    else:
                        path.lineTo(point)
                painter.drawPath(path)
                legend_x = rect.left() + series_number * 112
                painter.setPen(QtGui.QPen(color, 3))
                painter.drawLine(legend_x, rect.bottom() + 38, legend_x + 18, rect.bottom() + 38)
                painter.setPen(QtGui.QColor("#243746"))
                painter.drawText(legend_x + 24, rect.bottom() + 43, sanitize_display_text(str(name))[:32])


    class ScientificWorkspaceWindow(QtWidgets.QMainWindow):
        """Optional view over loader-verified project resources and host actions."""

        def __init__(self, parent=None, *, confirmation_handler=None):
            super().__init__(parent)
            self.setWindowTitle("SSEC · Centro de Control Científico")
            self.resize(1180, 800)
            self._confirmation_handler = confirmation_handler or self._confirm_simulation
            self._loaded_workspace: LoadedWorkspace | None = None
            self.workspace_view_model: WorkspaceViewModel | None = None
            self._simulation_actions: Mapping[str, object] = {}
            self.simulation_results: dict[str, ComponentView] = {}
            self._workers: dict[str, _SimulationThread] = {}
            self._generation = 0
            self._project_root: Path | None = None
            self._manifest_relative_path: str | None = None
            self._build_shell()
            self.setStyleSheet(
                "QMainWindow { background: #f2f5f7; color: #1d2d39; }"
                "QLabel { color: #243746; }"
                "QToolBar { background: #16384a; border: 0; spacing: 8px; padding: 8px; }"
                "QToolBar QLabel { color: #ffffff; font-size: 16px; font-weight: 600; }"
                "QPushButton { background: #176b87; color: white; border: 1px solid #10546b;"
                " border-radius: 4px; padding: 7px 12px; }"
                "QPushButton:hover { background: #125b73; }"
                "QPushButton:disabled { background: #9eafb8; color: #f5f7f8; }"
                "QPushButton:focus, QTabBar::tab:focus, QTableWidget:focus, QPlainTextEdit:focus {"
                " border: 2px solid #d68a31; }"
                "QTabWidget::pane { background: #f2f5f7; border: 1px solid #d9e1e6; }"
                "QTabBar::tab { background: #e7edf0; color: #243746; padding: 7px 12px; }"
                "QTabBar::tab:selected { background: #ffffff; color: #16384a; font-weight: 600; }"
                "QScrollArea, QScrollArea > QWidget > QWidget { background: #f2f5f7; }"
                "QGroupBox { background: white; color: #243746; border: 1px solid #d9e1e6;"
                " border-radius: 5px; }"
                "QGroupBox { margin-top: 12px; padding: 12px; font-weight: 600; }"
                "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
                "QLabel#workspaceDigestStatus { background: #e5f2ec; color: #245c3c;"
                " border: 1px solid #c3ddce; border-radius: 4px; padding: 8px; font-weight: 600; }"
                "QLabel#scientificNotice { color: #5b4a26; background: #fff8e7;"
                " border: 1px solid #ecdcae; border-radius: 4px; padding: 8px; }"
                "QTableWidget { background: #ffffff; color: #243746; gridline-color: #e1e7eb;"
                " alternate-background-color: #f6f8f9; selection-background-color: #d7eaf0;"
                " selection-color: #16384a; }"
                "QHeaderView::section { background: #e6edf1; color: #243746; padding: 5px; }"
                "QPlainTextEdit { background: #ffffff; color: #243746; selection-background-color: #d7eaf0; }"
                "QStatusBar { background: #e6edf1; color: #243746; }"
            )

        @property
        def simulation_running(self) -> bool:
            return bool(self._workers)

        @property
        def project_root(self) -> Path | None:
            return self._project_root

        def _build_shell(self) -> None:
            toolbar = self.addToolBar("Proyecto")
            toolbar.setMovable(False)
            heading = QtWidgets.QLabel("SSEC · Espacio científico")
            toolbar.addWidget(heading)
            toolbar.addSeparator()
            open_button = QtWidgets.QPushButton("Abrir espacio…")
            open_button.setObjectName("openWorkspaceButton")
            open_button.setAccessibleName("Abrir proyecto científico verificado")
            open_button.setToolTip("Seleccionar la raíz del proyecto y su manifiesto")
            open_button.clicked.connect(self.open_workspace_dialog)
            toolbar.addWidget(open_button)
            self.open_button = open_button

            shell = QtWidgets.QWidget(self)
            layout = QtWidgets.QVBoxLayout(shell)
            layout.setContentsMargins(16, 14, 16, 10)
            layout.setSpacing(10)
            self.workspace_heading = QtWidgets.QLabel("Selecciona un espacio científico")
            self.workspace_heading.setObjectName("workspaceHeading")
            self.workspace_heading.setStyleSheet("font-size: 21px; font-weight: 650; color: #16384a;")
            layout.addWidget(self.workspace_heading)
            self.digest_status = QtWidgets.QLabel("Sin workspace cargado · aún no verificado")
            self.digest_status.setObjectName("workspaceDigestStatus")
            self.digest_status.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            layout.addWidget(self.digest_status)
            self.scientific_notice = QtWidgets.QLabel(
                "La vista de artefactos y sus digests no validan ecuaciones, resultados, identificabilidad ni validez científica."
            )
            self.scientific_notice.setObjectName("scientificNotice")
            self.scientific_notice.setWordWrap(True)
            self.scientific_notice.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            layout.addWidget(self.scientific_notice)
            self.tabs = QtWidgets.QTabWidget()
            self.tabs.setObjectName("workspaceSections")
            self.tabs.setTabPosition(QtWidgets.QTabWidget.TabPosition.North)
            layout.addWidget(self.tabs, 1)
            self.setCentralWidget(shell)
            self.statusBar().showMessage("Listo")
            self._show_empty_state()

        def _show_empty_state(self) -> None:
            self.tabs.clear()
            empty = QtWidgets.QLabel(
                "Abre la raíz de un proyecto y selecciona un manifiesto. SSEC verificará sus recursos antes de mostrarlos."
            )
            empty.setObjectName("emptyWorkspaceState")
            empty.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            self.tabs.addTab(empty, "Inicio")

        def open_workspace_dialog(self) -> None:
            root = QtWidgets.QFileDialog.getExistingDirectory(
                self, "Seleccionar raíz del proyecto"
            )
            if not root:
                return
            manifest, _filter = QtWidgets.QFileDialog.getOpenFileName(
                self,
                "Seleccionar manifiesto científico",
                root,
                "Manifiestos JSON (*.json);;Todos los archivos (*)",
            )
            if not manifest:
                return
            try:
                relative = os.path.relpath(manifest, root).replace(os.sep, "/")
                self.load_workspace(root, relative)
            except (OSError, TypeError, ValueError, RecursionError) as exc:
                QtWidgets.QMessageBox.critical(
                    self,
                    "No se pudo abrir el workspace",
                    sanitize_display_text(str(exc))[:1000],
                )

        def load_workspace(
            self, project_root: str | os.PathLike[str], manifest_relative_path: str
        ) -> WorkspaceViewModel:
            """Verify all manifest/resource bytes before changing visible workspace state."""
            loaded = load_scientific_workspace(project_root, manifest_relative_path)
            model = build_workspace_view_model(loaded)
            try:
                actions = sir_simulation_actions_for_workspace(loaded)
                action_error = ""
            except (TypeError, ValueError, OverflowError) as exc:
                actions = {}
                action_error = sanitize_display_text(str(exc))[:300]

            self._generation += 1
            self._loaded_workspace = loaded
            self.workspace_view_model = model
            self._simulation_actions = actions
            self.simulation_results = {}
            self._project_root = Path(project_root)
            self._manifest_relative_path = manifest_relative_path
            self._render_workspace(action_error=action_error)
            self.statusBar().showMessage("Workspace cargado; solo se muestran bytes verificados", 8000)
            return model

        def _render_workspace(self, *, action_error: str = "") -> None:
            model = self.workspace_view_model
            if model is None:
                self._show_empty_state()
                return
            self.workspace_heading.setText(f"{model.title}  ·  {model.workspace_id}")
            self.digest_status.setText(
                f"Integridad de artefactos: {model.verification_status} · {len(model.resources)} recurso(s)"
            )
            self.scientific_notice.setText(sanitize_display_text(model.scientific_notice))
            self.tabs.clear()
            for section in model.sections:
                scroll = QtWidgets.QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
                page = QtWidgets.QWidget()
                column = QtWidgets.QVBoxLayout(page)
                column.setContentsMargins(12, 8, 12, 12)
                column.setSpacing(8)
                for component in section.components:
                    column.addWidget(self._render_component(component, action_error=action_error))
                if section.omitted_component_count:
                    omitted = QtWidgets.QLabel(
                        f"Se omitieron {section.omitted_component_count} componentes por el límite de vista."
                    )
                    omitted.setWordWrap(True)
                    column.addWidget(omitted)
                column.addStretch(1)
                scroll.setWidget(page)
                self.tabs.addTab(scroll, section.title)
            self.tabs.addTab(self._render_resources(model.resources), "Recursos")

        def _render_component(self, component: ComponentView, *, action_error: str = ""):
            card = QtWidgets.QGroupBox(sanitize_display_text(component.title))
            card.setObjectName(f"component-{component.component_id}")
            card_layout = QtWidgets.QVBoxLayout(card)
            message = QtWidgets.QLabel(sanitize_display_text(component.message))
            message.setWordWrap(True)
            message.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            message.setStyleSheet("color: #536273; font-weight: 400;")
            card_layout.addWidget(message)

            renderer = {
                "equation_view": self._render_equations,
                "parameter_table": self._render_parameters,
                "observation_table": self._render_json,
                "simulation_plot": self._render_simulation,
                "fit_summary": self._render_json,
                "sensitivity_plot": self._render_json,
                "uncertainty_summary": self._render_json,
                "audit_summary": self._render_json,
                "artifact_browser": self._render_artifact_browser,
                "code_view": self._render_code,
            }.get(component.component_type)
            if renderer is None or component.status != "ok":
                self._render_json(card_layout, component)
            else:
                renderer(card_layout, component, action_error=action_error)
            return card

        def _render_equations(self, layout, component: ComponentView, *, action_error: str = "") -> None:
            del action_error
            content = component.content
            if not isinstance(content, SirEquationView):
                self._render_json(layout, component)
                return
            lines = [
                f"Conjunto: {content.equation_set}",
                f"Estados: {', '.join(content.states)}",
                content.population_balance,
                "",
                *(f"{left} = {formula}" for left, formula in content.equations),
                "",
                f"Unidades declaradas: tiempo={content.time_unit}; población={content.population_unit}; tasa={content.rate_unit}",
            ]
            self._add_readonly_text(layout, "\n".join(map(sanitize_display_text, lines)), "equations-text")

        def _render_parameters(self, layout, component: ComponentView, *, action_error: str = "") -> None:
            del action_error
            content = component.content
            if not isinstance(content, SirParameterView):
                self._render_json(layout, component)
                return
            rows: list[tuple[str, str, str, str]] = []
            rows.extend(("Condición inicial", name, f"{value:.8g}", content.population_unit)
                        for name, value in content.initial_conditions)
            for profile in content.profiles:
                if profile.kind == "constant":
                    description = f"{profile.value:.8g}" if profile.value is not None else "—"
                else:
                    description = "; ".join(f"({x:.5g}, {y:.5g})" for x, y in profile.points)
                rows.append(("Parámetro", profile.name, description, profile.unit))
            rows.extend((
                ("Población inicial", "N₀", f"{content.initial_population:.8g}", content.population_unit),
                ("Intervalo", "t_span", f"[{content.time_span[0]:.7g}, {content.time_span[1]:.7g}]", content.time_unit),
                ("Integrador", "method", content.integrator_method, ""),
                ("Integrador", "max_step", f"{content.max_step:.7g}", content.time_unit),
                ("Integrador", "max_steps", str(content.max_steps), "pasos"),
            ))
            table = QtWidgets.QTableWidget(len(rows), 4)
            table.setObjectName("parameters-table")
            table.setHorizontalHeaderLabels(("Grupo", "Nombre", "Valor", "Unidad"))
            table.setAlternatingRowColors(True)
            table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
            table.setAccessibleName("Parámetros y configuración numérica declarados")
            for row_index, row in enumerate(rows):
                for column_index, value in enumerate(row):
                    item = QtWidgets.QTableWidgetItem(sanitize_display_text(value))
                    item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                    table.setItem(row_index, column_index, item)
            table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setStretchLastSection(True)
            table.setMaximumHeight(min(420, 42 + 29 * len(rows)))
            layout.addWidget(table)

        def _render_simulation(self, layout, component: ComponentView, *, action_error: str = "") -> None:
            result = self.simulation_results.get(component.component_id, component)
            content = result.content if isinstance(result.content, Mapping) else {}
            if content.get("times") and content.get("values"):
                chart = _TrajectoryPlot(content)
                chart.setObjectName(f"plot-{component.component_id}")
                layout.addWidget(chart)
                summary = QtWidgets.QLabel(
                    f"{content.get('method', 'Método no indicado')} · {content.get('row_count', 0)} puntos · "
                    f"series: {', '.join(map(str, content.get('series_names', ())))}"
                )
                summary.setWordWrap(True)
                summary.setTextFormat(QtCore.Qt.TextFormat.PlainText)
                layout.addWidget(summary)
            else:
                self._add_readonly_text(layout, _display_json(result.content), f"simulation-data-{component.component_id}", 150)

            action = self._simulation_actions.get(component.component_id)
            if action is not None:
                button = QtWidgets.QPushButton(f"Ejecutar: {action.label}")
                button.setObjectName(f"run-simulation-{component.component_id}")
                button.setAccessibleName(f"Solicitar confirmación y ejecutar {action.label}")
                button.setToolTip("Requiere confirmación humana antes de iniciar la acción confiable de SSEC")
                button.setEnabled(not self.simulation_running)
                button.clicked.connect(
                    lambda _checked=False, selected=component, approved=action:
                    self._request_and_run_simulation(selected, approved)
                )
                layout.addWidget(button)
            elif action_error:
                warning = QtWidgets.QLabel(f"Acción no disponible: {action_error}")
                warning.setWordWrap(True)
                warning.setTextFormat(QtCore.Qt.TextFormat.PlainText)
                warning.setStyleSheet("color: #9c3b2e;")
                layout.addWidget(warning)

        def _render_artifact_browser(self, layout, component: ComponentView, *, action_error: str = "") -> None:
            del action_error
            resources = component.content if isinstance(component.content, (tuple, list)) else ()
            self._add_resource_table(layout, resources, f"artifact-table-{component.component_id}")

        def _render_code(self, layout, component: ComponentView, *, action_error: str = "") -> None:
            del action_error
            text = component.content if isinstance(component.content, str) else _display_json(component.content)
            self._add_readonly_text(layout, text, f"code-text-{component.component_id}", 180)

        def _render_json(self, layout, component: ComponentView) -> None:
            value = component.preview_text or _display_json(component.content)
            self._add_readonly_text(layout, value, f"data-{component.component_id}", 160)

        def _add_readonly_text(self, layout, text: str, object_name: str, height: int = 240) -> None:
            view = QtWidgets.QPlainTextEdit()
            view.setObjectName(object_name)
            view.setReadOnly(True)
            view.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
            view.setPlainText(sanitize_display_text(text))
            view.setMinimumHeight(min(height, 120))
            view.setMaximumHeight(max(height, 140))
            view.setAccessibleName("Datos científicos en modo de solo lectura")
            layout.addWidget(view)

        def _render_resources(self, resources: Sequence[ResourceView]):
            page = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(page)
            self._add_resource_table(layout, resources, "workspace-resources-table")
            layout.addStretch(1)
            return page

        def _add_resource_table(self, layout, resources, object_name: str) -> None:
            rows = tuple(resources)
            table = QtWidgets.QTableWidget(len(rows), 5)
            table.setObjectName(object_name)
            table.setHorizontalHeaderLabels(("ID", "Tipo", "Ruta", "Tamaño", "SHA-256"))
            table.setAlternatingRowColors(True)
            table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
            table.setAccessibleName("Recursos capturados y verificados por SHA-256")
            for row_index, resource in enumerate(rows):
                values = (
                    str(resource.resource_id),
                    str(resource.kind),
                    str(resource.path),
                    str(resource.byte_count),
                    str(resource.sha256),
                )
                for column_index, value in enumerate(values):
                    item = QtWidgets.QTableWidgetItem(sanitize_display_text(value))
                    item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                    table.setItem(row_index, column_index, item)
            table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
            table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.Stretch)
            table.setMinimumHeight(min(420, 48 + 30 * max(1, len(rows))))
            layout.addWidget(table)

        def _confirm_simulation(self, prompt: str) -> bool:
            answer = QtWidgets.QMessageBox.question(
                self,
                "Confirmar simulación local",
                sanitize_display_text(prompt),
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            return answer == QtWidgets.QMessageBox.StandardButton.Yes

        def _request_and_run_simulation(self, component: ComponentView, action) -> None:
            workspace = self._loaded_workspace
            if workspace is None or self.simulation_running:
                return
            try:
                ticket = request_approved_simulation(
                    action,
                    workspace,
                    component,
                    confirm=self._confirmation_handler,
                )
            except (TypeError, ValueError) as exc:
                self.statusBar().showMessage(f"No se inició la simulación: {sanitize_display_text(str(exc))[:300]}")
                return
            if ticket is None:
                self.statusBar().showMessage("Simulación cancelada por el usuario", 5000)
                return
            self._generation += 1
            generation = self._generation
            thread = _SimulationThread(component.component_id, generation, ticket, self)
            thread.completed.connect(self._on_simulation_completed)
            thread.failed.connect(self._on_simulation_failed)
            thread.finished.connect(self._on_simulation_thread_finished)
            self._workers[component.component_id] = thread
            self.statusBar().showMessage("Simulación aprobada en ejecución local…")
            self._render_workspace()
            try:
                thread.start()
            except RuntimeError as exc:
                if thread.isRunning():
                    self.statusBar().showMessage(
                        "La simulación inició aunque Qt reportó un error al iniciar el worker. Espera a que termine.",
                        10_000,
                    )
                    return
                self._workers.pop(component.component_id, None)
                thread.deleteLater()
                self._render_workspace()
                self.statusBar().showMessage(
                    f"No se pudo iniciar la simulación; no se ejecutó: {sanitize_display_text(str(exc))[:300]}",
                    10_000,
                )

        @QtCore.Slot(str, int, object)
        def _on_simulation_completed(self, component_id: str, generation: int, result: ComponentView) -> None:
            if generation != self._generation or self.workspace_view_model is None:
                return
            self.simulation_results[component_id] = result
            self._render_workspace()
            self.statusBar().showMessage(
                "Resultado de simulación en memoria · no validado científicamente", 10_000
            )

        @QtCore.Slot(str, int, str)
        def _on_simulation_failed(self, component_id: str, generation: int, error: str) -> None:
            del component_id
            if generation != self._generation:
                return
            self.statusBar().showMessage(f"Falló la simulación; no se creó resultado: {error}", 10_000)

        @QtCore.Slot()
        def _on_simulation_thread_finished(self) -> None:
            thread = self.sender()
            if not isinstance(thread, _SimulationThread):
                return
            self._workers.pop(thread.component_id, None)
            if self.workspace_view_model is not None:
                self._render_workspace()
            thread.deleteLater()

        def closeEvent(self, event) -> None:
            if any(thread.isRunning() for thread in self._workers.values()):
                QtWidgets.QMessageBox.information(
                    self,
                    "Simulación en curso",
                    "Espera a que termine la acción local antes de cerrar esta ventana.",
                )
                event.ignore()
                return
            event.accept()

else:

    class ScientificWorkspaceWindow:  # pragma: no cover - exercised when optional Qt is absent.
        def __init__(self, *args, **kwargs):
            del args, kwargs
            raise RuntimeError("PySide6 is not installed; use the Tk frontend or install the optional desktop extra.")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", help="project root used by the safe resource loader")
    parser.add_argument("manifest", nargs="?", help="project-relative workspace manifest")
    arguments = parser.parse_args(argv)
    if bool(arguments.project_root) != bool(arguments.manifest):
        parser.error("--project-root and manifest must be provided together")
    if QtWidgets is None:
        print(
            "SSEC PySide6 frontend is unavailable. PySide6 is optional; use "
            "python scripts/scientific_workspace_app.py for the Tk frontend.",
            file=sys.stderr,
        )
        return 2
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
    window = ScientificWorkspaceWindow()
    if arguments.manifest:
        try:
            window.load_workspace(arguments.project_root, arguments.manifest)
        except (OSError, TypeError, ValueError, RecursionError) as exc:
            QtWidgets.QMessageBox.critical(window, "Workspace inválido", sanitize_display_text(str(exc))[:1000])
            return 2
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
