# Scientific workspace contracts

P3.1 adds a portable, declarative workspace manifest that a specialist can propose for a scientific project. The SSEC skill and a future optional desktop app can consume the same versioned contract. This increment validates workspace metadata; it does not build a GUI, read scientific artifacts, or run generated code.

## Validate a manifest

```python
import json
from pathlib import Path

from scripts.scientific_workspace import validate_workspace

data = json.loads(Path("workspace.json").read_text(encoding="utf-8"))
workspace = validate_workspace(data)
print(workspace.to_dict())
```

From the repository root, the portable skill or app tooling can validate a manifest and receive normalized JSON on standard output:

```text
python scripts/validate_workspace.py examples/scientific_workspace_minimal.json
```

The CLI exits `0` for valid manifests and `2` for input/validation errors. Pass `-` as the manifest argument to read from standard input. It reads at most 2 MiB, requires UTF-8 JSON, rejects duplicate object keys and non-standard `NaN`/infinity values, and never opens declared artifacts. Output JSON uses ASCII escapes so it can be piped on Windows terminals with non-UTF-8 output encodings.

`examples/scientific_workspace_minimal.json` is a generic inert example. Schema v1 has exact fields and rejects extensions until a later schema defines them:

- Workspace: `schema_version`, `model`, `artifacts`, `pages`.
- Model: `id`, `title`, `summary`.
- Artifact: `id`, `kind`, project-relative `path`.
- Page: `id`, `title`, `components`.
- Component: `id`, `kind`, `title`, `artifact_ids`.

IDs are unique within their own namespace: artifacts, pages, and components. Artifact paths are unique after Unicode NFKC normalization and case folding. Collection and text lengths are bounded by the validator. The JSON contract is data only: equations, source files, and user content are never evaluated by validation.

## Reusable component catalog

| Component | Accepted artifact kinds |
|---|---|
| `model_overview` | `model_definition` |
| `equations` | `model_definition` |
| `parameters` | `model_definition`, `optimization_result` |
| `simulation_plot` | `simulation_result`, `plot` |
| `optimization` | `optimization_result` |
| `sensitivity` | `sensitivity_result` |
| `uncertainty` | `uncertainty_result` |
| `results` | simulation, plot, optimization, sensitivity, uncertainty results |
| `audit` | `audit_report`, `test_report` |
| `project_files` | any declared artifact, or no binding |

This catalog only validates references. It does not assert that the file contents match the declared kind or that a dataset, equation, simulation, fit, or conclusion is scientifically valid. In particular, `simulation_result` is not currently loaded or rendered from the RK4 JSON output.

## Path and execution boundary

Manifest paths use relative POSIX separators. The validator rejects absolute paths, drive/ADS colons, backslashes, dot/parent/empty segments, Windows-forbidden characters, control characters, ASCII leading/trailing spaces, trailing dots, reserved Windows device basenames (including extensions and superscript COM/LPT aliases), and DOS 8.3 alias suffixes (`~digits`). These restrictions prevent common cross-platform aliases; see Microsoft's [Windows naming rules](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file) and [NTFS stream syntax](https://learn.microsoft.com/en-us/windows/win32/fileio/file-streams).

`resolve_artifact_path(project_root, relative_path)` requires an existing directory, resolves against its canonical path, and rejects detected symlink/junction escapes. It returns a `Path`, not an OS-level capability. Do not treat the check as a race-free safe-open API: any future reader of a concurrently mutable/untrusted project must enforce containment during the actual file open. The resolver also does not verify artifact existence, file type, hash, provenance, size, encoding, or file contents.

Workspace data must remain inert in both the portable skill and future application. A renderer may select only registered components and must escape displayed content. Code execution, HTML/plugin loading, artifact parsing, and scientific analysis belong to separately reviewed components and contracts.

## SIR scope

The generic manifest demonstrates only workspace structure. The user has not yet supplied the modified SIR equations, units, initial conditions, or experimental data. Therefore no SIR-specific contract, simulation, parameter identification, uncertainty result, or scientific validity claim is verified. The future integral case must preserve separate `SOFTWARE_VALIDITY`, `NUMERICAL_VALIDITY`, and `SCIENTIFIC_VALIDITY` evidence.
