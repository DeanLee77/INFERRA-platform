from src.domain.provider_verification import ProviderEvidencePackage, ProviderVerificationSubject
from src.ports.provider_verification_port import AbnLookupPort


class AbnLookupStubAdapter(AbnLookupPort):
    """Stub for ABN Lookup / Australian Business Register verification."""

    SOURCE = "abn_lookup"
    EXPECTED_KEYS = (
        "provider abn is active",
        "provider business identity matches claim",
    )

    def lookup_abn(
        self,
        subject: ProviderVerificationSubject,
    ) -> ProviderEvidencePackage:
        return ProviderEvidencePackage.unavailable(
            self.SOURCE,
            reason=(
                "ABN Lookup adapter is not configured. Supply an ABN Lookup web "
                "services GUID or internal business-identity service."
            ),
            expected_keys=self.EXPECTED_KEYS,
        )
