import sqlite3
from dataclasses import dataclass

from portal.evidence import SourceLocation


@dataclass(frozen=True, slots=True)
class FixedReading:
    specimen_id: str
    value: int
    location: SourceLocation


def init_reading_store(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS capture_readings (
            receipt TEXT NOT NULL REFERENCES capture_receipts (receipt),
            ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
            specimen_id TEXT NOT NULL,
            reading TEXT NOT NULL,
            page_id TEXT NOT NULL,
            row_number INTEGER NOT NULL CHECK (row_number >= 1),
            PRIMARY KEY (receipt, ordinal),
            UNIQUE (receipt, specimen_id),
            UNIQUE (receipt, page_id, row_number)
        )
    ''')


def insert_readings(
    db: sqlite3.Connection, receipt: str, readings: tuple[FixedReading, ...]
) -> None:
    db.executemany(
        'INSERT INTO capture_readings (receipt, ordinal, specimen_id, reading, page_id, row_number) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (
            (receipt, ordinal, reading.specimen_id, hex(reading.value), *reading.location.as_key())
            for ordinal, reading in enumerate(readings)
        ),
    )


def load_readings(db: sqlite3.Connection, receipt: str) -> tuple[FixedReading, ...]:
    rows = db.execute(
        'SELECT ordinal, specimen_id, reading, page_id, row_number '
        'FROM capture_readings WHERE receipt = ? ORDER BY ordinal',
        (receipt,),
    )
    readings = []
    for expected_ordinal, row in enumerate(rows):
        ordinal, specimen, value, page_id, row_number = row
        if ordinal != expected_ordinal:
            raise ValueError('stored readings have a gap in roster order')
        readings.append(FixedReading(specimen, int(value, 16), SourceLocation(page_id, row_number)))
    return tuple(readings)
