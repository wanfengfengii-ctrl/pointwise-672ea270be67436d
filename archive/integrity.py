import json
from hashlib import sha256

from archive.receipts import ReceiptRecord
from archive.records import FixedReading
from intake.identity import identify_named_import


class EvidenceMismatch(RuntimeError):
    pass


def capture_seal(
    receipt: str,
    registration_id: str,
    version: str,
    readings: tuple[FixedReading, ...],
    original: bytes,
) -> str:
    source = identify_named_import(registration_id, original)
    snapshot = [
        'named-capture-v1',
        receipt,
        registration_id,
        version,
        source.original_digest,
        [[row.specimen_id, hex(row.value), *row.location.as_key()] for row in readings],
    ]
    encoded = json.dumps(snapshot, ensure_ascii=True, separators=(',', ':')).encode('ascii')
    return sha256(encoded).hexdigest()


def verify_capture_seal(
    record: ReceiptRecord, readings: tuple[FixedReading, ...], original: bytes | None
) -> None:
    if original is None or not isinstance(original, bytes):
        raise EvidenceMismatch(f'original unavailable for {record.receipt}')
    identity = identify_named_import(record.registration_id, original)
    if identity.original_digest != record.original_digest:
        raise EvidenceMismatch(f'original digest differs for {record.receipt}')
    expected = capture_seal(record.receipt, record.registration_id, record.version, readings, original)
    if expected != record.seal:
        raise EvidenceMismatch(f'frozen capture differs for {record.receipt}')
