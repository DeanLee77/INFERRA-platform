from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

import structlog

from src.domain.reasoning.trace_extractor import TraceExtractor, TracePattern
from src.domain.state.fact_source import FactSource

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class MinedRuleCandidate:
    """A mined candidate that can be compiled into INFERRA rule text."""

    candidate_id: str
    antecedents: Tuple[str, ...]
    consequent: str
    support: int
    confidence: float
    lift: float = 0.0
    pattern_ids: Tuple[str, ...] = ()


class PatternMiner:
    """Mine simple co-occurrence rules from extracted trace patterns."""

    DEFAULT_MIN_SUPPORT = 2
    DEFAULT_MIN_CONFIDENCE = 0.5

    def __init__(
        self,
        min_support: int = DEFAULT_MIN_SUPPORT,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    ) -> None:
        self.min_support = max(1, int(min_support))
        self.min_confidence = min(max(float(min_confidence), 0.0), 1.0)

    def mine(self, patterns: List[TracePattern]) -> List[MinedRuleCandidate]:
        if not patterns:
            return []

        item_counts: Counter[str] = Counter()
        pair_counts: Counter[Tuple[str, str]] = Counter()
        total_frequency = 0

        for pattern in patterns:
            frequency = max(int(pattern.frequency), 0)
            if frequency == 0:
                continue
            total_frequency += frequency
            fact_names = tuple(sorted(set(pattern.fact_names)))
            for name in fact_names:
                item_counts[name] += frequency
            for idx, left in enumerate(fact_names):
                for right in fact_names[idx + 1:]:
                    pair_counts[(left, right)] += frequency

        if total_frequency == 0:
            return []

        frequent_items = {
            name for name, count in item_counts.items()
            if count >= self.min_support
        }
        decision_facts: Set[str] = set()
        for pattern in patterns:
            decision_facts.update(pattern.decision_path)

        candidates: List[MinedRuleCandidate] = []
        next_id = 1
        for consequent in sorted(frequent_items & decision_facts):
            antecedent_scores: List[Tuple[str, int, float]] = []
            for antecedent in sorted(frequent_items):
                if antecedent == consequent:
                    continue
                pair = tuple(sorted((antecedent, consequent)))
                pair_support = pair_counts.get(pair, 0)
                if pair_support < self.min_support:
                    continue
                antecedent_count = item_counts[antecedent]
                confidence = pair_support / antecedent_count if antecedent_count else 0.0
                if confidence >= self.min_confidence:
                    antecedent_scores.append((antecedent, pair_support, confidence))

            if not antecedent_scores:
                continue

            antecedents = tuple(score[0] for score in antecedent_scores)
            support = min(score[1] for score in antecedent_scores)
            confidence = min(score[2] for score in antecedent_scores)
            consequent_probability = item_counts[consequent] / total_frequency
            antecedent_probability = support / total_frequency
            expected = consequent_probability * antecedent_probability
            observed = support / total_frequency
            lift = observed / expected if expected > 0 else 0.0
            pattern_ids = tuple(
                pattern.pattern_id
                for pattern in patterns
                if consequent in pattern.decision_path
                and set(antecedents).issubset(set(pattern.fact_names))
            )

            candidates.append(
                MinedRuleCandidate(
                    candidate_id=f"mc_{next_id:04d}",
                    antecedents=antecedents,
                    consequent=consequent,
                    support=support,
                    confidence=round(min(confidence, 1.0), 4),
                    lift=round(lift, 4),
                    pattern_ids=pattern_ids,
                )
            )
            next_id += 1

        candidates.sort(
            key=lambda candidate: (
                -candidate.confidence,
                -candidate.support,
                candidate.consequent,
                candidate.candidate_id,
            )
        )
        log.info(
            "pattern_mining_complete",
            session_id="",
            node_id="",
            fact_source=FactSource.LEARNED.value,
            correlation_id="",
            rule_name="",
            candidate_count=len(candidates),
        )
        return candidates

    def mine_from_sessions(self, session_data_list: List[Dict]) -> List[MinedRuleCandidate]:
        extractor = TraceExtractor()
        patterns: List[TracePattern] = []
        for session_data in session_data_list:
            patterns.extend(extractor.extract_from_dict(session_data))
        return self.mine(patterns)
