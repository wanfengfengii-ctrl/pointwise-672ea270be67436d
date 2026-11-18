import sqlite3

from archive.database import BeforeCommit
from archive.readings import get_capture
from review.evaluate import evaluate_readings
from review.report import ReviewReport, build_report
from review.storage import load_report, save_report
from runs.registry import get_roster


def issue_review(
    db: sqlite3.Connection, receipt: str, *, before_commit: BeforeCommit | None = None
) -> ReviewReport:
    capture = get_capture(db, receipt)
    registered = get_roster(db, capture.registration_id)
    verdicts = evaluate_readings(capture, registered)
    report = build_report(
        capture.receipt,
        registered.registration_id,
        registered.roster.batch_id,
        registered.roster.version,
        verdicts,
    )
    save_report(db, report, before_commit=before_commit)
    return report


def get_report(db: sqlite3.Connection, report_id: str) -> ReviewReport:
    return load_report(db, report_id)
