from src.adapters.outbound.provider_verification.llm_evidence_collector_adapter import (
    LLMProviderEvidenceCollectorAdapter,
)
from src.domain.provider_verification import (
    EvidenceSourcePolicy,
    ProviderVerificationSubject,
)
from src.services.provider_verification_service import ProviderVerificationService


class _LLM:
    def chat(self, system_prompt, user_prompt, *, operation="", session_id="", rule_name=""):
        assert operation == "provider_evidence_collection"
        return """
        {
          "findings": [
            {
              "key": "provider adverse public source signal found",
              "value": true,
              "confidence": 0.82,
              "evidenceRefs": ["https://example.test/provider-risk"],
              "rationale": "Advisory adverse-source signal.",
              "requiresHumanReview": true
            }
          ],
          "errors": []
        }
        """


def test_provider_verification_service_defaults_to_review_when_integrations_missing():
    result = ProviderVerificationService().verify_provider(
        ProviderVerificationSubject(provider_name="Example Provider")
    )

    assert result.evidence.status == "requires_review"
    assert result.inferra_facts["provider evidence package requires human review"] is True
    assert result.evidence.provenance["sources"][0]["source"] == "ahpra"


def test_llm_evidence_collector_is_policy_gated():
    adapter = LLMProviderEvidenceCollectorAdapter(_LLM())
    subject = ProviderVerificationSubject(provider_name="Example Provider")

    disabled = adapter.collect_evidence(subject, EvidenceSourcePolicy())
    assert disabled.status == "unavailable"

    enabled = adapter.collect_evidence(
        subject,
        EvidenceSourcePolicy(
            allow_llm_advisory_evidence=True,
            allow_public_web_search=True,
        ),
    )
    facts = enabled.to_inferra_facts()

    assert enabled.status == "advisory"
    assert facts["provider adverse public source signal found"] is True
    assert facts["provider evidence package requires human review"] is True
