import sqlite3
from dataclasses import dataclass
from uuid import uuid4

from intake.identity import NamedImportIdentity


@dataclass(frozen=True, slots=True)
class ReceiptRecord:
    receipt: str
    registration_id: str
    version: str
    original_digest: str
    seal: str


_FIELDS = 'receipt, registration_id, version, original_digest, seal'


def new_receipt_id() -> str:
    return f'cap-{uuid4().hex}'


def init_receipt_store(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS capture_receipts (
            receipt TEXT PRIMARY KEY NOT NULL,
            registration_id TEXT NOT NULL REFERENCES rosters (registration_id),
            version TEXT NOT NULL,
            original_digest TEXT NOT NULL,
            seal TEXT NOT NULL
        )
    ''')
    db.execute('''
        CREATE INDEX IF NOT EXISTS capture_import_candidates
        ON capture_receipts (registration_id, original_digest)
    ''')


def insert_receipt(db: sqlite3.Connection, record: ReceiptRecord) -> None:
    db.execute(
        f'INSERT INTO capture_receipts ({_FIELDS}) VALUES (?, ?, ?, ?, ?)',
        (record.receipt, record.registration_id, record.version, record.original_digest, record.seal),
    )


def load_receipt(db: sqlite3.Connection, receipt: str) -> ReceiptRecord | None:
    row = db.execute(
        f'SELECT {_FIELDS} FROM capture_receipts WHERE receipt = ?', (receipt,)
    ).fetchone()
    return None if row is None else ReceiptRecord(*row)


def find_receipts_by_import(
    db: sqlite3.Connection, identity: NamedImportIdentity
) -> tuple[ReceiptRecord, ...]:
    rows = db.execute(
        f'SELECT {_FIELDS} FROM capture_receipts '
        'WHERE registration_id = ? AND original_digest = ? ORDER BY receipt',
        (identity.registration_id, identity.original_digest),
    )
    return tuple(ReceiptRecord(*row) for row in rows)
