# SSEC worktree development (experimental v0.2-dev.4)

This feature is separate from the existing read-only audit runner. It prepares actual linked Git worktrees, may launch real Gemini or Codex CLI processes when explicitly requested, and runs task-declared deterministic checks against each worker's separate candidate snapshot. **It does not do automated review, merges, pushes, commits, releases, authentication or scientific certification.**

## Safety

Worktrees isolate checked-out files and branches, **not filesystem permissions**. They share Git object storage and metadata. A provider may access files outside its worktree unless its OS sandbox actually prevents that. Use trusted Git repositories, check for symlinks and secrets, and confirm the sandbox backend is operational. Providers may incur real costs; SSEC does not enforce money limits. Hashes detect content changes but do not authenticate evidence against another process running as the same user.

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

Timeout, cancellation and cleanup go through runtime methods. Process completion
is reported separately from check results. `CHECKS_VERIFIED_AWAITING_REVIEW`
means the declared checks passed; `CHECKS_FAILED_NOT_REVIEWED` means check
evidence failed; `NOT_RUN` covers legacy packets without specs and executions
where checks could not start. None is a review or release approval.
Mailbox handoffs use only `WORKER_RESULT`; their stdout artifact is relative to
the task metadata root, for example `dev-logs/<execution-id>/<role>.stdout`.
Repeated executions therefore refer to distinct logs. If the runtime returns a
path outside that metadata root or no existing regular log file, the artifact
reference is empty; the full
observed path remains in the execution report. A reference identifies a log,
not authenticated execution or acceptance. Runtime output cannot grant test
acceptance or reviewer approval. FakeRuntime tests cover dispatch/control flow,
JSONL fixtures cover parsers, and one local Python child-process test covers
process/log lifecycle. None is provider E2E. Windows adapters configure a
kill-on-close Job Object, create the root suspended, assign it to the Job, then
resume its primary thread. POSIX adapters use a new session/process group.
Every terminal path, including natural root exit, stops residual contained
members and confirms quiescence before parsing JSONL or publishing hashes.
Windows confirmation queries zero active Job members; POSIX stops the group and
checks for remaining live members. Local Python parent/child tests on the Windows
host cover natural root success/failure, cancellation and failure after resume.
Detached/breakaway descendants and OS sandbox enforcement remain UNVERIFIED.
The POSIX backend observes root exit with `waitid(..., WNOWAIT)` and retains the
unreaped leader until group signalling and live-member confirmation finish; only
then does it reap the root. Under the host ownership precondition below, this
retains the PID/PGID through signalling instead of targeting a reused identity.
Runtime callers must leave reaping of that child to the runtime. If root
identity is lost, no group signal is sent and evidence fails closed. This POSIX
implementation requires non-reaping waitid plus procfs live-member inspection;
missing support is unavailable before provider creation. Its native path remains
unverified on this Windows host; offline order/concurrency regressions cover it.
POSIX also has an explicit host precondition: `SIGCHLD` must have `SIG_DFL`
disposition before launch. Ignored, custom or unknown dispositions make the
runtime unavailable before `Popen`. While runs are active, the host must not
change that disposition or run an external `waitpid(-1)`/other child reaper.
The runtime keeps `Popen` private and owns its wait/poll operations. The check
does not prevent a foreign reaper in another thread or later host changes; it
is an ownership precondition, not general isolation.
The handler check does not inspect native `sigaction` flags. Linux permits
`SA_NOCLDWAIT` with `SIG_DFL`; if that flag is active and a later `waitid`
observation fails with a generic error, cleanup may signal the numeric group
ID after the leader was auto-reaped. A reused ID could identify an unrelated
group. This is an **IMPORTANT unresolved risk**, not reproduced on the current
Windows host; native POSIX containment remains `NOT_RUN` and `EXPERIMENTAL`.
See [`P1 POSIX SIGCHLD review finding`](../docs/test-reports/p1-posix-sigchld-review-2026-11-02.md).
Confirmed identity loss means `ChildProcessError`/`ECHILD` or an unexpected PID.
Only when the host ownership preconditions above hold does an observation
`PermissionError`/other runtime error leave the exclusively owned leader
unreaped: the runtime then signals, confirms and reaps its group,
while keeping the run `FAILED`/`UNVERIFIED` with empty hashes/session evidence.
If signalling or confirmation fails, the leader is not reaped and explicit
cleanup retries quiescence. Repeated cleanup failure is recorded/raised as
`cleanup_error`; a later successful cleanup preserves the original immutable
`FAILED` result and cannot publish new hashes or upgrade it to success.
If tree termination or direct-process reap cannot be confirmed, the adapter
returns `FAILED` with termination `UNVERIFIED`, bounds its reap attempts, and
withholds session/child evidence and log hashes because surviving processes may
still modify those logs. Such a result does not confirm cancellation or cleanup;
remaining processes may require external intervention.

## Coordinator check evidence (P1.1b)

Initialization stores the complete original task packet, its canonical SHA-256
and stable task revision in task metadata. `execute` rejects a changed packet
before launching workers and uses only the stored packet for worker prompts and
check specs. Only `unit_tests`, `static_analysis` and `regression` are
executable process checks. A spec cannot claim review, scientific validation,
security, GUI, IDL or cross-platform evidence; declaring one of those IDs as a
command is rejected before worktree creation. Tasks without `check_specs`
remain compatible and report `NOT_RUN`.

After all worker processes succeed without a global cancellation, the runner
executes each task-declared check once per worker using a separate snapshot of
that worker's tracked and non-ignored untracked Git-visible files. A process
failure or global cancellation skips checks for all workers and reports
`NOT_RUN`. Check commands come only from validated `check_specs`; mailbox text
is never executed. Terminal manifests and their logs live under
`metadata/check-runs/<execution-id>/<role>/`. Timeout, cancellation, snapshot
drift, nonzero exit, invalid unittest summary, spawn failure or unconfirmed
process quiescence cannot produce `PASSED`.

`gate` reads manifests only under that task's metadata and checks task identity,
revision, digest, base commit, role, branch, command specs, snapshot/log paths,
current log hashes, and the current candidate tree hash. Editing tracked or
non-ignored untracked candidate files after a run invalidates that run. Each
manifest covers one worker's candidate; the worktrees are not combined or
tested as an integration result. Checks remain limited evidence: a deliberately
misleading test inside a real unittest suite may still lie. Hashes do not prove
who created evidence, and checks do not replace independent review, security or
scientific validation. Therefore `gate` remains `BLOCKED`,
`evidence_verified: false`, and `release_status: NOT_APPROVED` even when all
configured process checks pass. Reports keep `missing_spec_ids` for process
checks separate from `pending_evidence_ids` for review/science/security and
task-specific GUI/IDL/platform obligations. The local Python integration
fixture is offline and is not provider E2E.

## Inter-agent mailbox

Only known specialist roles can record structured communication: worker handoffs, review findings, change requests, and blockers. The mailbox API rejects `REVIEW_ACCEPTED` and `TEST_RESULT` for every sender, including reviewer roles. Role labels do not authenticate an execution or an independent context. Reviews should run separately on candidate worktree copies using the read-only `run_agents.py` audit process. The structured event is merely a record:

```bash
python scripts/worktree_coordinator.py message --project /path/to/my-git-project --task-id SEIR-BUILD-01 --sender software_auditor --kind REVIEW_FINDING --summary "Falta prueba de regresión del solver"
```

The `gate` checks for role handoffs, overlapping changed filenames, clean base and Git diff problems, and verifies per-worker check manifests as described above. It treats mailbox content as untrusted, including privileged event types inserted directly into `mailbox.jsonl`. No mailbox declaration can establish test success or reviewer acceptance. The gate remains `BLOCKED` with `evidence_verified: false` because this increment does not supply independent review, security or scientific evidence. No statement about software/scientific correctness is inferred from exit status 0 or self-reported reviews.

P1.1a closes the declaration-based readiness path, the runtime SPI increment
adds adapters and worker routing, and P1.1b produces and verifies task-bound
per-worker deterministic check evidence. These increments do not complete P1.1
or the multiagent consortium: separate-context review and acceptance remain
pending. P1 remains pending.

## Remaining phase-2 work

Automated reviewer invocation and verified test provenance, strict per-role file ownership, worktree crash recovery, truly containerized process isolation, cross-provider exchange of bounded artifacts, a live supervisory GUI and human-approved PR integration. Keep those as explicit open requirements rather than calling the consorcio finished.

Git worktree official reference: https://git-scm.com/docs/git-worktree
