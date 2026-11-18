import json
import sqlite3

from archive.integrity import EvidenceMismatch
from archive.readings import read_pair
from intake.accept import ingest_pairs
from pairs.model import NoJointInterpretation, PairConflict, PairInputError
from pairs.storage import UnknownPairBatch
from tests.pair_oracle import expected_pairs, has_solution
from tests.support import SAMPLES, StoreCase, fail_at_commit

CASES = json.loads((SAMPLES / 'pair-cases.json').read_text(encoding='utf-8'))
EXPECTED = {
    'path': [(10, 10), (20, 20)],
    'independent': [(10, 10), (10, 20), (20, 10), (20, 20)],
    'even': [(10, 10), (20, 20)],
    'anchored': [(10, 10)],
    'equal': [(10, 20)],
    'shifted': [(10, 30)],
}
REJECTED = ('odd', 'disjoint', 'foreign')


def accept(db, case):
    return ingest_pairs(db, case['batch_id'], case['roster'], case['exports'])


class PairAcceptTests(StoreCase):
    def test_sample_outcomes(self):
        for name, pair in EXPECTED.items():
            with self.subTest(case=name):
                receipt = accept(self.db, CASES[name])
                self.assertEqual(receipt, CASES[name]['batch_id'])
                self.assertEqual(read_pair(self.db, receipt, 'x', 'z'), pair)
        for name in REJECTED:
            with self.subTest(case=name):
                before = self.pair_counts()
                with self.assertRaises(ValueError):
                    accept(self.db, CASES[name])
                self.assertEqual(self.pair_counts(), before)

    def test_matches_brute_force_oracle(self):
        for name, case in CASES.items():
            if name == 'foreign':
                continue  # outside-roster input is a shape error, not a solvability one
            with self.subTest(case=name):
                oracle_solvable = has_solution(case['roster'], case['exports'])
                self.assertEqual(oracle_solvable, name not in ('odd', 'disjoint'))
                if not oracle_solvable:
                    continue
                receipt = accept(self.db, case)
                roster = case['roster']
                for left in roster:
                    for right in roster:
                        self.assertEqual(
                            read_pair(self.db, receipt, left, right),
                            expected_pairs(roster, case['exports'], left, right),
                            f'{name}: {left}/{right}',
                        )

    def test_random_batches_match_oracle(self):
        import random

        rng = random.Random(20261118)
        solvable_seen = 0
        for trial in range(120):
            size = rng.randint(1, 4)
            roster = [f's{index}' for index in range(size)]
            exports = []
            if size == 1:
                exports.append({'source_id': 'COVER', 'specimens': ['s0'],
                                'readings': [rng.randint(-3, 3)]})
            else:
                # A chain guarantees coverage while leaving components free.
                for index in range(size - 1):
                    exports.append({
                        'source_id': f'C{index}',
                        'specimens': [roster[index], roster[index + 1]],
                        'readings': [rng.randint(-3, 3), rng.randint(-3, 3)],
                    })
            for extra in range(rng.randint(0, 3)):
                members = ['s0'] if size == 1 else rng.sample(roster, rng.choice((1, 2)))
                exports.append({
                    'source_id': f'X{extra}',
                    'specimens': members,
                    'readings': [rng.randint(-3, 3) for _ in members],
                })
            batch_id = f'RANDOM-{trial}'
            if not has_solution(roster, exports):
                with self.assertRaises(NoJointInterpretation):
                    ingest_pairs(self.db, batch_id, roster, exports)
                continue
            solvable_seen += 1
            receipt = ingest_pairs(self.db, batch_id, roster, exports)
            for left in roster:
                for right in roster:
                    self.assertEqual(
                        read_pair(self.db, receipt, left, right),
                        expected_pairs(roster, exports, left, right),
                        f'trial {trial}: {left}/{right}',
                    )
        self.assertGreater(solvable_seen, 20)

    def test_overlapping_reports(self):
        roster = ['a', 'b', 'c']
        exports = [
            {'source_id': 'S1', 'specimens': ['a', 'b'], 'readings': [5, 7]},
            {'source_id': 'S2', 'specimens': ['b', 'c'], 'readings': [7, 9]},
            {'source_id': 'S3', 'specimens': ['a', 'c'], 'readings': [9, 5]},
            {'source_id': 'S4', 'specimens': ['a'], 'readings': [5]},
        ]
        case = {'batch_id': 'OVERLAP', 'roster': roster, 'exports': exports}
        receipt = ingest_pairs(self.db, **case)
        for left in roster:
            for right in roster:
                self.assertEqual(
                    read_pair(self.db, receipt, left, right),
                    expected_pairs(roster, exports, left, right),
                )
        self.assertEqual(read_pair(self.db, receipt, 'b', 'c'), [(7, 9)])

    def test_duplicate_values_count_twice(self):
        exports = [
            {'source_id': 'S1', 'specimens': ['x', 'y'], 'readings': [4, 4]},
            {'source_id': 'S2', 'specimens': ['y', 'z'], 'readings': [4, 4]},
        ]
        receipt = ingest_pairs(self.db, 'DOUBLE', ['x', 'y', 'z'], exports)
        self.assertEqual(read_pair(self.db, receipt, 'x', 'z'), [(4, 4)])
        self.assertEqual(read_pair(self.db, receipt, 'x', 'x'), [(4, 4)])
        self.assertEqual(read_pair(self.db, receipt, 'z', 'y'), [(4, 4)])

    def test_unordered_pair_semantics(self):
        # A two-specimen bag is a multiset: swapping the members must not matter
        # to the interpretation, but membership order is preserved on replay.
        export_a = {'source_id': 'S1', 'specimens': ['x', 'y'], 'readings': [3, 8]}
        export_b = {'source_id': 'S1', 'specimens': ['y', 'x'], 'readings': [3, 8]}
        first = ingest_pairs(self.db, 'ORDER-1', ['x', 'y'], [export_a])
        second = ingest_pairs(self.db, 'ORDER-2', ['x', 'y'], [export_b])
        self.assertEqual(read_pair(self.db, first, 'x', 'y'), [(3, 8), (8, 3)])
        self.assertEqual(read_pair(self.db, second, 'x', 'y'), [(3, 8), (8, 3)])

    def test_negative_and_zero_readings(self):
        exports = [
            {'source_id': 'S1', 'specimens': ['x', 'y'], 'readings': [-2, 0]},
            {'source_id': 'S2', 'specimens': ['y', 'z'], 'readings': [0, 3]},
        ]
        receipt = ingest_pairs(self.db, 'SIGNED', ['x', 'y', 'z'], exports)
        self.assertEqual(read_pair(self.db, receipt, 'x', 'z'), [(-2, 3)])

    def test_a_single_specimen_bag(self):
        exports = [
            {'source_id': 'S1', 'specimens': ['x'], 'readings': [11]},
            {'source_id': 'S2', 'specimens': ['x'], 'readings': [11]},
            {'source_id': 'S3', 'specimens': ['y'], 'readings': [12]},
        ]
        receipt = ingest_pairs(self.db, 'PINS', ['x', 'y'], exports)
        self.assertEqual(read_pair(self.db, receipt, 'x', 'y'), [(11, 12)])
        self.assertEqual(read_pair(self.db, receipt, 'x', 'x'), [(11, 11)])

    def test_reopens_after_accept(self):
        receipt = accept(self.db, CASES['independent'])
        self.reopen_store()
        self.assertEqual(read_pair(self.db, receipt, 'x', 'z'), EXPECTED['independent'])
        self.assertEqual(read_pair(self.db, receipt, 'z', 'x'), expected_pairs(
            CASES['independent']['roster'], CASES['independent']['exports'], 'z', 'x'))


class PairReplayTests(StoreCase):
    def test_replay_reuses_receipt(self):
        receipt = accept(self.db, CASES['path'])
        self.reopen_store()
        self.assertEqual(
            ingest_pairs(self.db, CASES['path']['batch_id'], CASES['path']['roster'],
                         CASES['path']['exports'], before_commit=fail_at_commit),
            receipt,
        )
        self.assertEqual(self.pair_counts(), (1, 2))

    def test_container_shapes_do_not_matter(self):
        case = CASES['path']
        receipt = accept(self.db, case)
        as_tuples = (
            case['batch_id'],
            tuple(case['roster']),
            tuple(
                {'readings': tuple(item['readings']), 'specimens': tuple(item['specimens']),
                 'source_id': item['source_id']}
                for item in case['exports']
            ),
        )
        self.assertEqual(ingest_pairs(self.db, *as_tuples), receipt)
        self.assertEqual(ingest_pairs(self.db, case['batch_id'], tuple(case['roster']),
                                      tuple(case['exports'])), receipt)
        # Export order is fixed evidence, so reversing it conflicts.
        reversed_exports = tuple(reversed([
            {'readings': tuple(item['readings']), 'specimens': tuple(item['specimens']),
             'source_id': item['source_id']}
            for item in case['exports']
        ]))
        with self.assertRaises(PairConflict):
            ingest_pairs(self.db, case['batch_id'], case['roster'], reversed_exports)

    def test_dict_field_order_and_list_or_tuple(self):
        case = CASES['path']
        reordered = [
            {'readings': list(item['readings']), 'specimens': list(item['specimens']),
             'source_id': item['source_id']}
            for item in case['exports']
        ]
        fields_altered = dict(case, exports=reordered)
        receipt = accept(self.db, case)
        self.assertEqual(ingest_pairs(self.db, **fields_altered), receipt)

        tupled = dict(
            case,
            roster=tuple(case['roster']),
            exports=[
                {'source_id': item['source_id'], 'specimens': tuple(item['specimens']),
                 'readings': tuple(item['readings'])}
                for item in case['exports']
            ],
        )
        self.assertEqual(ingest_pairs(self.db, **tupled), receipt)

    def test_member_order_is_evidence(self):
        # Members are compared as-is even though their readings form a bag, so
        # swapping them under the same batch id is a content conflict.
        accept(self.db, CASES['path'])
        swapped = dict(CASES['path'], exports=[
            {'source_id': 'E1', 'specimens': ['x', 'y'], 'readings': [10, 20]},
            CASES['path']['exports'][1],
        ])
        with self.assertRaises(PairConflict):
            accept(self.db, swapped)

    def test_content_conflict(self):
        receipt = accept(self.db, CASES['path'])
        changed = {
            'batch_id': 'P-01',
            'roster': ['x', 'y', 'z'],
            'exports': [
                {'source_id': 'E1', 'specimens': ['y', 'x'], 'readings': [10, 21]},
                CASES['path']['exports'][1],
            ],
        }
        with self.assertRaises(PairConflict):
            accept(self.db, changed)
        self.assertEqual(self.pair_counts(), (1, 2))
        self.assertEqual(read_pair(self.db, receipt, 'x', 'z'), EXPECTED['path'])

    def test_roster_compared_as_set(self):
        receipt = accept(self.db, CASES['path'])
        self.assertEqual(
            ingest_pairs(self.db, 'P-01', ['z', 'x', 'y'], CASES['path']['exports']), receipt
        )

    def test_input_mutation_after_accept(self):
        exports = [dict(item, specimens=list(item['specimens']), readings=list(item['readings']))
                   for item in CASES['path']['exports']]
        roster = list(CASES['path']['roster'])
        receipt = ingest_pairs(self.db, 'MUTABLE', roster, exports)
        roster.append('w')
        exports[0]['readings'][0] = 99
        exports[1]['specimens'].append('x')
        self.reopen_store()
        self.assertEqual(read_pair(self.db, receipt, 'x', 'z'), EXPECTED['path'])


class PairFailureTests(StoreCase):
    def test_invalid_inputs_are_rejected(self):
        base = {
            'batch_id': 'BAD',
            'roster': ['x', 'y'],
            'exports': [{'source_id': 'S1', 'specimens': ['x', 'y'], 'readings': [1, 2]}],
        }
        variants = {
            'empty roster': dict(base, roster=[]),
            'roster not sequence': dict(base, roster='xy'),
            'duplicate roster': dict(base, roster=['x', 'x']),
            'blank batch': dict(base, batch_id='  '),
            'non-string batch': dict(base, batch_id=5),
            'exports not sequence': dict(base, exports={'source_id': 'S1'}),
            'empty exports': dict(base, exports=[]),
            'missing coverage': dict(base, roster=['x', 'y', 'z']),
            'extra field': dict(base, exports=[
                {'source_id': 'S1', 'specimens': ['x', 'y'], 'readings': [1, 2], 'note': 'x'}]),
            'missing field': dict(base, exports=[{'source_id': 'S1', 'specimens': ['x', 'y']}]),
            'three members': dict(base, exports=[
                {'source_id': 'S1', 'specimens': ['x', 'y', 'x'], 'readings': [1, 2, 3]}]),
            'repeated member': dict(base, exports=[
                {'source_id': 'S1', 'specimens': ['x', 'x'], 'readings': [1, 2]},
                {'source_id': 'S2', 'specimens': ['y'], 'readings': [2]}]),
            'duplicate source': dict(base, exports=[
                {'source_id': 'S1', 'specimens': ['x'], 'readings': [1]},
                {'source_id': 'S1', 'specimens': ['y'], 'readings': [2]}]),
            'bool reading': dict(base, exports=[
                {'source_id': 'S1', 'specimens': ['x', 'y'], 'readings': [True, 2]}]),
            'float reading': dict(base, exports=[
                {'source_id': 'S1', 'specimens': ['x', 'y'], 'readings': [1.0, 2]}]),
            'short readings': dict(base, exports=[
                {'source_id': 'S1', 'specimens': ['x', 'y'], 'readings': [1]}]),
            'blank specimen': dict(base, roster=[' ', 'y']),
            'blank source': dict(base, exports=[
                {'source_id': '', 'specimens': ['x', 'y'], 'readings': [1, 2]}]),
        }
        for reason, case in variants.items():
            with self.subTest(reason=reason):
                with self.assertRaises(PairInputError):
                    ingest_pairs(self.db, **case)
                self.assertEqual(self.pair_counts(), (0, 0))
        self.reopen_store()
        self.assertEqual(self.pair_counts(), (0, 0))

    def test_unsatisfiable_batches(self):
        cases = {
            'odd cycle': CASES['odd'],
            'disjoint bags': CASES['disjoint'],
            'pinned conflict': {
                'batch_id': 'PIN', 'roster': ['x', 'y'],
                'exports': [
                    {'source_id': 'S1', 'specimens': ['x'], 'readings': [1]},
                    {'source_id': 'S2', 'specimens': ['x'], 'readings': [2]},
                    {'source_id': 'S3', 'specimens': ['y'], 'readings': [3]},
                ],
            },
        }
        for reason, case in cases.items():
            with self.subTest(reason=reason):
                with self.assertRaises(NoJointInterpretation):
                    ingest_pairs(self.db, **case)
                self.assertEqual(self.pair_counts(), (0, 0))
        self.reopen_store()
        self.assertEqual(self.pair_counts(), (0, 0))

    def test_failed_commit_reuses_batch_id(self):
        case = CASES['path']
        pending = []

        def reject_commit(db):
            pending.append(self.pair_counts())
            fail_at_commit(db)

        with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY constraint failed'):
            ingest_pairs(self.db, case['batch_id'], case['roster'], case['exports'],
                         before_commit=reject_commit)
        self.assertEqual(pending, [(1, 2)])
        self.reopen_store()
        self.assertEqual(self.pair_counts(), (0, 0))
        receipt = accept(self.db, case)
        self.assertEqual(receipt, case['batch_id'])
        self.assertEqual(read_pair(self.db, receipt, 'x', 'z'), EXPECTED['path'])

    def test_unsolvable_does_not_reserve_identifier(self):
        with self.assertRaises(NoJointInterpretation):
            accept(self.db, CASES['odd'])
        replacement = dict(CASES['path'], batch_id='P-03')
        receipt = accept(self.db, replacement)
        self.assertEqual(receipt, 'P-03')
        self.assertEqual(read_pair(self.db, receipt, 'x', 'z'), EXPECTED['path'])

    def test_named_results_survive_pair_work(self):
        from intake.accept import import_named
        from archive.readings import get_capture
        from tests.support import page, recording

        registration = self.register()
        raw = recording(page('P1', [['x', 200], ['y', 220]]))
        named = import_named(self.db, registration, raw)
        pair = accept(self.db, CASES['path'])
        self.reopen_store()
        self.assertEqual([row.value for row in get_capture(self.db, named).readings], [20, 22])
        self.assertEqual(read_pair(self.db, pair, 'x', 'z'), EXPECTED['path'])


class PairReadTests(StoreCase):
    def test_unknown_receipt(self):
        with self.assertRaises(KeyError):
            read_pair(self.db, 'unknown-batch', 'x', 'z')

    def test_unknown_specimen(self):
        receipt = accept(self.db, CASES['path'])
        for specimen in ('w', '', 'X'):
            with self.subTest(specimen=specimen):
                with self.assertRaises(KeyError):
                    read_pair(self.db, receipt, 'x', specimen)

    def test_named_receipt_is_not_an_anonymous_receipt(self):
        from intake.accept import import_named
        from tests.support import page, recording

        registration = self.register()
        named = import_named(self.db, registration, recording(page('P1', [['x', 200], ['y', 220]])))
        with self.assertRaises(KeyError):
            read_pair(self.db, named, 'x', 'y')

    def test_damaged_evidence_is_reported(self):
        damages = {
            'missing source': 'DELETE FROM pair_sources WHERE batch_id = ? AND ordinal = 1',
            'altered reading': "UPDATE pair_sources SET readings = '[11,20]' "
                               "WHERE batch_id = ? AND ordinal = 0",
            'altered roster': "UPDATE pair_batches SET roster = '[\"x\",\"y\"]' WHERE batch_id = ?",
            'altered seal': "UPDATE pair_batches SET seal = 'deadbeef' WHERE batch_id = ?",
            'short readings': "UPDATE pair_sources SET readings = '[10]' "
                              "WHERE batch_id = ? AND ordinal = 1",
            'dropped batch': (
                ('DELETE FROM pair_sources WHERE batch_id = ?',
                 'DELETE FROM pair_batches WHERE batch_id = ?')
            ),
        }
        for reason, statement in damages.items():
            with self.subTest(reason=reason):
                batch_id = f'DAMAGED-{len(reason)}-{reason[:4]}'.replace(' ', '_')
                case = dict(CASES['path'], batch_id=batch_id)
                receipt = accept(self.db, case)
                statements = statement if isinstance(statement, tuple) else (statement,)
                for sql in statements:
                    self.db.execute(sql, (receipt,))
                with self.assertRaises((EvidenceMismatch, KeyError)) as caught:
                    read_pair(self.db, receipt, 'x', 'z')
                if reason == 'dropped batch':
                    # With the row gone there is no evidence left to reuse or
                    # contradict, so a fresh accept may publish again.
                    self.assertIsInstance(caught.exception, UnknownPairBatch)
                else:
                    self.assertIsInstance(caught.exception, EvidenceMismatch)
                    with self.assertRaises(EvidenceMismatch):
                        accept(self.db, case)

    def test_replay_rejects_damaged_evidence(self):
        receipt = accept(self.db, CASES['path'])
        self.db.execute('DELETE FROM pair_sources WHERE batch_id = ? AND ordinal = 0', (receipt,))
        with self.assertRaises(EvidenceMismatch):
            accept(self.db, CASES['path'])
        with self.assertRaises(EvidenceMismatch):
            read_pair(self.db, receipt, 'x', 'z')
