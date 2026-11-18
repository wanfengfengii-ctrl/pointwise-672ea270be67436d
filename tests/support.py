import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.database import init_archive, open_archive
from review.storage import init_report_store
from runs.registry import register
from runs.storage import init_roster_store


SAMPLES = Path(__file__).resolve().parents[1] / 'samples'


def page(page_id, rows, columns=('specimen_id', 'reading')):
    return {'page_id': page_id, 'columns': list(columns), 'rows': list(rows)}


def recording(*pages, batch_id='LOT-17', scale=(1, 10)):
    return json.dumps({'batch_id': batch_id, 'source_scale': scale, 'pages': pages}).encode('utf-8')


def fail_at_commit(db):
    # A deferred foreign key lets the statement succeed and rejects the real COMMIT.
    db.execute('CREATE TEMP TABLE commit_guard_parent (id INTEGER PRIMARY KEY)')
    db.execute('''
        CREATE TEMP TABLE commit_guard_child (
            parent_id INTEGER REFERENCES commit_guard_parent (id) DEFERRABLE INITIALLY DEFERRED
        )
    ''')
    db.execute('INSERT INTO commit_guard_child (parent_id) VALUES (1)')


class StoreCase(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix='lab-regression-')
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'handoff.sqlite3'
        self.db = None
        self.addCleanup(self.close_store)
        self.reopen_store()

    def close_store(self):
        if self.db is not None:
            self.db.close()
            self.db = None

    def reopen_store(self):
        self.close_store()
        self.db = open_archive(self.path)
        self.initialize()

    def initialize(self):
        init_roster_store(self.db)
        init_archive(self.db)
        init_report_store(self.db)

    def register(self, *, version='v1', specimens=('x', 'y'), limit=20, scale=(1, 1)):
        return register(
            self.db, 'LOT-17', version, specimens,
            {specimen: limit for specimen in specimens}, scale,
        )

    def capture_counts(self):
        return self.db.execute('''
            SELECT (SELECT count(*) FROM capture_receipts),
                   (SELECT count(*) FROM capture_readings),
                   (SELECT count(*) FROM capture_originals)
        ''').fetchone()

    def report_ids(self):
        return {row[0] for row in self.db.execute('SELECT report_id FROM review_reports')}
