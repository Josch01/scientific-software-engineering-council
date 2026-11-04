"""Optional PySide6 application shell for projects, agents and science workspaces."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

try:
    from .scientific_workspace_view import WorkspaceViewModel
    from .scientific_workspace_qt import QtCore, QtGui, QtWidgets, ScientificWorkspaceWindow
except ImportError:  # Support direct execution from scripts/.
    from scientific_workspace_view import WorkspaceViewModel
    from scientific_workspace_qt import QtCore, QtGui, QtWidgets, ScientificWorkspaceWindow


_WORKSPACE_CATEGORY_COMPONENT_TYPES = {
    "experiments": frozenset({
        "observation_table", "observation_evaluation", "simulation_plot",
    }),
    "code": frozenset({"code_view", "artifact_browser"}),
    "results": frozenset({
        "fit_summary", "sensitivity_plot", "residual_plot", "uncertainty_summary",
    }),
}


def workspace_section_index(view_model: WorkspaceViewModel, category: str) -> int | None:
    """Return the first existing workspace section relevant to a navigation category."""
    if category not in _WORKSPACE_CATEGORY_COMPONENT_TYPES:
        raise ValueError(f"unknown workspace category: {category!r}")
    component_types = _WORKSPACE_CATEGORY_COMPONENT_TYPES[category]
    for index, section in enumerate(view_model.sections):
        if any(component.component_type in component_types for component in section.components):
            return index
    return None


if QtWidgets is None:
    class ControlCenterWindow:  # pragma: no cover - Qt is optional.
        """Unavailable placeholder that keeps importing the optional shell safe."""

        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("PySide6 is required for the SSEC Control Center")

else:
    class ControlCenterWindow(QtWidgets.QMainWindow):
        """One Qt shell around the existing verified workspace and supervisor pages."""

        ROUTES = (
            ("projects", "Proyectos", QtWidgets.QStyle.StandardPixmap.SP_DirOpenIcon),
            ("agents", "Agentes", QtWidgets.QStyle.StandardPixmap.SP_ComputerIcon),
            ("experiments", "Experimentos", QtWidgets.QStyle.StandardPixmap.SP_MediaPlay),
            ("audits", "Auditorías", QtWidgets.QStyle.StandardPixmap.SP_MessageBoxInformation),
            ("code", "Código", QtWidgets.QStyle.StandardPixmap.SP_FileIcon),
            ("results", "Resultados", QtWidgets.QStyle.StandardPixmap.SP_DirIcon),
        )

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("SSEC · Centro de Control Científico")
            self.resize(1440, 920)
            self.setMinimumSize(1080, 700)
            self.current_project_root: Path | None = None
            self.current_manifest_relative_path: str | None = None
            self.current_route = "projects"
            self._build_shell()
            self._apply_style()
            self.navigate("projects")

        def _apply_style(self) -> None:
            self.setStyleSheet(
                "QMainWindow { background: #f2f5f7; color: #1d2d39; }"
                "QLabel { color: #243746; }"
                "QToolBar { background: #16384a; border: 0; spacing: 8px; padding: 8px; }"
                "QToolBar QLabel { color: #ffffff; font-size: 17px; font-weight: 650; }"
                "QListWidget { background: #16384a; color: #f2f5f7; border: 0; padding: 8px; }"
                "QListWidget::item { padding: 11px 10px; border-radius: 4px; }"
                "QListWidget::item:selected { background: #176b87; color: white; font-weight: 600; }"
                "QListWidget::item:focus { border: 2px solid #d68a31; }"
                "QPushButton { background: #176b87; color: white; border: 1px solid #10546b;"
                " border-radius: 4px; padding: 8px 13px; }"
                "QPushButton:hover { background: #125b73; }"
                "QPushButton:disabled { background: #9eafb8; color: #f5f7f8; }"
                "QPushButton:focus, QLineEdit:focus, QPlainTextEdit:focus {"
                " border: 2px solid #d68a31; }"
                "QStatusBar { background: #e6edf1; color: #243746; }"
            )

        def _build_shell(self) -> None:
            toolbar = self.addToolBar("Centro de Control")
            toolbar.setMovable(False)
            title = QtWidgets.QLabel("SSEC · Centro de Control Científico")
            toolbar.addWidget(title)
            toolbar.addSeparator()
            self.active_project_label = QtWidgets.QLabel("Sin proyecto activo")
            self.active_project_label.setObjectName("activeProjectLabel")
            self.active_project_label.setAccessibleName("Proyecto activo")
            toolbar.addWidget(self.active_project_label)

            shell = QtWidgets.QWidget(self)
            shell_layout = QtWidgets.QHBoxLayout(shell)
            shell_layout.setContentsMargins(0, 0, 0, 0)
            shell_layout.setSpacing(0)
            self.navigation = QtWidgets.QListWidget(shell)
            self.navigation.setObjectName("controlCenterNavigation")
            self.navigation.setFixedWidth(220)
            self.navigation.setAccessibleName("Navegación principal del Centro de Control")
            self.navigation.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
            for route, label, standard_icon in self.ROUTES:
                item = QtWidgets.QListWidgetItem(
                    self.style().standardIcon(standard_icon), label
                )
                item.setData(QtCore.Qt.ItemDataRole.UserRole, route)
                item.setToolTip(label)
                self.navigation.addItem(item)
            self.navigation.currentRowChanged.connect(self._on_navigation_row_changed)
            shell_layout.addWidget(self.navigation)

            content = QtWidgets.QWidget(shell)
            content_layout = QtWidgets.QVBoxLayout(content)
            content_layout.setContentsMargins(18, 16, 18, 12)
            content_layout.setSpacing(10)
            self.page_heading = QtWidgets.QLabel("Proyectos")
            self.page_heading.setObjectName("controlCenterPageHeading")
            self.page_heading.setStyleSheet("font-size: 22px; font-weight: 650; color: #16384a;")
            content_layout.addWidget(self.page_heading)
            self.page_stack = QtWidgets.QStackedWidget(content)
            self.page_stack.setObjectName("controlCenterPages")
            content_layout.addWidget(self.page_stack, 1)
            shell_layout.addWidget(content, 1)
            self.setCentralWidget(shell)
            self.statusBar().showMessage("Listo")

            self.project_page = self._build_project_page()
            self.agent_page = self._build_agent_placeholder()
            self.workspace_page = self._build_workspace_page()
            self.audit_page = self._build_audit_page()
            self.pages = {
                "projects": self.project_page,
                "agents": self.agent_page,
                "audits": self.audit_page,
                "experiments": self.workspace_page,
                "code": self.workspace_page,
                "results": self.workspace_page,
            }
            for page in (self.project_page, self.agent_page, self.audit_page, self.workspace_page):
                self.page_stack.addWidget(page)

        def _build_project_page(self):
            page = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(page)
            layout.setContentsMargins(10, 8, 10, 8)
            intro = QtWidgets.QLabel(
                "Abre la carpeta de un proyecto y un manifiesto científico. "
                "El loader verifica contención y SHA-256 antes de mostrar los recursos."
            )
            intro.setObjectName("projectPageIntroduction")
            intro.setWordWrap(True)
            layout.addWidget(intro)
            self.project_details = QtWidgets.QGroupBox("Proyecto activo")
            detail_layout = QtWidgets.QFormLayout(self.project_details)
            self.project_root_value = QtWidgets.QLabel("Sin proyecto activo")
            self.project_root_value.setObjectName("projectRootValue")
            self.project_root_value.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            self.workspace_value = QtWidgets.QLabel("Sin workspace verificado")
            self.workspace_value.setObjectName("projectWorkspaceValue")
            self.workspace_value.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            detail_layout.addRow("Raíz", self.project_root_value)
            detail_layout.addRow("Workspace", self.workspace_value)
            layout.addWidget(self.project_details)
            self.open_project_button = QtWidgets.QPushButton("Abrir proyecto y workspace…")
            self.open_project_button.setObjectName("openProjectButton")
            self.open_project_button.setAccessibleName("Seleccionar proyecto y manifiesto científico")
            self.open_project_button.clicked.connect(self.open_project_dialog)
            layout.addWidget(self.open_project_button, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
            layout.addStretch(1)
            return page

        @staticmethod
        def _build_agent_placeholder():
            page = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(page)
            label = QtWidgets.QLabel("Configuración y progreso de especialistas")
            label.setObjectName("agentSupervisorPlaceholder")
            label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            layout.addWidget(label, 1)
            return page

        def _build_audit_page(self):
            page = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(page)
            intro = QtWidgets.QLabel(
                "Solicita una auditoría de recursos verificados. La selección de recursos y la "
                "confirmación de envío siguen a cargo de la vista científica. La salida no aprueba código ni resultados."
            )
            intro.setWordWrap(True)
            layout.addWidget(intro)
            self.workspace_audit_button = QtWidgets.QPushButton(
                "Solicitar auditoría del workspace…"
            )
            self.workspace_audit_button.setObjectName("openWorkspaceAuditButton")
            self.workspace_audit_button.clicked.connect(
                lambda: self.workspace_window.audit_button.click()
            )
            self.workspace_audit_button.setEnabled(False)
            layout.addWidget(self.workspace_audit_button, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
            self.audit_result_text = QtWidgets.QPlainTextEdit()
            self.audit_result_text.setObjectName("controlCenterAuditResult")
            self.audit_result_text.setReadOnly(True)
            self.audit_result_text.setAccessibleName("Resultado de auditoría, no aprobado")
            self.audit_result_text.setPlainText("Aún no hay resultado de auditoría en esta sesión.")
            layout.addWidget(self.audit_result_text, 1)
            self.workspace_window.auditResultChanged.connect(self._show_audit_result)
            return page

        def _build_workspace_page(self):
            page = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 0, 0)
            self.workspace_content = QtWidgets.QStackedWidget(page)
            self.workspace_content.setObjectName("controlCenterWorkspaceContent")
            self.workspace_window = ScientificWorkspaceWindow()
            self.workspace_window.setParent(page)
            self.workspace_window.setWindowFlag(QtCore.Qt.WindowType.Window, False)
            self.workspace_window.setObjectName("embeddedScientificWorkspace")
            self.workspace_window.open_button.hide()
            self.workspace_empty_label = QtWidgets.QLabel(
                "Abre un proyecto con un workspace científico para ver esta sección."
            )
            self.workspace_empty_label.setObjectName("workspaceCategoryEmptyState")
            self.workspace_empty_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.workspace_empty_label.setWordWrap(True)
            self.workspace_content.addWidget(self.workspace_window)
            self.workspace_content.addWidget(self.workspace_empty_label)
            self.workspace_content.setCurrentWidget(self.workspace_empty_label)
            layout.addWidget(self.workspace_content, 1)
            return page

        def _show_audit_result(self, report: object) -> None:
            if not isinstance(report, dict):
                self.audit_result_text.setPlainText("Resultado inválido · sin aprobación.")
                return
            self.audit_result_text.setPlainText(json.dumps(
                report, ensure_ascii=False, indent=2, allow_nan=False
            ))

        def _on_navigation_row_changed(self, row: int) -> None:
            if row < 0 or row >= self.navigation.count():
                return
            route = self.navigation.item(row).data(QtCore.Qt.ItemDataRole.UserRole)
            self.navigate(str(route))

        def navigate(self, route: str) -> None:
            route_indexes = {
                self.navigation.item(index).data(QtCore.Qt.ItemDataRole.UserRole): index
                for index in range(self.navigation.count())
            }
            if route not in route_indexes:
                raise ValueError(f"unknown control center route: {route!r}")
            row = route_indexes[route]
            if self.navigation.currentRow() != row:
                self.navigation.setCurrentRow(row)
                return
            self.current_route = route
            item = self.navigation.item(row)
            self.page_heading.setText(item.text())
            if route in {"experiments", "code", "results"}:
                self.page_stack.setCurrentWidget(self.workspace_page)
                model = self.workspace_window.workspace_view_model
                index = workspace_section_index(model, route) if model is not None else None
                if index is None:
                    self.workspace_empty_label.setText(
                        f"No hay componentes de {item.text().lower()} en el workspace cargado. "
                        "Abre un workspace que incluya esta sección para continuar."
                    )
                    self.workspace_content.setCurrentWidget(self.workspace_empty_label)
                else:
                    self.workspace_window.tabs.setCurrentIndex(index)
                    self.workspace_content.setCurrentWidget(self.workspace_window)
            else:
                self.page_stack.setCurrentWidget(self.pages[route])

        def open_project_dialog(self) -> None:
            project_root = QtWidgets.QFileDialog.getExistingDirectory(
                self, "Seleccionar raíz del proyecto"
            )
            if not project_root:
                return
            manifest, _filter = QtWidgets.QFileDialog.getOpenFileName(
                self,
                "Seleccionar manifiesto científico",
                project_root,
                "Manifiestos JSON (*.json);;Todos los archivos (*)",
            )
            if not manifest:
                return
            relative = os.path.relpath(manifest, project_root).replace(os.sep, "/")
            try:
                self.load_project(project_root, relative)
            except (OSError, TypeError, ValueError, RecursionError) as exc:
                QtWidgets.QMessageBox.critical(
                    self, "No se pudo abrir el proyecto", str(exc)[:1000]
                )

        def load_project(
            self, project_root: str | os.PathLike[str], manifest_relative_path: str
        ) -> WorkspaceViewModel:
            """Load both resources and shared project context only after verification succeeds."""
            model = self.workspace_window.load_workspace(project_root, manifest_relative_path)
            root = Path(project_root).resolve()
            self.current_project_root = root
            self.current_manifest_relative_path = manifest_relative_path
            self.active_project_label.setText(str(root))
            self.project_root_value.setText(str(root))
            self.workspace_value.setText(
                f"{model.title} · {model.workspace_id} · {model.verification_status}"
            )
            self.workspace_audit_button.setEnabled(True)
            if hasattr(self, "agent_supervisor"):
                self.agent_supervisor.set_project_root(root)
            self.statusBar().showMessage(
                f"Proyecto cargado · {model.verification_status}", 8_000
            )
            return model

