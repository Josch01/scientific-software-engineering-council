"""Optional Tkinter application for opening safe scientific workspaces."""
from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
import math
from pathlib import Path
import queue
import sys
import threading
from typing import Callable

try:
    from .scientific_workspace_actions import (
        ApprovedSimulationAction,
        request_approved_simulation,
        run_approved_simulation,
        sir_simulation_actions_for_workspace,
    )
    from .scientific_workspace_loader import load_scientific_workspace
    from .scientific_workspace_loader import LoadedWorkspace
    from .scientific_workspace_view import (
        ComponentView,
        WorkspaceViewModel,
        build_workspace_view_model,
        sanitize_display_text,
    )
except ImportError:  # Support `python scripts/scientific_workspace_app.py`.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.scientific_workspace_actions import (
        ApprovedSimulationAction,
        request_approved_simulation,
        run_approved_simulation,
        sir_simulation_actions_for_workspace,
    )
    from scripts.scientific_workspace_loader import load_scientific_workspace
    from scripts.scientific_workspace_loader import LoadedWorkspace
    from scripts.scientific_workspace_view import (
        ComponentView,
        WorkspaceViewModel,
        build_workspace_view_model,
        sanitize_display_text,
    )


MAX_TABLE_ROWS = 1_000
_SERIES_COLORS = ("#075985", "#9A3412", "#166534", "#6B21A8", "#155E75")
_SERIES_DASHES = ((), (7, 3), (2, 2), (8, 2, 2, 2), (4, 2))


def _approved_action_for(
    component: ComponentView,
    workspace: LoadedWorkspace | None,
    approved_simulations: Mapping[str, ApprovedSimulationAction],
) -> ApprovedSimulationAction | None:
    if (workspace is None or component.component_type != "simulation_plot"
            or not isinstance(approved_simulations, Mapping)):
        return None
    action = approved_simulations.get(component.component_id)
    if (not isinstance(action, ApprovedSimulationAction)
            or action.workspace_id != workspace.summary.workspace_id):
        return None
    return action


def _simulation_actions_for_workspace(
    workspace: LoadedWorkspace | None,
    host_actions: Mapping[str, ApprovedSimulationAction],
) -> tuple[dict[str, ApprovedSimulationAction], str | None]:
    actions: dict[str, ApprovedSimulationAction] = {}
    error = None
    if workspace is not None:
        try:
            actions.update(sir_simulation_actions_for_workspace(workspace))
        except (TypeError, ValueError) as exc:
            error = str(exc)
    actions.update(host_actions)
    return actions, error


def _run_simulation_ticket_for_ui(ticket):
    """Always return a terminal queue payload so Tk can restore its controls."""
    try:
        return "ok", run_approved_simulation(ticket)
    except BaseException as exc:
        return "error", f"{type(exc).__name__}: {exc}"[:2000]


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _format_json(value: object) -> str:
    rendered = json.dumps(_thaw(value), ensure_ascii=False, indent=2, sort_keys=True)
    return sanitize_display_text(rendered)


def _sample_indices(row_count: int, limit: int = MAX_TABLE_ROWS) -> tuple[int, ...]:
    if row_count <= limit:
        return tuple(range(row_count))
    if limit <= 1:
        return (0,)
    return tuple(round(index * (row_count - 1) / (limit - 1)) for index in range(limit))


def _readonly_text(parent, text: str, tk, ttk, *, height: int = 14) -> None:
    frame = ttk.Frame(parent)
    frame.pack(fill="both", expand=True, padx=8, pady=6)
    content = tk.Text(
        frame,
        wrap="none",
        height=height,
        undo=False,
        borderwidth=1,
        relief="solid",
        font="TkFixedFont",
    )
    y_scroll = ttk.Scrollbar(frame, orient="vertical", command=content.yview)
    x_scroll = ttk.Scrollbar(frame, orient="horizontal", command=content.xview)
    content.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
    content.grid(row=0, column=0, sticky="nsew")
    y_scroll.grid(row=0, column=1, sticky="ns")
    x_scroll.grid(row=1, column=0, sticky="ew")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    content.insert("1.0", text)
    content.configure(state="disabled")


def _render_json(parent, component: ComponentView, tk, ttk) -> None:
    preview = component.preview_text or _format_json(component.content)
    _readonly_text(parent, preview, tk, ttk)


def _render_code(parent, component: ComponentView, tk, ttk) -> None:
    _readonly_text(parent, str(component.content), tk, ttk, height=18)


def _render_artifact_browser(parent, component: ComponentView, tk, ttk) -> None:
    resources = component.content or ()
    columns = ("kind", "path", "bytes", "sha256")
    tree = ttk.Treeview(parent, columns=columns, show="tree headings", height=12)
    tree.heading("#0", text="Resource ID")
    tree.column("#0", width=150, stretch=False)
    for name, label, width in (
        ("kind", "Type", 130),
        ("path", "Project path", 260),
        ("bytes", "Bytes", 80),
        ("sha256", "SHA-256", 150),
    ):
        tree.heading(name, text=label)
        tree.column(name, width=width, stretch=name == "path")
    for resource in resources:
        tree.insert(
            "",
            "end",
            text=resource.resource_id,
            values=(resource.kind, resource.path, resource.byte_count, resource.sha256),
        )
    tree.pack(fill="both", expand=True, padx=8, pady=6)


def _make_data_table(parent, columns: tuple[str, ...], rows, ttk, *, height: int = 12) -> None:
    frame = ttk.Frame(parent)
    frame.pack(fill="both", expand=True, padx=8, pady=6)
    tree = ttk.Treeview(frame, columns=columns, show="headings", height=height)
    vertical = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    horizontal = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    for column in columns:
        tree.heading(column, text=column)
        tree.column(column, width=max(90, min(220, len(column) * 10)), stretch=True)
    for row in rows:
        tree.insert("", "end", values=row)
    tree.grid(row=0, column=0, sticky="nsew")
    vertical.grid(row=0, column=1, sticky="ns")
    horizontal.grid(row=1, column=0, sticky="ew")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)


def _render_observations(parent, component: ComponentView, tk, ttk) -> None:
    content = component.content
    units = content["variable_units"]
    safe_time_unit = sanitize_display_text(str(content["time_unit"]))
    columns = (f"Time ({safe_time_unit})",) + tuple(
        f"{sanitize_display_text(str(name))} ({sanitize_display_text(str(unit))})"
        for name, unit in units.items()
    )
    times = content["times"]
    observations = content["observations"]
    indices = _sample_indices(len(times))
    rows = []
    variable_names = tuple(units)
    for index in indices:
        row = observations[index]
        rows.append(
            (format(times[index], ".7g"),)
            + tuple(format(row[name], ".7g") if name in row else "—" for name in variable_names)
        )
    if len(indices) < len(times):
        ttk.Label(
            parent,
            text=f"Mostrando {len(indices):,} filas espaciadas de {len(times):,}; el recurso completo sigue intacto.",
            anchor="w",
        ).pack(fill="x", padx=8)
    _make_data_table(parent, columns, rows, ttk)
    provenance = _format_json(content["provenance"])
    ttk.Label(
        parent,
        text=f"Procedencia declarada: {provenance} · digest del contrato: {content['content_sha256']}",
        wraplength=900,
        justify="left",
    ).pack(fill="x", padx=8, pady=(0, 8))


def _range_fraction(value: float, minimum: float, maximum: float) -> float:
    if maximum == minimum:
        return 0.5
    span = maximum - minimum
    if math.isfinite(span):
        return (value - minimum) / span
    scale = max(abs(minimum), abs(maximum))
    lower_scaled = minimum / scale
    upper_scaled = maximum / scale
    return (value / scale - lower_scaled) / (upper_scaled - lower_scaled)


def _range_interpolate(minimum: float, maximum: float, fraction: float) -> float:
    if fraction <= 0.0:
        return minimum
    if fraction >= 1.0:
        return maximum
    scale = max(abs(minimum), abs(maximum), 1.0)
    scaled = minimum / scale + fraction * (maximum / scale - minimum / scale)
    return scaled * scale


def _render_simulation(parent, component: ComponentView, tk, ttk) -> None:
    content = component.content
    times = content["times"]
    series_names = content["series_names"]
    series_indices = content["series_indices"]
    values = content["values"]
    row_count = content["row_count"]
    summary = (
        f"Método declarado: {content['method']} · {row_count:,} filas · "
        "unidades no incluidas en el contrato de simulación"
    )
    ttk.Label(parent, text=summary, anchor="w").pack(fill="x", padx=8, pady=(6, 0))
    plotted_count = min(len(series_names), len(_SERIES_COLORS))
    legend = ttk.Frame(parent)
    legend.pack(fill="x", padx=8, pady=(4, 0))
    for series_index in range(plotted_count):
        holder = ttk.Frame(legend, padding=(2, 1))
        holder.grid(row=series_index // 3, column=series_index % 3, sticky="w")
        swatch = tk.Canvas(holder, width=34, height=18, highlightthickness=0, background="#F7F9FA")
        swatch.create_line(
            2,
            9,
            32,
            9,
            fill=_SERIES_COLORS[series_index],
            width=2,
            dash=_SERIES_DASHES[series_index],
        )
        swatch.pack(side="left", padx=(0, 4))
        ttk.Label(holder, text=series_names[series_index], wraplength=190).pack(side="left")
    if len(series_names) > plotted_count:
        ttk.Label(
            parent,
            text=f"La gráfica muestra {plotted_count} de {len(series_names)} series; la tabla incluye todas.",
            anchor="w",
        ).pack(fill="x", padx=8)
    chart = tk.Canvas(parent, height=300, background="#FFFFFF", highlightthickness=1, highlightbackground="#64748B")
    chart.pack(fill="x", expand=False, padx=8, pady=6)

    def redraw(_event=None) -> None:
        chart.delete("all")
        width = max(chart.winfo_width(), 320)
        height = max(chart.winfo_height(), 220)
        left, right, top, bottom = 64, width - 18, 24, height - 45
        selected = _sample_indices(len(times), 1_000)
        plotted_indices = series_indices[:plotted_count]
        plotted_values = [row[index] for row in values for index in plotted_indices]
        minimum_y = min(plotted_values)
        maximum_y = max(plotted_values)
        minimum_x, maximum_x = times[0], times[-1]

        for tick in range(5):
            fraction = tick / 4
            y = bottom - fraction * (bottom - top)
            value = _range_interpolate(minimum_y, maximum_y, fraction)
            chart.create_line(left, y, right, y, fill="#D4DDE3", dash=(2, 3))
            chart.create_text(left - 7, y, text=f"{value:.4g}", anchor="e", fill="#1F2937")
        chart.create_line(left, top, left, bottom, fill="#334155")
        chart.create_line(left, bottom, right, bottom, fill="#334155")
        chart.create_text((left + right) / 2, height - 14, text="Time (unit not supplied)", fill="#111827")
        chart.create_text(14, (top + bottom) / 2, text="State value\n(unit not supplied)", fill="#111827")
        chart.create_text(left, bottom + 17, text=f"{times[0]:.4g}", anchor="w", fill="#1F2937")
        chart.create_text(right, bottom + 17, text=f"{times[-1]:.4g}", anchor="e", fill="#1F2937")
        for series_index, state_index in enumerate(plotted_indices):
            points = []
            for index in selected:
                x = left + _range_fraction(times[index], minimum_x, maximum_x) * (right - left)
                y_value = values[index][state_index]
                y = bottom - _range_fraction(y_value, minimum_y, maximum_y) * (bottom - top)
                points.extend((x, y))
            if len(points) >= 4:
                chart.create_line(
                    *points,
                    fill=_SERIES_COLORS[series_index],
                    width=2,
                    dash=_SERIES_DASHES[series_index],
                )

    chart.bind("<Configure>", redraw)
    redraw()
    indices = _sample_indices(len(times))
    if len(indices) < len(times):
        ttk.Label(
            parent,
            text=f"Tabla: {len(indices):,} filas distribuidas en el intervalo; gráfica muestreada de {row_count:,} puntos.",
            anchor="w",
        ).pack(fill="x", padx=8)
    columns = ("Time",) + tuple(series_names)
    rows = [
        (format(times[index], ".7g"),)
        + tuple(format(values[index][state_index], ".7g") for state_index in series_indices)
        for index in indices
    ]
    _make_data_table(parent, columns, rows, ttk, height=8)


def _render_component(
    parent,
    component: ComponentView,
    tk,
    ttk,
    *,
    run_action=None,
    run_label: str = "Ejecutar simulación aprobada",
):
    frame = ttk.LabelFrame(parent, text=component.title, padding=6)
    frame.pack(fill="both", expand=True, padx=8, pady=6)
    if component.status == "error":
        ttk.Label(frame, text=component.message, foreground="#9B1C1C", wraplength=850).pack(
            fill="x", anchor="w", padx=8, pady=8
        )
        if run_action is not None:
            action_button = ttk.Button(frame, text=run_label, command=run_action)
            action_button.pack(anchor="w", padx=8, pady=6)
            return action_button
        return None
    ttk.Label(frame, text=component.message, wraplength=1000, justify="left").pack(
        fill="x", anchor="w", padx=8, pady=(4, 0)
    )
    action_button = None
    if run_action is not None:
        action_button = ttk.Button(frame, text=run_label, command=run_action)
        action_button.pack(anchor="w", padx=8, pady=6)
    renderer = COMPONENT_RENDERERS.get(component.component_type, _render_json)
    renderer(frame, component, tk, ttk)
    return action_button


COMPONENT_RENDERERS: Mapping[str, Callable] = {
    "equation_view": _render_json,
    "parameter_table": _render_json,
    "observation_table": _render_observations,
    "simulation_plot": _render_simulation,
    "fit_summary": _render_json,
    "sensitivity_plot": _render_json,
    "uncertainty_summary": _render_json,
    "audit_summary": _render_json,
    "artifact_browser": _render_artifact_browser,
    "code_view": _render_code,
}


def _scrollable_frame(parent, tk, ttk):
    container = ttk.Frame(parent)
    canvas = tk.Canvas(container, highlightthickness=0)
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    inner = ttk.Frame(canvas)
    window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
    inner.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind(
        "<Configure>",
        lambda event: canvas.itemconfigure(window_id, width=event.width),
    )
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")
    container.rowconfigure(0, weight=1)
    container.columnconfigure(0, weight=1)
    return container, inner


def _create_window_root(tk, parent):
    """Reuse the supervisor's Tk event loop when opening a workspace child."""
    return tk.Tk() if parent is None else tk.Toplevel(parent)


def _project_root_hint(project_root: str | Path | None) -> Path | None:
    """Return an existing project directory for file-dialog initialization."""
    if project_root is None or (isinstance(project_root, str) and not project_root.strip()):
        return None
    try:
        candidate = Path(project_root).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError):
        return None
    return candidate if candidate.is_dir() else None


def create_workspace_window(
    view_model: WorkspaceViewModel | None,
    *,
    parent=None,
    project_root: str | Path | None = None,
    loaded_workspace: LoadedWorkspace | None = None,
    approved_simulations: Mapping[str, ApprovedSimulationAction] | None = None,
):
    """Create the reusable Tk window; importing this module alone stays headless."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = _create_window_root(tk, parent)
    project_hint = _project_root_hint(project_root)
    root.title("SSEC · Scientific Workspace")
    root.minsize(900, 620)
    if parent is not None:
        root.transient(parent)
    style = ttk.Style(root)
    style.configure("TNotebook.Tab", padding=(12, 8))
    style.configure("WorkspaceNotice.TLabel", foreground="#0F3D45", background="#E8F1F4", padding=8)
    style.configure("WorkspaceTitle.TLabel", font=("TkDefaultFont", 15, "bold"))

    header = ttk.Frame(root, padding=(12, 10))
    header.pack(fill="x")
    title_var = tk.StringVar(value="Centro de Control Científico")
    ttk.Label(header, textvariable=title_var, style="WorkspaceTitle.TLabel").pack(side="left")
    status_var = tk.StringVar(value="Sin espacio científico abierto")
    ttk.Label(header, textvariable=status_var).pack(side="right", padx=(12, 0))
    open_button = ttk.Button(header, text="Abrir espacio…")
    open_button.pack(side="right")
    notice_var = tk.StringVar(
        value=(
            "Los digests de los artefactos coinciden con el manifiesto. "
            "Esto no valida el modelo, su precisión ni su validez científica."
        )
    )
    notice = ttk.Label(
        root,
        textvariable=notice_var,
        style="WorkspaceNotice.TLabel",
        wraplength=1200,
        justify="left",
    )
    notice.pack(fill="x", padx=12, pady=(0, 8))

    body = ttk.Panedwindow(root, orient="horizontal")
    body.pack(fill="both", expand=True, padx=12, pady=(0, 12))
    resource_panel = ttk.LabelFrame(body, text="Recursos cargados", padding=6)
    content_panel = ttk.Frame(body)
    body.add(resource_panel, weight=1)
    body.add(content_panel, weight=4)
    resource_tree = ttk.Treeview(resource_panel, columns=("kind", "bytes"), show="tree headings")
    resource_tree.heading("#0", text="ID / project path")
    resource_tree.heading("kind", text="Type")
    resource_tree.heading("bytes", text="Bytes")
    resource_tree.column("#0", width=190, stretch=True)
    resource_tree.column("kind", width=100, stretch=False)
    resource_tree.column("bytes", width=72, stretch=False, anchor="e")
    resource_tree.pack(fill="both", expand=True)
    notebook = ttk.Notebook(content_panel)
    notebook.pack(fill="both", expand=True)

    def display(model: WorkspaceViewModel | None) -> None:
        for page in result_tabs.values():
            notebook.forget(page)
            page.destroy()
        result_tabs.clear()
        simulation_buttons.clear()
        for tab in notebook.tabs():
            notebook.forget(tab)
        for item in resource_tree.get_children():
            resource_tree.delete(item)
        if model is None:
            title_var.set("Centro de Control Científico")
            status_var.set("Sin espacio científico abierto")
            notice_var.set(
                "Los artefactos cargados se verificarán antes de mostrarse. "
                "La visualización no valida el modelo ni su validez científica."
            )
            empty = ttk.Frame(notebook, padding=24)
            ttk.Label(
                empty,
                text="Abra un manifiesto de espacio científico para cargar sus secciones y artefactos.",
                wraplength=680,
                justify="left",
            ).pack(anchor="w")
            notebook.add(empty, text="Inicio")
            return
        title_var.set(model.title)
        status_var.set(
            f"{len(model.sections)} secciones · {len(model.resources)} recursos · "
            f"{model.verification_status}"
        )
        notice_text = (
            "Los digests de los artefactos coinciden con el manifiesto. "
            "Esto no valida el modelo, su precisión ni su validez científica."
        )
        current_actions, action_error = _simulation_actions_for_workspace(
            active_workspace[0], host_approved_simulations
        )
        active_simulation_actions[0] = current_actions
        if action_error:
            notice_text += (
                " Acción SIR deshabilitada: "
                f"{sanitize_display_text(action_error)}."
            )
        if model.omitted_component_count:
            notice_text += (
                f" Interfaz limitada: se omitieron {model.omitted_component_count} componentes "
                f"(máximo {model.omitted_component_count + sum(len(s.components) for s in model.sections)} mostrados)."
            )
        notice_var.set(notice_text)
        for resource in model.resources:
            resource_tree.insert(
                "", "end", text=f"{resource.resource_id}\n{resource.path}",
                values=(resource.kind, resource.byte_count),
            )
        for section in model.sections:
            page, inner = _scrollable_frame(notebook, tk, ttk)
            if section.omitted_component_count:
                ttk.Label(
                    inner,
                    text=f"Omitidos {section.omitted_component_count} componentes por el límite de la interfaz.",
                    foreground="#7C2D12",
                ).pack(fill="x", padx=8, pady=6)
            for component in section.components:
                action = _approved_action_for(
                    component, active_workspace[0], active_simulation_actions[0]
                )
                if action is None:
                    _render_component(inner, component, tk, ttk)
                    continue
                button_ref = {}

                def invoke(component=component, action=action, button_ref=button_ref):
                    run_simulation(component, action, button_ref["button"])

                button = _render_component(
                    inner,
                    component,
                    tk,
                    ttk,
                    run_action=invoke,
                    run_label=f"Ejecutar: {action.label}",
                )
                button_ref["button"] = button
                simulation_buttons[component.component_id] = button
            notebook.add(page, text=section.title)

    def open_workspace() -> None:
        if active_simulation[0] is not None:
            return
        selected_root = project_hint
        if selected_root is None:
            selected_root = filedialog.askdirectory(parent=root, title="Seleccionar raíz del proyecto")
            if not selected_root:
                return
        selected_manifest = filedialog.askopenfilename(
            parent=root,
            title="Seleccionar manifiesto del espacio científico",
            initialdir=str(selected_root),
            filetypes=(("Workspace manifest", "*.json"), ("All files", "*")),
        )
        if not selected_manifest:
            return
        try:
            root_path = Path(selected_root).resolve(strict=True)
            manifest_path = Path(selected_manifest).resolve(strict=True)
            relative_manifest = manifest_path.relative_to(root_path).as_posix()
            workspace = load_scientific_workspace(root_path, relative_manifest)
            model = build_workspace_view_model(workspace)
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror("No se pudo abrir el espacio", str(exc), parent=root)
            return
        active_workspace[0] = workspace
        display(model)

    open_button.configure(command=open_workspace)
    root.bind("<Control-o>", lambda _event: open_workspace())
    active_workspace = [loaded_workspace]
    host_approved_simulations = dict(approved_simulations or {})
    active_simulation_actions = [host_approved_simulations]
    simulation_buttons: dict[str, object] = {}
    result_tabs: dict[str, object] = {}
    active_simulation = [None]

    def show_simulation_result(component: ComponentView, result: ComponentView) -> None:
        previous = result_tabs.pop(component.component_id, None)
        if previous is not None:
            notebook.forget(previous)
            previous.destroy()
        page = ttk.Frame(notebook)
        _render_component(page, result, tk, ttk)
        notebook.add(page, text=f"Resultado · {component.title}")
        result_tabs[component.component_id] = page
        notebook.select(page)

    def run_simulation(component: ComponentView, action: ApprovedSimulationAction,
                       button) -> None:
        if active_simulation[0] is not None:
            return
        workspace = active_workspace[0]
        if workspace is None:
            messagebox.showerror(
                "No hay recursos verificados",
                "Abra primero un workspace validado por el loader seguro.",
                parent=root,
            )
            return
        try:
            ticket = request_approved_simulation(
                action,
                workspace,
                component,
                confirm=lambda prompt: messagebox.askyesno(
                    "Confirmar ejecución de callback", prompt, parent=root
                ),
            )
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror("No se pudo preparar la simulación", str(exc), parent=root)
            return
        if ticket is None:
            return
        for action_button in simulation_buttons.values():
            action_button.configure(state="disabled")
        button.configure(text="Ejecutando…")
        open_button.configure(state="disabled")
        status_var.set("Simulación en curso · callback aprobado · SIN VALIDACIÓN CIENTÍFICA")
        root.update_idletasks()

        result_queue = queue.Queue()
        active_simulation[0] = {"queue": result_queue, "component": component}

        def worker() -> None:
            result_queue.put(_run_simulation_ticket_for_ui(ticket))

        thread = threading.Thread(
            target=worker,
            name=f"ssec-simulation-{component.component_id}",
            daemon=True,
        )
        try:
            thread.start()
        except RuntimeError as exc:
            active_simulation[0] = None
            open_button.configure(state="normal")
            for action_button in simulation_buttons.values():
                action_button.configure(state="normal")
            button.configure(text=f"Ejecutar: {action.label}")
            messagebox.showerror("No se pudo iniciar la simulación", str(exc), parent=root)
            return
        root.after(100, poll_simulation_result)

    def poll_simulation_result() -> None:
        active = active_simulation[0]
        if active is None:
            return
        try:
            outcome, payload = active["queue"].get_nowait()
        except queue.Empty:
            root.after(100, poll_simulation_result)
            return
        component = active["component"]
        active_simulation[0] = None
        open_button.configure(state="normal")
        for component_id, action_button in simulation_buttons.items():
            action_button.configure(state="normal")
            action = active_simulation_actions[0].get(component_id)
            if action is not None:
                action_button.configure(text=f"Ejecutar: {action.label}")
        if outcome == "error":
            status_var.set("Simulación fallida · resultado no publicado")
            messagebox.showerror(
                "No se pudo mostrar el resultado",
                payload,
                parent=root,
            )
        else:
            status_var.set("Resultado de simulación en memoria · NO VALIDADO CIENTÍFICAMENTE")
            show_simulation_result(component, payload)

    # Component rendering occurs after all action handlers are defined so button
    # closures bind to the active, SHA-256-verified workspace.
    display(view_model)
    return root


def _check_report(view_model: WorkspaceViewModel) -> dict[str, object]:
    components = [component for section in view_model.sections for component in section.components]
    errors = [
        {"component_id": component.component_id, "message": component.message}
        for component in components
        if component.status != "ok"
    ]
    status = "VIEW_ERRORS" if errors else "VIEW_LIMITED" if view_model.omitted_component_count else "VIEW_PREPARED"
    return {
        "status": status,
        "artifact_status": view_model.verification_status,
        "workspace_id": view_model.workspace_id,
        "section_count": len(view_model.sections),
        "component_count": len(components) + view_model.omitted_component_count,
        "rendered_component_count": len(components),
        "omitted_component_count": view_model.omitted_component_count,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", help="project root used by the safe resource loader")
    parser.add_argument("--check", action="store_true", help="prepare view data without importing Tkinter")
    parser.add_argument("manifest", nargs="?", help="project-relative workspace manifest")
    arguments = parser.parse_args(argv)
    if arguments.check and (not arguments.project_root or not arguments.manifest):
        parser.error("--check requires --project-root and a manifest path")
    if bool(arguments.project_root) != bool(arguments.manifest):
        parser.error("--project-root and manifest must be provided together")

    model = None
    loaded_workspace = None
    if arguments.manifest:
        try:
            loaded_workspace = load_scientific_workspace(
                arguments.project_root, arguments.manifest
            )
            model = build_workspace_view_model(loaded_workspace)
        except (OSError, TypeError, ValueError, RecursionError) as exc:
            print(json.dumps({"status": "INVALID", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 2

    if arguments.check:
        report = _check_report(model)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0 if report["status"] == "VIEW_PREPARED" else 2

    try:
        import tkinter
    except ImportError as exc:
        print(f"SSEC desktop UI is unavailable: {exc}", file=sys.stderr)
        return 2
    try:
        root = create_workspace_window(model, loaded_workspace=loaded_workspace)
        root.mainloop()
    except (OSError, tkinter.TclError) as exc:
        print(f"SSEC desktop UI is unavailable: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
