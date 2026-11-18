import sqlite3
from dataclasses import dataclass

from archive.database import archive_snapshot
from archive.integrity import EvidenceMismatch, verify_capture_seal
from archive.originals import load_original
from archive.receipts import load_receipt
from archive.records import FixedReading, load_readings


class UnknownCapture(KeyError):
    pass


@dataclass(frozen=True, slots=True)
class NamedCapture:
    receipt: str
    registration_id: str
    version: str
    readings: tuple[FixedReading, ...]


def read_capture_evidence(db: sqlite3.Connection, receipt: str) -> tuple[NamedCapture, bytes]:
    with archive_snapshot(db):
        record = load_receipt(db, receipt)
        if record is None:
            raise UnknownCapture(receipt)
        try:
            readings = load_readings(db, receipt)
        except (TypeError, ValueError) as error:
            raise EvidenceMismatch(f'invalid frozen reading for {receipt}') from error
        original = load_original(db, receipt)
        verify_capture_seal(record, readings, original)
        return NamedCapture(record.receipt, record.registration_id, record.version, readings), original


def get_capture(db: sqlite3.Connection, receipt: str) -> NamedCapture:
    capture, _ = read_capture_evidence(db, receipt)
    return capture
