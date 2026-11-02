"""Ordinary inherited process containment; not an OS security sandbox.

Windows uses a kill-on-close Job Object assigned before the suspended primary
thread resumes. POSIX uses the session/process group created by the runtime.
Detached/breakaway descendants are outside the verified guarantee.
"""

import ctypes
import os
from pathlib import Path
import signal
import time


DWORD = ctypes.c_uint32
HANDLE = ctypes.c_void_p


class _BasicLimits(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", DWORD), ("SchedulingClass", DWORD)]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BasicLimits), ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


class _Accounting(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int64) for name in (
        "TotalUserTime", "TotalKernelTime", "ThisPeriodTotalUserTime", "ThisPeriodTotalKernelTime")]
    _fields_ += [(name, DWORD) for name in (
        "TotalPageFaultCount", "TotalProcesses", "ActiveProcesses", "TotalTerminatedProcesses")]


class _ThreadEntry(ctypes.Structure):
    _fields_ = [("dwSize", DWORD), ("cntUsage", DWORD), ("th32ThreadID", DWORD),
                ("th32OwnerProcessID", DWORD), ("tpBasePri", ctypes.c_int32),
                ("tpDeltaPri", ctypes.c_int32), ("dwFlags", DWORD)]


class WindowsJob:
    # CREATE_NEW_PROCESS_GROUP | CREATE_SUSPENDED (not exposed by subprocess).
    creationflags = 0x200 | 0x4

    def __init__(self):
        self._api = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([HANDLE, ctypes.c_wchar_p], HANDLE),
            "SetInformationJobObject": ([HANDLE, DWORD, HANDLE, DWORD], ctypes.c_int),
            "AssignProcessToJobObject": ([HANDLE, HANDLE], ctypes.c_int),
            "QueryInformationJobObject": ([HANDLE, DWORD, HANDLE, DWORD, ctypes.POINTER(DWORD)], ctypes.c_int),
            "TerminateJobObject": ([HANDLE, DWORD], ctypes.c_int),
            "CreateToolhelp32Snapshot": ([DWORD, DWORD], HANDLE),
            "Thread32First": ([HANDLE, ctypes.POINTER(_ThreadEntry)], ctypes.c_int),
            "Thread32Next": ([HANDLE, ctypes.POINTER(_ThreadEntry)], ctypes.c_int),
            "OpenThread": ([DWORD, ctypes.c_int, DWORD], HANDLE),
            "ResumeThread": ([HANDLE], DWORD),
            "CloseHandle": ([HANDLE], ctypes.c_int),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self._api, name)
            function.argtypes, function.restype = args, result
        self._handle = self._api.CreateJobObjectW(None, None)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self._assigned = False
        limits = _ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        try:
            self._check(self._api.SetInformationJobObject(
                self._handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
        except OSError:
            self.close()
            raise

    @staticmethod
    def _check(value):
        if not value:
            raise ctypes.WinError(ctypes.get_last_error())
        return value

    def attach(self, process):
        self._check(self._api.AssignProcessToJobObject(self._handle, int(process._handle)))
        self._assigned = True
        snapshot = self._api.CreateToolhelp32Snapshot(0x4, 0)  # TH32CS_SNAPTHREAD
        if snapshot == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        thread = None
        try:
            entry = _ThreadEntry()
            entry.dwSize = ctypes.sizeof(entry)
            found = self._api.Thread32First(snapshot, ctypes.byref(entry))
            while found:
                if entry.th32OwnerProcessID == process.pid:
                    thread = self._check(self._api.OpenThread(0x2, False, entry.th32ThreadID))
                    break
                found = self._api.Thread32Next(snapshot, ctypes.byref(entry))
            if thread is None:
                raise OSError("Suspended primary thread was not found")
            # Exactly one suspend belongs to CREATE_SUSPENDED. A different count
            # cannot prove this process was resumed as intended.
            if self._api.ResumeThread(thread) != 1:
                raise OSError("Primary thread resume could not be confirmed")
        finally:
            if thread is not None:
                self._api.CloseHandle(thread)
            self._api.CloseHandle(snapshot)

    def _active(self):
        info = _Accounting()
        self._check(self._api.QueryInformationJobObject(
            self._handle, 1, ctypes.byref(info), ctypes.sizeof(info), None))
        return info.ActiveProcesses

    def quiesce(self, process):
        if not self._assigned:
            raise OSError("Job assignment was not confirmed")
        if self._active():
            self._check(self._api.TerminateJobObject(self._handle, 1))
        deadline = time.monotonic() + 5
        while self._active():
            if time.monotonic() >= deadline:
                raise OSError("Job still has active processes after termination")
            time.sleep(.01)
        process.wait(timeout=5)

    def close(self):
        if self._handle is not None:
            self._check(self._api.CloseHandle(self._handle))
            self._handle = None


class PosixGroup:
    creationflags = 0

    def attach(self, process):
        # Popen(start_new_session=True) establishes the group before exec.
        self._pgid = process.pid

    def _has_live_members(self):
        try:
            os.killpg(self._pgid, 0)
        except ProcessLookupError:
            return False
        if not Path("/proc").is_dir():
            return True  # Portable fallback waits for the whole group to disappear.
        for directory in Path("/proc").iterdir():
            if not directory.name.isdigit():
                continue
            try:
                stat = (directory / "stat").read_text(encoding="utf-8", errors="replace")
            except FileNotFoundError:
                continue
            fields = stat[stat.rfind(")") + 2:].split()
            if len(fields) < 3:
                raise OSError("Process-group membership could not be read")
            # Linux zombies cannot retain writable userspace/stdio handles.
            try:
                group = int(fields[2])
            except ValueError as exc:
                raise OSError("Invalid process-group membership") from exc
            if group == self._pgid and fields[0] not in ("Z", "X"):
                return True
        return False

    def quiesce(self, process):
        try:
            os.killpg(self._pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
        deadline = time.monotonic() + 5
        while self._has_live_members():
            if time.monotonic() >= deadline:
                raise OSError("Process group still has live members after termination")
            time.sleep(.01)

    def close(self):
        pass


def new_containment():
    return WindowsJob() if os.name == "nt" else PosixGroup()
