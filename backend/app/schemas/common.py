"""Reusable validated field types and helpers."""

import itertools
from collections.abc import Sequence
from datetime import time
from typing import Annotated, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, Field

from app.core.uk import normalise_postcode, normalise_postcode_prefix, normalise_uk_phone


def _timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("Unknown timezone") from exc
    return value


def _website(value: str) -> str:
    value = value.strip()
    if not value.startswith(("https://", "http://")):
        value = "https://" + value
    return value


# Accepts "07700 900123" or "+44 7700 900123"; stored as E.164 "+447700900123".
UkPhone = Annotated[str, Field(max_length=30), AfterValidator(normalise_uk_phone)]
# Accepts "sw1a1aa"; stored as "SW1A 1AA".
UkPostcode = Annotated[str, Field(max_length=10), AfterValidator(normalise_postcode)]
# Coverage prefix: area ("M") or district ("M1", "SW1A").
PostcodePrefix = Annotated[str, Field(max_length=6), AfterValidator(normalise_postcode_prefix)]
Timezone = Annotated[str, Field(max_length=64), AfterValidator(_timezone)]
Website = Annotated[str, Field(max_length=200), AfterValidator(_website)]
Weekday = Annotated[int, Field(ge=0, le=6, description="0 = Monday … 6 = Sunday")]


class _Window(Protocol):
    @property
    def weekday(self) -> int: ...
    @property
    def start(self) -> time: ...
    @property
    def end(self) -> time: ...


def check_no_overlaps(windows: Sequence[_Window]) -> None:
    """Raise if two windows on the same weekday overlap (touching is fine: 12:00-12:00)."""
    by_day: dict[int, list[tuple[time, time]]] = {}
    for w in windows:
        by_day.setdefault(w.weekday, []).append((w.start, w.end))
    for day, spans in by_day.items():
        spans.sort()
        for (_, prev_end), (next_start, _) in itertools.pairwise(spans):
            if next_start < prev_end:
                raise ValueError(f"Overlapping times on weekday {day}")
