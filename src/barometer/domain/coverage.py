"""Coverage of usable observations within one independently scored dimension."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Coverage:
    available: int
    expected: int

    def __post_init__(self) -> None:
        if self.expected < 0 or not 0 <= self.available <= self.expected:
            raise ValueError("coverage must satisfy 0 <= available <= expected")

    @property
    def percent(self) -> int | None:
        return round(100 * self.available / self.expected) if self.expected else None

    @property
    def degraded(self) -> bool:
        return self.expected > 0 and self.available / self.expected < 0.70

    def label(self, name: str = "涵蓋率") -> str:
        if self.expected == 0:
            return f"{name}：尚未接入"
        return f"{name} {self.available}/{self.expected} 項（{self.percent}%）"
