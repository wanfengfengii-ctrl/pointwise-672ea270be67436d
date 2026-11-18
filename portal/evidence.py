from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceLocation:
    page_id: str
    row_number: int

    def __post_init__(self) -> None:
        if not isinstance(self.page_id, str) or not self.page_id.strip():
            raise ValueError('source page id must be a nonempty string')
        self.page_id.encode('utf-8')
        if type(self.row_number) is not int or self.row_number < 1:
            raise ValueError('source row number must be a positive integer')

    def as_key(self) -> tuple[str, int]:
        return self.page_id, self.row_number
