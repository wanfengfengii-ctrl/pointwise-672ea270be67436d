import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from archive.originals import init_original_store
from archive.receipts import init_receipt_store
from archive.records import init_reading_store
from pairs.tables import init_pair_store


BeforeCommit = Callable[[sqlite3.Connection], None]


def open_archive(path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(path, isolation_level=None)
    try:
        db.execute('PRAGMA foreign_keys = ON')
    except BaseException:
        db.close()
        raise
    return db


@contextmanager
def archive_write(
    db: sqlite3.Connection, *, before_commit: BeforeCommit | None = None
) -> Iterator[None]:
    db.execute('BEGIN IMMEDIATE')
    with db:
        changes_before = db.total_changes
        yield
        if before_commit is not None and db.total_changes != changes_before:
            before_commit(db)


@contextmanager
def archive_snapshot(db: sqlite3.Connection) -> Iterator[None]:
    if db.in_transaction:
        # Replay verification must remain inside the caller's write transaction.
        yield
        return
    db.execute('BEGIN')
    with db:
        yield


def init_archive(db: sqlite3.Connection) -> None:
    with archive_write(db):
        init_receipt_store(db)
        init_reading_store(db)
        init_original_store(db)
        init_pair_store(db)
