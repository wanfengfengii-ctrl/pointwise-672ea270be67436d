import sqlite3

from archive.commit import commit_capture
from archive.database import BeforeCommit
from archive.records import FixedReading
from intake.coverage import order_covered_rows
from intake.identity import identify_named_import
from intake.scales import NormalizationError, normalize_reading, parse_source_scale
from portal.columns import BadRecording
from portal.recording import decode_named_recording
from runs.registry import get_roster


def import_named(
    db: sqlite3.Connection,
    registration_id: str,
    raw: bytes,
    *,
    before_commit: BeforeCommit | None = None,
) -> str:
    roster = get_roster(db, registration_id).roster
    recording = decode_named_recording(raw)
    if recording.batch_id != roster.batch_id:
        raise BadRecording(f'recording belongs to {recording.batch_id!r}, expected {roster.batch_id!r}')

    source_scale = parse_source_scale(recording.source_scale)
    ordered = order_covered_rows(roster, recording.rows)
    readings = []
    for row in ordered:
        try:
            value = normalize_reading(row.raw_reading, source_scale, roster.scale)
        except NormalizationError as error:
            raise NormalizationError(f'{row.specimen_id!r} at {row.location.as_key()}: {error}') from error
        readings.append(FixedReading(row.specimen_id, value, row.location))

    identity = identify_named_import(registration_id, recording.raw)
    return commit_capture(
        db,
        identity,
        roster.version,
        tuple(readings),
        recording.raw,
        before_commit=before_commit,
    )
