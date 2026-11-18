"""Independent brute-force oracle for the anonymous pair contract.

Deliberately simple and separate from ``pairs.solve``: it enumerates integer
assignments from each specimen's recorded-reading domain and keeps those that
satisfy every source, so it can cross-check the production solver.

Accepts the same shapes the public entry points accept: ``roster`` is a
sequence of labels and each export is an object with ``members`` and
``readings`` attributes (the frozen :class:`pairs.model.PairSource`) or a
mapping with ``specimens``/``readings`` keys (the sample JSON form).
"""

from itertools import product


def _members(export):
    if hasattr(export, 'members'):
        return tuple(export.members)
    return tuple(export['specimens'])


def _readings(export):
    if hasattr(export, 'readings'):
        return tuple(export.readings)
    return tuple(export['readings'])


def _feasible(exports, values):
    for export in exports:
        picked = tuple(values[member] for member in _members(export))
        if sorted(picked) != sorted(_readings(export)):
            return False
    return True


def enumerate_solutions(roster, exports):
    """Yield every satisfying ``dict`` for ``roster``/``exports``."""
    roster = list(roster)
    exports = list(exports)
    domains = {specimen: set() for specimen in roster}
    for export in exports:
        for member in _members(export):
            domains[member].update(_readings(export))
    for assignment in product(*(sorted(domains[specimen]) for specimen in roster)):
        values = dict(zip(roster, assignment, strict=True))
        if _feasible(exports, values):
            yield values


def expected_pairs(roster, exports, left, right):
    """All ordered pairs that occur in some satisfying assignment."""
    pairs = {
        (values[left], values[right]) for values in enumerate_solutions(roster, exports)
    }
    return sorted(pairs)


def has_solution(roster, exports):
    return next(enumerate_solutions(roster, exports), None) is not None
