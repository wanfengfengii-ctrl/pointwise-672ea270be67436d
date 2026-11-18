import sqlite3

from archive.integrity import EvidenceMismatch
from archive.readings import UnknownCapture, get_capture, read_capture_evidence
from intake.accept import import_named
from portal.recording import decode_named_recording
from portal.source import PortalClosed, RecordedPortal
from review.issue import get_report, issue_review
from review.storage import UnknownReport
from runs.registry import register
from tests.support import SAMPLES, StoreCase, fail_at_commit, page, recording


class HandoffTests(StoreCase):
    def test_offline_issue_and_trace(self):
        registration = self.register()
        portal = RecordedPortal({'LOT-17': SAMPLES / 'named-complete.json'})
        self.addCleanup(portal.close)
        receipt = import_named(self.db, registration, portal.fetch_recording('LOT-17'))
        portal.close()
        self.reopen_store()
        with self.assertRaises(PortalClosed):
            portal.fetch_recording('LOT-17')

        report = issue_review(self.db, receipt)
        self.assertEqual((report.receipt, report.registration_id, report.version),
                         (receipt, registration, 'v1'))
        self.assertEqual(
            [(item.specimen_id, item.value, item.limit, item.passed) for item in report.verdicts],
            [('x', 20, 20, True), ('y', 22, 20, False)],
        )
        self.assertEqual(report.over_limit, ('y',))
        self.assertEqual(get_report(self.db, report.report_id), report)

        capture, original = read_capture_evidence(self.db, report.receipt)
        locations = {item.location.as_key(): item for item in decode_named_recording(original).rows}
        self.assertEqual(
            [(item.specimen_id, item.location.as_key(), locations[item.location.as_key()].specimen_id)
             for item in capture.readings],
            [('x', ('P1', 2), 'x'), ('y', ('P1', 1), 'y')],
        )

    def test_evidence_mismatch(self):
        registration = self.register()
        portal = RecordedPortal({'LOT-17': SAMPLES / 'named-complete.json'})
        self.addCleanup(portal.close)
        receipt = import_named(self.db, registration, portal.fetch_recording('LOT-17'))
        portal.close()
        alternate = recording(page('P1', [['y', 230], ['x', 200]]))
        self.db.execute('UPDATE capture_originals SET original = ? WHERE receipt = ?', (alternate, receipt))
        self.reopen_store()
        with self.assertRaises(EvidenceMismatch):
            get_capture(self.db, receipt)
        with self.assertRaises(EvidenceMismatch):
            issue_review(self.db, receipt)
        self.assertEqual(self.report_ids(), set())

    def test_frozen_reading_mismatch(self):
        registration = self.register()
        raw = (SAMPLES / 'named-complete.json').read_bytes()
        receipt = import_named(self.db, registration, raw)
        self.db.execute(
            'UPDATE capture_readings SET reading = ? WHERE receipt = ? AND specimen_id = ?',
            (hex(19), receipt, 'x'),
        )
        self.reopen_store()
        with self.assertRaises(EvidenceMismatch):
            read_capture_evidence(self.db, receipt)
        with self.assertRaises(EvidenceMismatch):
            issue_review(self.db, receipt)
        self.assertEqual(self.report_ids(), set())

    def test_unknown_capture(self):
        with self.assertRaises(UnknownCapture):
            get_capture(self.db, 'unknown-receipt')
        with self.assertRaises(UnknownCapture):
            issue_review(self.db, 'unknown-receipt')
        self.assertEqual(self.report_ids(), set())

    def test_report_write_failure(self):
        registration = self.register()
        raw = recording(page('P1', [['x', 200], ['y', 220]]))
        old_receipt = import_named(self.db, registration, raw)
        old_report = issue_review(self.db, old_receipt)
        next_raw = recording(page('P1', [['x', 190], ['y', 200]]))
        next_receipt = import_named(self.db, registration, next_raw)
        pending_ids = []

        def reject_commit(db):
            pending_ids.append(self.report_ids())
            fail_at_commit(db)

        with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY constraint failed'):
            issue_review(self.db, next_receipt, before_commit=reject_commit)
        self.assertEqual(len(pending_ids), 1)
        self.assertIn(old_report.report_id, pending_ids[0])
        failed_ids = pending_ids[0] - {old_report.report_id}
        self.assertEqual(len(failed_ids), 1)
        self.reopen_store()
        self.assertEqual(self.report_ids(), {old_report.report_id})
        with self.assertRaises(UnknownReport):
            get_report(self.db, next(iter(failed_ids)))
        self.assertEqual(get_report(self.db, old_report.report_id), old_report)
        self.assertEqual(read_capture_evidence(self.db, next_receipt)[1], next_raw)
        report = issue_review(self.db, next_receipt)
        self.assertEqual(report.receipt, next_receipt)
        self.assertEqual(report.over_limit, ())
        self.assertEqual(get_report(self.db, report.report_id), report)

    def test_historical_report_after_new_version(self):
        old_registration = self.register()
        raw = (SAMPLES / 'named-complete.json').read_bytes()
        receipt = import_named(self.db, old_registration, raw)
        signed = issue_review(self.db, receipt)
        self.register(version='v2', limit=25)
        self.reopen_store()
        historical = get_report(self.db, signed.report_id)
        self.assertEqual((historical.receipt, historical.registration_id, historical.version),
                         (receipt, old_registration, 'v1'))
        self.assertEqual([verdict.limit for verdict in historical.verdicts], [20, 20])
        self.assertEqual(historical.over_limit, ('y',))

    def test_version_before_issue(self):
        old_registration = self.register()
        raw = (SAMPLES / 'named-complete.json').read_bytes()
        receipt = import_named(self.db, old_registration, raw)
        self.register(version='v2', limit=25)
        self.reopen_store()
        report = issue_review(self.db, receipt)
        self.assertEqual((report.registration_id, report.version, report.over_limit),
                         (old_registration, 'v1', ('y',)))
        self.assertEqual([(row.limit, row.passed) for row in report.verdicts], [(20, True), (20, False)])

    def test_report_identity(self):
        raw = (SAMPLES / 'named-complete.json').read_bytes()
        old_registration = self.register()
        old_receipt = import_named(self.db, old_registration, raw)
        old_report = issue_review(self.db, old_receipt)
        new_registration = self.register(version='v2', limit=25)
        new_receipt = import_named(self.db, new_registration, raw)
        new_report = issue_review(self.db, new_receipt)
        self.assertNotEqual(old_report.report_id, new_report.report_id)
        self.assertNotEqual(old_receipt, new_receipt)

        self.initialize()
        self.reopen_store()
        expected = [
            (old_report.report_id, old_receipt, old_registration, 'v1', (20, 20), (True, False), ('y',)),
            (new_report.report_id, new_receipt, new_registration, 'v2', (25, 25), (True, True), ()),
        ]
        for report_id, receipt, registration, version, limits, decisions, over in expected:
            report = get_report(self.db, report_id)
            self.assertEqual((report.report_id, report.receipt, report.registration_id, report.version),
                             (report_id, receipt, registration, version))
            self.assertEqual([row.specimen_id for row in report.verdicts], ['x', 'y'])
            self.assertEqual([row.value for row in report.verdicts], [20, 22])
            self.assertEqual(tuple(row.limit for row in report.verdicts), limits)
            self.assertEqual(tuple(row.passed for row in report.verdicts), decisions)
            self.assertEqual(report.over_limit, over)

    def test_unknown_report(self):
        registration = self.register()
        raw = (SAMPLES / 'named-complete.json').read_bytes()
        existing = issue_review(self.db, import_named(self.db, registration, raw))
        with self.assertRaises(UnknownReport):
            get_report(self.db, 'unknown-report')
        self.assertEqual(self.report_ids(), {existing.report_id})

    def test_integers_beyond_sqlite_range(self):
        large = 2 ** 128
        registration = register(self.db, 'LOT-17', 'v1', ('x', 'y'),
                                {'x': large, 'y': -large}, (1, 1))
        raw = recording(page('P1', [['x', large + 1], ['y', -large]]), scale=(1, 1))
        receipt = import_named(self.db, registration, raw)
        report_id = issue_review(self.db, receipt).report_id
        self.reopen_store()
        report = get_report(self.db, report_id)
        self.assertEqual([(row.value, row.limit) for row in report.verdicts],
                         [(large + 1, large), (-large, -large)])
        self.assertEqual(report.over_limit, ('x',))
