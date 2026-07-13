from src.domain.provider_verification import ProviderEvidencePackage, ProviderVerificationSubject
from src.ports.provider_verification_port import HposProviderVerificationPort


class HposStubAdapter(HposProviderVerificationPort):
    """Stub for Services Australia / HPOS Medicare provider-number checks."""

    SOURCE = "hpos"
    EXPECTED_KEYS = (
        "provider medicare provider number active on service date",
        "provider number matches mbs service",
        "provider number matches service location",
    )

    def verify_provider_number(
        self,
        subject: ProviderVerificationSubject,
    ) -> ProviderEvidencePackage:
        return ProviderEvidencePackage.unavailable(
            self.SOURCE,
            reason=(
                "HPOS/Medicare provider-number adapter is not configured. Use "
                "Services Australia integration or an internal claiming-authority service."
            ),
            expected_keys=self.EXPECTED_KEYS,
        )
