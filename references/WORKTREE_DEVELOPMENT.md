# SSEC worktree development (experimental v0.2-dev.4)

This feature is separate from the existing read-only audit runner. It prepares actual linked Git worktrees and may launch real Gemini or Codex CLI processes when explicitly requested. **It does not do automated review, merges, pushes, commits, releases, authentication or scientific certification.**

## Safety

Worktrees isolate checked-out files and branches, **not filesystem permissions**. They share Git object storage and metadata. A provider may access files outside its worktree unless its OS sandbox actually prevents that. Use trusted Git repositories, check for symlinks and secrets, and confirm the sandbox backend is operational. Providers may incur real costs; SSEC does not enforce money limits. Worker outputs and mailbox messages are not cryptographically authenticated or verified test logs.

## Sequence

Start from the SSEC skill root with an existing, clean project Git repository. Replace the path and task JSON with your actual trusted project.

```bash
# Zero side effects: plan branches and roles
python scripts/worktree_coordinator.py plan examples/seir_worktree_build.json --project /path/to/my-git-project

# Opt-in: create role branches/worktrees beside the project
python scripts/worktree_coordinator.py init examples/seir_worktree_build.json --project /path/to/my-git-project --apply

# Zero CLI calls: show execution preview
python scripts/development_runner.py examples/seir_worktree_build.json --project /path/to/my-git-project --task-id SEIR-BUILD-01

# Real provider calls, opt-in, unmetered USD
python scripts/development_runner.py examples/seir_worktree_build.json --project /path/to/my-git-project --task-id SEIR-BUILD-01 --execute --accept-unmetered-cost --max-parallel 2 --max-minutes 30

# Read outputs and fail-closed candidate review
python scripts/worktree_coordinator.py status --project /path/to/my-git-project --task-id SEIR-BUILD-01
python scripts/worktree_coordinator.py gate --project /path/to/my-git-project --task-id SEIR-BUILD-01
```

Task metadata, mailbox and CLI stdout/stderr are stored in a sibling folder named `.<project-name>-ssec-worktrees/.ssec-state/<task-id>`. Worktrees are also outside the original checkout. Treat logs and task metadata as private. Clean up with Git's **worktree remove**, never by blindly deleting directories; this version has no automatic rollback.

## Runtime adapters (P1 increment; P1 remains pending)

Development execution now uses the typed `AgentRuntime` contract. Each persisted
`worker.provider` selects only its Codex or Gemini adapter; a missing or unsupported
provider is unavailable/failed and never falls back to another CLI. Preview does
not construct, discover or launch a runtime. Execution still requires explicit
unmetered-cost acknowledgement before runtime activity.

Codex requests `read-only` or `workspace-write` according to the runtime request;
development workers request writes in their own worktree. Gemini requests
`--sandbox` with default approval, which does not guarantee a read-only workspace.
Windows Gemini npm batch shims are resolved to native Node plus the installed JS
entry point, or reported unavailable; no batch shim is passed to subprocess.
Help/version discovery is bounded and does not inspect credentials or start a
model session. Sandbox effectiveness and native-subagent capability remain
**UNVERIFIED**. Real Codex, Gemini and cross-provider E2E remain **NOT_RUN**.

Each execute call gets a fresh `dev-logs/<execution-id>/` directory. Adapters
reject existing/aliased/owned output paths and create logs exclusively. Their
path reservations persist for the Python process lifetime, including after
completion, cleanup and log deletion. The runner preserves runtime status, exit
code, provider identity, parent session ID, log paths/hashes, timestamps, error
and observed child IDs. `requested_provider` records routing separately, so a
test double is not relabelled as a real provider. A parent session ID is never
added to the child-ID list. `runtime_result_observed` means the runtime returned
the record; it does not authenticate it or establish scientific validity.

Timeout, cancellation and cleanup go through runtime methods. `SUCCEEDED` is a
runtime outcome, while the overall successful execution remains
`PROCESSES_FINISHED_UNREVIEWED` and release status remains `NOT_APPROVED`.
Mailbox handoffs use only `WORKER_RESULT`; their stdout artifact is relative to
the task metadata root, for example `dev-logs/<execution-id>/<role>.stdout`.
Repeated executions therefore refer to distinct logs. If the runtime returns a
path outside that metadata root or no existing regular log file, the artifact
reference is empty; the full
observed path remains in the execution report. A reference identifies a log,
not authenticated execution or acceptance. Runtime output cannot grant test
acceptance or reviewer approval. FakeRuntime tests cover dispatch/control flow,
JSONL fixtures cover parsers, and one local Python child-process test covers
process/log lifecycle. None is provider E2E. Adapters start an OS process
group/session and stop the inherited tree (Windows taskkill /T, POSIX killpg),
then reap the direct process before publishing log hashes. A local Python
parent/child regression covers ordinary inherited descendants on the test host.
Detached descendants and OS sandbox enforcement remain UNVERIFIED.

## Inter-agent mailbox

Only known specialist roles can record structured communication: worker handoffs, review findings, change requests, and blockers. The mailbox API rejects `REVIEW_ACCEPTED` and `TEST_RESULT` for every sender, including reviewer roles. Role labels do not authenticate an execution or an independent context. Reviews should run separately on candidate worktree copies using the read-only `run_agents.py` audit process. The structured event is merely a record:

```bash
python scripts/worktree_coordinator.py message --project /path/to/my-git-project --task-id SEIR-BUILD-01 --sender software_auditor --kind REVIEW_FINDING --summary "Falta prueba de regresión del solver"
```

The `gate` checks for role handoffs, overlapping changed filenames, clean base and Git diff problems. It treats mailbox content as untrusted, including privileged event types inserted directly into `mailbox.jsonl`. No mailbox declaration can establish test success or reviewer acceptance. The gate currently remains `BLOCKED` with `evidence_verified: false` because the coordinator execution/evidence producer is not implemented. No statement about software/scientific correctness is inferred from exit status 0 or self-reported reviews.

P1.1a closes the declaration-based readiness path, and the runtime SPI increment
adds adapters and worker routing. Neither completes P1.1 or the multiagent
consortium: deterministic tests, separate-context review, and acceptance still
need coordinator-produced execution evidence. P1 remains pending.

## Remaining phase-2 work

Automated reviewer invocation and verified test provenance, strict per-role file ownership, worktree crash recovery, truly containerized process isolation, cross-provider exchange of bounded artifacts, a live supervisory GUI and human-approved PR integration. Keep those as explicit open requirements rather than calling the consorcio finished.

Git worktree official reference: https://git-scm.com/docs/git-worktree
