import sqlite3

from archive.integrity import EvidenceMismatch
from archive.readings import get_capture, read_capture_evidence
from intake.accept import import_named
from intake.coverage import CoverageError
from intake.scales import NormalizationError
from portal.columns import BadRecording
from portal.recording import decode_named_recording
from portal.source import RecordedPortal
from tests.support import SAMPLES, StoreCase, fail_at_commit, page, recording


class CaptureTests(StoreCase):
    def test_named_order_and_source(self):
        registration = self.register()
        portal = RecordedPortal({'LOT-17': SAMPLES / 'named-complete.json'})
        self.addCleanup(portal.close)
        raw = portal.fetch_recording('LOT-17')
        receipt = import_named(self.db, registration, raw)
        capture, original = read_capture_evidence(self.db, receipt)
        self.assertEqual(original, raw)
        self.assertEqual((capture.registration_id, capture.version), (registration, 'v1'))
        self.assertEqual(
            [(item.specimen_id, item.value, item.location.as_key()) for item in capture.readings],
            [('x', 20, ('P1', 2)), ('y', 22, ('P1', 1))],
        )
        self.assertEqual(self.capture_counts(), (1, 2, 1))

    def test_reordered_columns(self):
        registration = self.register()
        raw = recording(page('A', [['y', 220]]), page('B', [[200, 'x']], ('reading', 'specimen_id')))
        receipt = import_named(self.db, registration, raw)
        self.assertEqual(
            [(item.specimen_id, item.value, item.location.as_key())
             for item in get_capture(self.db, receipt).readings],
            [('x', 20, ('B', 1)), ('y', 22, ('A', 1))],
        )

    def test_original_locations(self):
        registration = self.register(specimens=('x', 'y', 'z'))
        raw = recording(page('P1', [['y', 220], ['z', 230]]), page('P2', [['x', 200]]))
        receipt = import_named(self.db, registration, raw)
        self.reopen_store()
        capture, original = read_capture_evidence(self.db, receipt)
        self.assertEqual(original, raw)
        self.assertEqual([row.location.as_key() for row in capture.readings],
                         [('P2', 1), ('P1', 1), ('P1', 2)])
        source = {row.location.as_key(): row.specimen_id for row in decode_named_recording(original).rows}
        self.assertEqual([source[row.location.as_key()] for row in capture.readings], ['x', 'y', 'z'])
        self.assertEqual([row.value for row in capture.readings], [20, 22, 23])

    def test_bad_source(self):
        registration = self.register()
        base = page('P1', [['x', 200], ['y', 220]])
        invalid = {
            'wrong batch': recording(base, batch_id='LOT-18'),
            'duplicate page': recording(base, page('P1', [])),
            'missing column': recording(page('P1', [['x']], ('specimen_id',))),
            'duplicate column': recording(page('P1', [['x', 200, 200]], ('specimen_id', 'reading', 'reading'))),
            'missing field': recording(page('P1', [['x'], ['y', 220]])),
            'bad json': b'{',
        }
        for reason, raw in invalid.items():
            with self.subTest(reason=reason):
                with self.assertRaises(BadRecording):
                    import_named(self.db, registration, raw)
                self.assertEqual(self.capture_counts(), (0, 0, 0))

    def test_missing_piece_and_retry(self):
        registration = self.register()
        for raw in ((SAMPLES / 'named-incomplete.json').read_bytes(), recording()):
            with self.assertRaisesRegex(CoverageError, 'missing readings'):
                import_named(self.db, registration, raw)
            self.assertEqual(self.capture_counts(), (0, 0, 0))
        complete = (SAMPLES / 'named-complete.json').read_bytes()
        receipt = import_named(self.db, registration, complete)
        self.assertEqual(tuple(row.value for row in get_capture(self.db, receipt).readings), (20, 22))

    def test_duplicate_specimen(self):
        registration = self.register()
        raw = recording(page('P1', [['x', 200], ['x', 200], ['y', 220]]))
        with self.assertRaisesRegex(CoverageError, 'duplicate reading'):
            import_named(self.db, registration, raw)
        self.assertEqual(self.capture_counts(), (0, 0, 0))
        fixed = recording(page('P1', [['y', 220], ['x', 200]]))
        receipt = import_named(self.db, registration, fixed)
        self.assertEqual(get_capture(self.db, receipt).readings[0].location.as_key(), ('P1', 2))
        self.assertEqual(self.capture_counts(), (1, 2, 1))

    def test_foreign_specimen(self):
        registration = self.register()
        raw = recording(page('P1', [['x', 200], ['y', 220], ['z', 300]]))
        with self.assertRaisesRegex(CoverageError, 'outside roster'):
            import_named(self.db, registration, raw)
        self.assertEqual(self.capture_counts(), (0, 0, 0))
        fixed = recording(page('P1', [['x', 200], ['y', 220]]))
        receipt = import_named(self.db, registration, fixed)
        self.assertEqual([row.specimen_id for row in get_capture(self.db, receipt).readings], ['x', 'y'])

    def test_inexact_scale(self):
        registration = self.register()
        for value in (201, -201):
            with self.subTest(value=value):
                raw = recording(page('P1', [['x', value], ['y', 220]]))
                with self.assertRaisesRegex(NormalizationError, 'not a whole standard unit'):
                    import_named(self.db, registration, raw)
                self.assertEqual(self.capture_counts(), (0, 0, 0))

    def test_null_reading(self):
        registration = self.register()
        for value in (None, True, 200.0):
            with self.subTest(value=value), self.assertRaisesRegex(BadRecording, 'integer'):
                import_named(self.db, registration, recording(page('P1', [['x', value], ['y', 220]])))
        self.assertEqual(self.capture_counts(), (0, 0, 0))

    def test_invalid_source_scale(self):
        registration = self.register()
        valid_rows = page('P1', [['x', 200], ['y', 220]])
        for scale in ((1, 0), (-1, 10), (0, 1)):
            with self.subTest(scale=scale), self.assertRaisesRegex(NormalizationError, 'invalid source scale'):
                import_named(self.db, registration, recording(valid_rows, scale=scale))
        self.assertEqual(self.capture_counts(), (0, 0, 0))

    def test_signed_exact(self):
        registration = self.register(scale=(1, 6))
        raw = recording(page('P1', [['y', 0], ['x', -5]]), scale=(2, 3))
        receipt = import_named(self.db, registration, raw)
        self.reopen_store()
        self.assertEqual([row.value for row in get_capture(self.db, receipt).readings], [-20, 0])

    def test_commit_failure_and_retry(self):
        registration = self.register()
        old_raw = recording(page('P1', [['x', 200], ['y', 220]]))
        old = import_named(self.db, registration, old_raw)
        old_capture = get_capture(self.db, old)
        new_raw = recording(page('P1', [['x', 210], ['y', 230]]))
        pending_counts = []

        def reject_commit(db):
            pending_counts.append(self.capture_counts())
            fail_at_commit(db)

        with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY constraint failed'):
            import_named(self.db, registration, new_raw, before_commit=reject_commit)
        self.assertEqual(pending_counts, [(2, 4, 2)])
        self.reopen_store()
        self.assertEqual(self.capture_counts(), (1, 2, 1))
        self.assertEqual(read_capture_evidence(self.db, old), (old_capture, old_raw))

        new = import_named(self.db, registration, new_raw)
        self.assertNotEqual(old, new)
        self.assertEqual(import_named(self.db, registration, new_raw), new)
        capture, original = read_capture_evidence(self.db, new)
        self.assertEqual([row.value for row in capture.readings], [21, 23])
        self.assertEqual(original, new_raw)
        self.assertEqual(self.capture_counts(), (2, 4, 2))

    def test_identical_replay(self):
        registration = self.register()
        raw = (SAMPLES / 'named-complete.json').read_bytes()
        receipt = import_named(self.db, registration, raw)
        self.reopen_store()
        self.assertEqual(import_named(self.db, registration, raw, before_commit=fail_at_commit), receipt)
        self.assertEqual(self.capture_counts(), (1, 2, 1))
        self.assertEqual(read_capture_evidence(self.db, receipt)[1], raw)

    def test_distinct_recordings(self):
        registration = self.register()
        first = recording(page('P1', [['x', 200], ['y', 220]]))
        second = recording(page('P1', [['x', 240], ['y', 220]]))
        equivalent_bytes = first + b'\n'
        receipts = [import_named(self.db, registration, raw) for raw in (first, second, equivalent_bytes)]
        self.assertEqual(len(set(receipts)), 3)
        self.reopen_store()
        for receipt, raw, expected in zip(
            receipts, (first, second, equivalent_bytes), ((20, 22), (24, 22), (20, 22)), strict=True
        ):
            capture, original = read_capture_evidence(self.db, receipt)
            self.assertEqual(original, raw)
            self.assertEqual(tuple(row.value for row in capture.readings), expected)
        self.assertEqual(self.capture_counts(), (3, 6, 3))

    def test_replay_rejects_damaged_candidate(self):
        registration = self.register()
        raw = recording(page('P1', [['x', 200], ['y', 220]]))
        receipt = import_named(self.db, registration, raw)
        self.db.execute('DELETE FROM capture_originals WHERE receipt = ?', (receipt,))
        with self.assertRaises(EvidenceMismatch):
            import_named(self.db, registration, raw)
        self.assertEqual(self.capture_counts(), (1, 2, 0))
