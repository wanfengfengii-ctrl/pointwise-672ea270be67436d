import json
import sqlite3
from fractions import Fraction
from uuid import uuid4

from runs.roster import RegisteredRoster, Roster


class RosterConflict(ValueError):
    pass


class UnknownRegistration(KeyError):
    pass


def init_roster_store(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS rosters (
            registration_id TEXT PRIMARY KEY NOT NULL,
            batch_id TEXT NOT NULL,
            version TEXT NOT NULL,
            scale_num TEXT NOT NULL,
            scale_den TEXT NOT NULL,
            ordered_limits TEXT NOT NULL,
            UNIQUE (batch_id, version)
        )
    ''')


_ROSTER_FIELDS = 'registration_id, batch_id, version, scale_num, scale_den, ordered_limits'


def _restore_roster(row: tuple) -> RegisteredRoster:
    registration_id, batch_id, version, numerator, denominator, snapshot = row
    pieces = json.loads(snapshot)
    roster = Roster(
        batch_id=batch_id,
        version=version,
        specimens=tuple(specimen for specimen, _ in pieces),
        limits=tuple(int(limit, 16) for _, limit in pieces),
        scale=Fraction(int(numerator, 16), int(denominator, 16)),
    )
    return RegisteredRoster(registration_id, roster)


def register_roster(db: sqlite3.Connection, roster: Roster) -> str:
    db.execute('BEGIN IMMEDIATE')
    with db:
        row = db.execute(
            f'SELECT {_ROSTER_FIELDS} FROM rosters WHERE batch_id = ? AND version = ?',
            (roster.batch_id, roster.version),
        ).fetchone()
        if row is not None:
            registered = _restore_roster(row)
            if registered.roster != roster:
                raise RosterConflict(f'roster version already fixed: {roster.batch_id}/{roster.version}')
            return registered.registration_id

        registration_id = f'reg-{uuid4().hex}'
        ordered_limits = json.dumps([
            (specimen, hex(limit))
            for specimen, limit in zip(roster.specimens, roster.limits, strict=True)
        ])
        db.execute(
            f'INSERT INTO rosters ({_ROSTER_FIELDS}) VALUES (?, ?, ?, ?, ?, ?)',
            (registration_id, roster.batch_id, roster.version,
             hex(roster.scale.numerator), hex(roster.scale.denominator), ordered_limits),
        )
    return registration_id


def load_roster(db: sqlite3.Connection, registration_id: str) -> RegisteredRoster:
    row = db.execute(
        f'SELECT {_ROSTER_FIELDS} FROM rosters WHERE registration_id = ?',
        (registration_id,),
    ).fetchone()
    if row is None:
        raise UnknownRegistration(registration_id)
    return _restore_roster(row)
