"""Frozen storage for anonymous pair batches."""

import json
import sqlite3
from hashlib import sha256

from archive.database import BeforeCommit, archive_snapshot, archive_write
from archive.integrity import EvidenceMismatch
from pairs.model import PairBatch, PairConflict, PairSource
from pairs.tables import init_pair_store

__all__ = [
    'EvidenceMismatch',
    'PairConflict',
    'UnknownPairBatch',
    'batch_seal',
    'init_pair_store',
    'load_batch',
    'record_batch',
    'require_specimen',
]


class UnknownPairBatch(KeyError):
    pass


def _encode_labels(values: tuple[str, ...]) -> str:
    return json.dumps(list(values), ensure_ascii=True, separators=(',', ':'))


def _encode_readings(values: tuple[int, ...]) -> str:
    return json.dumps(list(values), ensure_ascii=True, separators=(',', ':'))


def _decode_labels(raw: object) -> tuple[str, ...]:
    values = json.loads(raw)
    if not isinstance(values, list):
        raise ValueError('stored labels are not a list')
    labels = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError('stored label is not a nonempty string')
        value.encode('utf-8')
        labels.append(value)
    return tuple(labels)


def _decode_readings(raw: object) -> tuple[int, ...]:
    values = json.loads(raw)
    if not isinstance(values, list):
        raise ValueError('stored readings are not a list')
    readings = []
    for value in values:
        if type(value) is not int:
            raise ValueError('stored reading is not an integer')
        readings.append(value)
    return tuple(readings)


def batch_seal(batch: PairBatch) -> str:
    snapshot = [
        'anonymous-pair-v1',
        batch.batch_id,
        list(batch.roster),
        [[source.source_id, list(source.members), list(source.readings)] for source in batch.exports],
    ]
    encoded = json.dumps(snapshot, ensure_ascii=True, separators=(',', ':')).encode('ascii')
    return sha256(encoded).hexdigest()


def load_batch(db: sqlite3.Connection, batch_id: str) -> PairBatch:
    """Read frozen evidence and confirm it is complete, covered and sealed."""
    with archive_snapshot(db):
        row = db.execute(
            'SELECT roster, seal FROM pair_batches WHERE batch_id = ?', (batch_id,)
        ).fetchone()
        if row is None:
            raise UnknownPairBatch(batch_id)
        roster_raw, seal = row
        try:
            roster = _decode_labels(roster_raw)
        except (TypeError, ValueError) as error:
            raise EvidenceMismatch(f'invalid frozen roster for {batch_id}') from error

        sources = []
        rows = db.execute(
            'SELECT ordinal, source_id, members, readings '
            'FROM pair_sources WHERE batch_id = ? ORDER BY ordinal',
            (batch_id,),
        )
        for expected_ordinal, (ordinal, source_id, members_raw, readings_raw) in enumerate(rows):
            if ordinal != expected_ordinal:
                raise EvidenceMismatch(f'frozen sources have a gap for {batch_id}')
            try:
                if not isinstance(source_id, str) or not source_id.strip():
                    raise ValueError('stored source id is invalid')
                members = _decode_labels(members_raw)
                readings = _decode_readings(readings_raw)
                if len(members) not in (1, 2) or len(members) != len(readings):
                    raise ValueError('stored source shape is invalid')
                if len(set(members)) != len(members):
                    raise ValueError('stored source repeats a member')
                if not set(members) <= set(roster):
                    raise ValueError('stored source leaves the roster')
            except (TypeError, ValueError) as error:
                raise EvidenceMismatch(f'invalid frozen source for {batch_id}') from error
            sources.append(PairSource(source_id, members, readings))

        covered = {member for source in sources for member in source.members}
        if covered != set(roster):
            raise EvidenceMismatch(f'frozen coverage differs for {batch_id}')
        batch = PairBatch(batch_id, roster, tuple(sources))
        if batch_seal(batch) != seal:
            raise EvidenceMismatch(f'frozen evidence differs for {batch_id}')
        return batch


def record_batch(
    db: sqlite3.Connection,
    batch: PairBatch,
    *,
    before_commit: BeforeCommit | None = None,
) -> str:
    """Freeze a validated, solvable batch or reuse an identical one.

    Returns the batch id as its receipt.  A same-id submission with different
    evidence conflicts; a damaged frozen batch is reported as a mismatch; a
    failed insert or commit leaves no partial rows behind.
    """
    with archive_write(db, before_commit=before_commit):
        existing = db.execute(
            'SELECT 1 FROM pair_batches WHERE batch_id = ?', (batch.batch_id,)
        ).fetchone()
        if existing is not None:
            frozen = load_batch(db, batch.batch_id)
            if frozen != batch:
                raise PairConflict(f'batch already fixed differently: {batch.batch_id!r}')
            return frozen.batch_id

        db.execute(
            'INSERT INTO pair_batches (batch_id, roster, seal) VALUES (?, ?, ?)',
            (batch.batch_id, _encode_labels(batch.roster), batch_seal(batch)),
        )
        db.executemany(
            'INSERT INTO pair_sources (batch_id, ordinal, source_id, members, readings) '
            'VALUES (?, ?, ?, ?, ?)',
            (
                (batch.batch_id, ordinal, source.source_id,
                 _encode_labels(source.members), _encode_readings(source.readings))
                for ordinal, source in enumerate(batch.exports)
            ),
        )
    return batch.batch_id


def require_specimen(batch: PairBatch, specimen: object) -> str:
    """Return a specimen that belongs to the frozen roster, else ``KeyError``."""
    if isinstance(specimen, str) and specimen in batch.roster:
        return specimen
    raise KeyError(specimen)
