# P3 workspace validation CLI evidence — 2026-11-03

## Status

`EXPERIMENTAL`. The CLI exposes the P3.1 JSON contract for headless skill/app tooling. It validates manifest data and emits normalized JSON; it does not read declared artifact paths.

## Verified locally

- Windows 11, Python 3.14.0.
- `python -m unittest discover -s tests -p test_workspace_cli.py -v`: **7/7 passed**.
- Covered valid file and stdin input, normalized/portable JSON output (including Unicode text), semantic/JSON/filesystem errors and exit code 2, duplicate object keys, rejected `NaN`, and a 2 MiB input cap.
- Full repository CI is delegated to the draft PR's Windows/Linux × Python 3.11/3.12 matrix; check status before claiming cross-platform verification.

## Limits

- No artifact read, hash/provenance verification, renderer, GUI, generated-code execution, or SIR validation.
- Valid output means only that the manifest conforms to schema v1. It does not assert scientific or file-content validity.
