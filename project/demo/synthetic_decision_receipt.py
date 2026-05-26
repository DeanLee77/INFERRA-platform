import json
from datetime import datetime, timezone
from pathlib import Path


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
RULE_FIXTURE_NAME = "synthetic_dmepos_power_mobility_rule"
RULE_VERSION = "synthetic-0.1"
EVALUATOR_VERSION = "synthetic-receipt-evaluator-0.1"

FACT_LABELS = {
    "face-to-face evaluation documented": "Face-to-face evaluation documented",
    "home mobility need documented": "Home mobility need documented",
    "lower-acuity mobility aids ruled out": "Lower-acuity mobility aids ruled out",
    "safe operation documented": "Safe operation documented",
    "supplier order complete": "Supplier order complete",
    "unresolved safety contraindication": "Unresolved safety contraindication",
}

MISSING_EVIDENCE_PROMPTS = {
    "face-to-face evaluation documented": "Attach synthetic face-to-face evaluation evidence.",
    "home mobility need documented": "Document the synthetic in-home mobility limitation.",
    "lower-acuity mobility aids ruled out": "Document why lower-acuity mobility aids are insufficient.",
    "safe operation documented": "Document synthetic safe-operation assessment.",
    "supplier order complete": "Attach complete synthetic supplier order packet.",
}

RATIONALE_BY_OUTCOME = {
    "CERTIFY": [
        "All required synthetic evidence flags are present.",
        "No unresolved safety contraindication was supplied.",
    ],
    "REVIEW": [
        "The request needs manual review because one or more synthetic evidence flags are missing.",
        "The receipt lists missing-evidence prompts for the demo operator.",
    ],
    "DENY": [
        "The request is denied in this synthetic fixture because a hard-stop condition is present.",
        "The demo fixture does not represent payer policy or a production coverage decision.",
    ],
}

SOURCE_LABELS = {
    "fixture": "synthetic_fixture:dmepos_power_mobility_prior_auth_v0",
    "policy": "synthetic_policy_label:not_real_payer_policy",
    "case": "synthetic_case:no_phi_no_customer_data",
}


def load_rule_text() -> str:
    return (FIXTURE_DIR / "synthetic_dmepos_power_mobility_rule.txt").read_text(encoding="utf-8")


def load_cases() -> dict:
    with (FIXTURE_DIR / "synthetic_decision_cases.json").open(encoding="utf-8") as case_file:
        return json.load(case_file)


def build_fixture_manifest() -> dict:
    cases = load_cases()
    return {
        "ruleName": RULE_FIXTURE_NAME,
        "ruleVersion": RULE_VERSION,
        "sourceLabels": SOURCE_LABELS,
        "ruleText": load_rule_text(),
        "cases": [
            {
                "caseId": case_id,
                "label": case_data["label"],
                "expectedOutcome": case_data["expectedOutcome"],
            }
            for case_id, case_data in cases.items()
        ],
    }


def build_decision_receipt(case_id: str = "certify-ready") -> dict:
    cases = load_cases()
    if case_id not in cases:
        allowed_cases = ", ".join(sorted(cases))
        raise ValueError("Unknown synthetic caseId '{}'. Expected one of: {}".format(case_id, allowed_cases))

    case = cases[case_id]
    facts = case["facts"]
    outcome = _evaluate_outcome(facts)
    missing_prompts = _build_missing_evidence_prompts(facts, outcome)

    return {
        "receiptType": "synthetic_decision_receipt",
        "demoPath": "AXIOM/platform private synthetic decision receipt",
        "caseId": case_id,
        "caseLabel": case["label"],
        "rule": {
            "name": RULE_FIXTURE_NAME,
            "fixture": "project/demo/fixtures/synthetic_dmepos_power_mobility_rule.txt",
            "version": RULE_VERSION,
        },
        "inputFacts": _build_input_facts(facts),
        "missingEvidencePrompts": missing_prompts,
        "outcome": {
            "code": outcome,
            "label": "Synthetic {}".format(outcome.lower()),
            "expectedForFixture": case["expectedOutcome"],
            "confidence": "rule-determined",
        },
        "rationale": RATIONALE_BY_OUTCOME[outcome],
        "sourceLabels": SOURCE_LABELS,
        "trace": {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "platformRoute": "/service/inference/syntheticDecisionReceipt",
            "ruleRoute": "/service/rule/syntheticDecisionReceiptFixture",
            "evaluatorVersion": EVALUATOR_VERSION,
            "sanitization": {
                "containsPhi": False,
                "containsCustomerData": False,
                "containsSecrets": False,
                "usesRealPayerPolicy": False,
                "usesProductionIntegration": False,
            },
        },
    }


def _evaluate_outcome(facts: dict) -> str:
    if facts["unresolved safety contraindication"] or not facts["home mobility need documented"]:
        return "DENY"

    required_evidence_keys = [
        "face-to-face evaluation documented",
        "home mobility need documented",
        "lower-acuity mobility aids ruled out",
        "safe operation documented",
        "supplier order complete",
    ]
    if all(facts[key] for key in required_evidence_keys):
        return "CERTIFY"

    return "REVIEW"


def _build_missing_evidence_prompts(facts: dict, outcome: str) -> list:
    if outcome == "DENY":
        return []

    return [
        {
            "factKey": fact_key,
            "prompt": prompt,
            "sourceLabel": SOURCE_LABELS["fixture"],
        }
        for fact_key, prompt in MISSING_EVIDENCE_PROMPTS.items()
        if not facts[fact_key]
    ]


def _build_input_facts(facts: dict) -> list:
    return [
        {
            "key": fact_key,
            "label": FACT_LABELS[fact_key],
            "value": value,
            "sourceLabel": SOURCE_LABELS["case"],
        }
        for fact_key, value in facts.items()
    ]

