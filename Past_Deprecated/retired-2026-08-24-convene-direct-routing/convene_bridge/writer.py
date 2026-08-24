"""Atomic JSON replacement and one-writer locking."""

from __future__ import annotations

import errno
import json
import os
from pathlib import Path
import tempfile
import time


class AtomicWriteError(OSError):
    pass


class AtomicJSONWriter:
    def __init__(
        self,
        destination: str | Path,
        *,
        retry_timeout_s: float = 2.0,
        retry_interval_s: float = 0.05,
        clock=time.monotonic,
        sleeper=time.sleep,
        replacer=os.replace,
    ):
        self.destination = Path(destination)
        self.retry_timeout_s = retry_timeout_s
        self.retry_interval_s = retry_interval_s
        self._clock = clock
        self._sleep = sleeper
        self._replace = replacer

    def write(self, payload: dict) -> None:
        directory = self.destination.parent
        directory.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            dir=directory, prefix=f".{self.destination.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            deadline = self._clock() + self.retry_timeout_s
            while True:
                try:
                    self._replace(temporary, self.destination)
                    temporary = ""
                    return
                except OSError as exc:
                    if not _is_sharing_violation(exc) or self._clock() >= deadline:
                        raise AtomicWriteError("atomic destination replacement failed") from exc
                    self._sleep(min(self.retry_interval_s, max(0.0, deadline - self._clock())))
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass


def _is_sharing_violation(exc: OSError) -> bool:
    return getattr(exc, "winerror", None) in {5, 32, 33} or exc.errno in {
        errno.EACCES,
        errno.EPERM,
    }


class SingletonLock:
    """Advisory singleton held for the lifetime of the service process."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._handle = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            handle.close()
            raise RuntimeError("another state bridge writer already holds the lock") from exc
        self._handle = handle

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            self._handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> "SingletonLock":
        self.acquire()
        return self

    def __exit__(self, *_args) -> None:
        self.release()
