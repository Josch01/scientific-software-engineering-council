"""Optional PySide6 desktop frontend for verified scientific workspaces.

The module consumes the safe loader and bounded presentation models. Project
files remain inert; only host-registered actions may execute after confirmation.
"""
from __future__ import annotations

import argparse
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import threading

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:  # Keep this optional frontend importable without Qt installed.
    QtCore = QtGui = QtWidgets = None

try:
    from .configuration import DEFAULT_CONFIG, config_path, load_config
    from .scientific_workspace_actions import (
        ApprovedSimulationRun,
        request_approved_simulation,
        run_approved_simulation,
        sir_simulation_actions_for_workspace,
    )
    from .scientific_workspace_generation import (
        configured_proposal_providers,
        generate_workspace_proposal,
    )
    from .scientific_workspace_audit import run_workspace_audit
    from .scientific_workspace_loader import LoadedWorkspace, load_scientific_workspace
    from .scientific_workspace_qt_charts import ScientificChartWidget
    from .scientific_workspace_proposals import (
        approve_workspace_proposal,
        preview_workspace_proposal,
    )
    from .scientific_workspace_view import (
        ComponentView,
        FitSummaryView,
        ObservationEvaluationView,
        ResourceView,
        SirEquationView,
        SirParameterView,
        SensitivityPlotView,
        WorkspaceViewModel,
        build_workspace_view_model,
        sanitize_display_text,
    )
except ImportError:  # Direct execution from the scripts directory.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from configuration import DEFAULT_CONFIG, config_path, load_config
    from scientific_workspace_actions import (
        ApprovedSimulationRun,
        request_approved_simulation,
        run_approved_simulation,
        sir_simulation_actions_for_workspace,
    )
    from scientific_workspace_generation import (
        configured_proposal_providers,
        generate_workspace_proposal,
    )
    from scientific_workspace_audit import run_workspace_audit
    from scientific_workspace_loader import LoadedWorkspace, load_scientific_workspace
    from scientific_workspace_qt_charts import ScientificChartWidget
    from scientific_workspace_proposals import (
        approve_workspace_proposal,
        preview_workspace_proposal,
    )
    from scientific_workspace_view import (
        ComponentView,
        FitSummaryView,
        ObservationEvaluationView,
        ResourceView,
        SirEquationView,
        SirParameterView,
        SensitivityPlotView,
        WorkspaceViewModel,
        build_workspace_view_model,
        sanitize_display_text,
    )


MAX_FIT_RESIDUAL_TABLE_ROWS = 200


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


    class _ProposalThread(QtCore.QThread):
        progress = QtCore.Signal(object)
        completed = QtCore.Signal(object)
        failed = QtCore.Signal(str)

        def __init__(
            self,
            project_root,
            workspace,
            resource_ids,
            objective,
            config,
            cancel_event,
            parent=None,
        ):
            super().__init__(parent)
            self._project_root = project_root
            self._workspace = workspace
            self._resource_ids = tuple(resource_ids)
            self._objective = objective
            self._config = config
            self._cancel_event = cancel_event

        def run(self) -> None:
            try:
                summary = generate_workspace_proposal(
                    self._project_root,
                    self._workspace,
                    self._resource_ids,
                    self._objective,
                    self._config,
                    accept_unmetered_cost=True,
                    cancel_event=self._cancel_event,
                    progress_callback=self.progress.emit,
                )
            except BaseException as exc:
                self.failed.emit(f"{type(exc).__name__}: {exc}"[:2000])
            else:
                self.completed.emit(summary)


    class _AuditThread(QtCore.QThread):
        progress = QtCore.Signal(object)
        completed = QtCore.Signal(object)
        failed = QtCore.Signal(str)

        def __init__(self, project_root, workspace, resource_ids, config, cancel_file, parent=None):
            super().__init__(parent)
            self._project_root = project_root
            self._workspace = workspace
            self._resource_ids = tuple(resource_ids)
            self._config = config
            self._cancel_file = cancel_file

        def run(self) -> None:
            try:
                report = run_workspace_audit(
                    self._project_root,
                    self._workspace,
                    self._resource_ids,
                    self._config,
                    accept_unmetered_cost=True,
                    cancel_file=self._cancel_file,
                    progress_callback=self.progress.emit,
                )
            except BaseException as exc:
                self.failed.emit(f"{type(exc).__name__}: {exc}"[:2000])
            else:
                self.completed.emit(report)


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
                f"Eje x: Tiempo · {self._content.get('time_unit') or 'unidad no indicada'}. "
                f"Eje y: Población · {self._content.get('population_unit') or 'unidad no indicada'}. "
                f"Series: {', '.join(map(str, self._content.get('series_names', ())))}."
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
            painter.save()
            painter.translate(12, rect.center().y())
            painter.rotate(-90)
            painter.drawText(
                QtCore.QRectF(-rect.height() / 2, -10, rect.height(), 20),
                QtCore.Qt.AlignmentFlag.AlignCenter,
                f"Población · {self._content.get('population_unit') or 'unidad no indicada'}",
            )
            painter.restore()

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

        auditResultChanged = QtCore.Signal(object)

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
            self._proposal_worker: _ProposalThread | None = None
            self._proposal_cancel_event: threading.Event | None = None
            self._proposal_terminal: tuple[str, object] | None = None
            self._proposal_progress_dialog = None
            self._proposal_workspace: LoadedWorkspace | None = None
            self._proposal_project_root: Path | None = None
            self._audit_worker: _AuditThread | None = None
            self._audit_terminal: tuple[str, object] | None = None
            self._audit_progress_dialog = None
            self._audit_cancel_temp: tempfile.TemporaryDirectory | None = None
            self._audit_cancel_file: Path | None = None
            self._audit_cancel_requested = False
            self.audit_result: dict[str, object] | None = None
            self._audit_result_dialog = None
            self._generation = 0
            self._project_root: Path | None = None
            self._manifest_relative_path: str | None = None
            self._build_shell()
            self.setStyleSheet(
                "QMainWindow { background: #f2f5f7; color: #1d2d39; }"
                "QLabel { color: #243746; }"
                "QDialog, QProgressDialog { background: #f2f5f7; color: #243746; }"
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

        @property
        def proposal_running(self) -> bool:
            return self._proposal_worker is not None

        @property
        def audit_running(self) -> bool:
            return self._audit_worker is not None

        def _update_action_controls(self) -> None:
            has_workspace = self._loaded_workspace is not None and self._project_root is not None
            self.open_button.setEnabled(not self.proposal_running and not self.audit_running)
            workflow_busy = self.simulation_running or self.proposal_running or self.audit_running
            self.propose_button.setEnabled(has_workspace and not workflow_busy)
            self.import_proposal_button.setEnabled(has_workspace and not workflow_busy)
            self.audit_button.setEnabled(has_workspace and not workflow_busy)

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
            propose_button = QtWidgets.QPushButton("Proponer cambios con IA")
            propose_button.setObjectName("proposeWorkspaceButton")
            propose_button.setAccessibleName("Proponer cambios en el workspace con un CLI local")
            propose_button.clicked.connect(self._open_workspace_proposal_dialog)
            toolbar.addWidget(propose_button)
            self.propose_button = propose_button
            import_button = QtWidgets.QPushButton("Importar/revisar propuesta…")
            import_button.setObjectName("importWorkspaceProposalButton")
            import_button.setAccessibleName("Importar y revisar un manifiesto JSON de propuesta")
            import_button.clicked.connect(self._import_workspace_proposal)
            toolbar.addWidget(import_button)
            self.import_proposal_button = import_button
            audit_button = QtWidgets.QPushButton("Solicitar auditoría…")
            audit_button.setObjectName("auditWorkspaceButton")
            audit_button.setAccessibleName("Solicitar auditoría de recursos verificados")
            audit_button.clicked.connect(self._open_workspace_audit_dialog)
            toolbar.addWidget(audit_button)
            self.audit_button = audit_button

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
            self._update_action_controls()
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

        def _proposal_config(self, project_root: Path) -> tuple[dict[str, object], tuple[str, ...]]:
            policy_path = config_path(project_root)
            policy_folder = policy_path.parent
            if policy_folder.is_symlink() or policy_path.is_symlink():
                raise ValueError("la configuración SSEC no puede atravesar symlinks")
            if policy_folder.exists() and not policy_folder.is_dir():
                raise ValueError(".ssec existe, pero no es un directorio")
            policy = load_config(policy_path) if policy_path.exists() else dict(DEFAULT_CONFIG)
            return policy, configured_proposal_providers(policy)

        def _audit_config(self, project_root: Path) -> dict[str, object]:
            policy_path = config_path(project_root)
            policy_folder = policy_path.parent
            if policy_folder.is_symlink() or policy_path.is_symlink():
                raise ValueError("la configuración SSEC no puede atravesar symlinks")
            if policy_folder.exists() and not policy_folder.is_dir():
                raise ValueError(".ssec existe, pero no es un directorio")
            return load_config(policy_path) if policy_path.exists() else dict(DEFAULT_CONFIG)

        def _open_workspace_audit_dialog(self):
            workspace = self._loaded_workspace
            project_root = self._project_root
            if workspace is None or project_root is None:
                QtWidgets.QMessageBox.information(
                    self, "Abre un workspace primero", "La auditoría requiere un workspace verificado."
                )
                return None
            try:
                policy = self._audit_config(project_root)
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                QtWidgets.QMessageBox.critical(
                    self, "Configuración SSEC no válida", sanitize_display_text(str(exc))[:1000]
                )
                return None

            dialog = QtWidgets.QDialog(self)
            dialog.setObjectName("workspaceAuditRequestDialog")
            dialog.setWindowTitle("Solicitar auditoría del workspace")
            dialog.resize(900, 560)
            layout = QtWidgets.QVBoxLayout(dialog)
            intro = QtWidgets.QLabel(
                f"Workspace: {workspace.summary.title} · {workspace.summary.workspace_id}\n"
                "Selecciona únicamente recursos verificados que se compartirán con especialistas."
            )
            intro.setWordWrap(True)
            intro.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            layout.addWidget(intro)

            table = QtWidgets.QTableWidget(len(workspace.resources), 5)
            table.setObjectName("workspaceAuditResourceTable")
            table.setHorizontalHeaderLabels(("ID", "Tipo", "Ruta", "Bytes", "SHA-256"))
            table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
            table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setAlternatingRowColors(True)
            for row, resource in enumerate(workspace.resources):
                values = (resource.resource_id, resource.kind, resource.path,
                          str(len(resource.content)), resource.sha256)
                for column, value in enumerate(values):
                    item = QtWidgets.QTableWidgetItem(sanitize_display_text(value))
                    item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                    table.setItem(row, column, item)
            table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
            table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.Stretch)
            layout.addWidget(table, 1)

            note = QtWidgets.QLabel(
                f"Proveedor configurado: {policy['provider_mode']}. La ejecución CLI puede consumir cuota; "
                "SSEC no mide ni limita el coste. Solo se enviarán los recursos seleccionados y el contexto "
                "derivado. La salida es informativa: no equivale a una revisión independiente de SSEC, "
                "certificación científica ni aprobación."
            )
            note.setObjectName("workspaceAuditSafetyNotice")
            note.setWordWrap(True)
            note.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            layout.addWidget(note)

            buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Cancel)
            dispatch = buttons.addButton(
                "Enviar a especialistas…", QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole
            )
            dispatch.setObjectName("dispatchWorkspaceAuditButton")
            buttons.rejected.connect(dialog.reject)
            dispatch.clicked.connect(
                lambda: self._dispatch_workspace_audit(dialog, table, workspace, project_root, policy)
            )
            layout.addWidget(buttons)
            dialog.setModal(True)
            dialog.show()
            self._audit_request_dialog = dialog
            return dialog

        def _dispatch_workspace_audit(self, dialog, table, workspace, project_root, policy) -> None:
            selected_rows = sorted(index.row() for index in table.selectionModel().selectedRows())
            selected_ids = tuple(table.item(row, 0).text() for row in selected_rows)
            if not selected_ids:
                QtWidgets.QMessageBox.information(
                    dialog, "Selecciona recursos", "Selecciona al menos un recurso verificado."
                )
                return
            if self._loaded_workspace is not workspace or self._project_root != project_root:
                QtWidgets.QMessageBox.warning(
                    dialog, "Workspace cambió", "Vuelve a abrir la solicitud con el workspace activo."
                )
                return
            answer = QtWidgets.QMessageBox.question(
                dialog,
                "Confirmar envío a especialistas",
                f"Enviar {len(selected_ids)} recurso(s) de {workspace.summary.workspace_id!r} "
                f"al proveedor {policy['provider_mode']!r}? La operación CLI puede consumir cuota. "
                "SSEC no mide el coste. La salida no aprobará cambios ni certificará resultados. ¿Continuar?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                return
            dialog.accept()
            self._start_workspace_audit(workspace, project_root, selected_ids, policy)

        def _start_workspace_audit(self, workspace, project_root, selected_ids, policy) -> None:
            if self.audit_running or self.proposal_running or self.simulation_running:
                return
            cancel_temp = tempfile.TemporaryDirectory(prefix="ssec-qt-audit-cancel-")
            cancel_file = Path(cancel_temp.name) / "cancel.requested"
            progress = QtWidgets.QProgressDialog(
                "Preparando snapshot verificado…", "Cancelar", 0, 0, self
            )
            progress.setObjectName("workspaceAuditProgressDialog")
            progress.setWindowTitle("Auditoría del workspace")
            progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
            progress.setMinimumDuration(0)
            progress.setAutoClose(False)
            progress.setAutoReset(False)
            progress.canceled.connect(self._cancel_workspace_audit)
            worker = _AuditThread(project_root, workspace, selected_ids, policy, cancel_file, self)
            worker.progress.connect(self._on_workspace_audit_progress)
            worker.completed.connect(self._on_workspace_audit_completed)
            worker.failed.connect(self._on_workspace_audit_failed)
            worker.finished.connect(self._on_workspace_audit_finished)
            self._audit_worker = worker
            self._audit_terminal = None
            self._audit_progress_dialog = progress
            self._audit_cancel_temp = cancel_temp
            self._audit_cancel_file = cancel_file
            self._audit_cancel_requested = False
            self._update_action_controls()
            self.statusBar().showMessage("Auditoría en curso · salida no aprobada")
            progress.show()
            try:
                worker.start()
            except RuntimeError as exc:
                if worker.isRunning():
                    progress.setLabelText("La auditoría inició; espera el resultado terminal.")
                    return
                self._audit_worker = None
                self._audit_progress_dialog = None
                self._audit_cancel_temp = None
                self._audit_cancel_file = None
                cancel_temp.cleanup()
                progress.reset()
                progress.hide()
                progress.deleteLater()
                worker.deleteLater()
                self._update_action_controls()
                self.statusBar().showMessage(
                    f"No se pudo iniciar la auditoría; sin aprobación: {sanitize_display_text(str(exc))[:300]}",
                    10_000,
                )

        def _cancel_workspace_audit(self) -> None:
            cancel_file = self._audit_cancel_file
            if cancel_file is None or self._audit_cancel_requested:
                return
            try:
                cancel_file.write_text("cancel requested\n", encoding="utf-8")
            except OSError as exc:
                QtWidgets.QMessageBox.critical(
                    self, "No se pudo solicitar cancelación", sanitize_display_text(str(exc))[:500]
                )
                return
            self._audit_cancel_requested = True
            progress = self._audit_progress_dialog
            if progress is not None:
                progress.setLabelText("Cancelación solicitada · esperando el cierre de procesos locales")
                cancel_button = progress.findChild(QtWidgets.QPushButton)
                if cancel_button is not None:
                    cancel_button.setEnabled(False)
                progress.show()
            self.statusBar().showMessage("Cancelación solicitada · esperando el cierre de procesos locales")

        @QtCore.Slot(object)
        def _on_workspace_audit_progress(self, event: object) -> None:
            if self._audit_worker is None or not isinstance(event, Mapping):
                return
            label = sanitize_display_text(str(event.get("status", "Especialista trabajando")))[:300]
            if self._audit_progress_dialog is not None:
                self._audit_progress_dialog.setLabelText(label)
            if not self._audit_cancel_requested:
                self.statusBar().showMessage(f"Auditoría en curso · {label} · sin aprobación")

        @QtCore.Slot(object)
        def _on_workspace_audit_completed(self, result: object) -> None:
            self._audit_terminal = ("result", result)

        @QtCore.Slot(str)
        def _on_workspace_audit_failed(self, message: str) -> None:
            self._audit_terminal = ("error", sanitize_display_text(message)[:2000])

        @QtCore.Slot()
        def _on_workspace_audit_finished(self) -> None:
            worker = self.sender()
            if worker is not self._audit_worker:
                return
            terminal = self._audit_terminal
            progress = self._audit_progress_dialog
            cancel_temp = self._audit_cancel_temp
            cancel_requested = self._audit_cancel_requested
            self._audit_worker = None
            self._audit_terminal = None
            self._audit_progress_dialog = None
            self._audit_cancel_temp = None
            self._audit_cancel_file = None
            self._audit_cancel_requested = False
            if cancel_temp is not None:
                cancel_temp.cleanup()
            if progress is not None:
                progress.reset()
                progress.hide()
                progress.deleteLater()
            self._update_action_controls()
            worker.deleteLater()
            if terminal is None:
                report = {
                    "execution": "FAILED",
                    "error": "worker terminó sin resultado verificable",
                    "release_status": "NOT_APPROVED",
                    "scientific_validity": "NOT_CERTIFIED",
                }
            elif terminal[0] == "error":
                report = {
                    "execution": "FAILED",
                    "error": terminal[1],
                    "release_status": "NOT_APPROVED",
                    "scientific_validity": "NOT_CERTIFIED",
                }
            elif isinstance(terminal[1], Mapping):
                report = dict(terminal[1])
            else:
                report = {"execution": "FAILED", "error": "respuesta de auditoría inválida"}
            valid_states = {
                "PROCESSES_COMPLETED_NOT_AUDITED", "PARTIAL_OR_FAILED", "INTERRUPTED", "CANCELLED", "FAILED"
            }
            if report.get("execution") not in valid_states:
                report["unexpected_execution"] = report.get("execution")
                report["execution"] = "FAILED"
                report["error"] = "estado terminal no reconocido"
            report["release_status"] = "NOT_APPROVED"
            report["scientific_validity"] = "NOT_CERTIFIED"
            report["human_review"] = "NOT_PERFORMED"
            self.audit_result = report
            self.auditResultChanged.emit(dict(report))
            execution = report["execution"]
            if execution == "FAILED":
                message = "Auditoría fallida · sin aprobación"
            elif execution == "CANCELLED" or cancel_requested:
                message = f"Cancelación solicitada · {execution} · sin aprobación"
            elif execution == "PROCESSES_COMPLETED_NOT_AUDITED":
                message = "Procesos completados · salida no auditada independientemente ni aprobada"
            else:
                message = f"Auditoría {execution} · sin aprobación"
            self.statusBar().showMessage(message, 10_000)
            self._show_workspace_audit_result(report)

        def _show_workspace_audit_result(self, report: Mapping[str, object]) -> None:
            previous = self._audit_result_dialog
            if previous is not None:
                previous.close()
                previous.deleteLater()
            dialog = QtWidgets.QDialog(self)
            dialog.setObjectName("workspaceAuditResultDialog")
            dialog.setWindowTitle("Resultado de auditoría · no aprobado")
            dialog.resize(880, 620)
            layout = QtWidgets.QVBoxLayout(dialog)
            notice = QtWidgets.QLabel(
                "Los procesos CLI no constituyen una revisión independiente de SSEC, prueba aprobada, "
                "validación científica ni aprobación de cambios."
            )
            notice.setWordWrap(True)
            notice.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            layout.addWidget(notice)
            output = QtWidgets.QPlainTextEdit()
            output.setObjectName("workspaceAuditResultText")
            output.setReadOnly(True)
            output.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
            display = _display_json(report)
            if len(display) > 60_000:
                display = display[:60_000] + "\n… resultado truncado en la vista; el informe guardado conserva el contenido completo."
            output.setPlainText(display)
            layout.addWidget(output, 1)
            buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
            buttons.rejected.connect(dialog.reject)
            buttons.accepted.connect(dialog.accept)
            layout.addWidget(buttons)
            self._audit_result_dialog = dialog
            dialog.show()

        def _open_workspace_proposal_dialog(self):
            workspace = self._loaded_workspace
            project_root = self._project_root
            if workspace is None or project_root is None:
                QtWidgets.QMessageBox.information(
                    self, "Abre un workspace primero", "La propuesta requiere un workspace verificado."
                )
                return None
            try:
                policy, providers = self._proposal_config(project_root)
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                QtWidgets.QMessageBox.critical(
                    self, "Configuración SSEC no válida", sanitize_display_text(str(exc))[:1000]
                )
                return None
            if not providers:
                QtWidgets.QMessageBox.information(
                    self,
                    "Generación local no disponible",
                    "Codex CLI no ofrece aquí una política que impida ejecutar comandos. "
                    "Configure Gemini plan mode o use Importar/revisar propuesta… para cargar JSON.",
                )
                return None

            dialog = QtWidgets.QDialog(self)
            dialog.setObjectName("workspaceProposalRequestDialog")
            dialog.setWindowTitle("Proponer cambios con IA")
            dialog.resize(900, 650)
            layout = QtWidgets.QVBoxLayout(dialog)
            intro = QtWidgets.QLabel(
                f"Workspace: {workspace.summary.title} · {workspace.summary.workspace_id}\n"
                f"CLI local disponible para esta acción: {' → '.join(providers)}. "
                "Seleccione exactamente qué recursos verificados podrá leer el agente."
            )
            intro.setWordWrap(True)
            intro.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            layout.addWidget(intro)

            table = QtWidgets.QTableWidget(len(workspace.resources), 5)
            table.setObjectName("workspaceProposalResourceTable")
            table.setHorizontalHeaderLabels(("ID", "Tipo", "Ruta", "Bytes", "SHA-256"))
            table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
            table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setAlternatingRowColors(True)
            for row, resource in enumerate(workspace.resources):
                values = (resource.resource_id, resource.kind, resource.path,
                          str(len(resource.content)), resource.sha256)
                for column, value in enumerate(values):
                    item = QtWidgets.QTableWidgetItem(sanitize_display_text(value))
                    item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                    table.setItem(row, column, item)
            table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
            table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.Stretch)
            layout.addWidget(table, 1)

            layout.addWidget(QtWidgets.QLabel("Describa qué quiere agregar o modificar:"))
            objective = QtWidgets.QPlainTextEdit()
            objective.setObjectName("workspaceProposalObjective")
            objective.setPlaceholderText(
                "Ejemplo: agregue vistas de parámetros y compare las observaciones seleccionadas."
            )
            objective.setMaximumHeight(130)
            layout.addWidget(objective)
            note = QtWidgets.QLabel(
                "La CLI puede consumir cuota y SSEC no mide ni limita el coste. Solo se enviarán "
                "los bytes seleccionados y el contexto derivado. La salida debe ser JSON validado; "
                "se mostrará un diff completo. No se ejecutará código generado ni se sobrescribirá "
                "el manifiesto original. La aprobación será una acción separada."
            )
            note.setObjectName("workspaceProposalSafetyNotice")
            note.setWordWrap(True)
            note.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            layout.addWidget(note)

            buttons = QtWidgets.QDialogButtonBox(
                QtWidgets.QDialogButtonBox.StandardButton.Cancel
            )
            dispatch_button = buttons.addButton(
                "Solicitar propuesta…", QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole
            )
            dispatch_button.setObjectName("dispatchWorkspaceProposalButton")
            buttons.rejected.connect(dialog.reject)
            dispatch_button.clicked.connect(
                lambda: self._dispatch_workspace_proposal(
                    dialog, table, objective, workspace, project_root, policy, providers
                )
            )
            layout.addWidget(buttons)
            dialog.setModal(True)
            dialog.show()
            self._proposal_request_dialog = dialog
            return dialog

        def _dispatch_workspace_proposal(
            self, dialog, table, objective, workspace, project_root, policy, providers
        ) -> None:
            selected_rows = sorted(
                index.row() for index in table.selectionModel().selectedRows()
            )
            selected_ids = tuple(table.item(row, 0).text() for row in selected_rows)
            objective_text = objective.toPlainText().strip()
            if not selected_ids:
                QtWidgets.QMessageBox.information(
                    dialog, "Selecciona recursos", "Selecciona al menos un recurso verificado."
                )
                return
            if not objective_text:
                QtWidgets.QMessageBox.information(
                    dialog, "Describe los cambios", "Escribe qué quieres cambiar en el workspace."
                )
                return
            if self._loaded_workspace is not workspace or self._project_root != project_root:
                QtWidgets.QMessageBox.warning(
                    dialog, "Workspace cambió", "Vuelve a abrir la solicitud con el workspace activo."
                )
                return
            answer = QtWidgets.QMessageBox.question(
                dialog,
                "Confirmar propuesta con IA",
                f"Enviar {len(selected_ids)} recurso(s) de {workspace.summary.workspace_id!r} "
                f"al CLI local {' / '.join(providers)}? La llamada puede consumir cuota. "
                "SSEC no mide el coste. Solo se enviarán los bytes seleccionados. ¿Continuar?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                return
            dialog.accept()
            self._start_workspace_proposal(
                workspace, project_root, selected_ids, objective_text, policy
            )

        def _start_workspace_proposal(
            self, workspace, project_root, selected_ids, objective, policy
        ) -> None:
            if self.proposal_running or self.simulation_running or self.audit_running:
                return
            cancel_event = threading.Event()
            progress = QtWidgets.QProgressDialog(
                "Preparando snapshot verificado…", "Cancelar", 0, 0, self
            )
            progress.setObjectName("workspaceProposalProgressDialog")
            progress.setWindowTitle("Proponer cambios con IA")
            progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
            progress.setMinimumDuration(0)
            progress.setAutoClose(False)
            progress.setAutoReset(False)
            progress.canceled.connect(self._cancel_workspace_proposal)
            self._proposal_cancel_event = cancel_event
            self._proposal_terminal = None
            self._proposal_progress_dialog = progress
            self._proposal_workspace = workspace
            self._proposal_project_root = project_root
            worker = _ProposalThread(
                project_root, workspace, selected_ids, objective, policy, cancel_event, self
            )
            worker.progress.connect(self._on_workspace_proposal_progress)
            worker.completed.connect(self._on_workspace_proposal_completed)
            worker.failed.connect(self._on_workspace_proposal_failed)
            worker.finished.connect(self._on_workspace_proposal_finished)
            self._proposal_worker = worker
            self._update_action_controls()
            self.statusBar().showMessage("Propuesta en curso · todavía no aprobada")
            progress.show()
            try:
                worker.start()
            except RuntimeError as exc:
                if worker.isRunning():
                    progress.setLabelText("La propuesta inició; espera el resultado terminal.")
                    return
                self._proposal_worker = None
                self._proposal_cancel_event = None
                self._proposal_progress_dialog = None
                self._proposal_workspace = None
                self._proposal_project_root = None
                progress.reset()
                progress.hide()
                progress.deleteLater()
                worker.deleteLater()
                self._update_action_controls()
                self.statusBar().showMessage(
                    f"No se pudo iniciar la propuesta; no se aprobó: {sanitize_display_text(str(exc))[:300]}",
                    10_000,
                )

        def _cancel_workspace_proposal(self) -> None:
            cancel_event = self._proposal_cancel_event
            if cancel_event is None or cancel_event.is_set():
                return
            cancel_event.set()
            progress = self._proposal_progress_dialog
            if progress is not None:
                progress.setLabelText("Cancelación solicitada · esperando el CLI local")
                cancel_button = progress.findChild(QtWidgets.QPushButton)
                if cancel_button is not None:
                    cancel_button.setEnabled(False)
                progress.show()
            self.statusBar().showMessage("Cancelación solicitada · esperando el CLI local")

        @QtCore.Slot(object)
        def _on_workspace_proposal_progress(self, event: object) -> None:
            if self._proposal_worker is None or not isinstance(event, Mapping):
                return
            label = sanitize_display_text(str(event.get("status", "Agente trabajando")))[:300]
            if self._proposal_progress_dialog is not None:
                self._proposal_progress_dialog.setLabelText(label)
            if self._proposal_cancel_event is None or not self._proposal_cancel_event.is_set():
                self.statusBar().showMessage(f"Propuesta en curso · {label} · sin aprobación")

        @QtCore.Slot(object)
        def _on_workspace_proposal_completed(self, result: object) -> None:
            self._proposal_terminal = ("result", result)

        @QtCore.Slot(str)
        def _on_workspace_proposal_failed(self, message: str) -> None:
            self._proposal_terminal = ("error", sanitize_display_text(message)[:2000])

        @QtCore.Slot()
        def _on_workspace_proposal_finished(self) -> None:
            worker = self.sender()
            if worker is not self._proposal_worker:
                return
            terminal = self._proposal_terminal
            cancel_event = self._proposal_cancel_event
            cancel_requested = cancel_event is not None and cancel_event.is_set()
            active_workspace = self._proposal_workspace
            project_root = self._proposal_project_root
            progress = self._proposal_progress_dialog
            self._proposal_worker = None
            self._proposal_cancel_event = None
            self._proposal_terminal = None
            self._proposal_progress_dialog = None
            self._proposal_workspace = None
            self._proposal_project_root = None
            if progress is not None:
                progress.reset()
                progress.hide()
                progress.deleteLater()
            self._update_action_controls()
            worker.deleteLater()
            if terminal is None:
                self.statusBar().showMessage("La propuesta terminó sin resultado verificable", 10_000)
                return
            outcome, payload = terminal
            if outcome == "error":
                self.statusBar().showMessage("Propuesta fallida · sin aprobación", 10_000)
                QtWidgets.QMessageBox.critical(self, "No se pudo generar la propuesta", str(payload))
                return
            if not isinstance(payload, Mapping):
                self.statusBar().showMessage("Respuesta de propuesta inválida · sin aprobación", 10_000)
                return
            status = payload.get("status")
            if cancel_requested or status == "CANCELLED":
                self.statusBar().showMessage("Propuesta cancelada · sin aprobación", 10_000)
                return
            if status == "PROVIDER_UNAVAILABLE":
                self.statusBar().showMessage("CLI local no disponible · importación manual disponible", 10_000)
                QtWidgets.QMessageBox.information(
                    self,
                    "Proveedor local no disponible",
                    "No se aprobó ninguna propuesta. Usa Importar/revisar propuesta… para cargar JSON.",
                )
                return
            if status != "PROPOSAL_READY_NOT_APPROVED":
                self.statusBar().showMessage("Propuesta fallida · sin aprobación", 10_000)
                QtWidgets.QMessageBox.warning(
                    self,
                    "Propuesta no disponible",
                    sanitize_display_text(str(payload.get("error") or status or "Error desconocido"))[:1000],
                )
                return
            if (not isinstance(active_workspace, LoadedWorkspace)
                    or active_workspace is not self._loaded_workspace
                    or project_root != self._project_root):
                self.statusBar().showMessage(
                    "Workspace cambió durante la generación; propuesta conservada sin aprobar.", 10_000
                )
                return
            relative_path = payload.get("proposal_relative_path")
            if not isinstance(relative_path, str) or not relative_path:
                self.statusBar().showMessage("Propuesta sin ruta válida · sin aprobación", 10_000)
                return
            self.statusBar().showMessage("Propuesta recibida · revisar el diff antes de aprobar", 10_000)
            self._review_workspace_proposal(relative_path)

        def _import_workspace_proposal(self) -> None:
            workspace = self._loaded_workspace
            root = self._project_root
            if workspace is None or root is None:
                return
            selected, _filter = QtWidgets.QFileDialog.getOpenFileName(
                self,
                "Seleccionar propuesta JSON",
                str(root),
                "Workspace manifests (*.json);;Todos los archivos (*)",
            )
            if not selected:
                return
            try:
                resolved_root = root.resolve(strict=True)
                resolved_path = Path(selected).resolve(strict=True)
                relative_path = resolved_path.relative_to(resolved_root).as_posix()
            except (OSError, ValueError, RuntimeError) as exc:
                QtWidgets.QMessageBox.critical(
                    self, "Propuesta fuera del proyecto", sanitize_display_text(str(exc))[:1000]
                )
                return
            self._review_workspace_proposal(relative_path)

        def _review_workspace_proposal(self, relative_path: str):
            workspace = self._loaded_workspace
            root = self._project_root
            if workspace is None or root is None:
                return None
            try:
                preview = preview_workspace_proposal(root, workspace, relative_path)
            except (OSError, TypeError, ValueError) as exc:
                QtWidgets.QMessageBox.critical(
                    self, "Propuesta no válida", sanitize_display_text(str(exc))[:1000]
                )
                return None

            dialog = QtWidgets.QDialog(self)
            dialog.setObjectName("workspaceProposalReviewDialog")
            dialog.setWindowTitle("Revisar propuesta de workspace")
            dialog.resize(900, 650)
            layout = QtWidgets.QVBoxLayout(dialog)
            summary = QtWidgets.QLabel(
                f"Propuesta: {json.dumps(preview.workspace_title, ensure_ascii=True)}\n"
                f"SHA-256 semántico: {preview.proposal_manifest_sha256}"
            )
            summary.setWordWrap(True)
            summary.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            layout.addWidget(summary)
            diff = QtWidgets.QPlainTextEdit()
            diff.setObjectName("workspaceProposalDiff")
            diff.setReadOnly(True)
            diff.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
            diff.setPlainText(
                sanitize_display_text(preview.diff)
                if preview.changed
                else "La propuesta no contiene cambios respecto al workspace activo."
            )
            layout.addWidget(diff, 1)
            notice = QtWidgets.QLabel(
                "Este diff completo está acotado y corresponde al manifiesto validado. "
                "La propuesta no ejecuta código. Aprobar guarda una copia con nombre "
                "basado en su digest; el manifiesto activo no se sobrescribe."
            )
            notice.setWordWrap(True)
            notice.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            layout.addWidget(notice)
            buttons = QtWidgets.QDialogButtonBox()
            reject_button = buttons.addButton(
                "Rechazar", QtWidgets.QDialogButtonBox.ButtonRole.RejectRole
            )
            approve_button = buttons.addButton(
                "Aprobar y guardar", QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole
            )
            reject_button.setObjectName("rejectWorkspaceProposalButton")
            approve_button.setObjectName("approveWorkspaceProposalButton")
            approve_button.setEnabled(preview.changed)
            buttons.rejected.connect(dialog.reject)

            def approve() -> None:
                if not preview.changed:
                    return
                target_name = f".ssec-workspace-{preview.approved_manifest_sha256}.json"
                answer = QtWidgets.QMessageBox.question(
                    dialog,
                    "Aprobar propuesta",
                    f"Guardar como {target_name} y abrirlo como workspace activo? "
                    "El archivo fuente no se reemplazará.",
                    QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                    QtWidgets.QMessageBox.StandardButton.No,
                )
                if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                    return
                if self._loaded_workspace is not workspace or self._project_root != root:
                    QtWidgets.QMessageBox.warning(
                        dialog, "Workspace cambió", "Revisa de nuevo la propuesta activa."
                    )
                    return
                approve_button.setEnabled(False)
                try:
                    approved = approve_workspace_proposal(root, workspace, preview)
                    self.load_workspace(root, approved.manifest_relative_path)
                except (OSError, TypeError, ValueError) as exc:
                    approve_button.setEnabled(True)
                    QtWidgets.QMessageBox.critical(
                        dialog, "No se pudo aprobar la propuesta", sanitize_display_text(str(exc))[:1000]
                    )
                    return
                self.statusBar().showMessage(
                    f"Workspace aprobado guardado en {approved.manifest_relative_path}", 10_000
                )
                dialog.accept()

            buttons.accepted.connect(approve)
            layout.addWidget(buttons)
            dialog.setModal(True)
            dialog.show()
            self._proposal_review_dialog = dialog
            return dialog

        def load_workspace(
            self,
            project_root: str | os.PathLike[str],
            manifest_relative_path: str,
            *,
            expected_manifest_sha256: str | None = None,
        ) -> WorkspaceViewModel:
            """Verify workspace resources and optional manifest provenance before UI mutation."""
            loaded = load_scientific_workspace(project_root, manifest_relative_path)
            if expected_manifest_sha256 is not None:
                if (
                    not isinstance(expected_manifest_sha256, str)
                    or len(expected_manifest_sha256) != 64
                    or any(character not in "0123456789abcdef" for character in expected_manifest_sha256)
                ):
                    raise ValueError("expected workspace SHA-256 is invalid")
                actual_sha256 = hashlib.sha256(loaded.manifest_bytes).hexdigest()
                if actual_sha256 != expected_manifest_sha256:
                    raise ValueError("workspace manifest SHA-256 differs from the selected history record")
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
            self._update_action_controls()
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
                "fit_summary": self._render_fit_summary,
                "sensitivity_plot": self._render_sensitivity,
                "residual_plot": self._render_residuals,
                "uncertainty_summary": self._render_uncertainty,
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
                parameters = content.get("parameters", {})
                parameter_units = content.get("parameter_units", {})
                parameter_summary = " · ".join(
                    f"{name}={float(value):.8g} "
                    f"{parameter_units.get(name, 'unidad no indicada')}"
                    for name, value in parameters.items()
                ) if isinstance(parameters, Mapping) else ""
                summary = QtWidgets.QLabel(
                    f"{content.get('method', 'Método no indicado')} · {content.get('row_count', 0)} puntos · "
                    f"{content.get('step_count', 0)} pasos · paso solicitado "
                    f"{content.get('requested_max_step', '—')} · paso real "
                    f"{content.get('actual_step_size', '—')} · "
                    f"series: {', '.join(map(str, content.get('series_names', ())))} · "
                    f"parámetros: {parameter_summary or 'no indicados'}"
                )
                summary.setObjectName(f"simulation-summary-{component.component_id}")
                summary.setWordWrap(True)
                summary.setTextFormat(QtCore.Qt.TextFormat.PlainText)
                layout.addWidget(summary)
                self._add_source_provenance(layout, result)
            else:
                self._add_readonly_text(layout, _display_json(result.content), f"simulation-data-{component.component_id}", 150)

            action = self._simulation_actions.get(component.component_id)
            if action is not None:
                button = QtWidgets.QPushButton(f"Ejecutar: {action.label}")
                button.setObjectName(f"run-simulation-{component.component_id}")
                button.setAccessibleName(f"Solicitar confirmación y ejecutar {action.label}")
                button.setToolTip("Requiere confirmación humana antes de iniciar la acción confiable de SSEC")
                button.setEnabled(
                    not self.simulation_running and not self.proposal_running and not self.audit_running
                )
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

        def _add_source_provenance(self, layout, component: ComponentView) -> None:
            for source in component.source_resources:
                label = QtWidgets.QLabel(
                    f"Recurso verificado: {source.resource_id} · {source.path} · "
                    f"SHA-256 {source.sha256}. La huella acredita integridad de bytes, "
                    "no origen ni validez científica."
                )
                label.setObjectName(f"source-provenance-{component.component_id}")
                label.setWordWrap(True)
                label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
                layout.addWidget(label)

        def _render_fit_summary(self, layout, component: ComponentView, *, action_error: str = "") -> None:
            del action_error
            content = component.content
            if not isinstance(content, FitSummaryView):
                self._render_json(layout, component)
                return
            summary = QtWidgets.QLabel(
                f"{content.method} · estado {content.status} · coste {content.cost:.8g} · "
                f"iteraciones {content.iterations}/{content.max_iterations} · "
                f"evaluaciones {content.function_evaluations}/{content.max_function_evaluations} · "
                f"pasos aceptados {content.accepted_steps} · residuales {len(content.residuals)}\n"
                "Identificabilidad práctica: no evaluada. Incertidumbre estadística: no evaluada."
            )
            summary.setObjectName(f"fit-summary-{component.component_id}")
            summary.setWordWrap(True)
            summary.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            layout.addWidget(summary)
            table = QtWidgets.QTableWidget(len(content.parameters), 6)
            table.setObjectName("fit-parameters-table")
            table.setHorizontalHeaderLabels((
                "Parámetro", "Inicial", "Ajustado", "Límite inferior", "Límite superior", "Unidad"
            ))
            table.setAccessibleName("Parámetros y cotas del resultado de ajuste")
            table.setAlternatingRowColors(True)
            table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            for row_index, parameter in enumerate(content.parameters):
                values = (
                    parameter.name, f"{parameter.initial_value:.8g}",
                    f"{parameter.fitted_value:.8g}", f"{parameter.lower_bound:.8g}",
                    f"{parameter.upper_bound:.8g}", parameter.unit,
                )
                for column, value in enumerate(values):
                    table.setItem(row_index, column,
                                  QtWidgets.QTableWidgetItem(sanitize_display_text(value)))
            table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            layout.addWidget(table)
            residual_count = len(content.residuals)
            if residual_count > MAX_FIT_RESIDUAL_TABLE_ROWS:
                sampled_indexes = tuple(
                    round(index * (residual_count - 1) / (MAX_FIT_RESIDUAL_TABLE_ROWS - 1))
                    for index in range(MAX_FIT_RESIDUAL_TABLE_ROWS)
                )
            else:
                sampled_indexes = tuple(range(residual_count))
            residuals = QtWidgets.QTableWidget(len(sampled_indexes), 2)
            residuals.setObjectName("fit-residuals-table")
            residuals.setHorizontalHeaderLabels(("Índice", "Residuo"))
            residuals.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            for row_index, source_index in enumerate(sampled_indexes):
                residuals.setItem(row_index, 0, QtWidgets.QTableWidgetItem(str(source_index)))
                residuals.setItem(
                    row_index, 1, QtWidgets.QTableWidgetItem(f"{content.residuals[source_index]:.8g}")
                )
            if residual_count > len(sampled_indexes):
                residuals.setToolTip(
                    f"Vista tabular limitada a {len(sampled_indexes)} filas de "
                    f"{residual_count} residuales; se incluyen ambos extremos."
                )
            residuals.setMaximumHeight(min(300, 48 + 26 * len(sampled_indexes)))
            layout.addWidget(residuals)
            self._add_source_provenance(layout, component)

        def _render_sensitivity(self, layout, component: ComponentView, *, action_error: str = "") -> None:
            del action_error
            content = component.content
            if not isinstance(content, SensitivityPlotView):
                self._render_json(layout, component)
                return
            groups: dict[str, list] = {}
            for series in content.series:
                groups.setdefault(series.unit, []).append(series)
            for group_index, (unit, series_group) in enumerate(groups.items()):
                chart = ScientificChartWidget({
                    "title": f"Sensibilidad local · {unit}",
                    "x_label": f"Tiempo · {content.time_unit}",
                    "y_label": f"Derivada local · {unit}",
                    "series": [
                        {"name": series.label, "x": content.times, "y": series.values}
                        for series in series_group
                    ],
                })
                chart.setObjectName(f"plot-{component.component_id}-sensitivity-{group_index}")
                layout.addWidget(chart)
            method = QtWidgets.QLabel(
                f"Método: {content.method}; trayectoria base: {content.solver_method}. "
                "La sensibilidad local no demuestra identificabilidad práctica."
            )
            method.setWordWrap(True)
            method.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            layout.addWidget(method)
            self._add_source_provenance(layout, component)

        def _render_residuals(self, layout, component: ComponentView, *, action_error: str = "") -> None:
            del action_error
            content = component.content
            if not isinstance(content, ObservationEvaluationView):
                self._render_json(layout, component)
                return
            tabs = QtWidgets.QTabWidget()
            tabs.setObjectName(f"residual-tabs-{component.component_id}")
            for series_index, series in enumerate(content.series):
                page = QtWidgets.QWidget()
                page_layout = QtWidgets.QVBoxLayout(page)
                observed_chart = ScientificChartWidget({
                    "title": f"{series.variable}: observado y simulado",
                    "x_label": f"Tiempo · {content.time_unit}",
                    "y_label": f"Valor · {series.unit}",
                    "series": [
                        {"name": "Observado", "x": series.times, "y": series.observed},
                        {"name": "Simulado", "x": series.times, "y": series.simulated},
                    ],
                })
                observed_chart.setObjectName(
                    f"plot-{component.component_id}-observed-{series_index}"
                )
                page_layout.addWidget(observed_chart)
                zero = tuple(0.0 for _ in series.residuals)
                residual_chart = ScientificChartWidget({
                    "title": f"{series.variable}: residuo (simulado − observado)",
                    "x_label": f"Tiempo · {content.time_unit}",
                    "y_label": f"Residuo · {series.unit}",
                    "series": [
                        {"name": "Residuo", "x": series.times, "y": series.residuals},
                        {"name": "Referencia cero", "x": series.times, "y": zero},
                    ],
                })
                residual_chart.setObjectName(f"plot-{component.component_id}-residual-{series_index}")
                page_layout.addWidget(residual_chart)
                tabs.addTab(page, sanitize_display_text(series.variable))
            layout.addWidget(tabs)
            provenance = QtWidgets.QLabel(
                f"Procedencia declarada: { _display_json(content.provenance) } · "
                f"SHA-256 normalizado de observaciones: {content.observation_sha256}. "
                "Residuo = simulado − observado; no es incertidumbre estadística."
            )
            provenance.setWordWrap(True)
            provenance.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            layout.addWidget(provenance)
            self._add_source_provenance(layout, component)

        def _render_uncertainty(self, layout, component: ComponentView, *, action_error: str = "") -> None:
            del action_error
            status = QtWidgets.QLabel(
                "NOT_ASSESSED / NOT_CALCULATED · No hay una estimación estadística validada; "
                "no se muestran intervalos ni bandas de confianza."
            )
            status.setObjectName(f"uncertainty-status-{component.component_id}")
            status.setWordWrap(True)
            status.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            status.setStyleSheet("color: #825b18; font-weight: 600;")
            layout.addWidget(status)
            self._render_json(layout, component)
            self._add_source_provenance(layout, component)

        def _render_artifact_browser(self, layout, component: ComponentView, *, action_error: str = "") -> None:
            del action_error
            resources = component.content if isinstance(component.content, (tuple, list)) else ()
            self._add_resource_table(layout, resources, f"artifact-table-{component.component_id}")

        def _render_code(self, layout, component: ComponentView, *, action_error: str = "") -> None:
            del action_error
            text = component.content if isinstance(component.content, str) else _display_json(component.content)
            self._add_readonly_text(layout, text, f"code-text-{component.component_id}", 180)

        def _render_json(
            self, layout, component: ComponentView, *, action_error: str = ""
        ) -> None:
            del action_error
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
            if workspace is None or self.simulation_running or self.proposal_running or self.audit_running:
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
            self._update_action_controls()
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
                self._update_action_controls()
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
            self._update_action_controls()
            if self.workspace_view_model is not None:
                self._render_workspace()
            thread.deleteLater()

        def closeEvent(self, event) -> None:
            if self.audit_running:
                self._cancel_workspace_audit()
                QtWidgets.QMessageBox.information(
                    self,
                    "Auditoría en curso",
                    "Se solicitó cancelación. Espera a que terminen los procesos CLI locales antes de cerrar.",
                )
                event.ignore()
                return
            if self.proposal_running:
                self._cancel_workspace_proposal()
                QtWidgets.QMessageBox.information(
                    self,
                    "Propuesta en curso",
                    "Se solicitó cancelación. Espera a que termine el CLI local antes de cerrar esta ventana.",
                )
                event.ignore()
                return
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
