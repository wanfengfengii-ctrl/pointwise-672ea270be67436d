import sqlite3
from collections.abc import Mapping, Sequence
from fractions import Fraction

from runs.roster import RegisteredRoster, build_roster
from runs.storage import load_roster, register_roster


def register(
    db: sqlite3.Connection,
    batch_id: str,
    version: str,
    specimens: Sequence[str],
    limits: Mapping[str, int],
    scale: Fraction | Sequence[int],
) -> str:
    roster = build_roster(batch_id, version, specimens, limits, scale)
    return register_roster(db, roster)


def get_roster(db: sqlite3.Connection, registration_id: str) -> RegisteredRoster:
    return load_roster(db, registration_id)
