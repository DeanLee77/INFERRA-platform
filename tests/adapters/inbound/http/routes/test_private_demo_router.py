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
