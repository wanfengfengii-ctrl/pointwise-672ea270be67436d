import sqlite3
from dataclasses import dataclass

from archive.database import archive_snapshot
from archive.integrity import EvidenceMismatch, verify_capture_seal
from archive.originals import load_original
from archive.receipts import load_receipt
from archive.records import FixedReading, load_readings
from pairs.model import NoJointInterpretation
from pairs.solve import pair_values
from pairs.storage import load_batch, require_specimen


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


def read_pair(
    db: sqlite3.Connection, receipt: str, left: str, right: str
) -> list[tuple[int, int]]:
    """All ordered value pairs for two specimens that can hold simultaneously.

    Only the receipt's frozen evidence is consulted, so the query works after
    the portal and database are closed and reopened.  An unknown anonymous
    receipt or a specimen outside its roster raises ``KeyError``; damaged or
    inconsistent frozen evidence raises :class:`EvidenceMismatch` rather than
    returning a partial or guessed answer.  Named receipts keep their existing
    read and issue path.
    """
    batch = load_batch(db, receipt)
    left_id = require_specimen(batch, left)
    right_id = require_specimen(batch, right)
    try:
        return pair_values(batch, left_id, right_id)
    except NoJointInterpretation as error:
        # The seal confirmed the frozen evidence is what was accepted, and
        # acceptance requires a joint interpretation; failing to find one now
        # means the stored evidence cannot be trusted, so never guess.
        raise EvidenceMismatch(f'frozen evidence has no joint interpretation for {receipt}') from error
