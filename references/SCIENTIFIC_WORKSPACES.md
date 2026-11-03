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

The loader requires the manifest and declared resources to remain under the project root, rejects observed symlinks/reparse points and escaping handles, reads regular files only, and enforces a 16 MiB per-resource and 64 MiB aggregate default budget. Callers may lower either limit. It captures bytes from the checked open handle, verifies every declared SHA-256, and returns no workspace if any resource fails. The CLI prints only IDs, paths, sizes, and digests; it never prints file contents.

Python consumers can call `load_scientific_workspace(project_root, "workspace.json")` and read the resulting `LoadedResource.content` bytes. Consume those captured bytes; do not reopen the recorded path after verification. File bytes remain inert: the loader does not parse CSV, import Python, execute code, render UI, or assess scientific validity. A matching digest establishes byte equality with the value declared in the same manifest; it does not authenticate who produced either one.

The validator and loader are experimental. The SIR-specific model, units, equations, data provenance, numerical accuracy, identifiability, and scientific validity require project evidence and independent domain review.
