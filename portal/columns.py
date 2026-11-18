from dataclasses import dataclass


class BadRecording(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class NamedColumns:
    width: int
    specimen_index: int
    reading_index: int


def resolve_named_columns(labels: object) -> NamedColumns:
    if not isinstance(labels, list) or any(
        not isinstance(label, str) or not label.strip() for label in labels
    ):
        raise BadRecording('page columns must be an array of nonempty names')
    if labels.count('specimen_id') != 1 or labels.count('reading') != 1:
        raise BadRecording('page requires exactly one specimen_id column and one reading column')
    return NamedColumns(len(labels), labels.index('specimen_id'), labels.index('reading'))


def read_named_row(columns: NamedColumns, row: object) -> tuple[str, int]:
    if not isinstance(row, list) or len(row) != columns.width:
        raise BadRecording('data row width differs from the page column list')
    specimen = row[columns.specimen_index]
    reading = row[columns.reading_index]
    if not isinstance(specimen, str) or not specimen.strip():
        raise BadRecording('specimen_id must be a nonempty string')
    try:
        specimen.encode('utf-8')
    except UnicodeEncodeError as error:
        raise BadRecording('specimen_id must be valid UTF-8 text') from error
    if type(reading) is not int:
        raise BadRecording('reading must be an integer')
    return specimen, reading
