# P1 POSIX SIGCHLD Review Finding

**Evaluated revision:** `f72ec01` (`fix: require default SIGCHLD ownership precondition on POSIX`)

**Severity/state:** `IMPORTANT / NOT_REPRODUCED_LOCALLY / POSIX_NATIVE_NOT_RUN`.

## Finding

`PosixGroup` checks `signal.getsignal(SIGCHLD) == SIG_DFL`, but that does not inspect the kernel's native `sigaction` flags. Linux documents that `SA_NOCLDWAIT` can be used with `SIG_DFL`; terminated children then do not become zombies. CPython's `getsignal` reads its Python signal-handler table, so a native `sigaction` change is not necessarily reflected by this check.

If a child is auto-reaped and the later `waitid` call fails with a generic observation error such as `EPERM`, `PosixGroup.quiesce` currently treats that error as distinct from confirmed `ECHILD`, then signals the numeric process-group ID. If that ID has been reused, the signal could affect an unrelated process group. This requires the combined native signal state, an observation error, and numeric identity reuse; the complete sequence was not reproduced here.

Primary references: [Linux `sigaction(2)`](https://man7.org/linux/man-pages/man2/sigaction.2.html) documents `SA_NOCLDWAIT` and its applicability with `SIG_DFL`; [CPython 3.11 `signalmodule.c`](https://github.com/python/cpython/blob/v3.11.0/Modules/signalmodule.c#L561-L577) shows `getsignal` consulting CPython's internal handler table.

## Verification boundary

- Host: Windows, Python 3.14.0 (`sys.platform == "win32"`, `os.name == "nt"`).
- `wsl --list --quiet` reported only the internal `docker-desktop` distribution. Docker reported that its Linux engine pipe was unavailable. No usable POSIX runtime was present.
- Native `SA_NOCLDWAIT` behavior, `waitid` denial, and process-group ID reuse: `NOT_RUN`.
- Existing POSIX unit tests use doubles. They verify ordering and error handling, not Linux kernel behavior or PID reuse.
- Provider CLI/E2E, credentials, and model sessions: `NOT_RUN`.

## Decision and follow-up

Per the updated coordination directive, no additional runtime hardening is included in this increment without a reproducible critical defect. The proposed local waitability probe was uncommitted and was removed before verification; it is not part of this PR. The POSIX backend remains experimental and this finding remains open. Do not describe POSIX containment as verified or safe for arbitrary host signal/reaper configurations. Reproduce on an existing Linux CI/host without installing software, then decide whether a native action probe or a separate supervisor is warranted. No merge is requested.
