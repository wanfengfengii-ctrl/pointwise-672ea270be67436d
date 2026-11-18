from fractions import Fraction

from runs.registry import get_roster, register
from runs.storage import RosterConflict, UnknownRegistration
from tests.support import StoreCase


class RegistrationTests(StoreCase):
    def test_fixed_registration(self):
        registration = self.register()
        self.assertEqual(registration, self.register(scale=(2, 2)))
        self.assertEqual(registration, self.register(scale=Fraction(1)))
        saved = get_roster(self.db, registration)
        self.assertEqual(saved.registration_id, registration)
        self.assertEqual(saved.roster.specimens, ('x', 'y'))
        self.assertEqual(saved.roster.limits, (20, 20))
        self.assertEqual(saved.roster.scale, Fraction(1))

    def test_conflicting_limits(self):
        registration = self.register()
        with self.assertRaises(RosterConflict):
            register(self.db, 'LOT-17', 'v1', ('x', 'y'), {'x': 21, 'y': 20}, (1, 1))
        self.reopen_store()
        self.assertEqual(get_roster(self.db, registration).roster.limits, (20, 20))
        self.assertEqual(self.register(), registration)

    def test_duplicate_specimen(self):
        with self.assertRaisesRegex(ValueError, 'duplicate specimen'):
            self.register(specimens=('x', 'x'))
        self.assertEqual(self.db.execute('SELECT count(*) FROM rosters').fetchone(), (0,))
        registration = self.register()
        self.assertEqual(get_roster(self.db, registration).roster.specimens, ('x', 'y'))

    def test_invalid_roster_scale(self):
        for scale in ((1, 0), (0, 3), (-1, 2), (True, 2)):
            with self.subTest(scale=scale), self.assertRaises(ValueError):
                self.register(scale=scale)
        self.assertEqual(self.db.execute('SELECT count(*) FROM rosters').fetchone(), (0,))

    def test_incomplete_or_non_integer_limits(self):
        for limits in ({'x': 20}, {'x': 20, 'y': 20, 'z': 20}, {'x': 20, 'y': False}):
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                register(self.db, 'LOT-17', 'v1', ('x', 'y'), limits, (1, 1))
        self.assertEqual(self.db.execute('SELECT count(*) FROM rosters').fetchone(), (0,))
        with self.assertRaises(UnknownRegistration):
            get_roster(self.db, 'unknown')

    def test_reinitialize(self):
        old = self.register()
        new = self.register(version='v2', specimens=('y', 'x'), limit=25)
        self.assertNotEqual(old, new)
        self.initialize()
        self.reopen_store()
        old_roster = get_roster(self.db, old).roster
        new_roster = get_roster(self.db, new).roster
        self.assertEqual((old_roster.version, old_roster.specimens, old_roster.limits),
                         ('v1', ('x', 'y'), (20, 20)))
        self.assertEqual((new_roster.version, new_roster.specimens, new_roster.limits),
                         ('v2', ('y', 'x'), (25, 25)))
        self.assertEqual(old, self.register())
        self.assertEqual(new, self.register(version='v2', specimens=('y', 'x'), limit=25))

    def test_reordered_roster(self):
        registration = self.register()
        with self.assertRaises(RosterConflict):
            self.register(specimens=('y', 'x'))
        self.assertEqual(get_roster(self.db, registration).roster.specimens, ('x', 'y'))
