"""Cross-platform locks for generation writers."""

import os
from contextlib import contextmanager
from pathlib import Path

from .utils.exceptions import ConfigurationError


@contextmanager
def generation_lock(final_root: Path):
    """Holds an OS lock that is released even if the owning process exits."""
    final_root.parent.mkdir(parents=True, exist_ok=True)
    lock_path = final_root.with_name(f".{final_root.name}.lock")
    with lock_path.open("a+b") as lock_file:
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"0")
            lock_file.flush()
        lock_file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ConfigurationError(
                f"Cannot lock {final_root}; another writer may be running"
            ) from error
        try:
            yield
        finally:
            if os.name == "nt":
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
