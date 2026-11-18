from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True, slots=True)
class NamedImportIdentity:
    registration_id: str
    original_digest: str


def identify_named_import(registration_id: str, raw: bytes) -> NamedImportIdentity:
    return NamedImportIdentity(registration_id, sha256(raw).hexdigest())
