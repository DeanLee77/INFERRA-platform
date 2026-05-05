from src.services.rule_sandbox import RuleSandbox


def test_rule_sandbox_filters_invalid_candidates():
    sandbox = RuleSandbox()
    valid, errors = sandbox.filter_valid_candidates(
        "job-1",
        "rule",
        [
            "INPUT trace_pattern AS BOOLEAN\nlearned_fact IS TRUE IF trace_pattern",
            "learned_fact IS TRUE IF missing_fact",
        ],
    )

    assert valid == ["INPUT trace_pattern AS BOOLEAN\nlearned_fact IS TRUE IF trace_pattern"]
    assert errors
    assert "UNDECLARED_REFERENCE" in errors[0]


def test_rule_sandbox_promotes_valid_member():
    candidate = "INPUT trace_pattern AS BOOLEAN\nlearned_fact IS TRUE IF trace_pattern"
    result = RuleSandbox().promote_candidate(
        "job-1",
        candidate,
        [candidate],
        "rule",
    )

    assert result.status == "promoted"
    assert result.valid is True
    assert result.to_dict()["candidate_rules"] == [candidate]


def test_rule_sandbox_rejects_non_member():
    result = RuleSandbox().promote_candidate(
        "job-1",
        "INPUT other AS BOOLEAN",
        ["INPUT trace_pattern AS BOOLEAN"],
        "rule",
    )

    assert result.status == "rejected"
    assert result.errors == ["Candidate rule does not belong to induction job"]
