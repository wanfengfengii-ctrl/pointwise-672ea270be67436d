from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class SpecimenVerdict:
    specimen_id: str
    value: int
    limit: int
    passed: bool


@dataclass(frozen=True, slots=True)
class ReviewReport:
    report_id: str
    receipt: str
    registration_id: str
    batch_id: str
    version: str
    verdicts: tuple[SpecimenVerdict, ...]
    over_limit: tuple[str, ...]


def build_report(
    receipt: str,
    registration_id: str,
    batch_id: str,
    version: str,
    verdicts: tuple[SpecimenVerdict, ...],
) -> ReviewReport:
    return ReviewReport(
        report_id=f'qc-{uuid4().hex}',
        receipt=receipt,
        registration_id=registration_id,
        batch_id=batch_id,
        version=version,
        verdicts=verdicts,
        over_limit=tuple(verdict.specimen_id for verdict in verdicts if not verdict.passed),
    )
