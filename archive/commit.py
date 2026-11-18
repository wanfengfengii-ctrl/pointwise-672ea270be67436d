import sqlite3

from archive.database import BeforeCommit, archive_write
from archive.integrity import capture_seal
from archive.originals import store_original
from archive.readings import read_capture_evidence
from archive.receipts import ReceiptRecord, find_receipts_by_import, insert_receipt, new_receipt_id
from archive.records import FixedReading, insert_readings
from intake.identity import NamedImportIdentity


def commit_capture(
    db: sqlite3.Connection,
    identity: NamedImportIdentity,
    version: str,
    readings: tuple[FixedReading, ...],
    original: bytes,
    *,
    before_commit: BeforeCommit | None = None,
) -> str:
    with archive_write(db, before_commit=before_commit):
        for candidate in find_receipts_by_import(db, identity):
            _, archived_original = read_capture_evidence(db, candidate.receipt)
            if archived_original == original:
                return candidate.receipt

        receipt = new_receipt_id()
        record = ReceiptRecord(
            receipt=receipt,
            registration_id=identity.registration_id,
            version=version,
            original_digest=identity.original_digest,
            seal=capture_seal(receipt, identity.registration_id, version, readings, original),
        )
        insert_receipt(db, record)
        insert_readings(db, receipt, readings)
        store_original(db, receipt, original)
    return receipt
