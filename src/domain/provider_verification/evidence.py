from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ProviderVerificationSubject:
    """Provider and claim context needed by AU provider verification adapters."""

    provider_name: str = ""
    ahpra_registration_number: str = ""
    abn: str = ""
    medicare_provider_number: str = ""
    hpi_i: str = ""
    hpi_o: str = ""
    mbs_item_number: str = ""
    claimed_service_description: str = ""
    service_date: str = ""
    service_location: str = ""
    profession: str = ""
    specialty: str = ""
    supplied_evidence_urls: tuple[str, ...] = ()
    supplied_document_refs: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ProviderVerificationSubject":
        def _tuple_value(name: str) -> tuple[str, ...]:
            value = (
                payload.get(name)
                or payload.get(_snake_to_camel(name))
                or payload.get(_camel_to_snake(name))
            )
            if isinstance(value, str):
                return (value,) if value else ()
            if isinstance(value, (list, tuple)):
                return tuple(str(item) for item in value if str(item).strip())
            return ()

        values = {
            field_name: str(
                payload.get(field_name)
                or payload.get(_snake_to_camel(field_name))
                or ""
            ).strip()
            for field_name in (
                "provider_name",
                "ahpra_registration_number",
                "abn",
                "medicare_provider_number",
                "hpi_i",
                "hpi_o",
                "mbs_item_number",
                "claimed_service_description",
                "service_date",
                "service_location",
                "profession",
                "specialty",
            )
        }
        return cls(
            **values,
            supplied_evidence_urls=_tuple_value("supplied_evidence_urls"),
            supplied_document_refs=_tuple_value("supplied_document_refs"),
        )

    def redacted_context(self) -> dict[str, Any]:
        return {
            "provider_name": self.provider_name,
            "ahpra_registration_number": _redact_identifier(self.ahpra_registration_number),
            "abn": _redact_identifier(self.abn),
            "medicare_provider_number": _redact_identifier(self.medicare_provider_number),
            "hpi_i": _redact_identifier(self.hpi_i),
            "hpi_o": _redact_identifier(self.hpi_o),
            "mbs_item_number": self.mbs_item_number,
            "claimed_service_description": self.claimed_service_description,
            "service_date": self.service_date,
            "service_location": self.service_location,
            "profession": self.profession,
            "specialty": self.specialty,
            "supplied_evidence_urls": list(self.supplied_evidence_urls),
            "supplied_document_refs": list(self.supplied_document_refs),
        }


@dataclass(frozen=True)
class EvidenceSourcePolicy:
    """Runtime policy controlling which evidence collection channels are allowed."""

    allow_public_web_search: bool = False
    allow_user_supplied_urls: bool = True
    allow_user_supplied_documents: bool = True
    allow_llm_advisory_evidence: bool = False
    require_official_source_confirmation: bool = True
    max_public_results: int = 5


@dataclass(frozen=True)
class EvidenceFinding:
    """One normalized provider-verification signal with provenance."""

    key: str
    value: bool | int | float | str | None
    status: str
    source: str
    confidence: float = 0.0
    authoritative: bool = False
    evidence_refs: tuple[str, ...] = ()
    rationale: str = ""
    requires_human_review: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "status": self.status,
            "source": self.source,
            "confidence": self.confidence,
            "authoritative": self.authoritative,
            "evidenceRefs": list(self.evidence_refs),
            "rationale": self.rationale,
            "requiresHumanReview": self.requires_human_review,
        }


@dataclass(frozen=True)
class ProviderEvidencePackage:
    """Collection of normalized findings from one or more evidence sources."""

    source: str
    status: str
    findings: tuple[EvidenceFinding, ...] = ()
    errors: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def unavailable(
        cls,
        source: str,
        *,
        reason: str,
        expected_keys: tuple[str, ...] = (),
    ) -> "ProviderEvidencePackage":
        findings = tuple(
            EvidenceFinding(
                key=key,
                value=None,
                status="unavailable",
                source=source,
                confidence=0.0,
                authoritative=False,
                rationale=reason,
                requires_human_review=True,
            )
            for key in expected_keys
        )
        return cls(
            source=source,
            status="unavailable",
            findings=findings,
            errors=(reason,),
            provenance={"configured": False},
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "status": self.status,
            "findings": [finding.as_dict() for finding in self.findings],
            "errors": list(self.errors),
            "provenance": dict(self.provenance),
        }

    def to_inferra_facts(self) -> dict[str, Any]:
        facts: dict[str, Any] = {}
        needs_review = bool(self.errors)
        for finding in self.findings:
            if finding.value is not None and finding.status in {"verified", "not_verified", "advisory"}:
                facts[finding.key] = finding.value
            if finding.requires_human_review or finding.status in {"unavailable", "conflicting", "advisory"}:
                needs_review = True
        if needs_review:
            facts["provider evidence package requires human review"] = True
        return facts


def merge_evidence_packages(
    source: str,
    packages: tuple[ProviderEvidencePackage, ...],
) -> ProviderEvidencePackage:
    findings: list[EvidenceFinding] = []
    errors: list[str] = []
    provenance: dict[str, Any] = {"sources": []}
    status = "verified"

    for package in packages:
        findings.extend(package.findings)
        errors.extend(package.errors)
        provenance["sources"].append(package.as_dict())
        if package.status != "verified":
            status = "requires_review"

    return ProviderEvidencePackage(
        source=source,
        status=status,
        findings=tuple(findings),
        errors=tuple(errors),
        provenance=provenance,
    )


def _snake_to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _camel_to_snake(value: str) -> str:
    result = []
    for char in value:
        if char.isupper() and result:
            result.append("_")
        result.append(char.lower())
    return "".join(result)


def _redact_identifier(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}***{value[-2:]}"
