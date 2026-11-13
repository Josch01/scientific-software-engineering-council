"""Qt workspace for explicit, human-confirmed thesis SIR simulations."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
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
        THESIS_SIR_EQUATION_SET,
        THESIS_SIR_POPULATION,
        ThesisSIRParameters,
        WeeklyCountObservations,
        evaluate_thesis_sir_weekly_counts,
    )


MAX_STEPS_PER_INTERVAL = 20
MAX_STEP_WEEKS = 0.1
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
THESIS_SOURCE_REFERENCE = "Capítulo 3 · ecuaciones 3.1–3.8 · pp. impresas 9–11"
THESIS_PDF_SHA256 = "aa8ecad90a2d52942081b40fd78849d2dc4b280bbcb4b5bd828e4812dfec5486"


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


if QtWidgets is not None:
    class _ThesisSIRWorker(QtCore.QThread):
        succeeded = QtCore.Signal(object)
        failed = QtCore.Signal(str)

        def __init__(self, parameters, observations, parent=None):
            super().__init__(parent)
            self._parameters = parameters
            self._observations = observations

        def run(self) -> None:
            try:
                result = evaluate_thesis_sir_weekly_counts(
                    self._parameters,
                    self._observations,
                    max_step=MAX_STEP_WEEKS,
                    max_steps_per_interval=MAX_STEPS_PER_INTERVAL,
                )
                self.succeeded.emit(result.to_dict())
            except Exception as exc:
                self.failed.emit(f"{type(exc).__name__}: {str(exc)[:1000]}")


    class ThesisSIRPage(QtWidgets.QWidget):
        """Project-independent UI for read-only DGE import and thesis SIR runs."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setObjectName("thesisSIRPage")
            self.observations: WeeklyCountObservations | None = None
            self.source_path: Path | None = None
            self.result_payload: dict[str, object] | None = None
            self.state = "EMPTY"
            self._worker: _ThesisSIRWorker | None = None
            self._build_ui()

        @property
        def run_in_progress(self) -> bool:
            return self._worker is not None

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
                ("INTEGRADOR", "RK4 · paso máximo 0.1 semanas"),
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
            parameter_layout.addLayout(form)
            model_bounds = QtWidgets.QLabel(
                "γ se expresa en 1/semana. Introduce todos los valores; SSEC no asigna "
                "parámetros predeterminados ni ajusta el modelo automáticamente."
            )
            model_bounds.setObjectName("thesisSirHelperText")
            model_bounds.setWordWrap(True)
            parameter_layout.addWidget(model_bounds)
            setup_layout.addWidget(parameter_group)
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
            self.save_button = QtWidgets.QPushButton("Exportar resultado…")
            self.save_button.setObjectName("saveThesisSirResultButton")
            self.save_button.setEnabled(False)
            self.save_button.setMinimumHeight(42)
            self.save_button.clicked.connect(self.export_result_dialog)
            actions.addWidget(self.save_button, 1)
            results_layout.addLayout(actions)
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
            had_result_or_empty_state = (
                self.result_payload is not None
                or self.content_stack.currentWidget() is self.empty_state
            )
            self.result_payload = None
            self.save_button.setEnabled(False)
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
            self.run_button.setEnabled(False)
            self.save_button.setEnabled(False)
            self._clear_content()
            self.state = "EMPTY"
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
                f"Integrador: RK4 fijo · Δt={MAX_STEP_WEEKS:g} semanas · "
                f"máx. {MAX_STEPS_PER_INTERVAL} pasos/intervalo\n\n"
                "Se calculará en memoria con el motor científico incluido en SSEC. "
                "El archivo de datos no se modificará. ¿Confirmas la ejecución?"
            )

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
            self._set_run_status("Cálculo en curso · RK4 fijo · progreso no estimado", "active")
            worker = _ThesisSIRWorker(parameters, self.observations, self)
            worker.succeeded.connect(self._on_worker_success)
            worker.failed.connect(self._on_worker_failure)
            worker.finished.connect(self._on_worker_finished)
            self._worker = worker
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
            self._show_result_charts(payload)

        def _on_worker_failure(self, message: str) -> None:
            self.result_payload = None
            self.state = "FAILED"
            self.save_button.setEnabled(False)
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
