"""Actual local Linux flock/FD facts; no SDK, provider, manager or remote host."""

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "_reference_lock_runner", BASE / "tools/research/ivv_trusted_runner.py"
)
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


@unittest.skipUnless(sys.platform == "linux", "requires actual local Linux flock/procfs")
class ClaimLock(unittest.TestCase):
    def test_same_controller_reopened_descriptor_does_not_replay_claim(self):
        import fcntl

        fd = os.memfd_create("qm-offline-claim-epoch", os.MFD_CLOEXEC)
        self.addCleanup(lambda: os.close(fd))
        anchor = os.open(f"/proc/self/fd/{fd}", os.O_PATH | os.O_CLOEXEC)
        self.addCleanup(lambda: os.close(anchor))
        actor, _ = runner._controller_actor(os.getpid())
        os.lseek(fd, 1234567, os.SEEK_SET)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        claim = dict(
            controller=actor,
            claim_inode=list(runner.identity(os.fstat(fd))),
            claim_fd=fd,
            claim_offset=1234567,
        )

        class Name:
            def __truediv__(self, name):
                return SimpleNamespace(lstat=lambda: os.fstat(anchor))

        attempt = "connection-000002"
        binding = dict(
            controller=actor,
            claim_inode=claim["claim_inode"],
            unit="qm-ivv-recovery-" + attempt + ".service",
        )
        book = SimpleNamespace(root=Name(), _read=lambda name: {"pre_dispatch": binding})
        runner._reference_transition_owner(book, attempt, claim, False)
        os.close(fd)
        reopened = os.open(f"/proc/self/fd/{anchor}", os.O_RDONLY | os.O_CLOEXEC)
        self.assertEqual(reopened, fd)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.assertEqual(os.lseek(fd, 0, os.SEEK_CUR), 0)
        with self.assertRaises(ValueError):
            runner._reference_transition_owner(book, attempt, claim, False)

    def test_live_controller_released_lock_or_fd_refuses_child_may_owner(self):
        import fcntl

        controlled = os.environ.get("QM_CONDITION_SCRATCH")
        root = (
            Path(controlled) / "claim-lock"
            if controlled
            else Path(tempfile.mkdtemp(prefix="qm-claim-lock-"))
        )
        if controlled:
            root.mkdir(parents=True)
        path = root / "connection-000000.claim-lock.json"
        path.write_bytes(b"{}")
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
        self.addCleanup(lambda: os.close(fd) if fd >= 0 else None)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        info = Path(f"/proc/self/fdinfo/{fd}").read_bytes()
        if b"POSIX" in info:
            # WSL's Windows mount translates flock to POSIX. Do not widen the
            # production contract. Use a real Linux anonymous file for the
            # kernel FD/lock facts, modelling only the named-path lookup.
            os.close(fd)
            fd = os.memfd_create("qm-offline-claim-test", os.MFD_CLOEXEC)
            os.write(fd, b"{}")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            class AnonymousName:
                def __truediv__(self, name):
                    return SimpleNamespace(lstat=lambda: os.fstat(fd))

            root = AnonymousName()
            print(
                "WSL9p limitation: named lookup model; actual Linux memfd FLOCK/FD/controller facts"
            )
        actor, _ = runner._controller_actor(os.getpid())
        os.lseek(fd, 1234567, os.SEEK_SET)
        claim = dict(
            controller=actor,
            claim_inode=list(runner.identity(os.fstat(fd))),
            claim_fd=fd,
            claim_offset=1234567,
        )
        attempt = "connection-000002"
        binding = dict(
            controller=actor,
            claim_inode=claim["claim_inode"],
            unit="qm-ivv-recovery-" + attempt + ".service",
        )
        book = SimpleNamespace(root=root, _read=lambda name: {"pre_dispatch": binding})
        print("own synthetic lock fdinfo:", Path(f"/proc/self/fdinfo/{fd}").read_bytes())
        runner._reference_transition_owner(book, attempt, claim, False)
        fcntl.flock(fd, fcntl.LOCK_UN)
        with self.assertRaises(ValueError):
            runner._reference_transition_owner(book, attempt, claim, False)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        runner._reference_transition_owner(book, attempt, claim, False)
        os.close(fd)
        fd = -1

        # A real closed descriptor is absent; preserve the previously observed
        # named identity in the WSL-only lookup model to isolate this negative.
        class ClosedName:
            def __truediv__(self, name):
                return SimpleNamespace(
                    lstat=lambda: SimpleNamespace(
                        st_dev=claim["claim_inode"][0],
                        st_ino=claim["claim_inode"][1],
                        st_mode=claim["claim_inode"][2],
                        st_uid=claim["claim_inode"][3],
                    )
                )

        book.root = ClosedName()
        with self.assertRaises((ValueError, FileNotFoundError)):
            runner._reference_transition_owner(book, attempt, claim, False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
