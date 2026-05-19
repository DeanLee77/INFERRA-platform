from src.domain.reasoning.inferra_compiler import InferraCompiler
from src.domain.reasoning.pattern_miner import MinedRuleCandidate
from src.services.rule_validation_service import RuleValidationService


def test_compile_single_candidate_to_inferra_rule_text():
    candidate = MinedRuleCandidate(
        candidate_id="mc_0001",
        antecedents=("income",),
        consequent="eligible",
        support=3,
        confidence=0.9,
    )

    rule_text = InferraCompiler().compile(candidate)

    assert rule_text.splitlines() == [
        "INPUT income AS BOOLEAN",
        "eligible IS true",
        "    income IS true",
    ]


def test_compile_sanitizes_names_and_removes_duplicate_antecedents():
    candidate = MinedRuleCandidate(
        candidate_id="mc_0001",
        antecedents=("1 income", "1-income"),
        consequent="final result",
        support=3,
        confidence=0.9,
    )

    rule_text = InferraCompiler().compile(candidate)

    assert "INPUT _1_income AS BOOLEAN" in rule_text
    assert rule_text.count("INPUT _1_income AS BOOLEAN") == 1
    assert "final_result IS true" in rule_text


def test_compile_returns_empty_when_no_antecedents_remain():
    candidate = MinedRuleCandidate(
        candidate_id="mc_0001",
        antecedents=("eligible",),
        consequent="eligible",
        support=1,
        confidence=1.0,
    )

    assert InferraCompiler().compile(candidate) == ""


def test_compile_batch_skips_empty_rules_and_output_validates():
    candidates = [
        MinedRuleCandidate("mc_0001", ("income",), "eligible", 2, 1.0),
        MinedRuleCandidate("mc_0002", (), "ignored", 2, 1.0),
    ]

    compiled = InferraCompiler().compile_batch(candidates)

    assert len(compiled) == 1
    assert RuleValidationService().validate(compiled[0], "learned").valid
