from archive.integrity import EvidenceMismatch
from archive.readings import NamedCapture
from review.report import SpecimenVerdict
from runs.roster import RegisteredRoster


def evaluate_readings(
    capture: NamedCapture, registered: RegisteredRoster
) -> tuple[SpecimenVerdict, ...]:
    roster = registered.roster
    if capture.registration_id != registered.registration_id or capture.version != roster.version:
        raise EvidenceMismatch(f'roster binding differs for {capture.receipt}')
    if tuple(row.specimen_id for row in capture.readings) != roster.specimens:
        raise EvidenceMismatch(f'roster coverage differs for {capture.receipt}')
    return tuple(
        SpecimenVerdict(row.specimen_id, row.value, limit, row.value <= limit)
        for row, limit in zip(capture.readings, roster.limits, strict=True)
    )
