import json
import sqlite3

from archive.database import BeforeCommit, archive_write
from review.report import ReviewReport, SpecimenVerdict


class UnknownReport(KeyError):
    pass


_FIELDS = 'report_id, receipt, registration_id, batch_id, version, snapshot'


def init_report_store(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS review_reports (
            report_id TEXT PRIMARY KEY NOT NULL,
            receipt TEXT NOT NULL REFERENCES capture_receipts (receipt),
            registration_id TEXT NOT NULL REFERENCES rosters (registration_id),
            batch_id TEXT NOT NULL,
            version TEXT NOT NULL,
            snapshot TEXT NOT NULL
        )
    ''')


def save_report(
    db: sqlite3.Connection, report: ReviewReport, *, before_commit: BeforeCommit | None = None
) -> None:
    snapshot = json.dumps({
        'verdicts': [
            [row.specimen_id, hex(row.value), hex(row.limit), row.passed]
            for row in report.verdicts
        ],
        'over_limit': report.over_limit,
    })
    with archive_write(db, before_commit=before_commit):
        db.execute(
            f'INSERT INTO review_reports ({_FIELDS}) VALUES (?, ?, ?, ?, ?, ?)',
            (report.report_id, report.receipt, report.registration_id,
             report.batch_id, report.version, snapshot),
        )


def load_report(db: sqlite3.Connection, report_id: str) -> ReviewReport:
    row = db.execute(
        f'SELECT {_FIELDS} FROM review_reports WHERE report_id = ?', (report_id,)
    ).fetchone()
    if row is None:
        raise UnknownReport(report_id)
    fixed_id, receipt, registration_id, batch_id, version, snapshot = row
    saved = json.loads(snapshot)
    verdicts = tuple(
        SpecimenVerdict(specimen, int(value, 16), int(limit, 16), passed)
        for specimen, value, limit, passed in saved['verdicts']
    )
    return ReviewReport(
        fixed_id, receipt, registration_id, batch_id, version, verdicts, tuple(saved['over_limit'])
    )
