from collections.abc import Mapping
from pathlib import Path


class PortalClosed(OSError):
    pass


class RecordedPortal:
    def __init__(self, recordings: Mapping[str, str | Path]) -> None:
        self._recordings = {batch_id: Path(path) for batch_id, path in recordings.items()}
        self._closed = False

    def fetch_recording(self, batch_id: str) -> bytes:
        if self._closed:
            raise PortalClosed('recorded portal is offline')
        return self._recordings[batch_id].read_bytes()

    def close(self) -> None:
        self._closed = True
