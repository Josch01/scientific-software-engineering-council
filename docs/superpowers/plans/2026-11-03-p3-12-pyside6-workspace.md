# P3.12 — optional PySide6 workspace frontend

## Goal

Add an optional Qt desktop shell that consumes the verified workspace loader and immutable presentation model, renders the registered scientific components, and runs only SSEC's built-in SIR action after the existing explicit human confirmation. Keep business logic outside Tkinter and preserve the Tk frontend.

## Steps

1. Add offscreen Qt regression tests for verified loading/rendering, declined confirmation, and approved SIR results; observe failure before implementation.
2. Implement a PySide6 window with project/manifest selection, section navigation, fixed renderers, resource/digest status, keyboard access, visible focus, and scientific-validity notice.
3. Reuse the one-shot approved simulation action; execute it off the UI thread and show bounded in-memory results without writing project files.
4. Document launch, optional dependency, example workflow, CI coverage, and remaining limitations; update the feature matrix.
5. Run targeted Qt tests and the focused workspace suite locally, plus compile and diff checks; do not install dependencies or run provider calls.

## Acceptance checks

- Unverified or digest-mismatched workspace bytes never reach the view model.
- Only manifest-declared components map to fixed host renderers; project code remains inert.
- Declining the confirmation does not issue a run ticket or invoke the solver.
- A confirmed run displays an actual schema-validated result and leaves source files unchanged.
- The GUI remains optional and Tk stays available; PySide absence is reported clearly.
- Scientific validity, the user's concrete SIR, cross-platform Qt GUI coverage, and real provider calls remain accurately scoped.
