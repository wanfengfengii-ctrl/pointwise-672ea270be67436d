from fractions import Fraction

from runs.limits import validate_roster_scale


class NormalizationError(ValueError):
    pass


def parse_source_scale(components: tuple[int, int]) -> Fraction:
    try:
        return validate_roster_scale(components)
    except ValueError as error:
        raise NormalizationError(f'invalid source scale: {error}') from error


def normalize_reading(raw: int, source_scale: Fraction, standard_scale: Fraction) -> int:
    if type(raw) is not int:
        raise NormalizationError('reading must be an integer')
    if source_scale <= 0 or standard_scale <= 0:
        raise NormalizationError('reading scales must be positive')
    standard = raw * source_scale / standard_scale
    if standard.denominator != 1:
        raise NormalizationError('reading is not a whole standard unit')
    return standard.numerator
