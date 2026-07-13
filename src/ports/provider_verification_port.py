from abc import ABCMeta, abstractmethod

from src.domain.provider_verification import (
    EvidenceSourcePolicy,
    ProviderEvidencePackage,
    ProviderVerificationSubject,
)


class AhpraVerificationPort(metaclass=ABCMeta):
    """Port for AU Ahpra practitioner registration and restriction checks."""

    @abstractmethod
    def verify_practitioner(
        self,
        subject: ProviderVerificationSubject,
    ) -> ProviderEvidencePackage:
        pass  # pragma: no cover


class AbnLookupPort(metaclass=ABCMeta):
    """Port for Australian Business Register / ABN Lookup checks."""

    @abstractmethod
    def lookup_abn(
        self,
        subject: ProviderVerificationSubject,
    ) -> ProviderEvidencePackage:
        pass  # pragma: no cover


class HposProviderVerificationPort(metaclass=ABCMeta):
    """Port for Medicare/HPOS provider-number and claiming-authority checks."""

    @abstractmethod
    def verify_provider_number(
        self,
        subject: ProviderVerificationSubject,
    ) -> ProviderEvidencePackage:
        pass  # pragma: no cover


class ProviderLLMEvidencePort(metaclass=ABCMeta):
    """Port for configurable LLM-assisted provider evidence collection."""

    @abstractmethod
    def collect_evidence(
        self,
        subject: ProviderVerificationSubject,
        policy: EvidenceSourcePolicy,
    ) -> ProviderEvidencePackage:
        pass  # pragma: no cover
