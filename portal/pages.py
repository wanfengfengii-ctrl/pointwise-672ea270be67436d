from dataclasses import dataclass

from portal.columns import BadRecording, read_named_row, resolve_named_columns
from portal.evidence import SourceLocation


@dataclass(frozen=True, slots=True)
class NamedPageRow:
    specimen_id: str
    raw_reading: int
    location: SourceLocation


def decode_named_pages(pages: object) -> tuple[NamedPageRow, ...]:
    if not isinstance(pages, list):
        raise BadRecording('pages must be an array')

    seen_pages = set()
    decoded = []
    for page in pages:
        if not isinstance(page, dict):
            raise BadRecording('page must be an object')
        page_id = page.get('page_id')
        try:
            SourceLocation(page_id, 1)
        except ValueError as error:
            raise BadRecording('invalid page id') from error
        if page_id in seen_pages:
            raise BadRecording(f'duplicate page id: {page_id!r}')
        seen_pages.add(page_id)

        try:
            columns = resolve_named_columns(page.get('columns'))
        except BadRecording as error:
            raise BadRecording(f'page {page_id!r}: {error}') from error
        rows = page.get('rows')
        if not isinstance(rows, list):
            raise BadRecording(f'page {page_id!r} rows must be an array')
        for row_number, row in enumerate(rows, start=1):
            try:
                specimen, reading = read_named_row(columns, row)
            except BadRecording as error:
                raise BadRecording(f'page {page_id!r}, data row {row_number}: {error}') from error
            decoded.append(NamedPageRow(specimen, reading, SourceLocation(page_id, row_number)))
    return tuple(decoded)
