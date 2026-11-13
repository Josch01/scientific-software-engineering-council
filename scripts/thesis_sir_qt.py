"""Qt workspace for explicit, human-confirmed thesis SIR simulations."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import stat
from datetime import datetime, timezone
from collections.abc import Mapping

try:
    from PySide6 import QtCore, QtWidgets
    from PySide6.QtCore import QIODevice, QSaveFile
except ImportError:  # Keep the scientific engine usable without optional Qt.
    QtCore = QtWidgets = QIODevice = QSaveFile = None

try:
    from .scientific_ui_theme import COLORS
    from .scientific_workspace_qt_charts import ScientificChartWidget
    from .thesis_sir_data import MAX_RECONSTRUCTION_BYTES, parse_dge_reconstruction_json
    from .thesis_sir_model import (
        HarmonicTerm,
        THESIS_PDF_SHA256,
        THESIS_SOURCE_REFERENCE,
        THESIS_SIR_EQUATION_SET,
        THESIS_SIR_POPULATION,
        ThesisSIRParameters,
        WeeklyCountObservations,
        evaluate_thesis_sir_weekly_counts,
    )
except ImportError:  # Support direct execution from scripts/.
    from scientific_ui_theme import COLORS
    from scientific_workspace_qt_charts import ScientificChartWidget
    from thesis_sir_data import MAX_RECONSTRUCTION_BYTES, parse_dge_reconstruction_json
    from thesis_sir_model import (
        HarmonicTerm,
        THESIS_PDF_SHA256,
        THESIS_SOURCE_REFERENCE,
        THESIS_SIR_EQUATION_SET,
        THESIS_SIR_POPULATION,
        ThesisSIRParameters,
        WeeklyCountObservations,
        evaluate_thesis_sir_weekly_counts,
    )

try:
    from .thesis_sir_audit_workspace import write_thesis_sir_audit_workspace
except ImportError:
    from thesis_sir_audit_workspace import write_thesis_sir_audit_workspace

try:
    from .thesis_sir_analysis import analyze_thesis_sir_parameters
    from .thesis_sir_analysis_workspace import write_thesis_sir_analysis_workspace
except ImportError:
    from thesis_sir_analysis import analyze_thesis_sir_parameters
    from thesis_sir_analysis_workspace import write_thesis_sir_analysis_workspace


MAX_STEPS_PER_INTERVAL = 1000
DEFAULT_MAX_STEP_WEEKS = 0.01
RK4_STEP_CHOICES_WEEKS = (0.1, 0.05, 0.02, 0.01, 0.005, 0.001)
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _read_selected_file(path: str | os.PathLike[str]) -> bytes:
    """Read a user-selected regular file once, with a strict size and identity bound."""
    candidate = Path(path).expanduser()
    entry = candidate.lstat()
    if (stat.S_ISLNK(entry.st_mode)
            or getattr(entry, "st_file_attributes", 0) & _REPARSE_POINT):
        raise ValueError("selected reconstruction JSON must not be a symlink or reparse point")
    if not stat.S_ISREG(entry.st_mode):
        raise ValueError("selected reconstruction JSON must be a regular file")
    if entry.st_size < 1 or entry.st_size > MAX_RECONSTRUCTION_BYTES:
        raise ValueError("selected reconstruction JSON must be at most 1 MiB")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(candidate, flags)
    try:
        opened = os.fstat(descriptor)
        if (not stat.S_ISREG(opened.st_mode)
                or (entry.st_dev, entry.st_ino) != (opened.st_dev, opened.st_ino)):
            raise ValueError("selected reconstruction JSON changed while opening")
        with os.fdopen(descriptor, "rb", buffering=0) as stream:
            descriptor = -1
            payload = stream.read(MAX_RECONSTRUCTION_BYTES + 1)
            after = os.fstat(stream.fileno())
        if len(payload) > MAX_RECONSTRUCTION_BYTES:
            raise ValueError("selected reconstruction JSON must be at most 1 MiB")
        if (opened.st_size, opened.st_mtime_ns, opened.st_ino) != (
            after.st_size, after.st_mtime_ns, after.st_ino
        ):
            raise ValueError("selected reconstruction JSON changed while reading")
        if not payload:
            raise ValueError("selected reconstruction JSON must not be empty")
        return payload
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def thesis_parameters_from_fields(
    harmonic_count: int | None,
    fields: Mapping[str, str],
    harmonic_rows: list[tuple[str, str, str]],
    delay_days: float | None,
) -> ThesisSIRParameters:
    """Create the versioned model contract from explicit UI values only."""
    if harmonic_count not in (1, 2, 3):
        raise ValueError("selecciona el número de armónicos")

    def number(name: str) -> float:
        raw = fields.get(name, "").strip()
        if not raw:
            raise ValueError(f"falta el parámetro {name}")
        try:
            return float(raw)
        except (ValueError, OverflowError) as exc:
            raise ValueError(f"{name} debe ser un número finito; usa punto decimal") from exc

    if delay_days is None:
        raise ValueError("selecciona un escenario de retardo")
    if len(harmonic_rows) < harmonic_count:
        raise ValueError("faltan términos armónicos")
    harmonics = tuple(
        HarmonicTerm(
            cosine=float(row[0]), sine=float(row[1]), angular_frequency=float(row[2])
        )
        for row in harmonic_rows[:harmonic_count]
    )
    try:
        return ThesisSIRParameters(
            d0=number("d0"),
            harmonics=harmonics,
            gamma=number("gamma"),
            log10_initial_infectious=number("log10_initial_infectious"),
            susceptible_fraction=number("susceptible_fraction"),
            ascertainment_fraction=number("ascertainment_fraction"),
            delay_days=delay_days,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(str(exc)) from exc


def thesis_sir_fit_parameter_options(parameters: ThesisSIRParameters):
    """Return only supported dynamic fit parameters with their scientific units/domains."""
    values = [("d0", parameters.d0, "dimensionless", (-2.0, 2.0)),
              ("gamma", parameters.gamma, "1/week", (0.05, 0.70))]
    for index, harmonic in enumerate(parameters.harmonics):
        values.extend((
            (f"harmonic_{index}_cosine", harmonic.cosine, "dimensionless", (-2.0, 2.0)),
            (f"harmonic_{index}_sine", harmonic.sine, "dimensionless", (-2.0, 2.0)),
            (f"harmonic_{index}_angular_frequency", harmonic.angular_frequency,
             "rad/week", (0.05, 2.20)),
        ))
    return tuple(values)


if QtWidgets is not None:
    class _ThesisSIRWorker(QtCore.QThread):
        succeeded = QtCore.Signal(object)
        failed = QtCore.Signal(str)

        def __init__(
            self, parameters, observations, max_step, max_steps_per_interval, parent=None
        ):
            super().__init__(parent)
            self._parameters = parameters
            self._observations = observations
            self._max_step = max_step
            self._max_steps_per_interval = max_steps_per_interval

        def run(self) -> None:
            try:
                result = evaluate_thesis_sir_weekly_counts(
                    self._parameters,
                    self._observations,
                    max_step=self._max_step,
                    max_steps_per_interval=self._max_steps_per_interval,
                )
                self.succeeded.emit(result.to_dict())
            except Exception as exc:
                self.failed.emit(f"{type(exc).__name__}: {str(exc)[:1000]}")


    class _ThesisSIRAnalysisWorker(QtCore.QThread):
        succeeded = QtCore.Signal(str)
        failed = QtCore.Signal(str)

        def __init__(self, parameters, observations, fit_config, max_step, output_parent, parent=None):
            super().__init__(parent)
            self._parameters = parameters
            self._observations = observations
            self._fit_config = fit_config
            self._max_step = max_step
            self._output_parent = output_parent

        def run(self) -> None:
            try:
                started_at_utc = datetime.now(timezone.utc).isoformat()
                result = analyze_thesis_sir_parameters(
                    self._parameters,
                    self._observations,
                    initial_parameters=self._fit_config["initial_parameters"],
                    bounds=self._fit_config["bounds"],
                    perturbations=self._fit_config["perturbations"],
                    max_step=self._max_step,
                    max_steps_per_interval=MAX_STEPS_PER_INTERVAL,
                )
                completed_at_utc = datetime.now(timezone.utc).isoformat()
                workspace = write_thesis_sir_analysis_workspace(
                    self._output_parent,
                    result,
                    started_at_utc=started_at_utc,
                    completed_at_utc=completed_at_utc,
                )
                self.succeeded.emit(str(workspace))
            except Exception as exc:
                self.failed.emit(f"{type(exc).__name__}: {str(exc)[:1000]}")


    class ThesisSIRPage(QtWidgets.QWidget):
        """Project-independent UI for read-only DGE import and thesis SIR runs."""

        audit_workspace_ready = QtCore.Signal(str)
        analysis_workspace_ready = QtCore.Signal(str)
        activity_finished = QtCore.Signal()

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setObjectName("thesisSIRPage")
            self.observations: WeeklyCountObservations | None = None
            self.source_path: Path | None = None
            self.result_payload: dict[str, object] | None = None
            self.state = "EMPTY"
            self._worker: _ThesisSIRWorker | None = None
            self._analysis_worker: _ThesisSIRAnalysisWorker | None = None
            self.fit_configuration: dict[str, object] | None = None
            self._build_ui()

        @property
        def run_in_progress(self) -> bool:
            return self._worker is not None or self._analysis_worker is not None

        def _build_ui(self) -> None:
            outer = QtWidgets.QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            scroll = QtWidgets.QScrollArea(self)
            scroll.setObjectName("thesisSirScrollArea")
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.scroll_content = QtWidgets.QWidget(scroll)
            root = QtWidgets.QVBoxLayout(self.scroll_content)
            root.setContentsMargins(16, 12, 16, 16)
            root.setSpacing(14)

            hero = QtWidgets.QFrame(self.scroll_content)
            hero.setObjectName("thesisSirHeroCard")
            hero_layout = QtWidgets.QVBoxLayout(hero)
            hero_layout.setContentsMargins(18, 14, 18, 14)
            hero_layout.setSpacing(10)
            hero_header = QtWidgets.QHBoxLayout()
            hero_header.setSpacing(12)
            heading = QtWidgets.QLabel("Modelo SIR de tesis")
            heading.setObjectName("thesisSirPageTitle")
            hero_header.addWidget(heading, 1)
            page_kicker = QtWidgets.QLabel("SIMULACIÓN DECLARATIVA  ·  DATOS LOCALES")
            page_kicker.setObjectName("thesisSirKicker")
            page_kicker.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            hero_header.addWidget(page_kicker)
            hero_layout.addLayout(hero_header)
            model_note = QtWidgets.QLabel(
                "β(t) = exp(d₀ + Σ[aₖ cos(ωₖt) + bₖ sin(ωₖt)]) · "
                "dS/dt = −βSI/N · dI/dt = βSI/N − γI · dR/dt = γI"
            )
            model_note.setWordWrap(True)
            model_note.setObjectName("thesisSirEquationSummary")
            hero_layout.addWidget(model_note)
            source_note = QtWidgets.QLabel(
                f"Fuente del modelo: {THESIS_SOURCE_REFERENCE} · "
                f"tesis.pdf SHA-256 {THESIS_PDF_SHA256}"
            )
            source_note.setObjectName("thesisSirModelProvenance")
            source_note.setWordWrap(True)
            source_note.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            hero_layout.addWidget(source_note)

            model_facts = QtWidgets.QHBoxLayout()
            model_facts.setSpacing(8)
            for title, value in (
                ("POBLACIÓN FIJA", "129,960,600 personas"),
                ("INTEGRADOR", "RK4 fijo · paso configurable"),
                ("AJUSTE", "No automático"),
            ):
                fact = QtWidgets.QFrame(hero)
                fact.setObjectName("thesisSirFactCard")
                fact_layout = QtWidgets.QVBoxLayout(fact)
                fact_layout.setContentsMargins(10, 7, 10, 7)
                fact_layout.setSpacing(2)
                label = QtWidgets.QLabel(title, fact)
                label.setObjectName("thesisSirFactLabel")
                value_label = QtWidgets.QLabel(value, fact)
                value_label.setObjectName("thesisSirFactValue")
                value_label.setWordWrap(True)
                fact_layout.addWidget(label)
                fact_layout.addWidget(value_label)
                model_facts.addWidget(fact, 1)
            hero_layout.addLayout(model_facts)
            root.addWidget(hero)

            self.workspace_splitter = QtWidgets.QSplitter(
                QtCore.Qt.Orientation.Horizontal, self.scroll_content
            )
            self.workspace_splitter.setObjectName("thesisSirWorkspaceSplitter")
            self.workspace_splitter.setChildrenCollapsible(False)
            self.workspace_splitter.setHandleWidth(8)

            setup_panel = QtWidgets.QFrame(self.workspace_splitter)
            setup_panel.setObjectName("thesisSirSetupPanel")
            setup_layout = QtWidgets.QVBoxLayout(setup_panel)
            setup_layout.setContentsMargins(12, 12, 12, 12)
            setup_layout.setSpacing(12)
            setup_heading = QtWidgets.QLabel("Configuración")
            setup_heading.setObjectName("thesisSirPanelTitle")
            setup_layout.addWidget(setup_heading)

            source_group = QtWidgets.QGroupBox("Datos observados")
            source_group.setObjectName("thesisSirDataGroup")
            source_layout = QtWidgets.QVBoxLayout(source_group)
            source_layout.setSpacing(8)
            self.load_data_button = QtWidgets.QPushButton("Importar JSON de reconstrucción…")
            self.load_data_button.setObjectName("loadThesisSirDataButton")
            self.load_data_button.setMinimumHeight(40)
            self.load_data_button.clicked.connect(self.import_data_dialog)
            source_layout.addWidget(self.load_data_button)
            self.data_status = QtWidgets.QLabel("Sin datos importados · NOT_RUN")
            self.data_status.setObjectName("thesisSirDataStatus")
            self.data_status.setProperty("state", "neutral")
            self.data_status.setWordWrap(True)
            self.data_status.setAccessibleName("Estado de importación de datos")
            source_layout.addWidget(self.data_status)
            self.data_series_label = QtWidgets.QLabel(
                "Serie · DGE_monday_sunday_candidate"
            )
            self.data_series_label.setObjectName("thesisSirDataSeries")
            self.data_series_label.setWordWrap(True)
            source_layout.addWidget(self.data_series_label)
            self.data_source_label = QtWidgets.QLabel("Fuente · sin seleccionar")
            self.data_source_label.setObjectName("thesisSirDataSource")
            self.data_source_label.setWordWrap(True)
            self.data_source_label.setTextInteractionFlags(
                QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
            )
            source_layout.addWidget(self.data_source_label)
            self.data_digest_label = QtWidgets.QLabel("SHA-256 · no disponible")
            self.data_digest_label.setObjectName("thesisSirDataDigest")
            self.data_digest_label.setWordWrap(True)
            self.data_digest_label.setTextInteractionFlags(
                QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
            )
            source_layout.addWidget(self.data_digest_label)
            source_hint = QtWidgets.QLabel(
                "Solo se usa la serie DGE seleccionada; el archivo original no se modifica."
            )
            source_hint.setObjectName("thesisSirHelperText")
            source_hint.setWordWrap(True)
            source_layout.addWidget(source_hint)
            setup_layout.addWidget(source_group)

            parameter_group = QtWidgets.QGroupBox("Parámetros explícitos del modelo")
            parameter_group.setObjectName("thesisSirParameterGroup")
            self.parameter_group = parameter_group
            parameter_layout = QtWidgets.QVBoxLayout(parameter_group)
            parameter_layout.setSpacing(8)
            form = QtWidgets.QFormLayout()
            form.setHorizontalSpacing(12)
            form.setVerticalSpacing(8)
            self.harmonic_count = QtWidgets.QComboBox()
            self.harmonic_count.setObjectName("thesisSirHarmonicCount")
            self.harmonic_count.addItem("Selecciona…", None)
            for count in (1, 2, 3):
                self.harmonic_count.addItem(f"{count} armónico(s)", count)
            self.harmonic_count.currentIndexChanged.connect(self._resize_harmonic_table)
            form.addRow("Términos armónicos", self.harmonic_count)

            self.harmonic_table = QtWidgets.QTableWidget(0, 3)
            self.harmonic_table.setObjectName("thesisSirHarmonicsTable")
            self.harmonic_table.setHorizontalHeaderLabels(
                ("aₖ · cos", "bₖ · seno", "ωₖ · rad/sem")
            )
            for column, tooltip in enumerate((
                "aₖ · coeficiente de coseno",
                "bₖ · coeficiente de seno",
                "ωₖ · frecuencia angular (rad/semana)",
            )):
                self.harmonic_table.horizontalHeaderItem(column).setToolTip(tooltip)
            self.harmonic_table.horizontalHeader().setSectionResizeMode(
                QtWidgets.QHeaderView.ResizeMode.Stretch
            )
            self.harmonic_table.verticalHeader().setVisible(False)
            self.harmonic_table.setMaximumHeight(118)
            self.harmonic_table.itemChanged.connect(self._invalidate_result)
            form.addRow("Coeficientes", self.harmonic_table)

            self.parameter_fields: dict[str, QtWidgets.QLineEdit] = {}
            field_specs = (
                ("d0", "d₀ · sin unidades"),
                ("gamma", "γ · 1/semana"),
                ("log10_initial_infectious", "log₁₀(I₀/personas)"),
                ("susceptible_fraction", "S₀/N · fracción"),
                ("ascertainment_fraction", "q · fracción observada"),
            )
            for name, label in field_specs:
                edit = QtWidgets.QLineEdit()
                edit.setObjectName(f"thesisSirParameter_{name}")
                edit.setPlaceholderText("Valor explícito; usa punto decimal")
                edit.setAccessibleDescription(f"Parámetro {label}; entrada numérica explícita")
                edit.textChanged.connect(self._invalidate_result)
                self.parameter_fields[name] = edit
                form.addRow(label, edit)

            self.delay_days = QtWidgets.QComboBox()
            self.delay_days.setObjectName("thesisSirDelayScenario")
            self.delay_days.addItem("Selecciona…", None)
            for delay in (0.0, 3.5, 4.3, 6.5):
                self.delay_days.addItem(f"{delay:g} días", delay)
            self.delay_days.currentIndexChanged.connect(self._invalidate_result)
            form.addRow("Retardo declarado", self.delay_days)

            self.max_step_combo = QtWidgets.QComboBox()
            self.max_step_combo.setObjectName("thesisSirMaxStep")
            self.max_step_combo.setAccessibleName("Paso máximo del integrador RK4 en semanas")
            self.max_step_combo.setToolTip(
                "Paso fijo de integración. Reducirlo aumenta el número de pasos; "
                "no es una medida de incertidumbre ni garantiza validez científica."
            )
            for max_step in RK4_STEP_CHOICES_WEEKS:
                self.max_step_combo.addItem(f"{max_step:g} semanas", max_step)
            self.max_step_combo.setCurrentIndex(
                self.max_step_combo.findData(DEFAULT_MAX_STEP_WEEKS)
            )
            self.max_step_combo.currentIndexChanged.connect(self._invalidate_result)
            form.addRow("Paso máximo RK4", self.max_step_combo)
            parameter_layout.addLayout(form)
            model_bounds = QtWidgets.QLabel(
                "γ se expresa en 1/semana. Introduce todos los valores; SSEC no asigna "
                "parámetros predeterminados ni ajusta el modelo automáticamente."
            )
            model_bounds.setObjectName("thesisSirHelperText")
            model_bounds.setWordWrap(True)
            parameter_layout.addWidget(model_bounds)
            setup_layout.addWidget(parameter_group)

            fit_group = QtWidgets.QGroupBox("Ajuste de parámetros dinámicos")
            fit_group.setObjectName("thesisSirFitConfigurationGroup")
            fit_layout = QtWidgets.QVBoxLayout(fit_group)
            self.configure_fit_button = QtWidgets.QPushButton("Configurar parámetros de ajuste…")
            self.configure_fit_button.setObjectName("configureThesisSirFitButton")
            self.configure_fit_button.setEnabled(False)
            self.configure_fit_button.clicked.connect(self.configure_fit_parameters)
            fit_layout.addWidget(self.configure_fit_button)
            self.fit_configuration_status = QtWidgets.QLabel(
                "Sin parámetros seleccionados; SSEC no elegirá límites ni perturbaciones por ti."
            )
            self.fit_configuration_status.setObjectName("thesisSirFitConfigurationStatus")
            self.fit_configuration_status.setWordWrap(True)
            fit_layout.addWidget(self.fit_configuration_status)
            fit_hint = QtWidgets.QLabel(
                "Solo d₀, γ y coeficientes/frecuencias armónicas son ajustables. "
                "I₀, S₀/N, q y retardo permanecen fijos."
            )
            fit_hint.setObjectName("thesisSirHelperText")
            fit_hint.setWordWrap(True)
            fit_layout.addWidget(fit_hint)
            setup_layout.addWidget(fit_group)
            setup_layout.addStretch(1)

            results_panel = QtWidgets.QFrame(self.workspace_splitter)
            results_panel.setObjectName("thesisSirResultsPanel")
            results_layout = QtWidgets.QVBoxLayout(results_panel)
            results_layout.setContentsMargins(12, 12, 12, 12)
            results_layout.setSpacing(12)
            results_heading = QtWidgets.QLabel("Ejecución y resultados")
            results_heading.setObjectName("thesisSirPanelTitle")
            results_layout.addWidget(results_heading)

            actions = QtWidgets.QHBoxLayout()
            actions.setSpacing(8)
            self.run_button = QtWidgets.QPushButton("Confirmar y simular…")
            self.run_button.setObjectName("runThesisSirButton")
            self.run_button.setEnabled(False)
            self.run_button.setMinimumHeight(42)
            self.run_button.setAccessibleDescription(
                "Solicita confirmación humana antes de simular con los datos y parámetros declarados"
            )
            self.run_button.clicked.connect(self.start_simulation)
            actions.addWidget(self.run_button, 1)
            self.fit_button = QtWidgets.QPushButton("Ajustar a datos…")
            self.fit_button.setObjectName("runThesisSirFitButton")
            self.fit_button.setEnabled(False)
            self.fit_button.setMinimumHeight(42)
            self.fit_button.clicked.connect(self.start_parameter_fit)
            self.save_button = QtWidgets.QPushButton("Exportar resultado…")
            self.save_button.setObjectName("saveThesisSirResultButton")
            self.save_button.setEnabled(False)
            self.save_button.setMinimumHeight(42)
            self.save_button.clicked.connect(self.export_result_dialog)
            actions.addWidget(self.save_button, 1)
            results_layout.addWidget(self.fit_button)
            results_layout.addLayout(actions)
            self.audit_button = QtWidgets.QPushButton("Preparar bundle de auditoría…")
            self.audit_button.setObjectName("prepareThesisSirAuditButton")
            self.audit_button.setAccessibleDescription(
                "Crea una copia de auditoría con los datos seleccionados, el modelo, el resultado "
                "y el código exacto; el envío a especialistas requiere otra confirmación."
            )
            self.audit_button.setMinimumHeight(40)
            self.audit_button.setEnabled(False)
            self.audit_button.clicked.connect(self.prepare_audit_workspace_dialog)
            results_layout.addWidget(self.audit_button)
            audit_hint = QtWidgets.QLabel(
                "Preparar el bundle no invoca proveedores. El envío a especialistas se confirma después."
            )
            audit_hint.setObjectName("thesisSirHelperText")
            audit_hint.setWordWrap(True)
            results_layout.addWidget(audit_hint)
            self.progress_bar = QtWidgets.QProgressBar()
            self.progress_bar.setObjectName("thesisSirProgress")
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setTextVisible(False)
            self.progress_bar.setAccessibleName("Simulación en curso; progreso no estimado")
            self.progress_bar.hide()
            results_layout.addWidget(self.progress_bar)

            self.status_label = QtWidgets.QLabel("Sin simulación ejecutada · NOT_RUN")
            self.status_label.setObjectName("thesisSirRunStatus")
            self.status_label.setWordWrap(True)
            self.status_label.setAccessibleName("Estado de simulación del SIR de tesis")
            self.status_label.setProperty("state", "neutral")
            results_layout.addWidget(self.status_label)

            self.content_stack = QtWidgets.QStackedWidget()
            self.content_stack.setObjectName("thesisSirResultStack")
            self.empty_state = QtWidgets.QLabel(
                "Los resultados aparecerán aquí después de una simulación confirmada.\n\n"
                "Se mostrarán las observaciones y las trayectorias calculadas con sus unidades "
                "y procedencia. La incertidumbre estadística y la validez científica no se "
                "evalúan en este flujo."
            )
            self.empty_state.setObjectName("thesisSirEmptyState")
            self.empty_state.setWordWrap(True)
            self.empty_state.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.empty_state.setMinimumHeight(220)
            self.content_stack.addWidget(self.empty_state)
            results_layout.addWidget(self.content_stack, 1)

            self.workspace_splitter.addWidget(setup_panel)
            self.workspace_splitter.addWidget(results_panel)
            self.workspace_splitter.setStretchFactor(0, 5)
            self.workspace_splitter.setStretchFactor(1, 6)
            self.workspace_splitter.setSizes([520, 620])
            root.addWidget(self.workspace_splitter, 1)
            scroll.setWidget(self.scroll_content)
            outer.addWidget(scroll)

        def _resize_harmonic_table(self, _index: int) -> None:
            count = self.harmonic_count.currentData()
            rows = count if isinstance(count, int) else 0
            self.harmonic_table.blockSignals(True)
            self.harmonic_table.setRowCount(rows)
            for row in range(rows):
                for column in range(3):
                    if self.harmonic_table.item(row, column) is None:
                        self.harmonic_table.setItem(row, column, QtWidgets.QTableWidgetItem())
            self.harmonic_table.blockSignals(False)
            self._invalidate_result()

        def _clear_content(self) -> None:
            while self.content_stack.count() > 1:
                widget = self.content_stack.widget(1)
                self.content_stack.removeWidget(widget)
                widget.deleteLater()
            self.content_stack.setCurrentWidget(self.empty_state)

        def _set_run_status(self, message: str, state: str = "neutral") -> None:
            self.status_label.setText(message)
            self.status_label.setProperty("state", state)
            style = self.status_label.style()
            style.unpolish(self.status_label)
            style.polish(self.status_label)
            self.status_label.update()

        def _invalidate_result(self, *_args) -> None:
            if self.run_in_progress:
                return
            self.fit_configuration = None
            if hasattr(self, "fit_configuration_status"):
                self.fit_configuration_status.setText(
                    "Configuración de ajuste invalidada; vuelve a seleccionar parámetros, límites y perturbaciones."
                )
            had_result_or_empty_state = (
                self.result_payload is not None
                or self.content_stack.currentWidget() is self.empty_state
            )
            self.result_payload = None
            self.save_button.setEnabled(False)
            self.audit_button.setEnabled(False)
            self._update_analysis_controls()
            if self.observations is None:
                self.state = "EMPTY"
                return
            self.state = "READY"
            if had_result_or_empty_state:
                self._show_observation_chart()

        def import_data_dialog(self) -> None:
            path, _filter = QtWidgets.QFileDialog.getOpenFileName(
                self, "Seleccionar reconstrucción DGE", "", "JSON (*.json);;Todos los archivos (*)"
            )
            if not path:
                return
            try:
                self.load_data_file(path)
            except (OSError, TypeError, ValueError) as exc:
                QtWidgets.QMessageBox.warning(self, "JSON no importado", str(exc)[:1000])

        def load_data_file(self, path: str | os.PathLike[str]) -> None:
            if self.run_in_progress:
                raise ValueError("no se pueden cambiar los datos durante una simulación")
            self.observations = None
            self.source_path = None
            self.result_payload = None
            self.fit_configuration = None
            self.fit_configuration_status.setText(
                "Sin parámetros seleccionados; SSEC no elegirá límites ni perturbaciones por ti."
            )
            self.run_button.setEnabled(False)
            self.save_button.setEnabled(False)
            self.audit_button.setEnabled(False)
            self._clear_content()
            self.state = "EMPTY"
            self._update_analysis_controls()
            self.data_status.setText("Validando archivo local…")
            self.data_status.setProperty("state", "neutral")
            self.data_series_label.setText("Serie · DGE_monday_sunday_candidate")
            self.data_source_label.setText("Fuente · sin seleccionar")
            self.data_source_label.setToolTip("")
            self.data_digest_label.setText("SHA-256 · no disponible")
            candidate = Path(path).expanduser()
            try:
                payload = _read_selected_file(candidate)
                observations = parse_dge_reconstruction_json(payload)
                source_path = candidate.resolve(strict=True)
            except (OSError, TypeError, ValueError, RecursionError):
                self.data_status.setText("No se importaron datos · revisa el archivo seleccionado.")
                raise
            self.observations = observations
            self.source_path = source_path
            self.state = "READY"
            self.run_button.setEnabled(True)
            self.data_status.setText(
                f"Datos importados · {len(observations.counts)} semanas · "
                f"{sum(observations.counts):,} observaciones"
            )
            self.data_status.setProperty("state", "info")
            style = self.data_status.style()
            style.unpolish(self.data_status)
            style.polish(self.data_status)
            self.data_series_label.setText(f"Serie · {observations.series_id}")
            self.data_source_label.setText(f"Fuente · {source_path.name}")
            self.data_source_label.setToolTip(str(source_path))
            self.data_digest_label.setText(f"SHA-256 · {observations.source_sha256}")
            self._set_run_status(
                "Datos importados; todavía no se ha ejecutado el modelo · NOT_RUN",
                "info",
            )
            self._show_observation_chart()
            self._update_analysis_controls()

        def _fit_configuration_dialog(self, parameters: ThesisSIRParameters):
            dialog = QtWidgets.QDialog(self)
            dialog.setObjectName("thesisSirFitConfigurationDialog")
            dialog.setWindowTitle("Configurar ajuste SIR")
            dialog.setMinimumSize(1080, 460)
            layout = QtWidgets.QVBoxLayout(dialog)
            notice = QtWidgets.QLabel(
                "Selecciona cada parámetro y especifica límites y perturbación. "
                "Los valores iniciales y dominios permitidos se muestran para revisión."
            )
            notice.setWordWrap(True)
            layout.addWidget(notice)
            rows = thesis_sir_fit_parameter_options(parameters)
            table = QtWidgets.QTableWidget(len(rows), 8, dialog)
            table.setObjectName("thesisSirFitParameterTable")
            table.setAccessibleName("Parámetros ajustables, límites y perturbaciones")
            table.setAccessibleDescription(
                "Selecciona parámetros dinámicos y captura límites y perturbación en las tres columnas finales."
            )
            table.setHorizontalHeaderLabels(
                ["Incluir", "Parámetro", "Inicial", "Unidad", "Dominio permitido", "Límite inferior", "Límite superior", "Perturbación"]
            )
            table.horizontalHeader().setSectionResizeMode(
                QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
            table.horizontalHeader().setSectionResizeMode(
                1, QtWidgets.QHeaderView.ResizeMode.Stretch
            )
            for column, width in ((0, 60), (2, 90), (3, 100), (4, 175),
                                  (5, 110), (6, 110), (7, 115)):
                table.setColumnWidth(column, width)
            table.horizontalHeader().setStretchLastSection(False)
            table.setWordWrap(True)
            for row, (name, value, unit, domain) in enumerate(rows):
                include = QtWidgets.QTableWidgetItem()
                include.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                include.setCheckState(QtCore.Qt.CheckState.Unchecked)
                include.setWhatsThis(f"Incluir {name} en el ajuste")
                include.setToolTip(f"Incluir {name} como parámetro ajustable")
                table.setItem(row, 0, include)
                for column, text in ((1, name), (2, f"{value:.10g}"), (3, unit),
                                     (4, f"[{domain[0]:g}, {domain[1]:g}]")):
                    cell = QtWidgets.QTableWidgetItem(text)
                    cell.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable)
                    table.setItem(row, column, cell)
                for column in (5, 6, 7):
                    value_cell = QtWidgets.QTableWidgetItem("")
                    value_cell.setToolTip("Entrada numérica explícita; sin valor predeterminado")
                    table.setItem(row, column, value_cell)
            layout.addWidget(table, 1)
            columns_note = QtWidgets.QLabel(
                "En cada fila seleccionada, introduce los tres valores. La perturbación debe "
                "permanecer dentro de los límites alrededor del valor inicial."
            )
            columns_note.setWordWrap(True)
            layout.addWidget(columns_note)
            buttons = QtWidgets.QDialogButtonBox(
                QtWidgets.QDialogButtonBox.StandardButton.Save
                | QtWidgets.QDialogButtonBox.StandardButton.Cancel
            )
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            dialog.parameter_table = table
            return dialog, rows

        def configure_fit_parameters(self) -> None:
            if self.run_in_progress or self.observations is None:
                self._set_run_status("Importa los datos antes de configurar un ajuste.", "warning")
                return
            try:
                parameters = self._collect_parameters()
            except (TypeError, ValueError, OverflowError) as exc:
                self._set_run_status(f"Parámetros del modelo inválidos: {str(exc)[:500]}", "warning")
                return
            dialog, rows = self._fit_configuration_dialog(parameters)
            if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
                return
            initial: dict[str, float] = {}
            bounds: dict[str, tuple[float, float]] = {}
            perturbations: dict[str, float] = {}
            try:
                for row, (name, value, _unit, _domain) in enumerate(rows):
                    if dialog.parameter_table.item(row, 0).checkState() != QtCore.Qt.CheckState.Checked:
                        continue
                    lower_text = dialog.parameter_table.item(row, 5).text().strip()
                    upper_text = dialog.parameter_table.item(row, 6).text().strip()
                    step_text = dialog.parameter_table.item(row, 7).text().strip()
                    if not lower_text or not upper_text or not step_text:
                        raise ValueError(f"{name}: introduce límite inferior, superior y perturbación")
                    initial[name] = value
                    bounds[name] = (float(lower_text), float(upper_text))
                    perturbations[name] = float(step_text)
                if not initial:
                    raise ValueError("selecciona al menos un parámetro dinámico")
                option_by_name = {item[0]: item for item in rows}
                for name, value in initial.items():
                    lower, upper = bounds[name]
                    domain = option_by_name[name][3]
                    step = perturbations[name]
                    if not all(math.isfinite(item) for item in (lower, upper, step)):
                        raise ValueError(f"valores no finitos para {name}")
                    if lower >= upper or lower < domain[0] or upper > domain[1] or not lower <= value <= upper:
                        raise ValueError(f"límites no válidos para {name}")
                    if step <= 0 or value - step < lower or value + step > upper:
                        raise ValueError(f"perturbación no válida para {name}")
            except (TypeError, ValueError, OverflowError) as exc:
                self._set_run_status(f"Configuración de ajuste no guardada: {str(exc)[:500]}", "warning")
                return
            self.fit_configuration = {
                "initial_parameters": initial,
                "bounds": bounds,
                "perturbations": perturbations,
            }
            self.fit_configuration_status.setText(
                "Parámetros listos: " + ", ".join(initial) + " · límites y perturbaciones explícitos."
            )
            self._update_analysis_controls()

        def _update_analysis_controls(self) -> None:
            busy = self.run_in_progress
            has_data = self.observations is not None
            self.configure_fit_button.setEnabled(has_data and not busy)
            self.fit_button.setEnabled(has_data and self.fit_configuration is not None and not busy)
            self.run_button.setEnabled(has_data and not busy)
            self.load_data_button.setEnabled(not busy)
            self.parameter_group.setEnabled(not busy)

        def _show_observation_chart(self) -> None:
            self._clear_content()
            if self.observations is None:
                return
            chart = ScientificChartWidget({
                "title": "Observaciones semanales seleccionadas",
                "x_label": "Semana del conjunto · índice 1–56",
                "y_label": "Casos · conteo por 7 días",
                "series": [{
                    "name": self.observations.series_id,
                    "x": [float(index) for index in range(1, len(self.observations.counts) + 1)],
                    "y": list(self.observations.counts),
                }],
            }, self)
            chart.setObjectName("thesisSirObservedChart")
            self.content_stack.addWidget(chart)
            self.content_stack.setCurrentWidget(chart)

        def _collect_parameters(self) -> ThesisSIRParameters:
            values = {name: edit.text() for name, edit in self.parameter_fields.items()}
            rows: list[tuple[str, str, str]] = []
            for row in range(self.harmonic_table.rowCount()):
                cells = [self.harmonic_table.item(row, column) for column in range(3)]
                if any(cell is None or not cell.text().strip() for cell in cells):
                    raise ValueError(f"falta un coeficiente o frecuencia del armónico {row + 1}")
                rows.append(tuple(cell.text().strip() for cell in cells))
            return thesis_parameters_from_fields(
                self.harmonic_count.currentData(),
                values,
                rows,
                self.delay_days.currentData(),
            )

        def _confirmation_text(self, parameters: ThesisSIRParameters) -> str:
            if self.observations is None or self.source_path is None:
                raise ValueError("importa un JSON antes de simular")
            parameter_values = json.dumps(
                parameters.to_dict()["parameters"], ensure_ascii=False, allow_nan=False
            )
            return (
                f"Modelo: {THESIS_SIR_EQUATION_SET}\n"
                f"Fuente del modelo: {THESIS_SOURCE_REFERENCE} · PDF SHA-256 {THESIS_PDF_SHA256}\n"
                f"Datos: {self.source_path}\n"
                f"Serie: {self.observations.series_id} · {len(self.observations.counts)} semanas\n"
                f"SHA-256: {self.observations.source_sha256}\n"
                f"Parámetros explícitos: {parameter_values}\n"
                f"Integrador: RK4 fijo · Δt={self.max_step_combo.currentData():g} semanas · "
                f"máx. {MAX_STEPS_PER_INTERVAL} pasos/intervalo\n\n"
                "Se calculará en memoria con el motor científico incluido en SSEC. "
                "El archivo de datos no se modificará. ¿Confirmas la ejecución?"
            )

        def _analysis_confirmation_text(
            self, parameters: ThesisSIRParameters, output_parent: str | os.PathLike[str]
        ) -> str:
            if self.observations is None or self.source_path is None or self.fit_configuration is None:
                raise ValueError("se requieren observaciones y una configuración de ajuste válida")
            config = self.fit_configuration
            lines = [
                f"Modelo: {THESIS_SIR_EQUATION_SET}",
                f"Fuente: {THESIS_SOURCE_REFERENCE} · PDF SHA-256 {THESIS_PDF_SHA256}",
                f"Datos seleccionados: {self.source_path}",
                f"Serie: {self.observations.series_id} · {len(self.observations.counts)} semanas",
                f"SHA-256 de origen: {self.observations.source_sha256}",
                "Parámetros base: " + json.dumps(
                    parameters.to_dict()["parameters"], ensure_ascii=False, allow_nan=False
                ),
                "Parámetros ajustables: " + json.dumps(
                    config["initial_parameters"], ensure_ascii=False, allow_nan=False
                ),
                "Límites: " + json.dumps(config["bounds"], ensure_ascii=False, allow_nan=False),
                "Perturbaciones de sensibilidad: " + json.dumps(
                    config["perturbations"], ensure_ascii=False, allow_nan=False
                ),
                f"Integrador: RK4 fijo · Δt={self.max_step_combo.currentData():g} semanas · "
                f"máx. {MAX_STEPS_PER_INTERVAL} pasos/intervalo",
                f"Destino: se creará una subcarpeta nueva dentro de {Path(output_parent).expanduser()}",
                "Workspace que se escribirá: serie observada seleccionada, modelo, configuración "
                "del ajuste, resultados, bitácora y snapshots con SHA-256 del motor/código. "
                "No se copiará el JSON original ni la tesis.",
                "",
                "Se ejecutará el motor P3.31 local; no invoca modelos ni ejecuta código generado. "
                "Los archivos fuente no se modificarán. El ajuste no prueba identificabilidad ni "
                "validez científica; incertidumbre: NOT_CALCULATED.",
                "El cálculo no admite cancelación segura. ¿Confirmas el ajuste?",
            ]
            return "\n".join(lines)

        def start_parameter_fit(self) -> None:
            if self.run_in_progress:
                return
            if self.observations is None or self.source_path is None or self.fit_configuration is None:
                self._set_run_status(
                    "Importa datos y configura al menos un parámetro antes de ajustar.", "warning"
                )
                return
            try:
                parameters = self._collect_parameters()
            except (TypeError, ValueError, OverflowError) as exc:
                self._set_run_status(f"Parámetros del modelo inválidos: {str(exc)[:500]}", "warning")
                return
            output_parent = QtWidgets.QFileDialog.getExistingDirectory(
                self,
                "Seleccionar carpeta para el nuevo workspace de análisis",
                str(self.source_path.parent),
            )
            if not output_parent:
                return
            try:
                confirmation = self._analysis_confirmation_text(parameters, output_parent)
            except (TypeError, ValueError, OverflowError) as exc:
                self._set_run_status(f"No se puede confirmar el análisis: {str(exc)[:500]}", "warning")
                return
            answer = QtWidgets.QMessageBox.question(
                self,
                "Confirmar ajuste SIR",
                confirmation,
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                self._set_run_status("Ajuste no ejecutado · confirmación rechazada", "warning")
                return
            copied_config = {
                key: dict(value) for key, value in self.fit_configuration.items()
            }
            self.result_payload = None
            self.save_button.setEnabled(False)
            self.audit_button.setEnabled(False)
            self._clear_content()
            self.state = "RUNNING_ANALYSIS"
            self.progress_bar.setAccessibleName("Ajuste en curso; progreso no estimado")
            self.progress_bar.show()
            self._set_run_status(
                "Ajuste y sensibilidad en curso · progreso no estimado · no cancelable de forma segura",
                "active",
            )
            self._update_analysis_controls()
            worker = _ThesisSIRAnalysisWorker(
                parameters,
                self.observations,
                copied_config,
                float(self.max_step_combo.currentData()),
                output_parent,
                self,
            )
            worker.succeeded.connect(self._on_analysis_worker_success)
            worker.failed.connect(self._on_analysis_worker_failure)
            worker.finished.connect(self._on_analysis_worker_finished)
            self._analysis_worker = worker
            self._update_analysis_controls()
            worker.start()

        def _on_analysis_worker_success(self, workspace_path: str) -> None:
            self.state = "ANALYZED"
            self._set_run_status(
                "Análisis calculado y workspace verificado · NOT_ASSESSED / NOT_CALCULATED",
                "computed",
            )
            self.analysis_workspace_ready.emit(workspace_path)

        def _on_analysis_worker_failure(self, message: str) -> None:
            self.result_payload = None
            self.state = "FAILED"
            self.save_button.setEnabled(False)
            self.audit_button.setEnabled(False)
            self._clear_content()
            self._set_run_status(f"Falló el ajuste; no se cargaron resultados · {message[:1000]}", "error")

        def _on_analysis_worker_finished(self) -> None:
            worker = self._analysis_worker
            self._analysis_worker = None
            self.progress_bar.hide()
            self._update_analysis_controls()
            if worker is not None:
                worker.deleteLater()
            self.activity_finished.emit()

        def prepare_audit_workspace_dialog(self) -> None:
            if self.run_in_progress or self.observations is None or self.result_payload is None:
                self._set_run_status("Se requiere una simulación vigente para preparar la auditoría.", "warning")
                return
            initial = str(self.source_path.parent) if self.source_path is not None else str(Path.home())
            parent = QtWidgets.QFileDialog.getExistingDirectory(
                self, "Seleccionar carpeta para el bundle de auditoría", initial
            )
            if not parent:
                return
            try:
                parameters = self._collect_parameters()
            except (TypeError, ValueError, OverflowError) as exc:
                self._set_run_status(f"Parámetros inválidos; no se preparó bundle: {str(exc)[:400]}", "warning")
                return
            confirmation = (
                f"Crear una subcarpeta nueva dentro de:\n{Path(parent).expanduser()}\n\n"
                "Incluirá solo la serie DGE seleccionada, el modelo y parámetros, el resultado "
                "calculado y el código fuente exacto del motor/adaptador. El JSON original y la "
                "tesis no se copiarán ni modificarán.\n\n"
                "Esta acción es local y no invoca especialistas. Después podrás revisar y elegir "
                "recursos; enviarlos al CLI puede consumir cuota y requiere una confirmación separada.\n\n"
                "¿Preparar el bundle?"
            )
            answer = QtWidgets.QMessageBox.question(
                self,
                "Preparar workspace para auditoría",
                confirmation,
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                self._set_run_status("Bundle de auditoría no creado · confirmación rechazada", "warning")
                return
            try:
                workspace_root = write_thesis_sir_audit_workspace(
                    parent, self.observations, parameters, self.result_payload
                )
            except (OSError, TypeError, ValueError, RuntimeError) as exc:
                self._set_run_status(f"No se preparó el workspace de auditoría · {str(exc)[:700]}", "error")
                return
            self._set_run_status(
                "Audit workspace preparado · selecciona recursos y confirma el envío por separado",
                "info",
            )
            self.audit_workspace_ready.emit(str(workspace_root))

        def start_simulation(self) -> None:
            if self._worker is not None:
                return
            if self.observations is None:
                self._set_run_status("Importa el JSON de observaciones antes de simular.", "warning")
                return
            try:
                parameters = self._collect_parameters()
            except (TypeError, ValueError, OverflowError) as exc:
                self.state = "READY"
                self._set_run_status(f"Parámetros incompletos o inválidos: {str(exc)[:500]}", "warning")
                return
            answer = QtWidgets.QMessageBox.question(
                self,
                "Confirmar simulación SIR de tesis",
                self._confirmation_text(parameters),
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                self.state = "READY"
                self._set_run_status("Simulación no ejecutada · confirmación rechazada", "warning")
                return
            self.result_payload = None
            self.save_button.setEnabled(False)
            self._clear_content()
            self.state = "RUNNING"
            self.run_button.setEnabled(False)
            self.load_data_button.setEnabled(False)
            self.progress_bar.show()
            max_step = float(self.max_step_combo.currentData())
            self._set_run_status(
                f"Cálculo en curso · RK4 fijo · Δt={max_step:g} semanas · progreso no estimado",
                "active",
            )
            worker = _ThesisSIRWorker(
                parameters, self.observations, max_step, MAX_STEPS_PER_INTERVAL, self
            )
            worker.succeeded.connect(self._on_worker_success)
            worker.failed.connect(self._on_worker_failure)
            worker.finished.connect(self._on_worker_finished)
            self._worker = worker
            self._update_analysis_controls()
            worker.start()

        def _on_worker_success(self, payload: object) -> None:
            if not isinstance(payload, dict):
                self._on_worker_failure("resultado inválido del evaluador")
                return
            self.result_payload = payload
            self.state = "COMPUTED"
            self._set_run_status(
                "COMPUTED_FROM_DECLARED_INPUTS · validez, identificabilidad e "
                "incertidumbre estadística: NOT_ASSESSED", "computed"
            )
            self.save_button.setEnabled(True)
            self.audit_button.setEnabled(True)
            self._show_result_charts(payload)

        def _on_worker_failure(self, message: str) -> None:
            self.result_payload = None
            self.state = "FAILED"
            self.save_button.setEnabled(False)
            self.audit_button.setEnabled(False)
            self._clear_content()
            self._set_run_status(f"Fallo de simulación · {str(message)[:1000]}", "error")

        def _on_worker_finished(self) -> None:
            worker = self._worker
            self._worker = None
            self.progress_bar.hide()
            self.load_data_button.setEnabled(True)
            self.run_button.setEnabled(self.observations is not None)
            if worker is not None:
                worker.deleteLater()
            self._update_analysis_controls()
            self.activity_finished.emit()

        def _show_result_charts(self, payload: Mapping[str, object]) -> None:
            self._clear_content()
            prediction = payload.get("prediction")
            observations = payload.get("observations")
            if not isinstance(prediction, Mapping) or not isinstance(observations, Mapping):
                self._on_worker_failure("resultado sin observaciones o predicciones")
                return
            labels = observations.get("week_labels")
            observed = observations.get("counts")
            means = prediction.get("mean_cases")
            boundaries = prediction.get("state_boundary_times_week")
            states = prediction.get("states_at_boundaries_person")
            if not (isinstance(labels, list) and isinstance(observed, list)
                    and isinstance(means, list) and isinstance(boundaries, list)
                    and isinstance(states, list) and len(labels) == len(observed) == len(means)):
                self._on_worker_failure("resultado con dimensiones inconsistentes")
                return

            page = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(page)
            status = QtWidgets.QLabel(
                "Cálculo desde entradas declaradas · NOT_ASSESSED: validez científica, "
                "identificabilidad práctica e incertidumbre estadística."
            )
            status.setObjectName("scientificNotice")
            status.setWordWrap(True)
            layout.addWidget(status)
            chart_tabs = QtWidgets.QTabWidget(page)
            chart_tabs.setObjectName("thesisSirChartTabs")
            chart_tabs.setAccessibleName("Vistas gráficas de resultados SIR")
            fit_chart = ScientificChartWidget({
                "title": "Observado y media semanal predicha",
                "x_label": "Semana del conjunto · índice 1–56",
                "y_label": "Casos por 7 días · personas",
                "series": [
                    {"name": "Observado", "x": [float(i) for i in range(1, len(labels) + 1)],
                     "y": observed},
                    {"name": "Media predicha", "x": [float(i) for i in range(1, len(labels) + 1)],
                     "y": means},
                ],
            }, page)
            fit_chart.setObjectName("thesisSirFitChart")
            chart_tabs.addTab(fit_chart, "Observado vs. predicho")
            chart_tabs.setTabToolTip(
                0, "Compara los conteos observados con la media semanal calculada por el modelo."
            )

            if len(states) == len(boundaries) and states:
                compartment_chart = ScientificChartWidget({
                    "title": "Estados SIR en los límites de intervalo",
                    "x_label": "Tiempo relativo · semanas",
                    "y_label": "Personas · población fija",
                    "series": [
                        {"name": name, "x": boundaries,
                         "y": [state[index] for state in states]}
                        for index, name in enumerate(("S", "I", "R"))
                    ],
                }, page)
                compartment_chart.setObjectName("thesisSirCompartmentsChart")
                chart_tabs.addTab(compartment_chart, "Estados del modelo")
                chart_tabs.setTabToolTip(
                    1, "Muestra S, I y R en los límites de intervalo de la integración."
                )
            layout.addWidget(chart_tabs, 1)
            provenance = QtWidgets.QLabel(
                f"Serie {observations.get('series_id')} · fuente SHA-256 "
                f"{observations.get('source_sha256')} · semanas "
                f"{labels[0]}–{labels[-1]} · resultado sin ajuste automático."
            )
            provenance.setWordWrap(True)
            provenance.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            layout.addWidget(provenance)
            self.content_stack.addWidget(page)
            self.content_stack.setCurrentWidget(page)

        def export_result_dialog(self) -> None:
            if self.result_payload is None:
                return
            suggested = (
                str(self.source_path.with_name("thesis_sir_result.json"))
                if self.source_path is not None else "thesis_sir_result.json"
            )
            path, _filter = QtWidgets.QFileDialog.getSaveFileName(
                self, "Exportar resultado SIR", suggested, "JSON (*.json)"
            )
            if not path:
                return
            try:
                self.export_result_to(path)
            except (OSError, TypeError, ValueError) as exc:
                QtWidgets.QMessageBox.warning(self, "Resultado no exportado", str(exc)[:1000])

        def export_result_to(self, path: str | os.PathLike[str]) -> None:
            if self.result_payload is None:
                raise ValueError("no hay un resultado calculado para exportar")
            destination = Path(path).expanduser().resolve(strict=False)
            if self.source_path is not None:
                try:
                    if destination == self.source_path or (
                        destination.exists() and os.path.samefile(destination, self.source_path)
                    ):
                        raise ValueError("cannot overwrite the selected data source")
                except OSError as exc:
                    raise ValueError("cannot verify result destination against data source") from exc
            encoded = json.dumps(
                self.result_payload,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            ).encode("utf-8")
            output = QSaveFile(str(destination))
            if not output.open(QIODevice.OpenModeFlag.WriteOnly):
                raise OSError(output.errorString())
            written = output.write(encoded)
            if written != len(encoded):
                output.cancelWriting()
                raise OSError(output.errorString() or "short result write")
            if not output.commit():
                raise OSError(output.errorString())

else:
    class ThesisSIRPage:  # pragma: no cover - optional Qt dependency.
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("ThesisSIRPage requires PySide6")
