from src.domain.provider_verification import ProviderEvidencePackage, ProviderVerificationSubject
from src.ports.provider_verification_port import AhpraVerificationPort


class AhpraStubAdapter(AhpraVerificationPort):
    """Stub for Ahpra registration, conditions, restrictions, and warnings."""

    SOURCE = "ahpra"
    EXPECTED_KEYS = (
        "provider ahpra registration is current",
        "provider ahpra profession matches claimed service",
        "provider has incompatible practice restriction",
        "provider has public warning",
    )

    def verify_practitioner(
        self,
        subject: ProviderVerificationSubject,
    ) -> ProviderEvidencePackage:
        return ProviderEvidencePackage.unavailable(
            self.SOURCE,
            reason=(
                "Ahpra adapter is not configured. Use an approved Ahpra integration, "
                "employer service, or controlled manual register verification."
            ),
            expected_keys=self.EXPECTED_KEYS,
        )
