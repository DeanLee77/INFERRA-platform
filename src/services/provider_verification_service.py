from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from src.adapters.outbound.provider_verification import (
    AbnLookupStubAdapter,
    AhpraStubAdapter,
    HposStubAdapter,
    LLMProviderEvidenceCollectorAdapter,
)
from src.config import settings
from src.domain.provider_verification import (
    EvidenceSourcePolicy,
    ProviderEvidencePackage,
    ProviderVerificationSubject,
)
from src.domain.provider_verification.evidence import merge_evidence_packages
from src.ports.provider_verification_port import (
    AbnLookupPort,
    AhpraVerificationPort,
    HposProviderVerificationPort,
    ProviderLLMEvidencePort,
)


@dataclass(frozen=True)
class ProviderVerificationResult:
    evidence: ProviderEvidencePackage
    inferra_facts: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence": self.evidence.as_dict(),
            "inferraFacts": self.inferra_facts,
        }


class ProviderVerificationService:
    """Collect AU provider evidence and normalize it into INFERRA fact inputs."""

    def __init__(
        self,
        *,
        ahpra: AhpraVerificationPort | None = None,
        abn_lookup: AbnLookupPort | None = None,
        hpos: HposProviderVerificationPort | None = None,
        llm_evidence: ProviderLLMEvidencePort | None = None,
    ) -> None:
        self._ahpra = ahpra or AhpraStubAdapter()
        self._abn_lookup = abn_lookup or AbnLookupStubAdapter()
        self._hpos = hpos or HposStubAdapter()
        self._llm_evidence = llm_evidence or LLMProviderEvidenceCollectorAdapter()

    def verify_provider(
        self,
        subject: ProviderVerificationSubject | Mapping[str, Any],
        policy: EvidenceSourcePolicy | Mapping[str, Any] | None = None,
    ) -> ProviderVerificationResult:
        if not isinstance(subject, ProviderVerificationSubject):
            subject = ProviderVerificationSubject.from_mapping(subject)
        if policy is None:
            policy = EvidenceSourcePolicy(
                allow_public_web_search=settings.PROVIDER_EVIDENCE_ALLOW_PUBLIC_WEB_SEARCH,
                allow_user_supplied_urls=settings.PROVIDER_EVIDENCE_ALLOW_USER_SUPPLIED_URLS,
                allow_user_supplied_documents=settings.PROVIDER_EVIDENCE_ALLOW_USER_SUPPLIED_DOCUMENTS,
                allow_llm_advisory_evidence=settings.PROVIDER_EVIDENCE_ALLOW_LLM_ADVISORY,
                require_official_source_confirmation=(
                    settings.PROVIDER_EVIDENCE_REQUIRE_OFFICIAL_SOURCE_CONFIRMATION
                ),
                max_public_results=settings.PROVIDER_EVIDENCE_MAX_PUBLIC_RESULTS,
            )
        elif not isinstance(policy, EvidenceSourcePolicy):
            policy = EvidenceSourcePolicy(**dict(policy))

        packages = (
            self._ahpra.verify_practitioner(subject),
            self._abn_lookup.lookup_abn(subject),
            self._hpos.verify_provider_number(subject),
            self._llm_evidence.collect_evidence(subject, policy),
        )
        merged = merge_evidence_packages("provider_verification", packages)
        return ProviderVerificationResult(
            evidence=merged,
            inferra_facts=merged.to_inferra_facts(),
        )
