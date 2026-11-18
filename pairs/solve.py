"""Exact joint solving of anonymous one- and two-specimen exports.

Each source constrains its members: a single-specimen source pins one integer,
a two-specimen source demands that its members' value multiset equals its
reading multiset.  A batch is publishable exactly when one integer per roster
specimen exists that satisfies every source at once.

A two-specimen source with readings ``u, v`` forces its members to take those
two values in some order, i.e. it is the affine relation ``left + right = u+v``
plus the membership ``left in {u, v}``.  A specimen's value must therefore be
one of the readings of any source naming it, so in a connected component every
value is determined by a single root value, and the root has at most two
candidates.  Solving is thus linear per component and needs no enumeration.

Components of the source graph are independent, so a pair query solves only
the components it touches instead of the whole batch.
"""

from collections import deque
from dataclasses import dataclass

from pairs.model import NoJointInterpretation, PairBatch, PairSource


@dataclass(frozen=True, slots=True)
class JointSolution:
    """One integer assignment per roster specimen that satisfies every source."""

    values: tuple[tuple[str, int], ...]

    def as_dict(self) -> dict[str, int]:
        return dict(self.values)


def components(batch: PairBatch) -> tuple[tuple[str, ...], ...]:
    """Roster specimens grouped by shared two-specimen sources, roster ordered."""
    adjacency: dict[str, set[str]] = {specimen: set() for specimen in batch.roster}
    for source in batch.exports:
        if len(source.members) == 2:
            left, right = source.members
            adjacency[left].add(right)
            adjacency[right].add(left)
    seen: set[str] = set()
    grouped = []
    for specimen in batch.roster:
        if specimen in seen:
            continue
        seen.add(specimen)
        queue = deque([specimen])
        members = []
        while queue:
            current = queue.popleft()
            members.append(current)
            for neighbour in sorted(adjacency[current]):
                if neighbour not in seen:
                    seen.add(neighbour)
                    queue.append(neighbour)
        grouped.append(tuple(members))
    return tuple(grouped)


def _incident(batch: PairBatch) -> dict[str, tuple[PairSource, ...]]:
    incident: dict[str, list[PairSource]] = {specimen: [] for specimen in batch.roster}
    for source in batch.exports:
        for member in source.members:
            incident[member].append(source)
    return {specimen: tuple(sources) for specimen, sources in incident.items()}


def _root_domain(root: str, incident: dict[str, tuple[PairSource, ...]]) -> tuple[int, ...]:
    allowed: set[int] | None = None
    for source in incident[root]:
        offered = set(source.readings)
        allowed = offered if allowed is None else allowed & offered
        if not allowed:
            return ()
    return tuple(sorted(allowed or ()))


def _propagate(
    root: str,
    start: int,
    members: tuple[str, ...],
    incident: dict[str, tuple[PairSource, ...]],
) -> dict[str, int] | None:
    assigned = {root: start}
    queue = deque([root])
    while queue:
        current = queue.popleft()
        value = assigned[current]
        for source in incident[current]:
            if len(source.members) == 1:
                reading = source.readings[0]
                if reading != value:
                    return None
                continue
            left, right = source.members
            low, high = source.readings
            if value not in (low, high):
                return None
            partner = right if current == left else left
            required = low + high - value
            if partner in assigned:
                if assigned[partner] != required:
                    return None
            else:
                assigned[partner] = required
                queue.append(partner)
    if set(assigned) != set(members):
        return None
    return assigned


def component_solutions(batch: PairBatch, members: tuple[str, ...]) -> tuple[dict[str, int], ...]:
    """Every assignment of one component that satisfies all of its sources."""
    incident = _incident(batch)
    root = members[0]
    solutions = []
    seen: set[tuple[tuple[str, int], ...]] = set()
    for candidate in _root_domain(root, incident):
        assignment = _propagate(root, candidate, members, incident)
        if assignment is None:
            continue
        key = tuple(sorted(assignment.items()))
        if key not in seen:
            seen.add(key)
            solutions.append(assignment)
    return tuple(solutions)


def require_joint_interpretation(batch: PairBatch) -> None:
    """Confirm every component has at least one satisfying assignment."""
    for members in components(batch):
        if not component_solutions(batch, members):
            raise NoJointInterpretation(f'no joint interpretation for {batch.batch_id!r}')


def _component_index(batch: PairBatch, specimen: str) -> int:
    for index, members in enumerate(components(batch)):
        if specimen in members:
            return index
    raise KeyError(specimen)


def _solutions_for(batch: PairBatch, members: tuple[str, ...]) -> tuple[dict[str, int], ...]:
    solved = component_solutions(batch, members)
    if not solved:
        raise NoJointInterpretation(f'no joint interpretation for {batch.batch_id!r}')
    return solved


def pair_values(batch: PairBatch, left: str, right: str) -> list[tuple[int, int]]:
    """All ordered value pairs for two specimens over the joint interpretations.

    Only the components holding the requested specimens are solved; the other
    components may take any satisfying assignment and contribute no variation
    to this projection.
    """
    grouped = components(batch)
    left_index = _component_index(batch, left)
    right_index = _component_index(batch, right)

    if left_index == right_index:
        solved = _solutions_for(batch, grouped[left_index])
        return sorted({(values[left], values[right]) for values in solved})

    left_values = _solutions_for(batch, grouped[left_index])
    right_values = _solutions_for(batch, grouped[right_index])
    return sorted({
        (left_map[left], right_map[right])
        for left_map in left_values
        for right_map in right_values
    })


def joint_solutions(batch: PairBatch) -> tuple[JointSolution, ...]:
    """Every complete satisfying assignment, roster ordered.

    Intended for small batches and oracles; independent components multiply,
    so callers that only need one pair should use :func:`pair_values`.
    """
    combined: list[dict[str, int]] = [{}]
    for members in components(batch):
        solved = _solutions_for(batch, members)
        merged = []
        for prefix in combined:
            for values in solved:
                candidate = dict(prefix)
                candidate.update(values)
                merged.append(candidate)
        combined = merged
    return tuple(
        JointSolution(tuple((specimen, values[specimen]) for specimen in batch.roster))
        for values in combined
    )
