"""
RDF Range → FactValueType type safety bridge.

Enforces strict alignment between XSD RDF range types and INFERRA's
FactValueType enum during ontology sync. Type mismatches that cannot
be resolved are published to the dead-letter queue for manual review.

Used by the async sync pipeline after RDF compilation and before
fact injection into the LayeredFactStore.
"""

from datetime import datetime
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import structlog

from src.domain.fact_values.fact_value_type import FactValueType

log = structlog.get_logger()

XSD_NS = "http://www.w3.org/2001/XMLSchema#"

RDF_RANGE_TO_FACT_TYPE: Dict[str, FactValueType] = {
    f"{XSD_NS}boolean": FactValueType.BOOLEAN,
    f"{XSD_NS}integer": FactValueType.INTEGER,
    f"{XSD_NS}int": FactValueType.INTEGER,
    f"{XSD_NS}decimal": FactValueType.DECIMAL,
    f"{XSD_NS}double": FactValueType.DOUBLE,
    f"{XSD_NS}float": FactValueType.DOUBLE,
    f"{XSD_NS}date": FactValueType.DATE,
    f"{XSD_NS}dateTime": FactValueType.DATE,
    f"{XSD_NS}string": FactValueType.STRING,
    f"{XSD_NS}normalizedString": FactValueType.STRING,
    f"{XSD_NS}token": FactValueType.STRING,
    f"{XSD_NS}anyURI": FactValueType.URL,
}

FACT_TYPE_TO_RDF_RANGE: Dict[FactValueType, str] = {
    FactValueType.BOOLEAN: f"{XSD_NS}boolean",
    FactValueType.INTEGER: f"{XSD_NS}integer",
    FactValueType.DECIMAL: f"{XSD_NS}decimal",
    FactValueType.DOUBLE: f"{XSD_NS}double",
    FactValueType.DATE: f"{XSD_NS}date",
    FactValueType.STRING: f"{XSD_NS}string",
    FactValueType.URL: f"{XSD_NS}anyURI",
    FactValueType.HASH: f"{XSD_NS}string",
    FactValueType.GUID: f"{XSD_NS}string",
    FactValueType.TEXT: f"{XSD_NS}string",
    FactValueType.DEFI_STRING: f"{XSD_NS}string",
}

_COMPATIBLE_TYPES: Dict[FactValueType, Tuple[FactValueType, ...]] = {
    FactValueType.DOUBLE: (FactValueType.INTEGER, FactValueType.DECIMAL),
    FactValueType.DECIMAL: (FactValueType.INTEGER,),
    FactValueType.STRING: (FactValueType.TEXT, FactValueType.DEFI_STRING),
    FactValueType.TEXT: (FactValueType.STRING, FactValueType.DEFI_STRING),
    FactValueType.DEFI_STRING: (FactValueType.STRING, FactValueType.TEXT),
}


class TypeValidationError(Exception):
    """Raised when an RDF type cannot be aligned with the expected FactValueType."""

    def __init__(
        self,
        rule_name: str,
        rdf_type_uri: str,
        expected_type: FactValueType,
        actual_type: Optional[FactValueType],
    ):
        self.rule_name = rule_name
        self.rdf_type_uri = rdf_type_uri
        self.expected_type = expected_type
        self.actual_type = actual_type
        super().__init__(
            f"Type mismatch in rule '{rule_name}': RDF range '{rdf_type_uri}' maps to "
            f"{actual_type.value if actual_type else 'UNKNOWN'}, expected {expected_type.value}"
        )


def resolve_fact_type(rdf_type_uri: str) -> Optional[FactValueType]:
    """
    Resolve an XSD RDF type URI to a FactValueType.

    Args:
        rdf_type_uri: Full XSD type URI (e.g. 'http://www.w3.org/2001/XMLSchema#boolean')

    Returns:
        Corresponding FactValueType, or None if no mapping exists
    """
    return RDF_RANGE_TO_FACT_TYPE.get(rdf_type_uri)


def validate_type_alignment(
    rule_name: str,
    rdf_type_uri: str,
    expected_type: FactValueType,
) -> bool:
    """
    Validate that an RDF range type aligns with the expected FactValueType.

    Checks exact match first, then compatible widenings (e.g. INTEGER→DOUBLE).

    Args:
        rule_name: Rule name for logging and error context
        rdf_type_uri: XSD type URI from the RDF range
        expected_type: The FactValueType expected by the rule

    Returns:
        True if the types align (exact or compatible widening)

    Raises:
        TypeValidationError: If types are incompatible
    """
    actual_type = resolve_fact_type(rdf_type_uri)

    if actual_type is None:
        log.warning(
            "type_bridge_unknown_rdf_type",
            rule_name=rule_name,
            rdf_type_uri=rdf_type_uri,
            expected_type=expected_type.value,
        )
        raise TypeValidationError(rule_name, rdf_type_uri, expected_type, None)

    if actual_type == expected_type:
        return True

    compatible = _COMPATIBLE_TYPES.get(expected_type, ())
    if actual_type in compatible:
        log.debug(
            "type_bridge_compatible_widening",
            rule_name=rule_name,
            rdf_type_uri=rdf_type_uri,
            actual_type=actual_type.value,
            expected_type=expected_type.value,
        )
        return True

    log.error(
        "type_bridge_mismatch",
        rule_name=rule_name,
        rdf_type_uri=rdf_type_uri,
        actual_type=actual_type.value,
        expected_type=expected_type.value,
    )
    raise TypeValidationError(rule_name, rdf_type_uri, expected_type, actual_type)


def coerce_rdf_literal(
    literal_value: str,
    rdf_type_uri: str,
) -> Any:
    """
    Coerce an RDF literal string to a Python value matching the XSD type.

    Args:
        literal_value: String value from the RDF literal
        rdf_type_uri: XSD type URI determining the coercion target

    Returns:
        Coerced Python value (bool, int, float, str, datetime)

    Raises:
        ValueError: If the literal cannot be coerced to the target type
    """
    fact_type = resolve_fact_type(rdf_type_uri)

    if fact_type is None:
        return literal_value

    try:
        if fact_type == FactValueType.BOOLEAN:
            lower = literal_value.lower().strip()
            if lower in ("true", "1", "yes"):
                return True
            if lower in ("false", "0", "no"):
                return False
            raise ValueError(f"Cannot coerce '{literal_value}' to boolean")

        if fact_type == FactValueType.INTEGER:
            return int(literal_value)

        if fact_type in (FactValueType.DOUBLE, FactValueType.DECIMAL):
            return float(literal_value)

        if fact_type == FactValueType.DATE:
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.strptime(literal_value, fmt).strftime("%d/%m/%Y")
                except ValueError:
                    continue
            raise ValueError(f"Cannot parse date: '{literal_value}'")

        if fact_type == FactValueType.URL:
            parsed = urlparse(literal_value)
            if not parsed.scheme:
                raise ValueError(f"Invalid URL: '{literal_value}'")
            return literal_value

    except (ValueError, TypeError) as exc:
        log.warning(
            "type_bridge_coercion_failed",
            literal_value=literal_value,
            rdf_type_uri=rdf_type_uri,
            target_type=fact_type.value,
            error=str(exc),
        )
        raise

    return literal_value


def validate_and_coerce(
    rule_name: str,
    literal_value: str,
    rdf_type_uri: str,
    expected_type: FactValueType,
) -> Any:
    """
    Validate type alignment and coerce an RDF literal in one step.

    On type mismatch, publishes to DLQ and re-raises TypeValidationError.
    On coercion failure, publishes to DLQ and re-raises ValueError.

    Args:
        rule_name: Rule name for logging and DLQ context
        literal_value: String value from the RDF literal
        rdf_type_uri: XSD type URI from the RDF range
        expected_type: The FactValueType expected by the rule

    Returns:
        Coerced Python value matching expected_type

    Raises:
        TypeValidationError: If types are incompatible
        ValueError: If coercion fails
    """
    try:
        validate_type_alignment(rule_name, rdf_type_uri, expected_type)
        return coerce_rdf_literal(literal_value, rdf_type_uri)
    except (TypeValidationError, ValueError) as exc:
        try:
            _publish_type_error_to_dlq(
                rule_name=rule_name,
                literal_value=literal_value,
                rdf_type_uri=rdf_type_uri,
                expected_type=expected_type.value,
                error=str(exc),
            )
        except Exception:
            log.error(
                "type_bridge_dlq_publish_failed",
                rule_name=rule_name,
                rdf_type_uri=rdf_type_uri,
                expected_type=expected_type.value,
                error=str(exc),
                exc_info=True,
            )
        raise


def _publish_type_error_to_dlq(
    rule_name: str,
    literal_value: str,
    rdf_type_uri: str,
    expected_type: str,
    error: str,
) -> None:
    """Publish a type validation error to the dead-letter queue."""
    try:
        from src.tasks.rule_sync import publish_dead_letter_event

        source_hash = f"type_validation:{rule_name}:{rdf_type_uri}"
        publish_dead_letter_event(
            rule_name=rule_name,
            rule_text=literal_value,
            source_hash=source_hash,
            error=error,
        )
    except Exception:
        log.error(
            "type_bridge_dlq_publish_failed",
            rule_name=rule_name,
            rdf_type_uri=rdf_type_uri,
            expected_type=expected_type,
            error=error,
            exc_info=True,
        )
