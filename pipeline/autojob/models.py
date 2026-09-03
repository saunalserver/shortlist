"""Normalized job record produced by every source."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RawJob:
    url: str
    title: str
    company: str = ""
    source: str = ""
    location: str = ""
    description: str = ""
    snippet: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    employment_type: str | None = None
    posted_at: str | None = None  # ISO date if known
    remote: bool | None = None
    extra: dict[str, Any] = field(default_factory=dict)  # source-specific hints (company_slug, ...)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("extra", None)
        return d
