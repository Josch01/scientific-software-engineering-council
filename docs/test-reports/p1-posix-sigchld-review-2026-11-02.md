# P1 POSIX SIGCHLD Review Finding

**Base revision:** `a324e74` (`docs: record unresolved POSIX waitability risk`).

**Finding:** `REPRODUCED_ON_LOCAL_DOCKER_LINUX`; a fail-closed waitability precondition is implemented and covered by a Linux regression test. This is not host-native POSIX or sandbox certification.

## Exact reproduction

Environment: the already available `python:3.14.0-bookworm` Docker image, run with `--pull=never`.

In an isolated Linux Python process, native `sigaction` set `SIGCHLD` to `SIG_DFL` with `SA_NOCLDWAIT`. Python's `signal.getsignal(SIGCHLD)` continued to report `SIG_DFL`. `PosixGroup` accepted that state. A session leader then spawned a same-process-group Python descendant that would write a marker after 0.9 seconds and exit immediately. Calling `quiesce()` about 0.15 seconds later raised `LostRootIdentityError`; because the caller correctly refuses to signal a group after losing the leader identity, the descendant was not stopped and wrote its marker after cancellation.

This is the critical leak: a native auto-reap flag is invisible to `getsignal`, and the existing leader-identity check then prevents safe group signalling after the leader is gone.

## Correction

`PosixGroup` now starts a short-lived sacrificial Python child during construction and observes it with `waitid(P_PID, ..., WEXITED | WNOHANG | WNOWAIT)`. It requires the child's exit event to remain waitable and match the probe PID. `ECHILD`/`ChildProcessError`, an unexpected identity, another observation error, or failure to confirm within the bound raises `OSError`, so the provider/check work process is not launched. The probe is waited in a `finally` block and killed and waited if it exceeds its cleanup bound. The existing default `SIGCHLD` check remains in place. This checks actual wait behavior instead of relying on Python's view of the native signal disposition.

The Linux-only regression installs `SA_NOCLDWAIT` with native `sigaction` inside a subprocess, independently confirms that `waitid(...WNOWAIT)` sees the sacrificial child as already auto-reaped, and verifies `new_containment()` refuses before a sentinel work process can write its marker.

## Verification

RED, before the production change, from the worktree in Docker Linux:

```text
docker run --rm --pull=never -v "C:\Users\artur\Documents\Skill\ssec-worktrees\p1-posix-autoreap-fix:/work" -w /work python:3.14.0-bookworm python -m unittest discover -v -s tests -p test_posix_process_containment.py
test_native_sa_nocldwait_is_rejected_before_work_launch ... FAIL
AssertionError: 'WORK_LAUNCHED' != 'REFUSED'
Ran 1 test ... FAILED (failures=1)
```

GREEN after the change, same command: 1 test passed.

Commands run, all with the local `python:3.14.0-bookworm` image and `--pull=never` for Docker runs:

```text
docker run --rm --pull=never -v "C:\Users\artur\Documents\Skill\ssec-worktrees\p1-posix-autoreap-fix:/work" -w /work python:3.14.0-bookworm python -m unittest discover -v -s tests -p test_posix_process_containment.py
1 test passed

Windows: python -m unittest discover -v -s tests -p test_provider_runtimes.py
41 tests passed

docker run --rm --pull=never -v "C:\Users\artur\Documents\Skill\ssec-worktrees\p1-posix-autoreap-fix:/work" -w /work python:3.14.0-bookworm python -m unittest discover -v -s tests -p test_provider_runtimes.py
41 tests passed
```

The runtime suite is an offline/mocked provider contract suite. It is not provider CLI E2E evidence. Its local Python process-tree smoke cases do not establish provider behavior, provider sandbox effectiveness, or host-wide containment guarantees.

## Residual limits and NOT_RUN

- Host-native POSIX verification: `NOT_RUN`; the real kernel regression ran in the local Linux Docker container.
- Provider CLI/E2E, credentials, and model sessions: `NOT_RUN`.
- Sandbox certification: `NOT_RUN`.
- Full test suite: `NOT_RUN` (outside this task's scope).
- Process-group ID reuse stress: `NOT_RUN`.
- The probe establishes waitability at containment construction time. It cannot prevent another actor or a later native signal-state change from altering child reaping behavior afterward.
- Existing containment remains limited to inherited descendants in the process group; detached or breakaway descendants remain outside its guarantee. Do not describe this POSIX backend as a security sandbox.

Primary references: [Linux `sigaction(2)`](https://man7.org/linux/man-pages/man2/sigaction.2.html) documents `SA_NOCLDWAIT` and its applicability with `SIG_DFL`; [CPython 3.11 `signalmodule.c`](https://github.com/python/cpython/blob/v3.11.0/Modules/signalmodule.c#L561-L577) shows `getsignal` consulting CPython's internal handler table.
