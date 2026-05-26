from fastapi.testclient import TestClient

from src.main import app


def test_synthetic_decision_receipt_fixture_route_returns_cases():
    with TestClient(app) as client:
        response = client.get("/service/rule/syntheticDecisionReceiptFixture")

    assert response.status_code == 200
    data = response.json()
    assert data["ruleName"] == "synthetic_dmepos_power_mobility_rule"
    assert {case["expectedOutcome"] for case in data["cases"]} == {"CERTIFY", "REVIEW", "DENY"}


def test_synthetic_decision_receipt_route_returns_expected_outcome():
    with TestClient(app) as client:
        response = client.get("/service/inference/syntheticDecisionReceipt?caseId=review-missing-order")

    assert response.status_code == 200
    data = response.json()
    assert data["outcome"]["code"] == "REVIEW"
    assert data["trace"]["sanitization"] == {
        "containsPhi": False,
        "containsCustomerData": False,
        "containsSecrets": False,
        "usesRealPayerPolicy": False,
        "usesProductionIntegration": False,
    }


def test_synthetic_decision_receipt_route_rejects_unknown_case():
    with TestClient(app) as client:
        response = client.get("/service/inference/syntheticDecisionReceipt?caseId=missing")

    assert response.status_code == 400
    assert "Unknown synthetic caseId" in response.json()["detail"]
