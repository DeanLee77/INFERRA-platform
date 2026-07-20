"""Deterministic evaluation-history value types."""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class HistoryRecord:
    """Historical true/false counts for a single evaluated node."""

    name: str
    true_count: int = 0
    false_count: int = 0

    @property
    def total(self) -> int:
        return self.true_count + self.false_count

    @property
    def true_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.true_count / self.total

    @property
    def false_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.false_count / self.total

    def with_increment(self, is_true: bool) -> "HistoryRecord":
        if is_true:
            return HistoryRecord(
                name=self.name,
                true_count=self.true_count + 1,
                false_count=self.false_count,
            )
        return HistoryRecord(
            name=self.name,
            true_count=self.true_count,
            false_count=self.false_count + 1,
        )

    def __repr__(self) -> str:
        return json.dumps(
            {"name": self.name, "true": self.true_count, "false": self.false_count}
        )

