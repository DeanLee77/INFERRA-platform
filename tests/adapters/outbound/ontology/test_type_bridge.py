"""
Tests for the RDF_RANGE_TO_FACT_TYPE type safety bridge.

Covers:
- RDF_RANGE_TO_FACT_TYPE mapping completeness
- resolve_fact_type for known and unknown URIs
- validate_type_alignment: exact match, compatible widening, mismatch
- coerce_rdf_literal: all supported types, edge cases, failures
- validate_and_coerce: combined validation + coercion + DLQ
- TypeValidationError properties
"""

import pytest
from unittest.mock import patch, MagicMock

from src.adapters.outbound.ontology.type_bridge import (
    RDF_RANGE_TO_FACT_TYPE,
    FACT_TYPE_TO_RDF_RANGE,
    XSD_NS,
    TypeValidationError,
    resolve_fact_type,
    validate_type_alignment,
    coerce_rdf_literal,
    validate_and_coerce,
)
from src.domain.fact_values.fact_value_type import FactValueType


class TestRdfRangeMapping:
    def test_boolean_mapped(self):
        assert RDF_RANGE_TO_FACT_TYPE[f"{XSD_NS}boolean"] == FactValueType.BOOLEAN

    def test_integer_mapped(self):
        assert RDF_RANGE_TO_FACT_TYPE[f"{XSD_NS}integer"] == FactValueType.INTEGER

    def test_int_mapped_to_integer(self):
        assert RDF_RANGE_TO_FACT_TYPE[f"{XSD_NS}int"] == FactValueType.INTEGER

    def test_decimal_mapped(self):
        assert RDF_RANGE_TO_FACT_TYPE[f"{XSD_NS}decimal"] == FactValueType.DECIMAL

    def test_double_mapped(self):
        assert RDF_RANGE_TO_FACT_TYPE[f"{XSD_NS}double"] == FactValueType.DOUBLE

    def test_float_mapped_to_double(self):
        assert RDF_RANGE_TO_FACT_TYPE[f"{XSD_NS}float"] == FactValueType.DOUBLE

    def test_date_mapped(self):
        assert RDF_RANGE_TO_FACT_TYPE[f"{XSD_NS}date"] == FactValueType.DATE

    def test_dateTime_mapped_to_date(self):
        assert RDF_RANGE_TO_FACT_TYPE[f"{XSD_NS}dateTime"] == FactValueType.DATE

    def test_string_mapped(self):
        assert RDF_RANGE_TO_FACT_TYPE[f"{XSD_NS}string"] == FactValueType.STRING

    def test_anyURI_mapped_to_url(self):
        assert RDF_RANGE_TO_FACT_TYPE[f"{XSD_NS}anyURI"] == FactValueType.URL

    def test_reverse_mapping_boolean(self):
        assert FACT_TYPE_TO_RDF_RANGE[FactValueType.BOOLEAN] == f"{XSD_NS}boolean"

    def test_reverse_mapping_url(self):
        assert FACT_TYPE_TO_RDF_RANGE[FactValueType.URL] == f"{XSD_NS}anyURI"


class TestResolveFactType:
    def test_known_type(self):
        result = resolve_fact_type(f"{XSD_NS}boolean")
        assert result == FactValueType.BOOLEAN

    def test_unknown_type_returns_none(self):
        result = resolve_fact_type(f"{XSD_NS}unknownType")
        assert result is None

    def test_non_xsd_namespace_returns_none(self):
        result = resolve_fact_type("http://example.org/custom#MyType")
        assert result is None


class TestValidateTypeAlignment:
    def test_exact_match_returns_true(self):
        assert validate_type_alignment(
            "rule1", f"{XSD_NS}boolean", FactValueType.BOOLEAN
        )

    def test_exact_match_integer(self):
        assert validate_type_alignment(
            "rule1", f"{XSD_NS}integer", FactValueType.INTEGER
        )

    def test_compatible_widening_integer_to_double(self):
        assert validate_type_alignment(
            "rule1", f"{XSD_NS}integer", FactValueType.DOUBLE
        )

    def test_compatible_widening_integer_to_decimal(self):
        assert validate_type_alignment(
            "rule1", f"{XSD_NS}integer", FactValueType.DECIMAL
        )

    def test_compatible_widening_decimal_to_double(self):
        assert validate_type_alignment(
            "rule1", f"{XSD_NS}decimal", FactValueType.DOUBLE
        )

    def test_compatible_text_to_string(self):
        assert validate_type_alignment(
            "rule1", f"{XSD_NS}string", FactValueType.TEXT
        )

    def test_mismatch_raises_error(self):
        with pytest.raises(TypeValidationError) as exc_info:
            validate_type_alignment(
                "rule1", f"{XSD_NS}boolean", FactValueType.INTEGER
            )
        assert exc_info.value.rule_name == "rule1"
        assert exc_info.value.actual_type == FactValueType.BOOLEAN
        assert exc_info.value.expected_type == FactValueType.INTEGER

    def test_unknown_rdf_type_raises_error(self):
        with pytest.raises(TypeValidationError) as exc_info:
            validate_type_alignment(
                "rule1", f"{XSD_NS}gYear", FactValueType.STRING
            )
        assert exc_info.value.actual_type is None

    def test_string_to_boolean_mismatch(self):
        with pytest.raises(TypeValidationError):
            validate_type_alignment(
                "rule1", f"{XSD_NS}string", FactValueType.BOOLEAN
            )


class TestCoerceRdfLiteral:
    def test_boolean_true(self):
        assert coerce_rdf_literal("true", f"{XSD_NS}boolean") is True

    def test_boolean_false(self):
        assert coerce_rdf_literal("false", f"{XSD_NS}boolean") is False

    def test_boolean_1(self):
        assert coerce_rdf_literal("1", f"{XSD_NS}boolean") is True

    def test_boolean_0(self):
        assert coerce_rdf_literal("0", f"{XSD_NS}boolean") is False

    def test_boolean_yes(self):
        assert coerce_rdf_literal("yes", f"{XSD_NS}boolean") is True

    def test_boolean_no(self):
        assert coerce_rdf_literal("no", f"{XSD_NS}boolean") is False

    def test_boolean_case_insensitive(self):
        assert coerce_rdf_literal("True", f"{XSD_NS}boolean") is True
        assert coerce_rdf_literal("FALSE", f"{XSD_NS}boolean") is False

    def test_boolean_invalid_raises(self):
        with pytest.raises(ValueError):
            coerce_rdf_literal("maybe", f"{XSD_NS}boolean")

    def test_integer(self):
        assert coerce_rdf_literal("42", f"{XSD_NS}integer") == 42

    def test_integer_negative(self):
        assert coerce_rdf_literal("-7", f"{XSD_NS}integer") == -7

    def test_integer_invalid_raises(self):
        with pytest.raises(ValueError):
            coerce_rdf_literal("3.14", f"{XSD_NS}integer")

    def test_double(self):
        assert coerce_rdf_literal("3.14", f"{XSD_NS}double") == 3.14

    def test_float_maps_to_double(self):
        assert coerce_rdf_literal("2.5", f"{XSD_NS}float") == 2.5

    def test_decimal(self):
        assert coerce_rdf_literal("99.99", f"{XSD_NS}decimal") == 99.99

    def test_date_iso_format(self):
        result = coerce_rdf_literal("2025-01-15", f"{XSD_NS}date")
        assert "15/01/2025" == result

    def test_date_datetime_format(self):
        result = coerce_rdf_literal("2025-01-15T10:30:00", f"{XSD_NS}dateTime")
        assert "15/01/2025" == result

    def test_date_invalid_raises(self):
        with pytest.raises(ValueError):
            coerce_rdf_literal("not-a-date", f"{XSD_NS}date")

    def test_string_passthrough(self):
        assert coerce_rdf_literal("hello", f"{XSD_NS}string") == "hello"

    def test_url_valid(self):
        assert coerce_rdf_literal("https://example.com", f"{XSD_NS}anyURI") == "https://example.com"

    def test_url_invalid_no_scheme_raises(self):
        with pytest.raises(ValueError):
            coerce_rdf_literal("not-a-url", f"{XSD_NS}anyURI")

    def test_unknown_type_returns_string(self):
        assert coerce_rdf_literal("raw_value", "http://example.org/custom") == "raw_value"


class TestValidateAndCoerce:
    def test_valid_type_and_coercion(self):
        result = validate_and_coerce(
            "rule1", "42", f"{XSD_NS}integer", FactValueType.INTEGER
        )
        assert result == 42

    def test_compatible_type_and_coercion(self):
        result = validate_and_coerce(
            "rule1", "3", f"{XSD_NS}integer", FactValueType.DOUBLE
        )
        assert result == 3

    def test_mismatch_publishes_to_dlq(self):
        with patch(
            "src.adapters.outbound.ontology.type_bridge._publish_type_error_to_dlq"
        ) as mock_dlq:
            with pytest.raises(TypeValidationError):
                validate_and_coerce(
                    "rule1", "true", f"{XSD_NS}boolean", FactValueType.INTEGER
                )
            mock_dlq.assert_called_once()

    def test_coercion_failure_publishes_to_dlq(self):
        with patch(
            "src.adapters.outbound.ontology.type_bridge._publish_type_error_to_dlq"
        ) as mock_dlq:
            with pytest.raises(ValueError):
                validate_and_coerce(
                    "rule1", "not_int", f"{XSD_NS}integer", FactValueType.INTEGER
                )
            mock_dlq.assert_called_once()

    def test_dlq_publish_failure_does_not_swallow_original_error(self):
        with patch(
            "src.adapters.outbound.ontology.type_bridge._publish_type_error_to_dlq",
            side_effect=Exception("DLQ down"),
        ):
            with pytest.raises(TypeValidationError):
                validate_and_coerce(
                    "rule1", "true", f"{XSD_NS}boolean", FactValueType.INTEGER
                )


class TestTypeValidationError:
    def test_error_properties(self):
        err = TypeValidationError(
            rule_name="test_rule",
            rdf_type_uri=f"{XSD_NS}boolean",
            expected_type=FactValueType.INTEGER,
            actual_type=FactValueType.BOOLEAN,
        )
        assert err.rule_name == "test_rule"
        assert err.rdf_type_uri == f"{XSD_NS}boolean"
        assert err.expected_type == FactValueType.INTEGER
        assert err.actual_type == FactValueType.BOOLEAN
        assert "test_rule" in str(err)
        assert "BOOLEAN" in str(err)
        assert "INTEGER" in str(err)

    def test_error_with_unknown_type(self):
        err = TypeValidationError(
            rule_name="test_rule",
            rdf_type_uri="http://unknown#foo",
            expected_type=FactValueType.STRING,
            actual_type=None,
        )
        assert "UNKNOWN" in str(err)
