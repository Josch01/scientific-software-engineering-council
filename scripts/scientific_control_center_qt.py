"""Optional PySide6 application shell for projects, agents and science workspaces."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time
import uuid

try:
    from .scientific_ui_theme import motion_enabled, qt_stylesheet
except ImportError:  # Support direct execution from scripts/.
    from scientific_ui_theme import motion_enabled, qt_stylesheet

try:
    from .configuration import (
        AUDIT_LEVELS, DEFAULT_CONFIG, PERMISSIONS, PROVIDERS, config_path,
        load_config, save_config, validate_config,
    )
    from .config_panel import PROGRESS_LOG_LIMIT, build_policy, latest_progress_event
    from .prepare_agents import prepare
    from .run_agents import plan as plan_agent_audit
    from .build_sir_analysis_demo import build_analysis_workspace
    from .scientific_workspace_loader import load_scientific_workspace
    from .scientific_workspace_view import WorkspaceViewModel, build_workspace_view_model
    from .scientific_run_history import list_sir_analysis_runs, read_sir_analysis_run
    from .scientific_workspace_qt import QtCore, QtGui, QtWidgets, ScientificWorkspaceWindow
    from .thesis_sir_qt import ThesisSIRPage
except ImportError:  # Support direct execution from scripts/.
    from configuration import (
        AUDIT_LEVELS, DEFAULT_CONFIG, PERMISSIONS, PROVIDERS, config_path,
        load_config, save_config, validate_config,
    )
    from config_panel import PROGRESS_LOG_LIMIT, build_policy, latest_progress_event
    from prepare_agents import prepare
    from run_agents import plan as plan_agent_audit
    from build_sir_analysis_demo import build_analysis_workspace
    from scientific_workspace_loader import load_scientific_workspace
    from scientific_workspace_view import WorkspaceViewModel, build_workspace_view_model
    from scientific_run_history import list_sir_analysis_runs, read_sir_analysis_run
    from scientific_workspace_qt import QtCore, QtGui, QtWidgets, ScientificWorkspaceWindow
    from thesis_sir_qt import ThesisSIRPage


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


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _write_analysis_run_log(
    project_root: Path, run_id: str, payload: dict[str, object]
) -> str:
    """Create a small run record beneath the project without following links."""
    root = Path(project_root).resolve(strict=True)
    relative_parent = Path("generated") / "sir-analysis-runs"
    parent = root
    for part in relative_parent.parts:
        parent = parent / part
        try:
            info = parent.lstat()
        except FileNotFoundError:
            try:
                parent.mkdir(exist_ok=True)
            except FileExistsError:
                # A sibling process may have created a non-directory entry; validate it below.
                pass
            info = parent.lstat()
        if (stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise ValueError("analysis log path cannot traverse symlinks or reparse points")
        if not parent.is_dir():
            raise ValueError("analysis log parent must be a directory")
    target = parent / f"run-{run_id}.json"
    content = (json.dumps(
        payload, ensure_ascii=True, allow_nan=False, sort_keys=True,
        separators=(",", ":"),
    ) + "\n").encode("utf-8")
    with target.open("xb") as stream:
        stream.write(content)
    return target.relative_to(root).as_posix()


if QtWidgets is None:
    class ControlCenterWindow:  # pragma: no cover - Qt is optional.
        """Unavailable placeholder that keeps importing the optional shell safe."""

        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("PySide6 is required for the SSEC Control Center")

else:
    class _SirAnalysisThread(QtCore.QThread):
        progress_changed = QtCore.Signal(str)
        succeeded = QtCore.Signal(object)
        failed = QtCore.Signal(str)

        def __init__(
            self, project_root: Path, manifest_relative_path: str, output_dir: Path,
            run_id: str, expected_source_manifest_sha256: str, parent=None,
        ):
            super().__init__(parent)
            self.project_root = project_root
            self.manifest_relative_path = manifest_relative_path
            self.output_dir = output_dir
            self.run_id = run_id
            self.expected_source_manifest_sha256 = expected_source_manifest_sha256

        def run(self) -> None:
            started = time.perf_counter()
            started_at = _utc_timestamp()
            base_record: dict[str, object] = {
                "schema_version": 1,
                "run_id": self.run_id,
                "started_at_utc": started_at,
                "source_workspace_manifest": self.manifest_relative_path,
                "source_workspace_manifest_sha256": self.expected_source_manifest_sha256,
                "output_directory": self.output_dir.relative_to(self.project_root).as_posix(),
            }
            self.progress_changed.emit(
                "Verificando entradas y calculando con el motor científico P3.20…"
            )
            workspace_path: str | None = None
            result_manifest_sha256: str | None = None
            try:
                result = build_analysis_workspace(
                    self.project_root,
                    self.manifest_relative_path,
                    self.output_dir,
                    expected_source_manifest_sha256=self.expected_source_manifest_sha256,
                )
                workspace_path = result.get("workspace_path")
                if not isinstance(workspace_path, str):
                    raise ValueError("analysis builder returned no workspace manifest path")
                self.progress_changed.emit("Verificando el workspace y los resultados generados…")
                loaded = load_scientific_workspace(self.project_root, workspace_path)
                if loaded.summary.to_dict().get("status") != "VALID":
                    raise ValueError("generated workspace did not validate")
                build_workspace_view_model(loaded)
                result_manifest_sha256 = hashlib.sha256(loaded.manifest_bytes).hexdigest()
                finished_at = _utc_timestamp()
                run_log = {
                    **base_record,
                    "status": "SUCCEEDED",
                    "finished_at_utc": finished_at,
                    "duration_seconds": round(time.perf_counter() - started, 6),
                    "result_workspace_manifest": workspace_path,
                    "result_workspace_manifest_sha256": result_manifest_sha256,
                    "analysis_execution": result.get("analysis_execution"),
                    "scientific_validity": "NOT_ASSESSED",
                    "identifiability": "NOT_ASSESSED",
                    "uncertainty": "NOT_CALCULATED",
                    "real_user_sir": "NOT_RUN",
                }
                log_path = _write_analysis_run_log(self.project_root, self.run_id, run_log)
                result["run_id"] = self.run_id
                result["run_log_path"] = log_path
                result["result_workspace_manifest_sha256"] = result_manifest_sha256
                self.succeeded.emit(result)
            except Exception as exc:
                finished_at = _utc_timestamp()
                message = f"{type(exc).__name__}: {str(exc)[:1000]}"
                run_log = {
                    **base_record,
                    "status": "FAILED",
                    "finished_at_utc": finished_at,
                    "duration_seconds": round(time.perf_counter() - started, 6),
                    "error": message,
                    "result_workspace_manifest": workspace_path,
                    "result_workspace_manifest_sha256": result_manifest_sha256,
                    "scientific_validity": "NOT_ASSESSED",
                    "identifiability": "NOT_ASSESSED",
                    "uncertainty": "NOT_CALCULATED",
                    "real_user_sir": "NOT_RUN",
                }
                try:
                    log_path = _write_analysis_run_log(self.project_root, self.run_id, run_log)
                    message = f"{message} · bitácora: {log_path}"
                except Exception as log_exc:
                    message = f"{message} · no se pudo conservar la bitácora: {log_exc}"
                self.failed.emit(message)


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
            ("projects", "Proyectos"),
            ("thesis-sir", "SIR de tesis"),
            ("agents", "Agentes"),
            ("experiments", "Experimentos"),
            ("audits", "Auditorías"),
            ("code", "Código"),
            ("results", "Resultados"),
        )

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("SSEC · Centro de Control Científico")
            self.resize(1440, 920)
            self.setMinimumSize(1080, 700)
            self.current_project_root: Path | None = None
            self.current_manifest_relative_path: str | None = None
            self.current_route = "projects"
            self._sir_analysis_thread: _SirAnalysisThread | None = None
            self._page_transition_animation = None
            self._loading_sir_analysis_result = False
            self._build_shell()
            self._apply_style()
            self.navigate("projects")

        def _apply_style(self) -> None:
            self.setStyleSheet(qt_stylesheet())

        def _build_shell(self) -> None:
            toolbar = self.addToolBar("Centro de Control")
            toolbar.setMovable(False)
            toolbar.setObjectName("controlCenterToolbar")
            title = QtWidgets.QLabel("SSEC · Centro de Control Científico")
            title.setObjectName("controlCenterBrand")
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
            self.navigation.setFixedWidth(232)
            self.navigation.setUniformItemSizes(True)
            self.navigation.setAccessibleName("Navegación principal del Centro de Control")
            self.navigation.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
            for route, label in self.ROUTES:
                item = QtWidgets.QListWidgetItem(label)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, route)
                item.setToolTip(label)
                self.navigation.addItem(item)
            self.navigation.currentRowChanged.connect(self._on_navigation_row_changed)
            shell_layout.addWidget(self.navigation)

            content = QtWidgets.QWidget(shell)
            content_layout = QtWidgets.QVBoxLayout(content)
            content_layout.setContentsMargins(24, 20, 24, 16)
            content_layout.setSpacing(13)
            self.page_heading = QtWidgets.QLabel("Proyectos")
            self.page_heading.setObjectName("controlCenterPageHeading")
            content_layout.addWidget(self.page_heading)
            self.page_stack = QtWidgets.QStackedWidget(content)
            self.page_stack.setObjectName("controlCenterPages")
            content_layout.addWidget(self.page_stack, 1)
            shell_layout.addWidget(content, 1)
            self.setCentralWidget(shell)
            self.statusBar().showMessage("Listo")

            self.project_page = self._build_project_page()
            self.thesis_sir_page = ThesisSIRPage(self)
            self.thesis_sir_page.audit_workspace_ready.connect(
                self._open_thesis_sir_audit_workspace
            )
            self.thesis_sir_page.analysis_workspace_ready.connect(
                self._open_thesis_sir_analysis_workspace
            )
            self.thesis_sir_page.activity_finished.connect(
                self._update_sir_analysis_controls
            )
            self.agent_page = self._build_agent_page()
            self.agent_supervisor = self.agent_page
            self.workspace_page = self._build_workspace_page()
            self.audit_page = self._build_audit_page()
            self.pages = {
                "projects": self.project_page,
                "thesis-sir": self.thesis_sir_page,
                "agents": self.agent_page,
                "audits": self.audit_page,
                "experiments": self.workspace_page,
                "code": self.workspace_page,
                "results": self.workspace_page,
            }
            for page in (
                self.project_page,
                self.thesis_sir_page,
                self.agent_page,
                self.audit_page,
                self.workspace_page,
            ):
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
            analysis_group = QtWidgets.QGroupBox("Análisis científico declarativo")
            analysis_layout = QtWidgets.QVBoxLayout(analysis_group)
            analysis_actions = QtWidgets.QHBoxLayout()
            self.sir_analysis_button = QtWidgets.QPushButton("Ejecutar análisis…")
            self.sir_analysis_button.setObjectName("runSirAnalysisButton")
            self.sir_analysis_button.setAccessibleName(
                "Confirmar y ejecutar el análisis SIR con el motor científico de SSEC"
            )
            self.sir_analysis_button.setToolTip(
                "Ejecuta simulación, ajuste, sensibilidad y residuales a partir de recursos verificados"
            )
            self.sir_analysis_button.clicked.connect(self.start_sir_analysis)
            analysis_actions.addWidget(self.sir_analysis_button)
            self.sir_analysis_history_button = QtWidgets.QPushButton("Historial…")
            self.sir_analysis_history_button.setObjectName("sirAnalysisHistoryButton")
            self.sir_analysis_history_button.setAccessibleName(
                "Abrir historial de análisis SIR"
            )
            self.sir_analysis_history_button.setToolTip(
                "Consultar y reabrir resultados guardados tras verificar sus digests"
            )
            self.sir_analysis_history_button.clicked.connect(
                self.show_sir_analysis_history
            )
            analysis_actions.addWidget(self.sir_analysis_history_button)
            self.sir_analysis_status = QtWidgets.QLabel(
                "Carga modelo, observaciones y configuración de análisis para habilitar esta acción."
            )
            self.sir_analysis_status.setObjectName("sirAnalysisStatus")
            self.sir_analysis_status.setAccessibleName("Estado de ejecución del análisis SIR")
            self.sir_analysis_status.setWordWrap(True)
            self.sir_analysis_status.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            analysis_actions.addWidget(self.sir_analysis_status, 1)
            analysis_layout.addLayout(analysis_actions)
            self.sir_analysis_progress = QtWidgets.QProgressBar()
            self.sir_analysis_progress.setObjectName("sirAnalysisProgress")
            self.sir_analysis_progress.setAccessibleName("Progreso indeterminado del análisis SIR")
            self.sir_analysis_progress.setRange(0, 0)
            self.sir_analysis_progress.setTextVisible(False)
            self.sir_analysis_progress.hide()
            analysis_layout.addWidget(self.sir_analysis_progress)
            layout.addWidget(analysis_group)
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

        @property
        def analysis_running(self) -> bool:
            thesis_busy = getattr(self, "thesis_sir_page", None)
            return (self._sir_analysis_thread is not None
                    or (thesis_busy is not None and thesis_busy.run_in_progress))

        def _sir_analysis_resources(self):
            loaded = self.workspace_window._loaded_workspace
            if loaded is None:
                return None
            resources = {resource.resource_id: resource for resource in loaded.resources}
            required = {
                "model": "model_spec",
                "observations": "observations",
                "analysis-config": "generic",
            }
            if any(resources.get(name) is None or resources[name].kind != kind
                   for name, kind in required.items()):
                return None
            return loaded, resources

        def _update_sir_analysis_controls(self) -> None:
            inputs = self._sir_analysis_resources()
            busy = self.analysis_running
            self.sir_analysis_button.setEnabled(inputs is not None and not busy)
            self.sir_analysis_history_button.setEnabled(
                self.current_project_root is not None and not busy
            )
            self.open_project_button.setEnabled(not busy)
            self.workspace_audit_button.setEnabled(self.current_project_root is not None and not busy)
            if not busy and inputs is None:
                self.sir_analysis_status.setText(
                    "Para ejecutar, el workspace debe declarar recursos model_spec, observations y configuración generic."
                )

        def _create_sir_analysis_history_dialog(self, records):
            dialog = QtWidgets.QDialog(self)
            dialog.setObjectName("sirAnalysisHistoryDialog")
            dialog.setWindowTitle("Historial de análisis SIR")
            dialog.setMinimumSize(760, 380)
            layout = QtWidgets.QVBoxLayout(dialog)
            description = QtWidgets.QLabel(
                "Se muestran hasta 100 corridas recientes. No se recalculan; solo se "
                "abren resultados exitosos cuyo manifiesto y recursos vuelven a validar."
            )
            description.setWordWrap(True)
            layout.addWidget(description)
            integrity_notice = QtWidgets.QLabel(
                "Historial local sin firma. SHA-256 detecta cambios frente al digest "
                "guardado, pero no autentica quién produjo la corrida."
            )
            integrity_notice.setObjectName("sirAnalysisHistoryIntegrityNotice")
            integrity_notice.setProperty("state", "warning")
            integrity_notice.setAccessibleName(
                "Límite de autenticidad del historial local"
            )
            integrity_notice.setWordWrap(True)
            layout.addWidget(integrity_notice)
            table = QtWidgets.QTableWidget(len(records), 4, dialog)
            table.setObjectName("sirAnalysisHistoryTable")
            table.setAccessibleName("Corridas guardadas de análisis SIR")
            table.setHorizontalHeaderLabels(
                ["Fecha UTC", "Estado", "ID de corrida", "Resultado / detalle"]
            )
            table.setSelectionBehavior(
                QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
            )
            table.setSelectionMode(
                QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
            )
            table.setEditTriggers(
                QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
            )
            table.horizontalHeader().setStretchLastSection(True)
            table.horizontalHeader().setSectionResizeMode(
                0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
            table.horizontalHeader().setSectionResizeMode(
                1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
            table.horizontalHeader().setSectionResizeMode(
                2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
            for row, record in enumerate(records):
                detail = (
                    record.result_workspace_manifest
                    if record.can_open
                    else (record.issue or "Sin resultado verificable")
                )
                values = (record.started_at_utc, record.status, record.run_id, detail)
                for column, value in enumerate(values):
                    item = QtWidgets.QTableWidgetItem(value)
                    item.setData(QtCore.Qt.ItemDataRole.UserRole, record.run_id)
                    table.setItem(row, column, item)
            empty = QtWidgets.QLabel("No hay corridas guardadas en este proyecto.")
            empty.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            empty.setVisible(not records)
            table.setVisible(bool(records))
            layout.addWidget(empty)
            layout.addWidget(table, 1)

            buttons = QtWidgets.QHBoxLayout()
            buttons.addStretch(1)
            open_button = QtWidgets.QPushButton("Abrir resultado histórico")
            open_button.setObjectName("openHistoricalSirAnalysisButton")
            open_button.setEnabled(False)
            close_button = QtWidgets.QPushButton("Cerrar")
            buttons.addWidget(open_button)
            buttons.addWidget(close_button)
            layout.addLayout(buttons)

            def selected_record():
                row = table.currentRow()
                if row < 0 or row >= len(records):
                    return None
                return records[row]

            def update_open_button():
                record = selected_record()
                open_button.setEnabled(record is not None and record.can_open)

            def accept_openable_row(row, _column):
                if 0 <= row < len(records) and records[row].can_open:
                    dialog.accept()

            table.itemSelectionChanged.connect(update_open_button)
            table.cellDoubleClicked.connect(accept_openable_row)
            open_button.clicked.connect(dialog.accept)
            close_button.clicked.connect(dialog.reject)
            dialog.history_table = table
            dialog.history_records = records
            dialog.history_open_button = open_button
            return dialog

        def show_sir_analysis_history(self) -> None:
            if self.current_project_root is None:
                return
            try:
                records = list_sir_analysis_runs(self.current_project_root)
            except (OSError, TypeError, ValueError, RecursionError) as exc:
                self.sir_analysis_status.setText(
                    f"No se pudo leer el historial · {str(exc)[:500]}"
                )
                return
            dialog = self._create_sir_analysis_history_dialog(records)
            if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
                return
            row = dialog.history_table.currentRow()
            if 0 <= row < len(dialog.history_records):
                record = dialog.history_records[row]
                if record.can_open:
                    self.open_sir_analysis_history_run(record.run_id)

        def open_sir_analysis_history_run(self, run_id: str) -> bool:
            if self.current_project_root is None or self.analysis_running:
                return False
            try:
                record = read_sir_analysis_run(self.current_project_root, run_id)
                self.load_project(
                    self.current_project_root,
                    record.result_workspace_manifest,
                    expected_manifest_sha256=record.result_workspace_manifest_sha256,
                )
                self.navigate("results")
                self.sir_analysis_status.setText(
                    f"Histórico abierto · {record.started_at_utc} · corrida {record.run_id} · "
                    "incertidumbre NOT_CALCULATED · validez NOT_ASSESSED · SIR particular NOT_RUN."
                )
                return True
            except (OSError, TypeError, ValueError, RecursionError) as exc:
                self.sir_analysis_status.setText(
                    f"No se abrió el resultado histórico · {str(exc)[:700]}"
                )
                return False

        def _sir_analysis_preview(self, resources) -> str:
            _loaded, selected = resources
            model_resource = selected["model"]
            observations_resource = selected["observations"]
            config_resource = selected["analysis-config"]
            model = json.loads(model_resource.content.decode("utf-8"))
            observations = json.loads(observations_resource.content.decode("utf-8"))
            config = json.loads(config_resource.content.decode("utf-8"))
            if not isinstance(model, dict) or not isinstance(observations, dict) or not isinstance(config, dict):
                raise ValueError("model, observations and analysis configuration must be JSON objects")
            observation_rows = observations.get("observations", [])
            observation_provenance = observations.get("provenance", {})
            if not isinstance(observation_rows, list) or not isinstance(observation_provenance, dict):
                raise ValueError("observations structure is invalid")
            resource_lines = []
            for resource in (model_resource, observations_resource, config_resource):
                resource_lines.append(
                    f"- {resource.resource_id} ({resource.kind}): {resource.path} · "
                    f"SHA-256 {resource.sha256}"
                )
            return "\n".join((
                "Recursos verificados:",
                *resource_lines,
                "",
                f"Modelo: {model.get('model_type', 'sin tipo')} · "
                f"ecuaciones: {json.dumps(model.get('equations', {}), ensure_ascii=False, sort_keys=True)}",
                f"Condiciones iniciales: {json.dumps(model.get('initial_conditions', {}), ensure_ascii=False, sort_keys=True)}",
                f"Parámetros del modelo: {json.dumps(model.get('parameters', {}), ensure_ascii=False, sort_keys=True)}",
                f"Intervalo e integrador: {json.dumps({'t_span': model.get('t_span'), 'integrator': model.get('integrator')}, ensure_ascii=False, sort_keys=True)}",
                f"Observaciones: {len(observation_rows)} filas · "
                f"estado {observation_provenance.get('data_status', 'NOT_DECLARED')} · "
                f"unidades {json.dumps(observations.get('variables', []), ensure_ascii=False, sort_keys=True)}",
                f"Configuración de análisis: parámetros iniciales {json.dumps(config.get('initial_parameters', {}), ensure_ascii=False, sort_keys=True)} · "
                f"límites {json.dumps(config.get('bounds', {}), ensure_ascii=False, sort_keys=True)} · "
                f"fit_knots {json.dumps(config.get('fit_knots'), ensure_ascii=False, sort_keys=True)} · "
                f"máximos {config.get('max_iterations')} iteraciones / {config.get('max_function_evaluations')} evaluaciones",
                "",
                "Operación: volver a verificar SHA-256, ejecutar el builder SSEC P3.20 existente "
                "(simulación, ajuste, sensibilidad local y residuales), validar el workspace generado "
                "y abrir Resultados. Los recursos originales no se reemplazan; se crea una carpeta nueva.",
                "El motor actual no admite cancelación segura. Código Python del proyecto o de agentes: no se ejecuta.",
                "Validez e identificabilidad: NOT_ASSESSED · incertidumbre: NOT_CALCULATED · SIR particular del usuario: NOT_RUN.",
            ))

        def _create_sir_analysis_confirmation(self, preview: str):
            confirmation = QtWidgets.QMessageBox(self)
            confirmation.setWindowTitle("Confirmar análisis científico")
            confirmation.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            confirmation.setText(preview)
            confirmation.setStandardButtons(
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No
            )
            confirmation.button(QtWidgets.QMessageBox.StandardButton.Yes).setText(
                "Ejecutar análisis"
            )
            confirmation.button(QtWidgets.QMessageBox.StandardButton.No).setText(
                "No ejecutar"
            )
            confirmation.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)
            return confirmation

        def start_sir_analysis(self) -> None:
            if self.analysis_running:
                return
            inputs = self._sir_analysis_resources()
            root = self.current_project_root
            manifest_path = self.current_manifest_relative_path
            if inputs is None or root is None or manifest_path is None:
                self.sir_analysis_status.setText(
                    "No se inició: el workspace no contiene los recursos requeridos."
                )
                return
            loaded, _resources = inputs
            try:
                preview = self._sir_analysis_preview(inputs)
                expected_manifest_sha256 = hashlib.sha256(loaded.manifest_bytes).hexdigest()
            except (UnicodeDecodeError, TypeError, ValueError, RecursionError) as exc:
                self.sir_analysis_status.setText(f"No se inició: entradas inválidas · {exc}")
                return

            run_id = uuid.uuid4().hex
            output_dir = root / "generated" / "sir-analysis" / run_id
            destination = output_dir.relative_to(root).as_posix()
            confirmation = self._create_sir_analysis_confirmation(
                f"¿Ejecutar el análisis SIR?\n\n{preview}\n\n"
                f"Destino nuevo: {destination}/workspace.json\n"
                f"Bitácora persistente: generated/sir-analysis-runs/run-{run_id}.json"
            )
            if confirmation.exec() != QtWidgets.QMessageBox.StandardButton.Yes:
                self.sir_analysis_status.setText(
                    "Ejecución rechazada; no se escribieron resultados ni bitácora."
                )
                return

            thread = _SirAnalysisThread(
                root, manifest_path, output_dir, run_id,
                expected_manifest_sha256, self,
            )
            thread.progress_changed.connect(self._on_sir_analysis_progress)
            thread.succeeded.connect(self._on_sir_analysis_succeeded)
            thread.failed.connect(self._on_sir_analysis_failed)
            thread.finished.connect(self._on_sir_analysis_finished)
            self._sir_analysis_thread = thread
            self.workspace_window.setEnabled(False)
            self.sir_analysis_progress.show()
            self.sir_analysis_status.setText(
                f"En curso · ejecución {run_id[:8]} · el resultado anterior no se presenta como nuevo."
            )
            self._update_sir_analysis_controls()
            thread.start()

        @QtCore.Slot(str)
        def _on_sir_analysis_progress(self, message: str) -> None:
            self.sir_analysis_status.setText(message)

        @QtCore.Slot(object)
        def _on_sir_analysis_succeeded(self, result: object) -> None:
            if not isinstance(result, dict):
                self._on_sir_analysis_failed("El worker devolvió un resultado inválido.")
                return
            workspace_path = result.get("workspace_path")
            if not isinstance(workspace_path, str) or self.current_project_root is None:
                self._on_sir_analysis_failed("No se recibió una ruta de workspace válida.")
                return
            try:
                self._loading_sir_analysis_result = True
                self.load_project(self.current_project_root, workspace_path)
                self.navigate("results")
                self.sir_analysis_status.setText(
                    f"Análisis calculado y workspace verificado · {workspace_path} · "
                    "validez e identificabilidad NOT_ASSESSED · incertidumbre NOT_CALCULATED · "
                    "SIR particular NOT_RUN."
                )
            except (OSError, TypeError, ValueError, RecursionError) as exc:
                self._on_sir_analysis_failed(
                    f"El cálculo terminó, pero el workspace no pudo cargarse: {exc}"
                )
            finally:
                self._loading_sir_analysis_result = False

        @QtCore.Slot(str)
        def _on_sir_analysis_failed(self, error: str) -> None:
            self.sir_analysis_status.setText(
                f"Falló el análisis; no se cargaron resultados · {error[:1500]}"
            )

        @QtCore.Slot()
        def _on_sir_analysis_finished(self) -> None:
            thread = self.sender()
            if thread is not self._sir_analysis_thread:
                return
            self._sir_analysis_thread = None
            self.workspace_window.setEnabled(True)
            self.sir_analysis_progress.hide()
            self._update_sir_analysis_controls()
            thread.deleteLater()

        def closeEvent(self, event) -> None:
            if self.analysis_running:
                QtWidgets.QMessageBox.information(
                    self,
                    "Análisis en curso",
                    "El motor no admite cancelación segura. Espera a que termine antes de cerrar.",
                )
                event.ignore()
                return
            super().closeEvent(event)

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
            route_changed = route != self.current_route
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
            if route_changed:
                self._animate_page_transition()

        def _animate_page_transition(self) -> None:
            if not motion_enabled():
                return
            effect = self.page_stack.graphicsEffect()
            if not isinstance(effect, QtWidgets.QGraphicsOpacityEffect):
                effect = QtWidgets.QGraphicsOpacityEffect(self.page_stack)
                self.page_stack.setGraphicsEffect(effect)
            if self._page_transition_animation is not None:
                self._page_transition_animation.stop()
            effect.setOpacity(0.94)
            animation = QtCore.QPropertyAnimation(effect, b"opacity", self)
            animation.setDuration(150)
            animation.setStartValue(0.94)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
            self._page_transition_animation = animation
            animation.start()

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
            self,
            project_root: str | os.PathLike[str],
            manifest_relative_path: str,
            *,
            expected_manifest_sha256: str | None = None,
        ) -> WorkspaceViewModel:
            """Load both resources and shared project context only after verification succeeds."""
            if self.analysis_running and not self._loading_sir_analysis_result:
                raise ValueError("analysis is running; wait before changing the project workspace")
            root, policy = self.agent_supervisor.project_context(project_root)
            if self.agent_supervisor.process_running and root != self.agent_supervisor.project_root:
                raise ValueError("espera a que termine la auditoría antes de cambiar de proyecto")
            model = self.workspace_window.load_workspace(
                project_root,
                manifest_relative_path,
                expected_manifest_sha256=expected_manifest_sha256,
            )
            self.current_project_root = root
            self.current_manifest_relative_path = manifest_relative_path
            self.active_project_label.setText(root.name or str(root))
            self.active_project_label.setToolTip(str(root))
            self.project_root_value.setText(str(root))
            self.workspace_value.setText(
                f"{model.title} · {model.workspace_id} · {model.verification_status}"
            )
            self.workspace_audit_button.setEnabled(True)
            self.agent_supervisor.set_project_root(root, policy=policy)
            self._update_sir_analysis_controls()
            self.statusBar().showMessage(
                f"Proyecto cargado · {model.verification_status}", 8_000
            )
            return model

        def _open_thesis_sir_audit_workspace(self, workspace_path: str) -> None:
            """Load the verified SIR bundle and open, but do not submit, its audit request."""
            root = Path(workspace_path)
            try:
                self.load_project(root, "workspace.json")
            except (OSError, TypeError, ValueError, RecursionError) as exc:
                self.thesis_sir_page._set_run_status(
                    f"Bundle creado pero no se pudo abrir en el Centro de Control · {str(exc)[:600]}",
                    "error",
                )
                return
            self.navigate("audits")
            self.statusBar().showMessage(
                "Bundle SIR verificado; revisa recursos y confirma por separado el envío.", 10_000
            )
            self.workspace_audit_button.click()

        def _open_thesis_sir_analysis_workspace(self, workspace_path: str) -> None:
            """Open a digest-verified P3.31 analysis workspace in the current window."""
            root = Path(workspace_path)
            try:
                self._loading_sir_analysis_result = True
                self.load_project(root, "workspace.json")
                self.navigate("results")
                self.sir_analysis_status.setText(
                    "Ajuste SIR de tesis calculado y verificado en esta aplicación · "
                    "validez e identificabilidad NOT_ASSESSED · incertidumbre NOT_CALCULATED · "
                    "SIR real NOT_RUN."
                )
                self.statusBar().showMessage(
                    "Workspace SIR de análisis cargado; revisa resultados y procedencia.", 10_000
                )
            except (OSError, TypeError, ValueError, RecursionError) as exc:
                self.thesis_sir_page._on_analysis_worker_failure(
                    f"El resultado se generó, pero no se pudo abrir: {str(exc)[:700]}"
                )
            finally:
                self._loading_sir_analysis_result = False



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

