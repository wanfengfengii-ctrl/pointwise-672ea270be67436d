from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from runs.limits import validate_piece_limits, validate_roster_scale


@dataclass(frozen=True, slots=True)
class Roster:
    batch_id: str
    version: str
    specimens: tuple[str, ...]
    limits: tuple[int, ...]
    scale: Fraction


@dataclass(frozen=True, slots=True)
class RegisteredRoster:
    registration_id: str
    roster: Roster


def _require_label(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field} must be a nonempty string')
    value.encode('utf-8')


def build_roster(
    batch_id: str,
    version: str,
    specimens: Sequence[str],
    limits: Mapping[str, int],
    scale: Fraction | Sequence[int],
) -> Roster:
    _require_label(batch_id, 'batch_id')
    _require_label(version, 'version')
    if not isinstance(specimens, Sequence) or isinstance(specimens, (str, bytes)):
        raise ValueError('specimens must be an ordered sequence of labels')
    ordered = tuple(specimens)
    if not ordered:
        raise ValueError('roster must contain at least one specimen')
    for specimen in ordered:
        _require_label(specimen, 'specimen_id')
    if len(set(ordered)) != len(ordered):
        raise ValueError('duplicate specimen in roster')

    return Roster(
        batch_id=batch_id,
        version=version,
        specimens=ordered,
        limits=validate_piece_limits(ordered, limits),
        scale=validate_roster_scale(scale),
    )
