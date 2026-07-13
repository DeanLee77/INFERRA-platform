from __future__ import annotations

import json
from typing import Any

import structlog

from src.domain.provider_verification import (
    EvidenceFinding,
    EvidenceSourcePolicy,
    ProviderEvidencePackage,
    ProviderVerificationSubject,
)
from src.ports.provider_verification_port import ProviderLLMEvidencePort

log = structlog.get_logger(__name__)

MAX_LLM_EVIDENCE_RESPONSE_CHARS = 12000


class LLMProviderEvidenceCollectorAdapter(ProviderLLMEvidencePort):
    """
    Configurable LLM evidence collector.

    This adapter is advisory only. It can summarize supplied evidence, propose
    public-search checks, or normalize adverse-source signals. Official sources
    still need authoritative adapters before INFERRA treats legitimacy as proven.
    """

    SOURCE = "llm_provider_evidence"

    def __init__(self, llm_orchestrator: Any = None) -> None:
        self._llm = llm_orchestrator

    def collect_evidence(
        self,
        subject: ProviderVerificationSubject,
        policy: EvidenceSourcePolicy,
    ) -> ProviderEvidencePackage:
        if not policy.allow_llm_advisory_evidence:
            return ProviderEvidencePackage.unavailable(
                self.SOURCE,
                reason="LLM provider evidence collection is disabled by policy.",
                expected_keys=("provider adverse public source signal found",),
            )
        if self._llm is None or not hasattr(self._llm, "chat"):
            return ProviderEvidencePackage.unavailable(
                self.SOURCE,
                reason="LLM orchestrator with chat() is not configured.",
                expected_keys=("provider adverse public source signal found",),
            )

        system_prompt = (
            "You are an evidence-normalisation assistant for Australian medical "
            "provider fraud screening. Return JSON only. Do not decide legal "
            "eligibility. Official-source facts must remain unverified unless "
            "authoritative evidence is provided by the caller."
        )
        user_prompt = json.dumps(
            {
                "task": "Collect advisory provider evidence for INFERRA fact inputs.",
                "provider": subject.redacted_context(),
                "policy": {
                    "allowPublicWebSearch": policy.allow_public_web_search,
                    "allowUserSuppliedUrls": policy.allow_user_supplied_urls,
                    "allowUserSuppliedDocuments": policy.allow_user_supplied_documents,
                    "requireOfficialSourceConfirmation": policy.require_official_source_confirmation,
                    "maxPublicResults": policy.max_public_results,
                },
                "requiredJsonShape": {
                    "findings": [
                        {
                            "key": "provider adverse public source signal found",
                            "value": False,
                            "confidence": 0.0,
                            "evidenceRefs": [],
                            "rationale": "brief reason",
                            "requiresHumanReview": True,
                        }
                    ],
                    "errors": [],
                },
                "allowedKeys": [
                    "provider adverse public source signal found",
                    "provider public evidence confidence below threshold",
                    "provider identity evidence requires manual review",
                    "provider evidence package requires human review",
                ],
            },
            sort_keys=True,
        )

        try:
            content = self._llm.chat(
                system_prompt,
                user_prompt,
                operation="provider_evidence_collection",
                rule_name="provider_verification",
            )
        except Exception as exc:
            log.warning("provider_llm_evidence_collection_failed", error=str(exc))
            return ProviderEvidencePackage.unavailable(
                self.SOURCE,
                reason=f"LLM provider evidence collection failed: {str(exc)[:300]}",
                expected_keys=("provider adverse public source signal found",),
            )

        return self._parse_response(content[:MAX_LLM_EVIDENCE_RESPONSE_CHARS], policy)

    def _parse_response(
        self,
        content: str,
        policy: EvidenceSourcePolicy,
    ) -> ProviderEvidencePackage:
        try:
            payload = json.loads(_strip_json_fence(content))
        except Exception as exc:
            return ProviderEvidencePackage.unavailable(
                self.SOURCE,
                reason=f"LLM provider evidence response was not valid JSON: {str(exc)[:200]}",
                expected_keys=("provider evidence package requires human review",),
            )

        findings: list[EvidenceFinding] = []
        for raw in payload.get("findings") or []:
            if not isinstance(raw, dict):
                continue
            key = str(raw.get("key") or "").strip()
            if key not in _ALLOWED_LLM_FACT_KEYS:
                continue
            refs = raw.get("evidenceRefs") or raw.get("evidence_refs") or []
            if not isinstance(refs, list):
                refs = []
            findings.append(
                EvidenceFinding(
                    key=key,
                    value=raw.get("value"),
                    status="advisory",
                    source=self.SOURCE,
                    confidence=_bounded_confidence(raw.get("confidence")),
                    authoritative=False,
                    evidence_refs=tuple(str(ref) for ref in refs if str(ref).strip()),
                    rationale=str(raw.get("rationale") or "")[:1000],
                    requires_human_review=bool(raw.get("requiresHumanReview", True)),
                )
            )

        if not findings:
            findings.append(
                EvidenceFinding(
                    key="provider evidence package requires human review",
                    value=True,
                    status="advisory",
                    source=self.SOURCE,
                    confidence=0.0,
                    authoritative=False,
                    rationale="LLM returned no accepted provider evidence findings.",
                    requires_human_review=True,
                )
            )

        errors = tuple(str(item) for item in payload.get("errors") or [] if str(item).strip())
        return ProviderEvidencePackage(
            source=self.SOURCE,
            status="advisory",
            findings=tuple(findings),
            errors=errors,
            provenance={
                "allowPublicWebSearch": policy.allow_public_web_search,
                "allowUserSuppliedUrls": policy.allow_user_supplied_urls,
                "allowUserSuppliedDocuments": policy.allow_user_supplied_documents,
            },
        )


_ALLOWED_LLM_FACT_KEYS = {
    "provider adverse public source signal found",
    "provider public evidence confidence below threshold",
    "provider identity evidence requires manual review",
    "provider evidence package requires human review",
}


def _strip_json_fence(content: str) -> str:
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return text


def _bounded_confidence(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, parsed))
