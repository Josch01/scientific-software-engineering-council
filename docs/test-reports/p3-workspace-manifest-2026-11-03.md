# P3.1 scientific workspace manifest evidence

**State:** experimental contract and validator; local Windows/Linux verification, independent review, and branch CI complete. No SIR-specific workspace was built.

## Implemented

Schema v1 describes an ordered scientific workspace using 9 resource kinds and a fixed registry of 10 reusable components: equations, parameter/observation tables, simulation and sensitivity plots, fit/uncertainty/audit summaries, artifact browser, and source-code view. Component configs and resource roles are checked against exact schemas and declared references. The model-agnostic template exercises 8 resources and 9 component instances through the read-only CLI.

The validator bounds input to 1 MiB and limits nesting, cardinalities, paths, IDs, and text. It rejects duplicate JSON keys, invalid UTF-8, non-finite numbers, traversal, non-portable/Windows-reserved paths, Unicode/case collisions, and Win32 8.3 alias suffixes. It reads only the manifest; referenced paths are inert declarations. The CLI returns exit 0 for valid input and 2 for invalid input.

## Verification

| Environment | Command | Result |
|---|---|---|
| Windows, Python 3.14.0 | `python -m unittest tests.test_scientific_workspace -q` | PASS, 10 tests |
| Docker/Linux, `python:3.14.0-bookworm` | Same unittest command | PASS, 10 tests |
| Windows, Python 3.14.0 | `python -m py_compile scripts/scientific_workspace.py tests/test_scientific_workspace.py` | PASS |
| Windows, Python 3.14.0 | `python scripts/scientific_workspace.py examples/scientific_workspace_template.json` | PASS, `status=VALID`; 8 resources, 4 sections, 9 components |
| Windows, Python 3.14.0 | `git diff --check` | PASS |
| GitHub Actions | [Run #104](https://github.com/Josch01/scientific-software-engineering-council/actions/runs/41694267712), Windows/Ubuntu × Python 3.11/3.12 | PASS, 4/4 jobs |

An independent read-only review found and reproduced a DOS 8.3 alias gap for names such as `DATA$~1.CSV` and `DATA!~1.CSV`. Regression tests now reject both, including aliases in directory segments, while accepting ordinary `ordinary~1-copy.csv`. The final reviewer reported no critical or important findings.

## Limits and pending work

- This is a structural manifest validator, not a loader or renderer. It does not open, resolve, hash, display, or execute resource artifacts.
- Before any future loader reads a resource it must enforce workspace-root containment, symlink-safe resolution, and any declared content digest. That boundary is not implemented here.
- No desktop GUI, agent-driven workspace configuration, project-specific generated code, SIR equations/data, simulation plots, fitting, or audit workflow is included in P3.1.
- The template is a schema example only; it makes no mathematical, numerical, identifiability, or scientific-validity claim.
- Branch Actions run #104 passed all four Windows/Ubuntu × Python 3.11/3.12 jobs. The AGY provider E2E is unrelated and remains `NOT_RUN`.

## Next increment

Keep the manifest as the stable UI boundary. Before adding rendering/loading or further workspace features, confirm they are needed for the first SIR end-to-end case; the user has authorized this manifest/validator increment but has not supplied SIR equations or experimental data.
