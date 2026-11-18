import sqlite3


def init_original_store(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS capture_originals (
            receipt TEXT PRIMARY KEY NOT NULL REFERENCES capture_receipts (receipt),
            original BLOB NOT NULL CHECK (typeof(original) = 'blob')
        )
    ''')


def store_original(db: sqlite3.Connection, receipt: str, raw: bytes) -> None:
    db.execute('INSERT INTO capture_originals (receipt, original) VALUES (?, ?)', (receipt, raw))


def load_original(db: sqlite3.Connection, receipt: str) -> bytes | None:
    row = db.execute('SELECT original FROM capture_originals WHERE receipt = ?', (receipt,)).fetchone()
    return None if row is None else row[0]
