# Scientific workspace manifests and resources

SSEC workspaces use a versioned JSON manifest to describe project resources and fixed reusable views. See `examples/scientific_workspace_template.json` for a model-agnostic schema example.

## Validate the layout

```text
python scripts/scientific_workspace.py examples/scientific_workspace_template.json
```

This validates schema, component configuration, resource kinds, and portable relative paths. It does not stat or open resources.

## Load verified project resources

Place a manifest and its resources under the selected project root. Every resource that will be loaded must declare its expected lowercase SHA-256:

```json
{"id":"observations","kind":"observations","path":"data/observations.json","sha256":"<64 lowercase hex characters>"}
```

Run:

```text
python scripts/scientific_workspace_loader.py --project-root PROJECT_ROOT workspace.json
```

The loader requires the manifest and declared resources to remain under the project root, rejects observed symlinks/reparse points and escaping handles, reads regular files only, and enforces a 16 MiB per-resource and 64 MiB aggregate default budget. Callers may lower either limit. It captures bytes from the checked open handle, verifies every declared SHA-256, and returns no workspace if any resource fails. The CLI prints only IDs, paths, sizes, and digests; its `ARTIFACT_DIGESTS_MATCHED` status describes the digest comparison only, not model or scientific validity.

Python consumers can call `load_scientific_workspace(project_root, "workspace.json")` and read the resulting `LoadedResource.content` bytes. Consume those captured bytes; do not reopen the recorded path after verification. File bytes remain inert: the loader does not parse CSV, import Python, execute code, render UI, or assess scientific validity. A matching digest establishes byte equality with the value declared in the same manifest; it does not authenticate who produced either one.

The validator and loader are experimental. The SIR-specific model, units, equations, data provenance, numerical accuracy, identifiability, and scientific validity require project evidence and independent domain review.

## Optional dynamic desktop workspace

Open the first reusable Tkinter workspace window with:

```text
python scripts/scientific_workspace_app.py --project-root PROJECT_ROOT workspace.json
```

The window can also start without arguments and use **Abrir espacio…** to select a project root and its manifest. From the SSEC configuration panel, **Abrir espacio científico** creates a child `Toplevel` on the existing Tk root and starts the manifest picker in the selected project. Both paths use the same loader, which checks the manifest and every declared SHA-256 before the UI receives captured bytes. Sections and components come from the validated manifest and are rendered by a fixed registry; manifest text cannot provide Python renderer code. The `code_view` component displays bounded UTF-8 text only. The standalone CLI registers no simulation callbacks.

A trusted host may optionally pass `loaded_workspace` and a fixed `approved_simulations` map (`component_id -> ApprovedSimulationAction`) to `create_workspace_window`. Actions are supplied by host code; neither manifests nor project files can register or import them. A matching `simulation_plot` shows a button, and each run requires a human confirmation that names the callback and states that it runs locally without sandboxing. The callback receives immutable bytes captured by the safe loader plus the validated component view. It runs on a daemon thread so the Tk event loop can respond. The returned `OdeSolution` must pass row, value, parameter, schema, and series checks before the app opens an in-memory result tab. A callback error leaves the prior view intact. Closing the workspace does not cancel a callback already running; the host must supply reviewed, bounded callbacks. The result is not saved to the project and does not establish model validity.

To exercise loading and view preparation without Tk or a display server:

```text
python scripts/scientific_workspace_app.py --check --project-root PROJECT_ROOT workspace.json
```

Exit 0 with `VIEW_PREPARED` means the declared component renderers accepted the available artifacts; it is not a scientific verdict. Exit 2 reports a loader/component error or `VIEW_LIMITED` when the UI would omit components. The simulation renderer understands only `scientific_core` simulation-result schema v1; observation tables use the versioned observation contract. Other artifacts are shown as bounded inert JSON/text. The initial UI is capped at 100 components, 1 MiB per JSON artifact, and 2 MiB of unique JSON data; JSON text previews are 32 KiB, text/code previews 256 KiB, tables show at most 1,000 sampled rows, and graphs plot at most 5 configured series while the table lists them all. Approved simulation output is additionally capped at 100,000 rows, 1,000,000 time/value entries and 100 parameters before the app copies it for rendering. The UI states when these limits omit content. Plot axes say when units are absent. A visualization, digest match, or prepared view does not establish numerical accuracy, identifiability, or scientific validity.

The GUI is optional; the manifest validator, loader, and presentation CLI remain usable headlessly. A real SIR run remains `NOT_RUN` until its equations, units, initial conditions, and experimental data are supplied.
