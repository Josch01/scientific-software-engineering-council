# SSEC local audit runner — v0.2 experimental

## What works

- Executes installed Gemini CLI, Codex CLI, or AGY from separate processes; `both` keeps its existing Gemini/Codex routing.
- The router selects only required roles; each role receives its own packet and a disposable source snapshot.
- Bounded **top-level** concurrency, wave scheduling (reviewers later), a global wall-clock deadline, cancellation flag, and logs per process.
- Codex launched via `codex exec --sandbox read-only --json --skip-git-repo-check --cd ...`; Gemini via `gemini --sandbox --approval-mode default --output-format json -p ...`.
- `--mode agy` assigns implementation workers to AGY and independent reviewers to Codex. AGY workers get a per-worktree profile limited to file tools; shell commands and nested subagents are disabled. AGY uses its documented `event/init`, `event/step_update`, and nested `event/result` stream protocol.
- Local desktop configuration panel has an explicitly confirmed **4 · Ejecutar auditoría** action, run-status polling, and **Cancelar** action.
- Optional `--emit-progress-jsonl` emits bounded schema-v1 `SSEC_PROGRESS` snapshots for the supervisor; the default CLI continues to print only its JSON report.
- Dry-run is the default. The stage runs **audits only**. No file merges, code changes to the original project, real bills measured, or scientific certifications.

## Commands

Use Python 3.11+ and install/authenticate the CLI(s) chosen in the panel before running. For now prepare a JSON TASK_PACKET using `examples/seir_desktop_audit.json` as a reference, and set `kind: audit`.

```bash
# default: previews without invoking CLIs or writing anything
python scripts/run_agents.py examples/seir_desktop_audit.json --project /path/to/project --mode gemini

# explicit real execution; cost remains unmetered
python scripts/run_agents.py examples/seir_desktop_audit.json --project /path/to/project --mode codex --execute --accept-unmetered-cost
python scripts/run_agents.py examples/seir_desktop_audit.json --project /path/to/project --mode both --execute --accept-unmetered-cost

# optional machine-readable progress events for a dashboard or log consumer
python scripts/run_agents.py examples/seir_desktop_audit.json --project /path/to/project --mode gemini --execute --accept-unmetered-cost --emit-progress-jsonl
```

If `.ssec/config.json` exists, it is loaded and provides concurrency, timeout and audit level. CLI `--mode` overrides the provider choice. Each run writes logs and `run_summary.json` inside `.ssec/runs/<run-id>/`. CLI exit status zero is recorded as `EXIT_ZERO_UNREVIEWED`, **not** `PASS` or `RELEASE_READY`. Review logs manually. Mode `both` invokes separate real processes, **not** an integrated multi-provider parent with autonomous inter-agent messaging.

Progress events contain `schema_version`, run/task IDs, execution state, completed/total counts, per-agent role/provider/status, and `release_status=NOT_APPROVED`. `RUNNING` is emitted only after process creation succeeds. A process exit does not mean its review passed; a valid event never approves integration or release.

## Safety and limits

- Only execute when you trust your local CLI installation, authentication, workspace and upstream providers. Gemini `--sandbox` requires a working sandbox backend; otherwise the run fails. On Windows Docker/Podman availability varies; don't disable sandbox to make it work.
- The project is snapshotted into independent disposable directories; the original tree is never used as the subprocess working directory. **This is not an OS-grade sandbox**: CLIs and subprocesses can access other resources if their permissions or sandbox settings permit. Do not use untrusted code/secrets without external OS isolation.
- Common secrets/virtual environments/git metadata are omitted by name. This is a best-effort filter, **not a secrets scanner**. Review the project before sending it to any cloud model; ensure no sensitive content is present in allowed files.
- Each source file is limited to 15 MiB, total to 60 MiB; larger projects fail before execution. No silent truncation of files.
- Global wall clock maximum is enforced. Cost budget (USD) is **advisory** because provider usage and billing may not be directly accessible; explicit acknowledgment is required to run.
- A separate context per CLI process lowers anchoring; it does not prove reviewer independence. Native nested provider subagents are not spawned by this runner: the top-level launched role processes are the workers. Concurrency applies to these top-level processes, not to any child process the provider might choose to launch.
- No remote installations, arbitrary shell command strings, escalation flags, or auto-merge. Failure in a wave stops subsequent waves.
- Logs may reveal sensitive prompts; `.ssec/` is gitignored, but never upload logs publicly without reviewing them.

## Future milestone

Worktree-based code editing and patch exchange; structured artifact review; hard controls on nested child agents and costs; isolated execution for agent-generated model code; and automated release authorization. None of these are implied by this runner. The first SIR prototype runs only trusted callbacks explicitly reviewed and approved by a person; it does not automatically execute generated Python.

Official CLI guidance:
- https://learn.chatgpt.com/docs/non-interactive-mode
- https://learn.chatgpt.com/docs/cli/reference
- https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/cli-reference.md
