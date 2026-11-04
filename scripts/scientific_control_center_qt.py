"""Optional PySide6 application shell for projects, agents and science workspaces."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import uuid

try:
    from .configuration import (
        AUDIT_LEVELS, DEFAULT_CONFIG, PERMISSIONS, PROVIDERS, config_path,
        load_config, save_config, validate_config,
    )
    from .config_panel import PROGRESS_LOG_LIMIT, build_policy, latest_progress_event
    from .prepare_agents import prepare
    from .run_agents import plan as plan_agent_audit
    from .scientific_workspace_view import WorkspaceViewModel
    from .scientific_workspace_qt import QtCore, QtGui, QtWidgets, ScientificWorkspaceWindow
except ImportError:  # Support direct execution from scripts/.
    from configuration import (
        AUDIT_LEVELS, DEFAULT_CONFIG, PERMISSIONS, PROVIDERS, config_path,
        load_config, save_config, validate_config,
    )
    from config_panel import PROGRESS_LOG_LIMIT, build_policy, latest_progress_event
    from prepare_agents import prepare
    from run_agents import plan as plan_agent_audit
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
    class AgentSupervisorPage(QtWidgets.QWidget):
        """Qt controls over the existing policy, preparation and audit runner contracts."""

        def __init__(self, parent=None, *, confirmation_handler=None):
            super().__init__(parent)
            self.setObjectName("agentSupervisorPage")
            self._confirmation_handler = confirmation_handler
            self.project_root: Path | None = None
            self._process: QtCore.QProcess | None = None
            self._log_path: Path | None = None
            self.current_cancel_file: Path | None = None
            self.cancel_file_was_requested = False
            self.release_status = "NOT_APPROVED"
            self.progress_event: dict | None = None
            self._build_ui()
            self._progress_timer = QtCore.QTimer(self)
            self._progress_timer.setInterval(300)
            self._progress_timer.timeout.connect(self._read_progress_tail)
            self.set_project_root(None)

        @staticmethod
        def _unapproved(message: str) -> str:
            if "NO APROBADA" in message:
                return message
            return f"{message} · NO APROBADA"

        @property
        def process_running(self) -> bool:
            return bool(
                self._process is not None
                and self._process.state() != QtCore.QProcess.ProcessState.NotRunning
            )

        @staticmethod
        def project_context(project_root: str | os.PathLike[str]) -> tuple[Path, dict]:
            candidate = Path(project_root).expanduser()
            if candidate.is_symlink():
                raise ValueError("la raíz del proyecto no puede ser un symlink")
            try:
                root = candidate.resolve(strict=True)
            except OSError as exc:
                raise ValueError("la raíz del proyecto debe existir") from exc
            if not root.is_dir():
                raise ValueError("la raíz del proyecto debe ser un directorio")
            policy_path = config_path(root)
            policy_folder = policy_path.parent
            if policy_folder.is_symlink() or policy_path.is_symlink():
                raise ValueError("la configuración SSEC no puede atravesar symlinks")
            if policy_folder.exists() and not policy_folder.is_dir():
                raise ValueError(".ssec existe, pero no es un directorio")
            policy = load_config(policy_path) if policy_path.exists() else json.loads(
                json.dumps(DEFAULT_CONFIG)
            )
            return root, policy

        def set_project_root(
            self,
            project_root: str | os.PathLike[str] | None,
            *,
            policy: dict | None = None,
        ) -> None:
            if project_root is None:
                root = None
                selected_policy = json.loads(json.dumps(DEFAULT_CONFIG))
            else:
                root, selected_policy = (
                    self.project_context(project_root) if policy is None
                    else (Path(project_root).resolve(strict=True), validate_config(policy))
                )
            if self.process_running and root != self.project_root:
                raise ValueError("espera a que termine la auditoría antes de cambiar de proyecto")
            self.project_root = root
            self._set_policy_controls(selected_policy)
            self.project_label.setText(str(root) if root is not None else "Sin proyecto activo")
            self.status_label.setText(
                self._unapproved("Listo para configurar especialistas · NOT_APPROVED")
                if root is not None else self._unapproved("Selecciona un proyecto · NOT_APPROVED")
            )
            self._update_controls()

        def _build_ui(self) -> None:
            root_layout = QtWidgets.QVBoxLayout(self)
            root_layout.setContentsMargins(0, 0, 0, 0)
            scroll = QtWidgets.QScrollArea(self)
            scroll.setObjectName("agentSupervisorScrollArea")
            scroll.setWidgetResizable(True)
            content = QtWidgets.QWidget(scroll)
            outer = QtWidgets.QVBoxLayout(content)
            outer.setContentsMargins(10, 8, 10, 8)
            outer.setSpacing(10)
            intro = QtWidgets.QLabel(
                "Configura una tarea de auditoría, revisa el plan y supervisa el runner local. "
                "El costo estimado es orientativo; SSEC no lo mide ni limita automáticamente."
            )
            intro.setWordWrap(True)
            outer.addWidget(intro)

            project_group = QtWidgets.QGroupBox("Proyecto activo")
            project_layout = QtWidgets.QVBoxLayout(project_group)
            self.project_label = QtWidgets.QLabel("Sin proyecto activo")
            self.project_label.setObjectName("agentProjectRoot")
            self.project_label.setWordWrap(True)
            self.project_label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            project_layout.addWidget(self.project_label)
            outer.addWidget(project_group)

            policy_group = QtWidgets.QGroupBox("Política de especialistas")
            policy_form = QtWidgets.QFormLayout(policy_group)
            self.provider_combo = QtWidgets.QComboBox()
            self.provider_combo.setObjectName("agentProviderMode")
            self.provider_combo.addItems(PROVIDERS)
            self.permissions_combo = QtWidgets.QComboBox()
            self.permissions_combo.setObjectName("agentPermissions")
            self.permissions_combo.addItems(PERMISSIONS)
            self.audit_combo = QtWidgets.QComboBox()
            self.audit_combo.setObjectName("agentAuditLevel")
            self.audit_combo.addItems(AUDIT_LEVELS)
            self.parallel_spin = QtWidgets.QSpinBox()
            self.parallel_spin.setObjectName("agentParallelLimit")
            self.parallel_spin.setRange(1, 12)
            self.minutes_spin = QtWidgets.QSpinBox()
            self.minutes_spin.setObjectName("agentRuntimeBudget")
            self.minutes_spin.setRange(1, 1440)
            self.cost_spin = QtWidgets.QDoubleSpinBox()
            self.cost_spin.setObjectName("agentEstimatedCost")
            self.cost_spin.setRange(0, 10_000)
            self.cost_spin.setDecimals(2)
            policy_form.addRow("Proveedor", self.provider_combo)
            policy_form.addRow("Permisos solicitados", self.permissions_combo)
            policy_form.addRow("Nivel de auditoría", self.audit_combo)
            policy_form.addRow("Agentes en paralelo (plan)", self.parallel_spin)
            policy_form.addRow("Tiempo orientativo (min)", self.minutes_spin)
            policy_form.addRow("Costo estimado (USD)", self.cost_spin)
            outer.addWidget(policy_group)

            task_group = QtWidgets.QGroupBox("Tarea")
            task_layout = QtWidgets.QHBoxLayout(task_group)
            self.task_path_edit = QtWidgets.QLineEdit()
            self.task_path_edit.setObjectName("agentTaskPath")
            self.task_path_edit.setAccessibleName("Ruta del archivo JSON de tarea")
            self.task_path_edit.setPlaceholderText("Selecciona un archivo JSON de tarea")
            choose_task = QtWidgets.QPushButton("Seleccionar tarea…")
            choose_task.setObjectName("chooseAgentTaskButton")
            choose_task.clicked.connect(self._choose_task)
            task_layout.addWidget(self.task_path_edit, 1)
            task_layout.addWidget(choose_task)
            outer.addWidget(task_group)

            safety = QtWidgets.QLabel(
                "La vista previa y preparación de perfiles no ejecutan modelos. Ejecutar una auditoría "
                "CLI puede consumir cuota; la confirmación explica que el costo real no se puede medir. "
                "La salida del proceso no significa revisión independiente, aprobación de cambios ni validez científica."
            )
            safety.setObjectName("agentSafetyNotice")
            safety.setWordWrap(True)
            outer.addWidget(safety)

            buttons = QtWidgets.QHBoxLayout()
            self.preview_button = QtWidgets.QPushButton("Previsualizar plan")
            self.preview_button.setObjectName("previewAgentPlanButton")
            self.preview_button.clicked.connect(self.preview_plan)
            self.save_policy_button = QtWidgets.QPushButton("Guardar política…")
            self.save_policy_button.setObjectName("saveAgentPolicyButton")
            self.save_policy_button.clicked.connect(self.save_policy)
            self.prepare_button = QtWidgets.QPushButton("Preparar perfiles…")
            self.prepare_button.setObjectName("prepareAgentProfilesButton")
            self.prepare_button.clicked.connect(self.prepare_profiles)
            self.run_button = QtWidgets.QPushButton("Ejecutar auditoría…")
            self.run_button.setObjectName("startAgentAuditButton")
            self.run_button.clicked.connect(self.start_audit)
            self.cancel_button = QtWidgets.QPushButton("Solicitar cancelación…")
            self.cancel_button.setObjectName("cancelAgentAuditButton")
            self.cancel_button.clicked.connect(self.cancel_audit)
            for button in (
                self.preview_button, self.save_policy_button, self.prepare_button,
                self.run_button, self.cancel_button,
            ):
                buttons.addWidget(button)
            outer.addLayout(buttons)

            self.status_label = QtWidgets.QLabel("Selecciona un proyecto · NOT_APPROVED")
            self.status_label.setObjectName("agentSupervisorStatus")
            self.status_label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            self.status_label.setWordWrap(True)
            outer.addWidget(self.status_label)
            self.progress_bar = QtWidgets.QProgressBar()
            self.progress_bar.setObjectName("agentSupervisorProgress")
            self.progress_bar.setRange(0, 1)
            outer.addWidget(self.progress_bar)
            self.progress_table = QtWidgets.QTableWidget(0, 3)
            self.progress_table.setObjectName("agentSupervisorRoles")
            self.progress_table.setHorizontalHeaderLabels(("Especialista", "Proveedor", "Estado"))
            self.progress_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            self.progress_table.setAlternatingRowColors(True)
            self.progress_table.horizontalHeader().setSectionResizeMode(
                QtWidgets.QHeaderView.ResizeMode.Stretch
            )
            outer.addWidget(self.progress_table)
            self.log_view = QtWidgets.QPlainTextEdit()
            self.log_view.setObjectName("agentSupervisorLog")
            self.log_view.setReadOnly(True)
            self.log_view.setMaximumBlockCount(2000)
            self.log_view.setAccessibleName("Plan y log acotado de la auditoría de agentes")
            outer.addWidget(self.log_view, 1)
            scroll.setWidget(content)
            root_layout.addWidget(scroll, 1)

        def _set_policy_controls(self, policy: dict) -> None:
            self.provider_combo.setCurrentText(policy["provider_mode"])
            self.permissions_combo.setCurrentText(policy["permissions"])
            self.audit_combo.setCurrentText(policy["audit_level"])
            self.parallel_spin.setValue(policy["max_parallel_agents"])
            self.minutes_spin.setValue(policy["budget"]["max_runtime_minutes"])
            self.cost_spin.setValue(float(policy["budget"]["max_estimated_cost_usd"]))

        def _policy_from_controls(self) -> dict:
            return build_policy(
                self.provider_combo.currentText(),
                str(self.parallel_spin.value()),
                self.permissions_combo.currentText(),
                str(self.minutes_spin.value()),
                self.cost_spin.value(),
                self.audit_combo.currentText(),
            )

        def _read_task(self) -> tuple[Path, dict]:
            raw_path = self.task_path_edit.text().strip()
            if not raw_path:
                raise ValueError("selecciona un archivo JSON de tarea")
            task_path = Path(raw_path).expanduser()
            task = json.loads(task_path.read_text(encoding="utf-8"))
            if not isinstance(task, dict):
                raise ValueError("el archivo de tarea debe contener un objeto JSON")
            return task_path.resolve(strict=True), task

        def _inputs(self) -> tuple[Path, Path, dict, dict]:
            if self.project_root is None:
                raise ValueError("abre un proyecto antes de configurar especialistas")
            task_path, task = self._read_task()
            policy = self._policy_from_controls()
            return self.project_root, task_path, task, policy

        def _confirm(self, title: str, message: str) -> bool:
            if self._confirmation_handler is not None:
                return bool(self._confirmation_handler(title, message))
            answer = QtWidgets.QMessageBox.question(
                self, title, message,
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            return answer == QtWidgets.QMessageBox.StandardButton.Yes

        def _show_error(self, title: str, message: object) -> None:
            rendered = f"{title}: {message}"
            self.status_label.setText(self._unapproved(f"{rendered} · NOT_APPROVED"))
            self.log_view.setPlainText(rendered[:PROGRESS_LOG_LIMIT])

        @staticmethod
        def _json_text(value: object) -> str:
            return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)

        def preview_plan(self) -> dict | None:
            try:
                project, _task_path, task, policy = self._inputs()
                result = prepare(task, policy["provider_mode"], project, apply=False, config=policy)
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, RecursionError) as exc:
                self._show_error("No se pudo previsualizar", exc)
                return None
            self.log_view.setPlainText(self._json_text(result)[:PROGRESS_LOG_LIMIT])
            self.status_label.setText(
                self._unapproved(
                    f"Plan preparado · {result['agent_count']} perfiles · sin ejecución · NOT_APPROVED"
                )
            )
            return result

        def save_policy(self) -> Path | None:
            if self.project_root is None:
                self._show_error("No se pudo guardar", "abre un proyecto primero")
                return None
            policy = self._policy_from_controls()
            target = config_path(self.project_root)
            if not self._confirm(
                "Guardar política de especialistas",
                f"Se creará o actualizará la política local en {target}. "
                "La operación escribe esta configuración y no inicia modelos. ¿Continuar?",
            ):
                self.status_label.setText(
                    self._unapproved("Guardado de política cancelado · NOT_APPROVED")
                )
                return None
            try:
                saved = save_config(self.project_root, policy)
            except (OSError, ValueError, TypeError) as exc:
                self._show_error("No se pudo guardar", exc)
                return None
            self.status_label.setText(
                self._unapproved(f"Política guardada en {saved} · NOT_APPROVED")
            )
            return saved

        def prepare_profiles(self) -> dict | None:
            try:
                project, _task_path, task, policy = self._inputs()
                preview = prepare(task, policy["provider_mode"], project, apply=False, config=policy)
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, RecursionError) as exc:
                self._show_error("No se pudo preparar", exc)
                return None
            if not self._confirm(
                "Preparar perfiles SSEC",
                f"Se escribirán {preview['agent_count']} perfiles y paquetes en {project}. "
                "No se ejecutarán modelos. ¿Continuar?",
            ):
                self.status_label.setText("Preparación cancelada · NOT_APPROVED")
                return None
            try:
                result = prepare(task, policy["provider_mode"], project, apply=True, config=policy)
            except (OSError, ValueError, TypeError, KeyError, FileExistsError) as exc:
                self._show_error("No se pudo preparar", exc)
                return None
            self.log_view.setPlainText(self._json_text(result)[:PROGRESS_LOG_LIMIT])
            self.status_label.setText(
                self._unapproved(
                    f"Perfiles preparados · {result['agent_count']} · no se ejecutaron modelos · NOT_APPROVED"
                )
            )
            return result

        def _run_paths(self, project: Path) -> tuple[Path, Path]:
            ssec_folder = project / ".ssec"
            run_folder = ssec_folder / "gui_runs"
            for folder in (ssec_folder, run_folder):
                if folder.is_symlink():
                    raise ValueError("el directorio de logs no puede atravesar symlinks")
                if folder.exists() and not folder.is_dir():
                    raise ValueError("el directorio de logs debe ser una carpeta")
            run_folder.mkdir(parents=True, exist_ok=True)
            token = uuid.uuid4().hex[:12]
            log_path = run_folder / f"{token}.log"
            cancel_path = run_folder / f"{token}.cancel"
            if log_path.exists() or cancel_path.exists():
                raise FileExistsError("colisión al crear los archivos de auditoría")
            return log_path, cancel_path

        def _runner_command(
            self,
            task_path: Path,
            project: Path,
            policy_path: Path,
            cancel_path: Path,
        ) -> tuple[str, list[str]]:
            runner = Path(__file__).resolve().parent / "run_agents.py"
            arguments = [
                str(runner), str(task_path), "--project", str(project), "--config", str(policy_path),
                "--execute", "--accept-unmetered-cost", "--cancel-file", str(cancel_path),
                "--emit-progress-jsonl",
            ]
            return sys.executable, arguments

        def start_audit(self) -> bool:
            if self.process_running:
                return False
            try:
                project, task_path, task, policy = self._inputs()
                if task.get("kind") != "audit":
                    raise ValueError("el runner disponible admite solo tareas kind=audit")
                plan_agent_audit(task, policy)
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, RecursionError) as exc:
                self._show_error("Auditoría no iniciada", exc)
                return False
            if not self._confirm(
                "Ejecución real con costo no medido",
                f"Antes de iniciar se guardará la política local en {config_path(project)}. "
                "Después se iniciarán CLIs locales en copias temporales del proyecto. Esta acción puede "
                "consumir cuota y el costo en USD NO puede limitarse automáticamente. Los resultados "
                "no se integrarán ni aprobarán automáticamente. ¿Confirmas la ejecución?",
            ):
                self.status_label.setText(self._unapproved("Ejecución cancelada · NOT_APPROVED"))
                return False
            try:
                policy_file = save_config(project, policy)
                log_path, cancel_path = self._run_paths(project)
                program, arguments = self._runner_command(task_path, project, policy_file, cancel_path)
                process = self._process
                if process is None:
                    process = QtCore.QProcess(self)
                    process.started.connect(self._on_process_started)
                    process.errorOccurred.connect(
                        lambda error, proc=process: self._on_process_error(proc, error)
                    )
                    process.finished.connect(
                        lambda code, status, proc=process: self._on_process_finished(
                            proc, code, status
                        )
                    )
                    self._process = process
                process.setWorkingDirectory(str(project))
                process.setProcessChannelMode(QtCore.QProcess.ProcessChannelMode.MergedChannels)
                process.setStandardOutputFile(str(log_path))
                self._log_path = log_path
                self.current_cancel_file = cancel_path
                self.cancel_file_was_requested = False
                self.progress_event = None
                self.release_status = "NOT_APPROVED"
                self.progress_bar.setRange(0, 1)
                self.progress_bar.setValue(0)
                self.progress_table.setRowCount(0)
                self.log_view.clear()
                self.status_label.setText(
                    self._unapproved("Iniciando auditoría local · NOT_APPROVED")
                )
                self._update_controls()
                self._progress_timer.start()
                process.start(program, arguments)
                return True
            except (OSError, ValueError, TypeError) as exc:
                self._progress_timer.stop()
                self._update_controls()
                self._show_error("Auditoría no iniciada", exc)
                return False

        def cancel_audit(self) -> bool:
            if not self.process_running or self.current_cancel_file is None:
                return False
            if not self._confirm(
                "Solicitar cancelación",
                "Se escribirá la señal de cancelación para el runner. El proceso puede tardar "
                "en terminar; su salida seguirá como NOT_APPROVED. ¿Continuar?",
            ):
                return False
            try:
                if self.current_cancel_file.is_symlink():
                    raise ValueError("el archivo de cancelación no puede ser un symlink")
                self.current_cancel_file.write_text("cancel\n", encoding="utf-8")
            except (OSError, ValueError) as exc:
                self._show_error("No se pudo solicitar cancelación", exc)
                return False
            self.cancel_file_was_requested = True
            self.status_label.setText(self._unapproved(
                "Cancelación solicitada · el proceso sigue sin aprobar · NOT_APPROVED"
            ))
            self._update_controls()
            return True

        def _read_progress_tail(self) -> None:
            log_path = self._log_path
            if log_path is None:
                return
            try:
                with log_path.open("rb") as handle:
                    handle.seek(0, os.SEEK_END)
                    size = handle.tell()
                    handle.seek(max(0, size - PROGRESS_LOG_LIMIT * 4), os.SEEK_SET)
                    tail = handle.read(PROGRESS_LOG_LIMIT * 4).decode("utf-8", errors="replace")
            except OSError:
                return
            tail = tail[-PROGRESS_LOG_LIMIT:]
            self.log_view.setPlainText(tail)
            event = latest_progress_event(tail)
            if event is None:
                return
            self.progress_event = event
            self.progress_bar.setRange(0, event["total"])
            self.progress_bar.setValue(event["completed"])
            rows = event["roles"]
            self.progress_table.setRowCount(len(rows))
            for row_index, row in enumerate(rows):
                for column, key in enumerate(("role", "provider", "status")):
                    self.progress_table.setItem(
                        row_index, column, QtWidgets.QTableWidgetItem(str(row[key]))
                    )
            self.status_label.setText(
                self._unapproved(
                    f"{event['completed']} / {event['total']} procesos · "
                    f"{event['execution']} · NOT_APPROVED"
                )
            )

        def _on_process_started(self) -> None:
            self.status_label.setText(
                self._unapproved("CLI de auditoría en ejecución · NOT_APPROVED")
            )
            self._update_controls()

        def _on_process_error(self, process, error) -> None:
            if process is not self._process:
                return
            if error != QtCore.QProcess.ProcessError.FailedToStart:
                return
            self._progress_timer.stop()
            message = process.errorString()[:1000]
            self.status_label.setText(
                self._unapproved(f"LAUNCH_FAILED · {message} · NOT_APPROVED")
            )
            self._update_controls()

        def _on_process_finished(self, process, exit_code: int, exit_status) -> None:
            if process is not self._process:
                return
            self._progress_timer.stop()
            self._read_progress_tail()
            event = self.progress_event or {}
            execution = str(event.get("execution", "UNKNOWN"))
            if exit_status == QtCore.QProcess.ExitStatus.CrashExit or exit_code != 0:
                message = f"CLI_FAILED · exit={exit_code} · {execution}"
            elif self.cancel_file_was_requested:
                message = f"Cancelación solicitada · {execution} · NOT_APPROVED"
            elif execution == "PROCESSES_COMPLETED_NOT_AUDITED":
                message = f"{execution} · salida no auditada · NOT_APPROVED"
            else:
                message = f"EXIT_ZERO_UNREVIEWED · {execution} · NOT_APPROVED"
            self.release_status = "NOT_APPROVED"
            self.status_label.setText(self._unapproved(message))
            self._update_controls()

        def _choose_task(self) -> None:
            initial = str(self.project_root or Path.cwd())
            path, _filter = QtWidgets.QFileDialog.getOpenFileName(
                self, "Seleccionar tarea de auditoría", initial, "Tareas JSON (*.json);;Todos los archivos (*)"
            )
            if path:
                self.task_path_edit.setText(path)

        def _update_controls(self) -> None:
            has_project = self.project_root is not None
            busy = self.process_running
            for widget in (
                self.provider_combo, self.permissions_combo, self.audit_combo, self.parallel_spin,
                self.minutes_spin, self.cost_spin, self.task_path_edit, self.preview_button,
                self.save_policy_button, self.prepare_button, self.run_button,
            ):
                widget.setEnabled(has_project and not busy)
            self.cancel_button.setEnabled(busy and not self.cancel_file_was_requested)


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
            self.agent_page = self._build_agent_page()
            self.agent_supervisor = self.agent_page
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

        def _build_agent_page(self):
            return AgentSupervisorPage(self)

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
            root, policy = self.agent_supervisor.project_context(project_root)
            if self.agent_supervisor.process_running and root != self.agent_supervisor.project_root:
                raise ValueError("espera a que termine la auditoría antes de cambiar de proyecto")
            model = self.workspace_window.load_workspace(project_root, manifest_relative_path)
            self.current_project_root = root
            self.current_manifest_relative_path = manifest_relative_path
            self.active_project_label.setText(str(root))
            self.project_root_value.setText(str(root))
            self.workspace_value.setText(
                f"{model.title} · {model.workspace_id} · {model.verification_status}"
            )
            self.workspace_audit_button.setEnabled(True)
            self.agent_supervisor.set_project_root(root, policy=policy)
            self.statusBar().showMessage(
                f"Proyecto cargado · {model.verification_status}", 8_000
            )
            return model


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Centro de Control Científico SSEC")
    parser.add_argument("--project-root", type=Path, help="raíz del proyecto que se abrirá")
    parser.add_argument(
        "--manifest", default="workspace.json",
        help="manifiesto bajo la raíz del proyecto (por defecto: workspace.json)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    if QtWidgets is None:
        raise RuntimeError("PySide6 es necesario para abrir el Centro de Control SSEC")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
    window = ControlCenterWindow()
    if args.project_root is not None:
        window.load_project(args.project_root, args.manifest)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

