"""Linux kernel regressions for POSIX process containment."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


@unittest.skipUnless(sys.platform == "linux", "requires Linux sigaction semantics")
class PosixProcessContainmentTests(unittest.TestCase):
    def test_native_sa_nocldwait_is_rejected_before_work_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "work-launched"
            child_script = textwrap.dedent(
                r"""
                import ctypes
                import errno
                import os
                from pathlib import Path
                import signal
                import subprocess
                import sys
                import time

                class SigSet(ctypes.Structure):
                    _fields_ = [("values", ctypes.c_ulong * (128 // ctypes.sizeof(ctypes.c_ulong)))]

                class SigAction(ctypes.Structure):
                    _fields_ = [
                        ("handler", ctypes.c_void_p),
                        ("mask", SigSet),
                        ("flags", ctypes.c_int),
                        ("restorer", ctypes.c_void_p),
                    ]

                libc = ctypes.CDLL(None, use_errno=True)
                libc.sigaction.argtypes = [
                    ctypes.c_int, ctypes.POINTER(SigAction), ctypes.POINTER(SigAction)
                ]
                libc.sigaction.restype = ctypes.c_int
                action = SigAction()
                action.handler = None  # SIG_DFL
                action.flags = 2  # Linux SA_NOCLDWAIT
                if libc.sigaction(signal.SIGCHLD, ctypes.byref(action), None) != 0:
                    error = ctypes.get_errno()
                    raise OSError(error, os.strerror(error))
                if signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL:
                    raise RuntimeError("native sigaction unexpectedly changed getsignal")

                # Verify that the kernel applied auto-reaping before testing the
                # containment factory, independently of its implementation.
                pid = os.fork()
                if pid == 0:
                    os._exit(0)
                deadline = time.monotonic() + 5
                while True:
                    try:
                        event = os.waitid(
                            os.P_PID, pid,
                            os.WEXITED | os.WNOHANG | os.WNOWAIT,
                        )
                    except ChildProcessError:
                        break
                    except OSError as error:
                        if error.errno == errno.ECHILD:
                            break
                        raise
                    if event is not None and event.si_pid == pid:
                        os.waitpid(pid, 0)
                        raise RuntimeError("SA_NOCLDWAIT did not auto-reap the probe child")
                    if time.monotonic() >= deadline:
                        raise RuntimeError("probe child did not become waitable or auto-reaped")
                    time.sleep(0.01)

                from scripts.process_containment import new_containment

                try:
                    containment = new_containment()
                except OSError:
                    print("REFUSED", flush=True)
                else:
                    containment.close()
                    subprocess.run(
                        [
                            sys.executable,
                            "-c",
                            "from pathlib import Path; import sys; "
                            "Path(sys.argv[1]).write_text('started')",
                            sys.argv[1],
                        ],
                        check=True,
                    )
                    print("WORK_LAUNCHED", flush=True)
                """
            )
            result = subprocess.run(
                [sys.executable, "-c", child_script, str(marker)],
                capture_output=True,
                text=True,
                timeout=15,
            )

            self.assertEqual(
                result.returncode,
                0,
                f"isolated regression subprocess failed:\n{result.stdout}\n{result.stderr}",
            )
            self.assertEqual(result.stdout.strip(), "REFUSED")
            self.assertFalse(marker.exists(), "work process launched before refusing containment")


if __name__ == "__main__":
    unittest.main()
