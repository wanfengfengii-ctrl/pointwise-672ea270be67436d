import json
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.database import init_archive, open_archive
from archive.readings import read_capture_evidence
from intake.accept import import_named
from intake.coverage import CoverageError
from portal.recording import decode_named_recording
from portal.source import RecordedPortal
from review.issue import get_report, issue_review
from review.storage import init_report_store
from runs.registry import register
from runs.storage import init_roster_store


def initialize(db) -> None:
    init_roster_store(db)
    init_archive(db)
    init_report_store(db)


def main() -> None:
    samples = Path(__file__).resolve().parent / 'samples'
    plan = json.loads((samples / 'roster.json').read_text(encoding='utf-8'))
    batch_id = plan['batch_id']
    with TemporaryDirectory(prefix='lab-handoff-') as temporary:
        database = Path(temporary) / 'handoff.sqlite3'
        with closing(open_archive(database)) as db:
            initialize(db)
            registration = register(db, **plan)
            incomplete = RecordedPortal({batch_id: samples / 'named-incomplete.json'})
            try:
                import_named(db, registration, incomplete.fetch_recording(batch_id))
            except CoverageError as error:
                print(f'缺片录制未发布。{error}')
            else:
                raise AssertionError('incomplete recording was published')
            finally:
                incomplete.close()

            portal = RecordedPortal({batch_id: samples / 'named-complete.json'})
            try:
                receipt = import_named(db, registration, portal.fetch_recording(batch_id))
            finally:
                portal.close()

        with closing(open_archive(database)) as db:
            initialize(db)
            capture, original = read_capture_evidence(db, receipt)
            report = get_report(db, issue_review(db, receipt).report_id)

        recording = decode_named_recording(original)
        source_rows = {row.location.as_key(): row for row in recording.rows}
        actual = [
            [row.specimen_id, row.value, *row.location.as_key(), source_rows[row.location.as_key()].specimen_id]
            for row in capture.readings
        ]
        expected = [['x', 20, 'P1', 2, 'x'], ['y', 22, 'P1', 1, 'y']]
        downstream_actual = {
            'verdicts': [[row.specimen_id, row.value, row.limit, row.passed] for row in report.verdicts],
            'over_limit': list(report.over_limit),
            'receipt_bound': report.receipt == receipt and report.registration_id == registration,
            'version': report.version,
        }
        downstream_expected = {
            'verdicts': [['x', 20, 20, True], ['y', 22, 20, False]],
            'over_limit': ['y'],
            'receipt_bound': True,
            'version': 'v1',
        }
        if actual != expected or downstream_actual != downstream_expected:
            raise AssertionError((actual, downstream_actual))
        for verdict in report.verdicts:
            print(f'{verdict.specimen_id}={verdict.value}，上限 {verdict.limit}，'
                  f'{"通过" if verdict.passed else "越限"}')
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'v7',
            'input': {'plan': plan, 'source_scale': list(recording.source_scale),
                      'source_rows': [[row.specimen_id, row.raw_reading, *row.location.as_key()]
                                      for row in recording.rows]},
            'expected': expected,
            'actual': actual,
            'downstream_expected': downstream_expected,
            'downstream_actual': downstream_actual,
            'code_paths': ['portal/pages.py', 'intake/accept.py', 'intake/scales.py',
                           'archive/readings.py', 'review/issue.py', 'review/evaluate.py'],
            'oracle': '按固定样例手算 200/10=20、220/10=22，核对 P1 第 2、1 行和上限 20。',
        }, ensure_ascii=False, separators=(',', ':')))


if __name__ == '__main__':
    main()
