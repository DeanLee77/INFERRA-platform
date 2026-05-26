from src.domain.reasoning.pattern_miner import MinedRuleCandidate, PatternMiner
from src.domain.reasoning.trace_extractor import TracePattern


def test_mined_rule_candidate_is_immutable():
    candidate = MinedRuleCandidate(
        candidate_id="mc_0001",
        antecedents=("income",),
        consequent="eligible",
        support=2,
        confidence=1.0,
    )

    try:
        candidate.support = 3
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("MinedRuleCandidate should be frozen")


def test_mine_returns_empty_for_no_patterns():
    assert PatternMiner().mine([]) == []


def test_mine_discovers_decision_fact_from_repeated_patterns():
    patterns = [
        TracePattern("tp_1", ("eligible", "income", "age"), ("eligible",), 2, "rule"),
        TracePattern("tp_2", ("eligible", "income"), ("eligible",), 1, "rule"),
    ]

    candidates = PatternMiner(min_support=2, min_confidence=0.5).mine(patterns)

    assert candidates
    assert candidates[0].consequent == "eligible"
    assert "income" in candidates[0].antecedents
    assert candidates[0].support >= 2
    assert candidates[0].confidence >= 0.5


def test_mine_ignores_patterns_without_decision_facts():
    patterns = [TracePattern("tp_1", ("income", "age"), (), 5, "rule")]

    assert PatternMiner(min_support=1).mine(patterns) == []


def test_mine_from_sessions_uses_trace_extractor():
    sessions = [
        {"working_memory": {"eligible": True, "income": True}},
        {"working_memory": {"eligible": True, "income": True}},
    ]

    candidates = PatternMiner(min_support=1).mine_from_sessions(sessions)

    assert candidates
