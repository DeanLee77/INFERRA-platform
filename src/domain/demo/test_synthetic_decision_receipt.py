from src.domain.demo import build_decision_receipt, build_fixture_manifest, load_cases


def test_synthetic_cases_produce_expected_outcomes():
    for case_id, case_data in load_cases().items():
        receipt = build_decision_receipt(case_id)

        assert receipt["outcome"]["code"] == case_data["expectedOutcome"]
        assert receipt["outcome"]["expectedForFixture"] == case_data["expectedOutcome"]


def test_receipt_contains_required_private_demo_evidence():
    receipt = build_decision_receipt("review-missing-order")

    assert receipt["receiptType"] == "synthetic_decision_receipt"
    assert receipt["inputFacts"]
    assert receipt["missingEvidencePrompts"]
    assert receipt["rationale"]
    assert receipt["sourceLabels"]["policy"] == "synthetic_policy_label:not_real_payer_policy"
    assert receipt["trace"]["sanitization"] == {
        "containsPhi": False,
        "containsCustomerData": False,
        "containsSecrets": False,
        "usesRealPayerPolicy": False,
        "usesProductionIntegration": False,
    }


def test_fixture_manifest_exposes_rule_and_cases():
    manifest = build_fixture_manifest()

    assert manifest["ruleName"] == "synthetic_dmepos_power_mobility_rule"
    assert "synthetic power mobility request is CERTIFY" in manifest["ruleText"]
    assert {case["expectedOutcome"] for case in manifest["cases"]} == {"CERTIFY", "REVIEW", "DENY"}
