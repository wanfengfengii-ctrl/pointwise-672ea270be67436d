"""Anonymous pair handoff demo.

Fetches the ``path`` and ``independent`` recordings from a recorded portal,
accepts both batches, then disables the source and closes the archive.  After
reopening only the archive, it reads x/z back from each receipt and shows the
concrete difference: two pairs versus four.  The named demo in ``demo.py``
remains runnable on its own.
"""

import json
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.database import init_archive, open_archive
from archive.readings import read_pair
from intake.accept import ingest_pairs
from portal.source import PortalClosed, RecordedPortal
from review.storage import init_report_store
from runs.storage import init_roster_store

EXPECTED = {
    'P-01': [(10, 10), (20, 20)],
    'P-02': [(10, 10), (10, 20), (20, 10), (20, 20)],
}
RECORDINGS = {'P-01': 'pair-path.json', 'P-02': 'pair-independent.json'}
SAMPLE_CASES = ('path', 'independent')


def initialize(db) -> None:
    init_roster_store(db)
    init_archive(db)
    init_report_store(db)


def main() -> None:
    samples = Path(__file__).resolve().parent / 'samples'
    catalog = json.loads((samples / 'pair-cases.json').read_text(encoding='utf-8'))

    with TemporaryDirectory(prefix='lab-pairs-') as temporary:
        database = Path(temporary) / 'handoff.sqlite3'
        receipts = {}
        with closing(open_archive(database)) as db:
            initialize(db)
            portal = RecordedPortal(
                {batch_id: samples / name for batch_id, name in RECORDINGS.items()}
            )
            try:
                for sample_name, batch_id in zip(SAMPLE_CASES, RECORDINGS, strict=True):
                    recording = json.loads(portal.fetch_recording(batch_id).decode('utf-8'))
                    if recording != catalog[sample_name]:
                        raise AssertionError((sample_name, recording))
                    receipts[batch_id] = ingest_pairs(db, **recording)
            finally:
                # The shift is over: the source is disabled and the archive closed.
                portal.close()

        try:
            portal.fetch_recording('P-01')
        except PortalClosed:
            pass
        else:
            raise AssertionError('disabled portal still served a recording')

        with closing(open_archive(database)) as db:
            initialize(db)
            observed = {
                batch_id: read_pair(db, receipt, 'x', 'z')
                for batch_id, receipt in receipts.items()
            }
            reversed_pairs = {
                batch_id: read_pair(db, receipt, 'z', 'x')
                for batch_id, receipt in receipts.items()
            }

        if observed != EXPECTED or set(receipts.values()) != set(EXPECTED):
            raise AssertionError((observed, receipts))
        if reversed_pairs != {key: sorted((b, a) for a, b in value)
                              for key, value in EXPECTED.items()}:
            raise AssertionError(reversed_pairs)

        for batch_id, receipt in receipts.items():
            pairs = observed[batch_id]
            print(f'{batch_id}（回执 {receipt}）x/z 可行读数对 {len(pairs)} 对：{pairs}')
        print('两批共用同一清册形状，但 path 只允许同值对角，independent 允许交叉。')
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'pairs-v1',
            'inputs': {name: catalog[name] for name in SAMPLE_CASES},
            'receipts': receipts,
            'expected': EXPECTED,
            'actual': observed,
            'reversed_actual': reversed_pairs,
            'code_paths': ['intake/accept.py', 'pairs/model.py', 'pairs/solve.py',
                           'pairs/storage.py', 'archive/readings.py'],
            'oracle': '枚举每片取值：path 两份来源共享 y，故 x=z 只能同为 10 或同为 20；'
                      'independent 的 x/y 与 z/w 互不约束，x、z 各取 10 或 20。',
        }, ensure_ascii=False, separators=(',', ':')))


if __name__ == '__main__':
    main()
