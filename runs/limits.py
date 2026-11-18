from collections.abc import Mapping, Sequence
from fractions import Fraction


def validate_piece_limits(
    specimens: tuple[str, ...], limits: Mapping[str, int]
) -> tuple[int, ...]:
    if not isinstance(limits, Mapping) or set(limits) != set(specimens):
        raise ValueError('limits must name exactly the roster specimens')

    ordered = tuple(limits[specimen] for specimen in specimens)
    if any(type(limit) is not int for limit in ordered):
        raise ValueError('every limit must be an integer')
    return ordered


def validate_roster_scale(scale: Fraction | Sequence[int]) -> Fraction:
    if isinstance(scale, Fraction):
        ratio = scale
    else:
        if not isinstance(scale, Sequence) or len(scale) != 2:
            raise ValueError('scale requires an integer numerator and denominator')
        numerator, denominator = scale
        if type(numerator) is not int or type(denominator) is not int:
            raise ValueError('scale components must be integers')
        if denominator == 0:
            raise ValueError('scale denominator must be nonzero')
        ratio = Fraction(numerator, denominator)

    if ratio <= 0:
        raise ValueError('scale must be positive')
    return ratio
