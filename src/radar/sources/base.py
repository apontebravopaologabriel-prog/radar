from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from radar.domain.models import RawJob


class JobSource(Protocol):
    name: str

    def search(
        self, query: str, location: str | None = None, limit: int = 25
    ) -> Iterable[RawJob]: ...
