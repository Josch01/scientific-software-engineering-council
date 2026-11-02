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

## Inter-agent mailbox

Only known specialist roles can record structured events. An implementation role cannot submit `REVIEW_ACCEPTED`. Reviews should run separately on candidate worktree copies using the read-only `run_agents.py` audit process. The structured event is merely a record:

```bash
python scripts/worktree_coordinator.py message --project /path/to/my-git-project --task-id SEIR-BUILD-01 --sender software_auditor --kind REVIEW_FINDING --summary "Falta prueba de regresión del solver"
```

The `gate` checks for role handoffs, declarations of reviewer acceptance, declared mandatory checks, overlapping changed filenames, clean base and Git diff problems. Its best possible outcome is `DECLARED_READY_FOR_HUMAN_REVIEW`, **never `RELEASE_APPROVED`**. No statement about software/scientific correctness is inferred from exit status 0 or self-reported reviews.

## Remaining phase-2 work

Automated reviewer invocation and verified test provenance, strict per-role file ownership, worktree crash recovery, truly containerized process isolation, cross-provider exchange of bounded artifacts, a live supervisory GUI and human-approved PR integration. Keep those as explicit open requirements rather than calling the consorcio finished.

Git worktree official reference: https://git-scm.com/docs/git-worktree
