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

The window can also start without arguments and use **Abrir espacio…** to select a project root and its manifest. From the SSEC configuration panel, **Abrir espacio científico** creates a child `Toplevel` on the existing Tk root and starts the manifest picker in the selected project. Both paths use the same loader, which checks the manifest and every declared SHA-256 before the UI receives captured bytes. Sections and components come from the validated manifest and are rendered by a fixed registry; manifest text cannot provide Python renderer code. For the closed SIR v1 contract, `equation_view` renders the fixed equations and `parameter_table` renders initial conditions, rate profiles, units, interval, and solver settings. Other model resources use bounded inert JSON views. The `code_view` component displays bounded UTF-8 text only. A workspace with exactly one verified, valid SIR `model_spec` automatically binds SSEC's built-in declarative SIR action to its `simulation_plot` components. No project Python is imported or executed.

### Optional PySide6 desktop frontend

When PySide6 is already available in the Python environment, the native Qt frontend can be started with:

```text
python scripts/scientific_workspace_qt.py --project-root PROJECT_ROOT workspace.json
```

Without arguments it opens a window with **Abrir espacio…** and asks for the project root and manifest. This frontend is optional; it does not install dependencies and the Tk app remains available. It calls the same safe loader and `WorkspaceViewModel`, uses a fixed component-renderer registry, shows the manifest sections and verified resource digests, and draws available simulation series with native Qt painting. Only SSEC's built-in declarative SIR callback is currently exposed here. Each run asks for the existing explicit human confirmation, runs on a Qt worker thread, validates the returned solver data through the shared result contract, and keeps the result in memory without modifying project files.

P3.13 adds **Proponer cambios con IA** and **Importar/revisar propuesta…** to the Qt toolbar. Proposal generation reads `.ssec` configuration, offers only the provider modes that have the existing read-only proposal policy, lets the user select verified resource IDs, and asks for explicit quota confirmation before dispatch. The existing P3.11 service stages only those captured bytes and component context; its result remains `PROPOSAL_READY_NOT_APPROVED`. Qt shows a bounded complete diff from `preview_workspace_proposal`; a separate human approval calls `approve_workspace_proposal`, which creates or reuses a digest-named manifest and then opens the verified copy. Source manifests/resources are not overwritten, and generated code is never executed.

If the configured provider mode cannot support that proposal policy, the generation button explains the limitation and **Importar/revisar propuesta…** remains available for JSON under the project root. If a configured Gemini CLI is absent or its policy cannot be applied, the service returns `PROVIDER_UNAVAILABLE` and no review is approved. Cancellation and worker-start failures remain terminal and do not create approval. Qt proposal UI tests use deterministic mocked service responses; they do not invoke Codex, Gemini, or AGY and do not prove account compatibility or scientific validity. The real provider path remains `NOT_RUN`.

The Qt frontend exposes audit dispatch through **Solicitar auditoría…**. It starts with no resources selected, requires explicit quota confirmation, and sends only the selected loader-verified resources to the existing audit service. Cancellation uses a temporary request file that is retained until the worker exits. The read-only result view marks `human_review=NOT_PERFORMED`, `release_status=NOT_APPROVED`, and `scientific_validity=NOT_CERTIFIED`; a successful CLI exit is reported as `PROCESSES_COMPLETED_NOT_AUDITED`. No project code is executed. Real provider invocation and Linux Qt visual use remain `NOT_RUN`; the offscreen tests mock the audit service. Qt WebEngine is not required. Neither Qt nor Tk views certify scientific validity.

### Native fit, sensitivity, and residual views (P3.16)

The Qt frontend now projects `LeastSquaresFit`, `OdeSensitivity`, and `ObservationEvaluation` schema v1 into bounded display models while leaving all numerical work in `scientific_core`. Fit results show method, status, cost, work counts, configured parameter order, initial/fitted values, declared bounds, residual values, and source resource digest. The residual table is capped at 200 evenly sampled rows, including both endpoints, while the summary retains the full count. The fit schema carries no parameter-unit fields: without a validated linked model context, the view says `unidad no indicada`; P3.17 derives SIR labels only from an explicitly linked, validated model resource. A fit status or residual magnitude is not an identifiability or uncertainty result.

Sensitivity values are selected with the declared `[time][state][parameter]` tensor order and plotted by configured state/parameter axes. The sensitivity schema has no unit fields; the view labels time and derivative units as not supplied unless the manifest links a validated SIR context. Sensitivity remains a local derivative result and does not establish practical identifiability.

The `observation_evaluation` resource kind and `residual_plot` component consume the versioned evaluation record. For each observed variable, Qt shows separate observed-versus-simulated and residual plots over the original observation times, along with the declared units, provenance, normalized observation digest, and verified resource ID/path/SHA-256. Sparse rows and `(time, variable)` residual coordinates are preserved. The result verifier checks residual values against supplied simulated-minus-observed values; it does not fit, estimate uncertainty, or infer missing observations.

When Qt WebEngine is available, chart pages are authored by SSEC, loaded from one bounded local `setHtml` document, and contain no CDN or remote/file fetches, Python bridge, or project-supplied HTML/script. A restrictive CSP hashes the inline chart script; only Qt's initial `data:text/html` document is admitted and later navigation is blocked. Labels travel as base64 JSON and are inserted as text. Hover inspection and legend toggles are available. The SVG trace samples at most 2,001 points per series; hover readouts still access the full validated values. Pages above 2,000,000 UTF-8 bytes fall back to QtPainter and a bounded table to stay within the local data-URL budget. The native plot includes both axis labels. Model/observation units must match exactly; no unit conversion is implied. Missing WebEngine, large-page fallback, and fallback rendering are tested.

Uncertainty remains inert JSON with `NOT_ASSESSED / NOT_CALCULATED`; SSEC creates no estimate, interval, or confidence band. This keeps fit error, local sensitivity, practical identifiability, and statistical uncertainty distinct.

Open the fully checked synthetic view demonstration from the repository root:

```text
python scripts/scientific_workspace_qt.py --project-root examples scientific_workspace_science_views_demo/workspace.json
```

`examples/scientific_workspace_science_views_demo/README.md` marks every value as a synthetic UI fixture. This example is not the user's SIR, experimental evidence, identifiability analysis, or a scientifically validated result. The user's SIR remains `NOT_RUN` until its equations and data are supplied.

### Declarative SIR analysis workspace (P3.17)

Open the reproducible SIR analysis workspace from the repository root:

```text
python scripts/scientific_workspace_qt.py --project-root examples/sir_analysis_workspace_demo workspace.json
```

Regenerate the model, exact synthetic observations, simulation, fit, local sensitivity, observation evaluation, and resource hashes with `python scripts/build_sir_analysis_demo.py`. The builder calls the existing scientific-core APIs; the agent or project does not supply executable code. The workspace includes equation and parameter views, observations, a simulation plot, fit summary, sensitivity plot, residual plots, an uncertainty summary, and the builder source as inert text.

The `simulation_plot`, `fit_summary`, and `sensitivity_plot` components may declare optional `config.context_refs`. These IDs must resolve to manifest resources distinct from the primary result, and only the kinds allowed by each component are accepted. For a `model_spec`, the UI derives time, population, and rate unit labels only after strict validation as SIR v1. The fit panel may also link one observations resource for provenance. Primary and context paths/digests are shown as byte-integrity evidence; they do not prove which inputs produced the result.

This demo samples observations from the same declared synthetic SIR simulation used by the fit. The optimizer's `STALLED` status is displayed as returned even though its rates are close to the known synthetic rates; it is not relabeled as converged. Residuals are raw simulation-minus-observation values, and local sensitivity does not establish practical identifiability. Uncertainty remains `NOT_ASSESSED / NOT_CALCULATED` with no intervals or bands. The user's SIR and experimental data remain `NOT_RUN`.

The built-in action accepts only the closed, versioned SIR equation set documented in `SCIENCE_NUMERICS.md`; it validates the verified resource bytes and uses SSEC's existing RK4 solver. Each run requires human confirmation. A custom `approved_simulations` map may still be passed by a trusted host and takes precedence for matching components; projects cannot register callbacks. Host callbacks receive immutable bytes captured by the safe loader plus the validated component view, and run on a daemon thread. The returned `OdeSolution` must pass row, value, parameter, schema, and series checks before the app opens an in-memory result tab. Callback errors leave the prior view intact. Closing the workspace does not cancel an already running host callback; only reviewed, bounded callbacks should be supplied. The result is not saved to the project and establishes no model validity. Invalid or ambiguous SIR model specs show a visible error and do not create a runnable action.

### Propose workspace changes with a local CLI

With a verified workspace open, choose **Proponer cambios con IA**, describe the desired layout, and select the resource IDs that may be read. SSEC asks for explicit confirmation before sending those selected bytes and derived component context to the configured local CLI; the request may consume account quota, which SSEC does not measure. The current proposal route uses Gemini CLI only when `--approval-mode plan` and a per-run administrator policy are supported. That policy denies all tools except built-in file reads and denies MCP tools; if standard system administrator policies would shadow the per-run policy, SSEC fails closed. Codex CLI is not launched for proposals because its read-only shell sandbox still permits model-generated commands to execute. Configure Gemini for this action, or use **Revisar propuesta** to inspect a manually imported JSON manifest.

The CLI sees a temporary snapshot with only the selected verified resources. Its response must match the bounded JSON layout contract and pass the existing workspace validator and safe loader. SSEC stores a candidate under `.ssec/runs/<run_id>/`; it never runs generated code or overwrites original workspace files. The GUI then opens the existing complete diff and asks for human approval before saving a digest-named copy. Deterministic fake-runtime tests do not establish provider compatibility or scientific validity; real provider generation remains `NOT_RUN`.

### Audit selected workspace resources in Qt

Choose **Solicitar auditoría…**, select the verified resource IDs to share, and confirm the possible account quota use. No resource is selected by default. The Qt worker calls the same `run_workspace_audit` service as the Tk frontend; it stages the selected verified bytes, supports cancellation, and retains the cancellation file until local processes exit. The read-only report is informational. Completed CLI processes are not an independent SSEC review, a test pass, scientific validation, or release approval. The service persists its report under `.ssec/runs/`. Development tests use a mocked service; no real CLI/model call is made by this UI test suite.

To exercise loading and view preparation without Tk or a display server:

```text
python scripts/scientific_workspace_app.py --check --project-root PROJECT_ROOT workspace.json
```

The checked-in synthetic SIR workspace can be opened interactively from the repository root with:

```text
python scripts/scientific_workspace_app.py --project-root examples sir_scientific_workspace.json
```

Select **Ejecutar: SIR** in the simulation component and approve the confirmation to run the declarative model. The example is synthetic software evidence only; its results do not validate the user's SIR or any scientific claim.

Exit 0 with `VIEW_PREPARED` means the declared component renderers accepted the available artifacts; it is not a scientific verdict. Exit 2 reports a loader/component error or `VIEW_LIMITED` when the UI would omit components. The simulation renderer understands only `scientific_core` simulation-result schema v1; observation tables use the versioned observation contract. Other artifacts are shown as bounded inert JSON/text. The initial UI is capped at 100 components, 1 MiB per JSON artifact, and 2 MiB of unique JSON data; JSON text previews are 32 KiB, text/code previews 256 KiB, tables show at most 1,000 sampled rows, and graphs plot at most 5 configured series while the table lists them all. Approved simulation output is additionally capped at 100,000 rows, 1,000,000 time/value entries and 100 parameters before the app copies it for rendering. The UI states when these limits omit content. Plot axes say when units are absent. A visualization, digest match, or prepared view does not establish numerical accuracy, identifiability, or scientific validity.

The GUI is optional; the manifest validator, loader, and presentation CLI remain usable headlessly. A real SIR run remains `NOT_RUN` until its equations, units, initial conditions, and experimental data are supplied.
