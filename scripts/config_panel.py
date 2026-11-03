#!/usr/bin/env python3
"""SSEC local graphical policy panel (Tkinter). No network or AI execution."""
from __future__ import annotations

import argparse
import json
import sys
import subprocess
import uuid
from pathlib import Path

if __package__:
    from .configuration import (AUDIT_LEVELS, DEFAULT_CONFIG, PERMISSIONS,
                                PROVIDERS, config_path, load_config, save_config,
                                validate_config)
    from .prepare_agents import prepare
else:
    from configuration import (AUDIT_LEVELS, DEFAULT_CONFIG, PERMISSIONS,
                               PROVIDERS, config_path, load_config, save_config,
                               validate_config)
    from prepare_agents import prepare


UI_NOTE = (
    "SSEC prepara perfiles y puede ejecutar auditorías bajo confirmación explícita. "
    "No garantiza aislamiento del SO ni limita el coste real en USD."
)


def build_policy(provider: str, cap: str | int, permissions: str,
                 minutes: str | int, cost: str | float,
                 audit: str) -> dict:
    """Separates validated UI state from any visible toolkit dependency."""
    try:
        cap_value = int(cap)
        minutes_value = int(minutes)
        cost_value = float(cost)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("Los límites deben ser números válidos") from exc
    if str(cap).strip() != str(cap_value) or str(minutes).strip() != str(minutes_value):
        raise ValueError("Los límites de agentes y minutos deben ser enteros")
    return validate_config({
        "schema_version": 1,
        "provider_mode": provider,
        "max_parallel_agents": cap_value,
        "permissions": permissions,
        "budget": {"max_runtime_minutes": minutes_value,
                   "max_estimated_cost_usd": cost_value},
        "audit_level": audit,
    })


def open_scientific_workspace(parent, project_root, *, window_factory=None):
    """Open the workspace view as a child of the already-running supervisor."""
    if window_factory is None:
        if __package__:
            from .scientific_workspace_app import create_workspace_window
        else:
            from scientific_workspace_app import create_workspace_window
        window_factory = create_workspace_window
    return window_factory(None, parent=parent, project_root=project_root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="headless smoke test without importing GUI")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--task", type=Path, default=Path(__file__).resolve().parents[1]
                        / "examples/seir_desktop_audit.json")
    args = parser.parse_args()
    if args.check:
        assert build_policy("gemini", "2", "read_only", "60", "10", "standard")
        print("GUI model valid (headless check); no desktop window opened")
        return 0
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError:
        print("Tkinter no está instalado en este Python. Instala python3-tk o usa --check.",
              file=sys.stderr)
        return 2

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"No se puede abrir la GUI: {exc}. Se requiere escritorio con pantalla.",
              file=sys.stderr)
        return 2
    root.title("SSEC · Control de especialistas")
    root.geometry("885x760")
    root.minsize(770, 630)
    root.configure(bg="#f4f7fc")
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    style.configure("Main.TFrame", background="#f4f7fc")
    style.configure("Panel.TFrame", background="white")
    style.configure("Main.TLabel", background="#f4f7fc", foreground="#344054",
                    font=("Segoe UI", 10))
    style.configure("Header.TLabel", background="#f4f7fc", foreground="#10243a",
                    font=("Segoe UI", 19, "bold"))
    style.configure("Note.TLabel", background="#f4f7fc", foreground="#596477",
                    font=("Segoe UI", 9))
    style.configure("Panel.TLabel", background="white", foreground="#263849",
                    font=("Segoe UI", 10))
    style.configure("Panel.TButton", padding=(12, 8))

    provider = tk.StringVar(value=DEFAULT_CONFIG["provider_mode"])
    parallel = tk.StringVar(value=str(DEFAULT_CONFIG["max_parallel_agents"]))
    permission = tk.StringVar(value=DEFAULT_CONFIG["permissions"])
    minutes = tk.StringVar(value=str(DEFAULT_CONFIG["budget"]["max_runtime_minutes"]))
    cost = tk.StringVar(value=str(DEFAULT_CONFIG["budget"]["max_estimated_cost_usd"]))
    audit = tk.StringVar(value=DEFAULT_CONFIG["audit_level"])
    project = tk.StringVar(value=str(args.project))
    task_file = tk.StringVar(value=str(args.task))

    main_frame = ttk.Frame(root, style="Main.TFrame", padding=(24, 20))
    main_frame.pack(fill="both", expand=True)
    ttk.Label(main_frame, text="Scientific Software Engineering Council",
              style="Header.TLabel").pack(anchor="w")
    ttk.Label(main_frame, text="Configura la distribución de especialistas para tu proyecto",
              style="Main.TLabel").pack(anchor="w", pady=(4, 12))

    def path_row(label: str, variable, pick):
        line = ttk.Frame(main_frame, style="Main.TFrame")
        line.pack(fill="x", pady=4)
        ttk.Label(line, text=label, style="Main.TLabel", width=17).pack(side="left")
        ttk.Entry(line, textvariable=variable).pack(side="left", fill="x", expand=True, padx=(6, 10))
        ttk.Button(line, text="Explorar", command=pick).pack(side="right")

    def pick_project():
        value = filedialog.askdirectory(title="Directorio del proyecto", initialdir=project.get())
        if value:
            project.set(value)
            try:
                saved = config_path(Path(value))
                if saved.is_file():
                    load_fields(load_config(saved))
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                messagebox.showwarning("Configuración existente inválida", str(exc))

    def pick_task():
        value = filedialog.askopenfilename(title="Seleccionar TASK_PACKET JSON",
                                           filetypes=[("Archivos JSON", "*.json")])
        if value:
            task_file.set(value)

    path_row("Proyecto", project, pick_project)
    path_row("Tarea JSON", task_file, pick_task)

    panel = ttk.Frame(main_frame, style="Panel.TFrame", padding=18)
    panel.pack(fill="x", pady=(12, 8))
    for col in (1, 3):
        panel.columnconfigure(col, weight=1)

    def combo(row, col, label, variable, choices):
        ttk.Label(panel, text=label, style="Panel.TLabel").grid(row=row, column=col, sticky="w", padx=(0, 8), pady=9)
        ttk.Combobox(panel, textvariable=variable, values=choices,
                     state="readonly", width=23).grid(row=row, column=col + 1,
                                                      sticky="ew", padx=(0, 18), pady=9)

    combo(0, 0, "Proveedor", provider, PROVIDERS)
    combo(0, 2, "Auditoría", audit, AUDIT_LEVELS)
    combo(1, 0, "Permisos solicitados", permission, PERMISSIONS)
    ttk.Label(panel, text="Máx. en paralelo", style="Panel.TLabel").grid(row=1, column=2, sticky="w")
    ttk.Spinbox(panel, textvariable=parallel, from_=1, to=12, width=10).grid(row=1, column=3,
                                                                           sticky="w", pady=9)
    ttk.Label(panel, text="Presupuesto (min)", style="Panel.TLabel").grid(row=2, column=0, sticky="w")
    ttk.Spinbox(panel, textvariable=minutes, from_=1, to=1440, width=10).grid(row=2, column=1,
                                                                               sticky="w", pady=9)
    ttk.Label(panel, text="Costo máximo (USD)", style="Panel.TLabel").grid(row=2, column=2, sticky="w")
    ttk.Entry(panel, textvariable=cost, width=12).grid(row=2, column=3, sticky="w", pady=9)

    ttk.Label(main_frame, text=UI_NOTE, style="Note.TLabel", wraplength=790).pack(anchor="w", pady=(4, 8))
    output = tk.Text(main_frame, height=14, wrap="word", bg="#0f1d30", fg="#e7ecf6",
                     insertbackground="white", font=("Consolas", 9), relief="flat", padx=15, pady=12)
    output.pack(fill="both", expand=True)

    def write_output(value: object):
        rendered = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        output.configure(state="normal")
        output.delete("1.0", "end")
        output.insert("end", rendered)
        output.configure(state="disabled")

    def load_fields(config: dict):
        provider.set(config["provider_mode"])
        parallel.set(str(config["max_parallel_agents"]))
        permission.set(config["permissions"])
        minutes.set(str(config["budget"]["max_runtime_minutes"]))
        cost.set(str(config["budget"]["max_estimated_cost_usd"]))
        audit.set(config["audit_level"])

    def get_inputs():
        p = Path(project.get()).expanduser()
        c = build_policy(provider.get(), parallel.get(), permission.get(), minutes.get(),
                         cost.get(), audit.get())
        t = json.loads(Path(task_file.get()).read_text(encoding="utf-8"))
        return p, c, t

    def preview():
        try:
            p, c, task = get_inputs()
            result = prepare(task, c["provider_mode"], p, apply=False, config=c)
            write_output(result)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            messagebox.showerror("Error de validación", str(exc))

    def save():
        try:
            p, c, _ = get_inputs()
            target = config_path(p)
            if target.exists() and not messagebox.askyesno(
                "Confirmar", f"¿Actualizar la configuración existente?\n{target}"
            ):
                return
            saved = save_config(p, c)
            write_output(f"Configuración guardada en: {saved}\n\n{UI_NOTE}")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            messagebox.showerror("No se pudo guardar", str(exc))

    def apply():
        try:
            p, c, task = get_inputs()
            preview_result = prepare(task, c["provider_mode"], p, apply=False, config=c)
            if not messagebox.askyesno(
                "Preparar perfiles SSEC",
                f"Se crearán perfiles y packets de {preview_result['agent_count']} roles\n"
                f"en {p}. No se ejecutarán modelos. ¿Continuar?"
            ):
                return
            result = prepare(task, c["provider_mode"], p, apply=True, config=c)
            write_output(result)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            messagebox.showerror("No se pudo preparar", str(exc))

    active_run = {"process": None, "cancel": None, "log": None}

    def poll_run():
        proc = active_run["process"]
        if proc is None:
            return
        logfile = active_run["log"]
        try:
            if logfile and logfile.exists():
                data = logfile.read_text(encoding="utf-8", errors="replace")
                if data:
                    write_output(data[-12000:])
        except OSError:
            pass
        if proc.poll() is None:
            root.after(700, poll_run)
        else:
            if not (logfile and logfile.exists() and logfile.stat().st_size):
                write_output(f"Proceso finalizado con código {proc.returncode}. Consultar .ssec/runs/")
            active_run["process"] = None
            run_button.configure(state="normal")
            cancel_button.configure(state="disabled")

    def start_audit():
        if active_run["process"] is not None:
            return
        try:
            p, c, task = get_inputs()
            if task["kind"] != "audit":
                raise ValueError("El ejecutor v0.2 admite solo auditorías por ahora")
            from pathlib import Path as _Path
            if __package__:
                from .run_agents import plan as _plan
            else:
                from run_agents import plan as _plan
            _plan(task, c)
            if not messagebox.askyesno(
                "Ejecución real con coste no medido",
                "Se iniciarán CLIs reales en copias temporales del proyecto. "
                "El coste en USD NO puede limitarse automáticamente. "
                "Los resultados NO se integrarán en el proyecto original. "
                "¿Confirmas expresamente la ejecución?"
            ):
                return
            save_config(p, c)
            out_dir = p / ".ssec" / "gui_runs"
            if out_dir.is_symlink():
                raise ValueError("Directorio de logs enlazado no permitido")
            out_dir.mkdir(parents=True, exist_ok=True)
            unique = uuid.uuid4().hex[:12]
            log = out_dir / f"{unique}.log"
            cancel = out_dir / f"{unique}.cancel"
            cmd = [sys.executable, str(_Path(__file__).resolve().parent / "run_agents.py"),
                   str(_Path(task_file.get()).resolve()), "--project", str(p),
                   "--config", str(config_path(p)), "--execute",
                   "--accept-unmetered-cost", "--cancel-file", str(cancel)]
            with log.open("wb") as handle:
                active_run["process"] = subprocess.Popen(cmd, cwd=p, stdin=subprocess.DEVNULL,
                                                        stdout=handle, stderr=subprocess.STDOUT,
                                                        shell=False)
            active_run["cancel"], active_run["log"] = cancel, log
            run_button.configure(state="disabled")
            cancel_button.configure(state="normal")
            write_output("Auditoría iniciada. Salida en " + str(log))
            root.after(700, poll_run)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            messagebox.showerror("Ejecución no iniciada", str(exc))

    def cancel_audit():
        if active_run["process"] is None:
            return
        if messagebox.askyesno("Cancelar", "¿Solicitar cancelación de la auditoría activa?"):
            active_run["cancel"].write_text("cancel", encoding="utf-8")
            write_output("Cancelación solicitada. Los agentes terminarán al recibir la señal.")

    def open_workspace():
        try:
            open_scientific_workspace(root, project.get())
        except (OSError, ValueError, TypeError, ImportError, tk.TclError) as exc:
            messagebox.showerror("No se pudo abrir el espacio científico", str(exc), parent=root)

    buttons = ttk.Frame(main_frame, style="Main.TFrame")
    buttons.pack(fill="x", pady=(12, 0))
    ttk.Button(buttons, text="1 · Previsualizar", command=preview,
               style="Panel.TButton").pack(side="left", padx=(0, 9))
    ttk.Button(buttons, text="2 · Guardar configuración", command=save,
               style="Panel.TButton").pack(side="left", padx=(0, 9))
    ttk.Button(buttons, text="3 · Preparar perfiles", command=apply,
               style="Panel.TButton").pack(side="right")
    ttk.Button(buttons, text="Abrir espacio científico", command=open_workspace,
               style="Panel.TButton").pack(side="right", padx=5)
    run_button = ttk.Button(buttons, text="4 · Ejecutar auditoría", command=start_audit,
                            style="Panel.TButton")
    run_button.pack(side="left", padx=5)
    cancel_button = ttk.Button(buttons, text="Cancelar", command=cancel_audit,
                               state="disabled", style="Panel.TButton")
    cancel_button.pack(side="left", padx=5)
    saved = config_path(Path(project.get()))
    if saved.is_file():
        try:
            load_fields(load_config(saved))
        except (ValueError, OSError, json.JSONDecodeError):
            write_output("Existe una configuración inválida en el proyecto; corrígela antes de continuar.")
    else:
        write_output("Elige el proveedor y el nivel de auditoría.\n\n"
                     "1) Previsualizar sin escribir.\n"
                     "2) Guardar .ssec/config.json (opcional).\n"
                     "3) Preparar perfiles con confirmación.\n\n" + UI_NOTE)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
