from fastapi.testclient import TestClient

from src.main import app


def test_synthetic_fixture_route_returns_private_demo_manifest():
    client = TestClient(app)

    response = client.get("/service/rule/syntheticDecisionReceiptFixture")

    assert response.status_code == 200
    data = response.json()
    assert data["ruleName"] == "synthetic_dmepos_power_mobility_rule"
    assert data["sourceLabels"]["case"] == "synthetic_case:no_phi_no_customer_data"
    assert {case["caseId"] for case in data["cases"]} == {
        "certify-ready",
        "review-missing-order",
        "deny-contraindication",
    }


def test_synthetic_receipt_route_returns_review_case_shape():
    client = TestClient(app)

    response = client.get("/service/inference/syntheticDecisionReceipt?caseId=review-missing-order")

    assert response.status_code == 200
    data = response.json()
    assert data["receiptType"] == "synthetic_decision_receipt"
    assert data["outcome"]["code"] == "REVIEW"
    assert data["outcome"]["expectedForFixture"] == "REVIEW"
    assert data["missingEvidencePrompts"] == [
        {
            "factKey": "supplier order complete",
            "prompt": "Attach complete synthetic supplier order packet.",
            "sourceLabel": "synthetic_fixture:dmepos_power_mobility_prior_auth_v0",
        }
    ]
    assert data["trace"]["sanitization"] == {
        "containsPhi": False,
        "containsCustomerData": False,
        "containsSecrets": False,
        "usesRealPayerPolicy": False,
        "usesProductionIntegration": False,
    }


def test_synthetic_receipt_route_rejects_unknown_case():
    client = TestClient(app)

    response = client.get("/service/inference/syntheticDecisionReceipt?caseId=unknown")

    assert response.status_code == 400
    assert "Unknown synthetic caseId" in response.json()["error"]


def test_reasoning_run_review_fixture_route_returns_ui_contract():
    client = TestClient(app)

    response = client.get("/service/inference/reasoningRunReviewFixture")

    assert response.status_code == 200
    data = response.json()
    assert data["fixture_type"] == "reasoning_run_review_contract"
    assert set(data["required_result_states"]) == {
        "running",
        "success",
        "needs_review",
        "abstain",
        "contradiction",
        "error",
    }
    assert [stage for stage in data["required_stages"]] == [
        "parse",
        "retrieve",
        "reason",
        "verify",
        "summarize",
        "receipt",
    ]
    assert {source["path"] for source in data["source_rule_examples"]} == {
        "docs/reference/examples/mrca_ultimate_master_convergence_met.txt",
        "docs/reference/examples/drca_ultimate_master_convergence_met.txt",
        "docs/reference/examples/vea_part_ii_sections_5_to_6.txt",
    }


def test_reasoning_run_review_run_route_filters_by_result_state():
    client = TestClient(app)

    response = client.get("/service/inference/reasoningRunReviewRun?resultState=contradiction")

    assert response.status_code == 200
    data = response.json()
    assert data["result_state"] == "contradiction"
    assert data["allowed_actions"]["primary"] == "resolve_contradiction"
    assert "accept_internal_use" in data["allowed_actions"]["disallowed"]
    assert data["contradictions"][0]["unqualified_accept_disabled"] is True


def test_reasoning_run_review_run_route_rejects_unknown_state():
    client = TestClient(app)

    response = client.get("/service/inference/reasoningRunReviewRun?resultState=unsupported")

    assert response.status_code == 400
    assert "Unknown result_state" in response.json()["error"]
