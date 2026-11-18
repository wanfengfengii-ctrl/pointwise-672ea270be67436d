"""Validated, immutable shape of one anonymous pair recording."""

from dataclasses import dataclass

SOURCE_FIELDS = frozenset({'source_id', 'specimens', 'readings'})


class PairInputError(ValueError):
    """The recording is not a well-formed anonymous pair export."""


class PairConflict(ValueError):
    """The batch id is already fixed to different evidence."""


class NoJointInterpretation(ValueError):
    """No single integer assignment satisfies every source of the batch."""


@dataclass(frozen=True, slots=True)
class PairSource:
    source_id: str
    members: tuple[str, ...]
    readings: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class PairBatch:
    batch_id: str
    roster: tuple[str, ...]
    exports: tuple[PairSource, ...]


def _require_label(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PairInputError(f'{field} must be a nonempty string')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError as error:
        raise PairInputError(f'{field} must be valid UTF-8 text') from error
    return value


def _as_sequence(value: object, field: str) -> tuple:
    if not isinstance(value, (list, tuple)):
        raise PairInputError(f'{field} must be a list or tuple')
    return tuple(value)


def parse_pair_batch(batch_id: object, roster: object, exports: object) -> PairBatch:
    """Validate a recorded batch and freeze it into immutable value objects.

    The returned batch is independent of the caller's containers, so mutating
    them afterwards cannot change what was accepted.
    """
    _require_label(batch_id, 'batch_id')

    roster_values = _as_sequence(roster, 'roster')
    if not roster_values:
        raise PairInputError('roster must not be empty')
    ordered = []
    for specimen in roster_values:
        _require_label(specimen, 'specimen_id')
        if specimen in ordered:
            raise PairInputError(f'duplicate specimen in roster: {specimen!r}')
        ordered.append(specimen)
    canonical_roster = tuple(sorted(ordered))
    allowed = set(canonical_roster)

    export_values = _as_sequence(exports, 'exports')
    sources = []
    source_ids: set[str] = set()
    covered: set[str] = set()
    for index, export in enumerate(export_values):
        if not isinstance(export, dict) or set(export) != SOURCE_FIELDS:
            raise PairInputError(
                f'export {index} must have exactly source_id, specimens and readings'
            )
        source_id = _require_label(export['source_id'], f'export {index} source_id')
        if source_id in source_ids:
            raise PairInputError(f'duplicate source_id: {source_id!r}')
        source_ids.add(source_id)

        member_values = _as_sequence(export['specimens'], f'export {source_id!r} specimens')
        if len(member_values) not in (1, 2):
            raise PairInputError(f'export {source_id!r} must name one or two specimens')
        members = []
        for member in member_values:
            _require_label(member, 'specimen_id')
            if member not in allowed:
                raise PairInputError(f'specimen outside roster: {member!r}')
            if member in members:
                raise PairInputError(f'duplicate specimen in export {source_id!r}')
            members.append(member)

        reading_values = _as_sequence(export['readings'], f'export {source_id!r} readings')
        if len(reading_values) != len(members):
            raise PairInputError(f'export {source_id!r} needs one reading per specimen')
        readings = []
        for reading in reading_values:
            if type(reading) is not int:
                raise PairInputError(f'export {source_id!r} readings must be integers')
            readings.append(reading)

        covered.update(members)
        sources.append(PairSource(source_id, tuple(members), tuple(readings)))

    missing = [specimen for specimen in canonical_roster if specimen not in covered]
    if missing:
        raise PairInputError(f'missing readings for {missing!r}')

    return PairBatch(batch_id, canonical_roster, tuple(sources))
