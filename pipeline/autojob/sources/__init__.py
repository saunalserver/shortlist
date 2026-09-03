"""Source registry. Each module exposes ``NAME`` and ``fetch(settings) -> list[RawJob]``."""
from __future__ import annotations

import importlib
from types import ModuleType

from autojob.settings import Settings

# Order matters only for logging; every source is independent.
SOURCE_NAMES = [
    "adzuna",
    "jooble",
    "boards",
    "jobbank",
    "serper",
    "remotive",
    "remoteok",
    "jobicy",
    "themuse",
    "weworkremotely",
    "himalayas",
    "workday",
    "eluta",
    "ats_companies",
    "yc",
]


def load(name: str) -> ModuleType:
    if name not in SOURCE_NAMES:
        raise KeyError(f"unknown source '{name}' (known: {', '.join(SOURCE_NAMES)})")
    return importlib.import_module(f"autojob.sources.{name}")


def enabled(settings: Settings, only: list[str] | None = None) -> list[str]:
    names = only or [n for n in SOURCE_NAMES if settings.source_enabled(n)]
    for n in names:
        if n not in SOURCE_NAMES:
            raise KeyError(f"unknown source '{n}'")
    return names
