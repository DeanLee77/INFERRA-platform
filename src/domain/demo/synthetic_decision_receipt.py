from datetime import datetime, timezone


RULE_FIXTURE_NAME = "synthetic_dmepos_power_mobility_rule"
RULE_VERSION = "synthetic-0.1"
EVALUATOR_VERSION = "synthetic-receipt-evaluator-0.1"

RULE_TEXT = """INPUT face-to-face evaluation documented AS BOOLEAN
INPUT home mobility need documented AS BOOLEAN
INPUT lower-acuity mobility aids ruled out AS BOOLEAN
INPUT safe operation documented AS BOOLEAN
INPUT supplier order complete AS BOOLEAN
INPUT unresolved safety contraindication AS BOOLEAN

synthetic power mobility request is CERTIFY
\tAND face-to-face evaluation documented
\tAND home mobility need documented
\tAND lower-acuity mobility aids ruled out
\tAND safe operation documented
\tAND supplier order complete
\tAND NOT unresolved safety contraindication

synthetic power mobility request is REVIEW
\tOR NOT face-to-face evaluation documented
\tOR NOT lower-acuity mobility aids ruled out
\tOR NOT safe operation documented
\tOR NOT supplier order complete

synthetic power mobility request is DENY
\tOR unresolved safety contraindication
\tOR NOT home mobility need documented
"""

SYNTHETIC_CASES = {
    "certify-ready": {
        "label": "Certify-ready synthetic request",
        "expectedOutcome": "CERTIFY",
        "facts": {
            "face-to-face evaluation documented": True,
            "home mobility need documented": True,
            "lower-acuity mobility aids ruled out": True,
            "safe operation documented": True,
            "supplier order complete": True,
            "unresolved safety contraindication": False,
        },
    },
    "review-missing-order": {
        "label": "Review synthetic request with missing order evidence",
        "expectedOutcome": "REVIEW",
        "facts": {
            "face-to-face evaluation documented": True,
            "home mobility need documented": True,
            "lower-acuity mobility aids ruled out": True,
            "safe operation documented": True,
            "supplier order complete": False,
            "unresolved safety contraindication": False,
        },
    },
    "deny-contraindication": {
        "label": "Deny synthetic request with unresolved safety contraindication",
        "expectedOutcome": "DENY",
        "facts": {
            "face-to-face evaluation documented": True,
            "home mobility need documented": True,
            "lower-acuity mobility aids ruled out": True,
            "safe operation documented": True,
            "supplier order complete": True,
            "unresolved safety contraindication": True,
        },
    },
}

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


def build_fixture_manifest() -> dict:
    return {
        "ruleName": RULE_FIXTURE_NAME,
        "ruleVersion": RULE_VERSION,
        "sourceLabels": SOURCE_LABELS,
        "ruleText": RULE_TEXT,
        "cases": [
            {
                "caseId": case_id,
                "label": case_data["label"],
                "expectedOutcome": case_data["expectedOutcome"],
            }
            for case_id, case_data in SYNTHETIC_CASES.items()
        ],
    }


def build_decision_receipt(case_id: str = "certify-ready") -> dict:
    if case_id not in SYNTHETIC_CASES:
        allowed_cases = ", ".join(sorted(SYNTHETIC_CASES))
        raise ValueError(f"Unknown synthetic caseId '{case_id}'. Expected one of: {allowed_cases}")

    case = SYNTHETIC_CASES[case_id]
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
            "fixture": "src/domain/demo/synthetic_decision_receipt.py",
            "version": RULE_VERSION,
        },
        "inputFacts": _build_input_facts(facts),
        "missingEvidencePrompts": missing_prompts,
        "outcome": {
            "code": outcome,
            "label": f"Synthetic {outcome.lower()}",
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
