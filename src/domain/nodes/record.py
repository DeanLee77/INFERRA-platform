"""
History Record Module.
Tracks historical true/false counts for DFS topological sort optimization.

When ML_OPTIMIZED_DFS is enabled, the engine uses HistoryRecord data to
reorder child traversal so that nodes most likely to prune the search
space are visited first:
- OR rules: visit most-likely-TRUE child first (shortest path to TRUE parent)
- AND rules: visit most-likely-FALSE child first (shortest path to FALSE parent)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class HistoryRecord:
    """
    Immutable record of historical true/false evaluation counts for a single node.

    Used by TopologicalSort.dfs_topological_sort_with_record to optimize
    the DFS traversal order based on past evaluation outcomes.
    """

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

    def with_increment(self, is_true: bool) -> HistoryRecord:
        if is_true:
            return HistoryRecord(name=self.name, true_count=self.true_count + 1, false_count=self.false_count)
        return HistoryRecord(name=self.name, true_count=self.true_count, false_count=self.false_count + 1)

    def __repr__(self) -> str:
        return json.dumps({"name": self.name, "true": self.true_count, "false": self.false_count})
