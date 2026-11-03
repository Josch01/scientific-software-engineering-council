# P3 workspace manifest CLI plan

Add a small headless entry point so the portable skill and future app tooling can validate an agent-proposed workspace contract without importing Python manually.

## Scope

- Implement `scripts/validate_workspace.py` for a UTF-8 JSON file or standard input.
- Emit only normalized JSON on success and a concise argparse error on failure.
- Bound input to 2 MiB, reject duplicate JSON keys and non-standard `NaN`/infinity constants, then delegate semantic checks to `validate_workspace`.
- Document commands, exit behavior, and the fact that artifact contents remain unopened.

## Verification

- Add subprocess tests for valid file/stdin, semantic/JSON errors, duplicate fields, non-standard numbers, and oversized input.
- Run focused CLI tests, skill structure validation, and the repository workflow on the stacked PR. No full local suite is needed for this small increment.
