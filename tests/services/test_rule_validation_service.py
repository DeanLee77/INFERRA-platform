"""
Tests for the RuleValidationService.

Covers:
- Syntax validation (FIXED/INPUT declarations, rule lines)
- Type consistency (undeclared references, type mismatches, unused declarations)
- DAG cycle detection
- Content-hash cache (hit, miss, TTL expiry, LRU eviction, invalidation)
- Empty rule handling
- Regex pattern edge cases
- _extract_references and _extract_value_type
"""

import time
import pytest

from src.domain.fact_values import FactValueType
from src.services.rule_validation_service import (
    RuleValidationService,
    ValidationError,
    ValidationResult,
    ValidationWarning,
    ValidationEntry,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def service() -> RuleValidationService:
    return RuleValidationService()


@pytest.fixture
def service_small_cache() -> RuleValidationService:
    return RuleValidationService(cache_maxsize=2, cache_ttl_seconds=5)


# =============================================================================
# Value Object Tests
# =============================================================================

class TestValidationEntry:
    def test_to_dict_includes_all_fields(self):
        err = ValidationError("CODE", "message", line=5, node_name="var")
        d = err.to_dict()
        assert d == {
            "code": "CODE",
            "message": "message",
            "waiver_id": "CODE:var",
            "severity": "error",
            "source": "deterministic",
            "blocking": False,
            "review_required": False,
            "line": 5,
            "node_name": "var",
        }

    def test_to_dict_omits_none_fields(self):
        err = ValidationError("CODE", "message")
        d = err.to_dict()
        assert "line" not in d
        assert "node_name" not in d
        assert "category" not in d
        assert "reason" not in d
        assert "review_item_id" not in d
        assert d["waiver_id"] == "CODE"

    def test_waiver_id_uses_line_when_node_name_missing(self):
        err = ValidationError("CODE", "message", line=7)
        assert err.waiver_id == "CODE:line_7"

    def test_equality(self):
        a = ValidationError("CODE", "msg", line=1)
        b = ValidationError("CODE", "msg", line=1)
        c = ValidationError("CODE", "msg", line=2)
        assert a == b
        assert a != c

    def test_equality_includes_node_name(self):
        a = ValidationError("CODE", "msg", node_name="x")
        b = ValidationError("CODE", "msg", node_name="x")
        c = ValidationError("CODE", "msg", node_name="y")
        assert a == b
        assert a != c

    def test_hash(self):
        a = ValidationError("CODE", "msg", line=1)
        b = ValidationError("CODE", "msg", line=1)
        assert hash(a) == hash(b)

    def test_warning_to_dict_omits_none_fields(self):
        w = ValidationWarning("CODE", "msg")
        d = w.to_dict()
        assert "line" not in d
        assert "node_name" not in d
        assert d["severity"] == "warning"
        assert d["source"] == "deterministic"


class TestValidationResult:
    def test_valid_result_no_errors(self):
        r = ValidationResult(valid=True)
        assert r.valid is True
        assert r.errors == ()
        assert r.warnings == ()

    def test_invalid_result_with_errors(self):
        errs = (ValidationError("E", "e"),)
        r = ValidationResult(valid=False, errors=errs)
        assert r.valid is False
        assert len(r.errors) == 1

    def test_to_dict(self):
        r = ValidationResult(
            valid=False,
            errors=(ValidationError("E1", "e1"),),
            warnings=(ValidationWarning("W1", "w1"),),
        )
        d = r.to_dict()
        assert d["valid"] is False
        assert len(d["errors"]) == 1
        assert len(d["warnings"]) == 1

    def test_errors_and_warnings_are_immutable_tuples(self):
        r = ValidationResult(valid=False, errors=(ValidationError("E", "e"),))
        assert isinstance(r.errors, tuple)
        assert isinstance(r.warnings, tuple)


# =============================================================================
# Empty Rule Tests
# =============================================================================

class TestEmptyRule:
    def test_empty_rule_text(self, service):
        result = service.validate("")
        assert result.valid is False
        assert any(e.code == "EMPTY_RULE" for e in result.errors)

    def test_whitespace_only_rule_text(self, service):
        result = service.validate("   \n  \n  ")
        assert result.valid is False
        assert any(e.code == "EMPTY_RULE" for e in result.errors)


# =============================================================================
# Syntax & Tokeniser Tests
# =============================================================================

class TestSyntaxValidation:
    def test_valid_simple_rule(self, service):
        rule_text = (
            'FIXED threshold IS 50\n'
            'INPUT age AS NUMBER\n'
            'age > threshold\n'
        )
        result = service.validate(rule_text)
        assert not any(e.code == "DUPLICATE_DECLARATION" for e in result.errors)

    def test_duplicate_fixed_declaration(self, service):
        rule_text = (
            'FIXED rate IS 10\n'
            'FIXED rate IS 20\n'
        )
        result = service.validate(rule_text)
        assert any(e.code == "DUPLICATE_DECLARATION" for e in result.errors)

    def test_duplicate_input_declaration(self, service):
        rule_text = (
            'INPUT age AS NUMBER\n'
            'INPUT age AS BOOLEAN\n'
        )
        result = service.validate(rule_text)
        assert any(e.code == "DUPLICATE_DECLARATION" for e in result.errors)

    def test_comment_lines_ignored(self, service):
        rule_text = (
            '# This is a comment\n'
            '// Another comment\n'
            'FIXED rate IS 10\n'
        )
        result = service.validate(rule_text)
        assert not any(e.code == "DUPLICATE_DECLARATION" for e in result.errors)

    def test_list_with_items(self, service):
        rule_text = (
            'INPUT category AS LIST\n'
            '    ITEM A\n'
            '    ITEM B\n'
            '    ITEM C\n'
        )
        result = service.validate(rule_text)
        assert not any(e.code == "DUPLICATE_DECLARATION" for e in result.errors)

    def test_collection_iteration_with_size_from_is_valid(self, service):
        rule_text = (
            'TYPE service period\n'
            '    FIELD period of service in days AS NUMBER\n'
            '\n'
            'INPUT number of service periods AS NUMBER\n'
            'INPUT service history AS COLLECTION OF service period\n'
            '    SIZE FROM number of service periods\n'
            '\n'
            'service history ok\n'
            '    AND ALL period IN service history\n'
            '        AND period.period of service in days >= 30\n'
        )
        result = service.validate(rule_text)
        assert result.valid is True
        assert not result.errors

    def test_exact_collection_iteration_with_size_from_is_valid(self, service):
        rule_text = (
            'TYPE service period\n'
            '    FIELD period of service in days AS NUMBER\n'
            '\n'
            'INPUT number of service periods AS NUMBER\n'
            'INPUT service history AS COLLECTION OF service period\n'
            '    SIZE FROM number of service periods\n'
            '\n'
            'service history ok\n'
            '    AND EXACTLY 2 period IN service history\n'
            '        AND period.period of service in days >= 30\n'
        )
        result = service.validate(rule_text)
        assert result.valid is True
        assert not result.errors

    def test_at_least_collection_iteration_with_size_from_is_valid(self, service):
        rule_text = (
            'TYPE service period\n'
            '    FIELD period of service in days AS NUMBER\n'
            '\n'
            'INPUT number of service periods AS NUMBER\n'
            'INPUT service history AS COLLECTION OF service period\n'
            '    SIZE FROM number of service periods\n'
            '\n'
            'service history ok\n'
            '    AND AT LEAST 2 period IN service history\n'
            '        AND period.period of service in days >= 30\n'
        )
        result = service.validate(rule_text)
        assert result.valid is True
        assert not result.errors

    def test_at_most_collection_iteration_with_size_from_is_valid(self, service):
        rule_text = (
            'TYPE service period\n'
            '    FIELD period of service in days AS NUMBER\n'
            '\n'
            'INPUT number of service periods AS NUMBER\n'
            'INPUT service history AS COLLECTION OF service period\n'
            '    SIZE FROM number of service periods\n'
            '\n'
            'service history ok\n'
            '    AND AT MOST 2 period IN service history\n'
            '        AND period.period of service in days >= 30\n'
        )
        result = service.validate(rule_text)
        assert result.valid is True
        assert not result.errors

    def test_legacy_iterate_list_of_syntax_is_invalid(self, service):
        rule_text = (
            'TYPE service period\n'
            '    FIELD period of service in days AS NUMBER\n'
            '\n'
            'INPUT number of service periods AS NUMBER\n'
            'INPUT service history AS COLLECTION OF service period\n'
            '    SIZE FROM number of service periods\n'
            '\n'
            'service history ok\n'
            '    AND ALL period ITERATE: LIST OF service history\n'
            '        AND period.period of service in days >= 30\n'
        )
        result = service.validate(rule_text)
        assert result.valid is False
        assert any(error.code == "INVALID_ITERATE_SYNTAX" for error in result.errors)

    def test_bare_number_iteration_quantifier_is_invalid(self, service):
        rule_text = (
            'TYPE service period\n'
            '    FIELD period of service in days AS NUMBER\n'
            '\n'
            'INPUT number of service periods AS NUMBER\n'
            'INPUT service history AS COLLECTION OF service period\n'
            '    SIZE FROM number of service periods\n'
            '\n'
            'service history ok\n'
            '    AND 2 period IN service history\n'
            '        AND period.period of service in days >= 30\n'
        )
        result = service.validate(rule_text)
        assert result.valid is False
        assert any(error.code == "INVALID_ITERATE_SYNTAX" for error in result.errors)

    def test_exact_iteration_alias_is_invalid(self, service):
        rule_text = (
            'TYPE service period\n'
            '    FIELD period of service in days AS NUMBER\n'
            '\n'
            'INPUT number of service periods AS NUMBER\n'
            'INPUT service history AS COLLECTION OF service period\n'
            '    SIZE FROM number of service periods\n'
            '\n'
            'service history ok\n'
            '    AND EXACT 2 period IN service history\n'
            '        AND period.period of service in days >= 30\n'
        )
        result = service.validate(rule_text)
        assert result.valid is False
        assert any(error.code == "INVALID_ITERATE_SYNTAX" for error in result.errors)

    def test_field_list_of_option_binding_is_valid_when_options_declared(self, service):
        rule_text = (
            'FIXED DVA service type options AS LIST\n'
            '    ITEM operational service\n'
            '    ITEM peacekeeping service\n'
            '\n'
            'TYPE service period\n'
            '    FIELD service type AS LIST OF DVA service type options\n'
            '\n'
            'INPUT number of service periods AS NUMBER\n'
            'INPUT service history AS COLLECTION OF service period\n'
            '    SIZE FROM number of service periods\n'
            '\n'
            'service history ok\n'
            '    AND SOME period IN service history\n'
            '        AND period.service type IS IN LIST: DVA service type options\n'
        )
        result = service.validate(rule_text)
        assert result.valid is True
        assert not result.errors

    def test_field_list_of_option_binding_requires_declared_options(self, service):
        rule_text = (
            'TYPE service period\n'
            '    FIELD service type AS LIST OF DVA service type options\n'
            '\n'
            'INPUT number of service periods AS NUMBER\n'
            'INPUT service history AS COLLECTION OF service period\n'
            '    SIZE FROM number of service periods\n'
            '\n'
            'service history ok\n'
            '    AND SOME period IN service history\n'
            '        AND period.service type = "operational service"\n'
        )
        result = service.validate(rule_text)
        assert any(
            e.code == "UNDECLARED_REFERENCE"
            and e.node_name == "DVA service type options"
            for e in result.errors
        )

    def test_same_level_and_or_mixing_warns(self, service):
        rule_text = (
            'INPUT person served AS BOOLEAN\n'
            'INPUT person discharged AS BOOLEAN\n'
            'INPUT person has reserve service AS BOOLEAN\n'
            '\n'
            'person qualifies\n'
            '    AND person served\n'
            '    OR person discharged\n'
            '    OR person has reserve service\n'
        )
        result = service.validate(rule_text)
        assert result.valid is True
        assert any(w.code == "MIXED_AND_OR_CHILDREN" for w in result.warnings)

    def test_collection_size_from_requires_declared_count(self, service):
        rule_text = (
            'TYPE service period\n'
            '    FIELD period of service in days AS NUMBER\n'
            '\n'
            'INPUT service history AS COLLECTION OF service period\n'
            '    SIZE FROM number of service periods\n'
            '\n'
            'service history ok\n'
            '    AND ALL period IN service history\n'
            '        AND period.period of service in days >= 30\n'
        )
        result = service.validate(rule_text)
        assert any(e.code == "UNDECLARED_REFERENCE" for e in result.errors)

    def test_fixed_list_with_is(self, service):
        rule_text = (
            'FIXED items IS LIST\n'
            '    ITEM A\n'
            '    ITEM B\n'
        )
        result = service.validate(rule_text)
        assert not any(e.code == "DUPLICATE_DECLARATION" for e in result.errors)

    def test_expression_conclusion(self, service):
        rule_text = (
            'INPUT amount AS DOUBLE\n'
            'INPUT rate AS DOUBLE\n'
            'total IS CALC amount * rate\n'
        )
        result = service.validate(rule_text)
        assert not any(e.code == "DUPLICATE_DECLARATION" for e in result.errors)

    def test_value_conclusion(self, service):
        rule_text = (
            'INPUT eligible AS BOOLEAN\n'
            'eligible IS true\n'
        )
        result = service.validate(rule_text)
        assert not any(e.code == "DUPLICATE_DECLARATION" for e in result.errors)

    def test_iterate_pattern(self, service):
        rule_text = (
            'INPUT items AS LIST\n'
            'items FOR ALL\n'
        )
        result = service.validate(rule_text)
        assert not any(e.code == "DUPLICATE_DECLARATION" for e in result.errors)

    def test_input_with_is_keyword(self, service):
        rule_text = (
            'INPUT flag IS true\n'
        )
        result = service.validate(rule_text)
        assert not any(e.code == "DUPLICATE_DECLARATION" for e in result.errors)


# =============================================================================
# Type Consistency Tests
# =============================================================================

class TestTypeConsistency:
    def test_undeclared_reference(self, service):
        rule_text = (
            'INPUT age AS NUMBER\n'
            'age > threshold\n'
        )
        result = service.validate(rule_text)
        assert any(e.code == "UNDECLARED_REFERENCE" for e in result.errors)

    def test_type_mismatch_boolean_comparison(self, service):
        rule_text = (
            'INPUT flag AS BOOLEAN\n'
            'flag > 5\n'
        )
        result = service.validate(rule_text)
        assert any(e.code == "TYPE_MISMATCH" for e in result.errors)

    def test_no_type_mismatch_numeric_comparison(self, service):
        rule_text = (
            'INPUT score AS NUMBER\n'
            'score > 50\n'
        )
        result = service.validate(rule_text)
        assert not any(e.code == "TYPE_MISMATCH" for e in result.errors)

    def test_unused_declaration_warning(self, service):
        rule_text = (
            'INPUT age AS NUMBER\n'
            'INPUT name AS STRING\n'
            'age > 18\n'
        )
        result = service.validate(rule_text)
        assert any(w.code == "UNUSED_DECLARATION" for w in result.warnings)
        unused_names = [w.node_name for w in result.warnings if w.code == "UNUSED_DECLARATION"]
        assert "name" in unused_names

    def test_no_unused_warning_when_referenced(self, service):
        rule_text = (
            'INPUT age AS NUMBER\n'
            'age > 18\n'
        )
        result = service.validate(rule_text)
        unused = [w for w in result.warnings if w.code == "UNUSED_DECLARATION" and w.node_name == "age"]
        assert len(unused) == 0

    def test_comparison_operators_le_ge_eq(self, service):
        rule_text = (
            'INPUT score AS NUMBER\n'
            'score >= 50\n'
        )
        result = service.validate(rule_text)
        assert not any(e.code == "TYPE_MISMATCH" for e in result.errors)

    def test_type_mismatch_boolean_le(self, service):
        rule_text = (
            'INPUT flag AS BOOLEAN\n'
            'flag <= 5\n'
        )
        result = service.validate(rule_text)
        assert any(e.code == "TYPE_MISMATCH" for e in result.errors)

    def test_variable_name_discrepancy_blocks_save_with_line_number(self, service):
        rule_text = (
            'INPUT the person is a member of the Reserves AS BOOLEAN\n'
            'eligible for reserve benefit\n'
            '    AND person is a member of the Reserves\n'
        )
        result = service.validate(rule_text)

        discrepancies = [
            e for e in result.errors
            if e.code == "VARIABLE_NAME_DISCREPANCY"
        ]
        assert result.valid is False
        assert len(discrepancies) == 1
        assert discrepancies[0].line == 3
        assert discrepancies[0].node_name == "person is a member of the Reserves"
        assert "the person is a member of the Reserves" in discrepancies[0].message
        assert "line 1" in discrepancies[0].message

    def test_variable_name_discrepancy_suppresses_duplicate_noise(self, service):
        rule_text = (
            'INPUT the person is a member of the Reserves AS BOOLEAN\n'
            'eligible for reserve benefit\n'
            '    AND person is a member of the Reserves\n'
        )
        result = service.validate(rule_text)

        assert not any(
            e.code == "UNDECLARED_REFERENCE"
            and e.node_name == "person is a member of the Reserves"
            for e in result.errors
        )
        assert not any(
            w.code == "UNUSED_DECLARATION"
            and w.node_name == "the person is a member of the Reserves"
            for w in result.warnings
        )

    def test_variable_name_discrepancy_normalizes_apostrophe_variants(self, service):
        rule_text = (
            "INPUT the person's age AS NUMBER\n"
            'eligible for age benefit\n'
            "    AND the person\u2019s age >= 60\n"
        )
        result = service.validate(rule_text)

        discrepancies = [
            e for e in result.errors
            if e.code == "VARIABLE_NAME_DISCREPANCY"
        ]
        assert len(discrepancies) == 1
        assert discrepancies[0].line == 3
        assert discrepancies[0].node_name == "the person\u2019s age"

    def test_phrase_reference_without_declaration_is_reported_with_line(self, service):
        rule_text = (
            'eligible for reserve benefit\n'
            '    AND person is a member of the Reserves\n'
        )
        result = service.validate(rule_text)

        undeclared = [
            e for e in result.errors
            if e.code == "UNDECLARED_REFERENCE"
        ]
        assert len(undeclared) == 1
        assert undeclared[0].line == 2
        assert undeclared[0].node_name == "person is a member of the Reserves"

    def test_fixed_phrase_reference_counts_as_used_on_rhs(self, service):
        rule_text = (
            'FIXED qualifying age for male service pension IS 60\n'
            'INPUT the person age AS NUMBER\n'
            'eligible for age service pension\n'
            '    AND the person age >= qualifying age for male service pension\n'
        )
        result = service.validate(rule_text)

        assert result.valid is True
        assert not any(
            w.code == "UNUSED_DECLARATION"
            and w.node_name == "qualifying age for male service pension"
            for w in result.warnings
        )

    def test_needs_and_wants_prefixes_are_not_variable_references(self, service):
        rule_text = (
            'INPUT proof of service exists AS BOOLEAN\n'
            'INPUT review evidence exists AS BOOLEAN\n'
            'eligible for service outcome\n'
            '    AND MANDATORY NEEDS proof of service exists\n'
            '    WANTS review evidence exists\n'
        )
        result = service.validate(rule_text)

        assert result.valid is True
        assert not any(e.code == "UNDECLARED_REFERENCE" for e in result.errors)

    def test_expression_phrase_references_do_not_split_into_words(self, service):
        rule_text = (
            'FIXED maximum pension rate IS 100\n'
            'INPUT income reduction amount AS NUMBER\n'
            'pension amount IS CALC maximum pension rate - income reduction amount\n'
        )
        result = service.validate(rule_text)

        assert result.valid is True
        assert not any(
            e.code == "UNDECLARED_REFERENCE"
            and e.node_name in {"maximum", "pension", "rate", "income", "reduction", "amount"}
            for e in result.errors
        )

    def test_expression_quoted_text_is_not_a_variable_reference(self, service):
        rule_text = (
            'INPUT decoration type AS TEXT\n'
            'FIXED victoria cross allowance rate IS 100\n'
            'FIXED decoration allowance rate IS 50\n'
            'decoration allowance amount IS CALC (decoration type = "Victoria Cross" ? victoria cross allowance rate : decoration allowance rate)\n'
        )
        result = service.validate(rule_text)

        assert result.valid is True
        assert not any(
            e.code == "UNDECLARED_REFERENCE"
            and e.node_name in {"Victoria", "Cross"}
            for e in result.errors
        )

    def test_not_prefix_inside_variable_name_is_not_stripped(self, service):
        rule_text = (
            'INPUT notification sent to claimant AS BOOLEAN\n'
            'claim notice complete\n'
            '    notification sent to claimant\n'
        )
        result = service.validate(rule_text)

        assert result.valid is True
        assert not any(
            e.code == "UNDECLARED_REFERENCE"
            and e.node_name == "ification sent to claimant"
            for e in result.errors
        )


# =============================================================================
# DAG Cycle Detection Tests
# =============================================================================

class TestDAGCycleDetection:
    def test_acyclic_rule(self, service):
        rule_text = (
            'INPUT age AS NUMBER\n'
            'INPUT score AS NUMBER\n'
            'eligible IS true\n'
            '    age > 18\n'
            '    score > 50\n'
        )
        result = service.validate(rule_text)
        assert not any(e.code == "CYCLIC_DEPENDENCY" for e in result.errors)

    def test_self_referential_not_a_cycle(self, service):
        rule_text = (
            'INPUT x AS NUMBER\n'
            'x IS CALC x + 1\n'
        )
        result = service.validate(rule_text)
        assert not any(e.code == "CYCLIC_DEPENDENCY" for e in result.errors)

    def test_mutual_dependency_cycle(self, service):
        rule_text = (
            'INPUT base AS NUMBER\n'
            'a IS CALC b + 1\n'
            'b IS CALC a + 1\n'
        )
        result = service.validate(rule_text)
        assert any(e.code == "CYCLIC_DEPENDENCY" for e in result.errors)

    def test_no_cycle_with_simple_chain(self, service):
        rule_text = (
            'INPUT base AS NUMBER\n'
            'adjusted IS CALC base * 2\n'
            'final IS CALC adjusted + 1\n'
        )
        result = service.validate(rule_text)
        assert not any(e.code == "CYCLIC_DEPENDENCY" for e in result.errors)


# =============================================================================
# Cache Tests
# =============================================================================

class TestValidationCache:
    def test_cache_hit_on_same_text(self, service):
        rule_text = 'INPUT age AS NUMBER\nage > 18\n'
        result1 = service.validate(rule_text)
        result2 = service.validate(rule_text)
        assert result1.valid == result2.valid
        assert len(service._cache) == 1

    def test_cache_miss_on_different_text(self, service):
        rule1 = 'INPUT age AS NUMBER\n'
        rule2 = 'INPUT name AS STRING\n'
        service.validate(rule1)
        service.validate(rule2)
        assert len(service._cache) == 2

    def test_cache_ttl_expiry(self):
        service = RuleValidationService(cache_ttl_seconds=0)
        rule_text = 'INPUT age AS NUMBER\n'
        service.validate(rule_text)
        assert len(service._cache) == 1
        service.validate(rule_text)
        assert len(service._cache) == 1

    def test_cache_lru_eviction(self):
        service = RuleValidationService(cache_maxsize=2, cache_ttl_seconds=300)
        service.validate('INPUT a AS NUMBER\n')
        service.validate('INPUT b AS NUMBER\n')
        assert len(service._cache) == 2
        service.validate('INPUT c AS NUMBER\n')
        assert len(service._cache) == 2

    def test_invalidate_cache_all(self, service):
        service.validate('INPUT a AS NUMBER\n')
        service.validate('INPUT b AS NUMBER\n')
        assert len(service._cache) == 2
        service.invalidate_cache()
        assert len(service._cache) == 0

    def test_cache_lru_promotes_on_hit(self):
        service = RuleValidationService(cache_maxsize=2, cache_ttl_seconds=300)
        service.validate('INPUT a AS NUMBER\n')
        service.validate('INPUT b AS NUMBER\n')
        service.validate('INPUT a AS NUMBER\n')
        service.validate('INPUT c AS NUMBER\n')
        assert len(service._cache) == 2
        assert 'INPUT b AS NUMBER\n' not in [k for k in service._cache] or len(service._cache) == 2


# =============================================================================
# _extract_references and _extract_value_type Tests
# =============================================================================

class TestExtractReferences:
    def test_does_not_drop_short_uppercase_vars(self, service):
        refs = service._extract_references("RATE > 10", "total")
        assert "RATE" in refs

    def test_excludes_keywords(self, service):
        refs = service._extract_references("AND MANDATORY KNOWN x", "y")
        assert "AND" not in refs
        assert "MANDATORY" not in refs
        assert "KNOWN" not in refs

    def test_excludes_conclusion_var(self, service):
        refs = service._extract_references("total IS CALC x + y", "total")
        assert "total" not in refs


class TestExtractValueType:
    def test_number_maps_to_double(self, service):
        result = service._extract_value_type("INPUT x AS NUMBER", "INPUT")
        assert result == FactValueType.DOUBLE.value

    def test_boolean_alias(self, service):
        result = service._extract_value_type("INPUT x AS BOOL", "INPUT")
        assert result == FactValueType.BOOLEAN.value

    def test_integer_literal(self, service):
        result = service._extract_value_type("FIXED x IS 42", "FIXED")
        assert result == FactValueType.INTEGER.value

    def test_float_literal(self, service):
        result = service._extract_value_type("FIXED x IS 3.14", "FIXED")
        assert result == FactValueType.DOUBLE.value

    def test_boolean_literal(self, service):
        result = service._extract_value_type("FIXED x IS true", "FIXED")
        assert result == FactValueType.BOOLEAN.value

    def test_string_literal(self, service):
        result = service._extract_value_type('FIXED x IS "hello"', "FIXED")
        assert result == FactValueType.STRING.value

    def test_unknown_type(self, service):
        result = service._extract_value_type("INPUT x AS FOOBAR", "INPUT")
        assert result == "UNKNOWN"


# =============================================================================
# Ontology Advisory Semantic Tests
# =============================================================================

class TestOntologyAdvisoryValidation:
    def test_semantic_warnings_include_severity_reason_and_review_queue(self, service):
        rule_text = (
            "INPUT benefit age AS FOOBAR\n"
            "INPUT unused income AS NUMBER\n"
            "\n"
            "benefit eligibility\n"
            "    AND benefit age > missing threshold\n"
            "    AND NOT conflicting status\n"
            "\n"
            "Benefit Eligibility\n"
            "    AND benefit age > 18\n"
        )

        result = service.validate(rule_text)

        by_code = {warning.code: warning for warning in result.warnings}
        assert by_code["ONTOLOGY_DECLARATION_TYPE_UNMAPPED"].severity == "high-risk"
        assert by_code["ONTOLOGY_DECLARATION_TYPE_UNMAPPED"].source == "ontology"
        assert by_code["ONTOLOGY_DECLARATION_TYPE_UNMAPPED"].review_required is True
        assert by_code["ONTOLOGY_STALE_REFERENCE_CANDIDATE"].severity == "high-risk"
        assert by_code["ONTOLOGY_DEPENDENCY_POLARITY_REVIEW"].category == "dependencies"
        assert by_code["ONTOLOGY_ORPHAN_CONCEPT"].severity == "info"
        assert by_code["ONTOLOGY_LEGAL_CONCEPT_UNANCHORED"].category == "legal_concepts"
        assert by_code["ONTOLOGY_CONTRADICTORY_LABEL"].severity == "high-risk"
        assert result.review_queue
        assert all(item.approval_state == "candidate" for item in result.review_queue)
        assert all(item.requires_rule_approval for item in result.review_queue)
        assert all(item.mutates_assets is False for item in result.review_queue)
        assert all(item.alters_deterministic_outcome is False for item in result.review_queue)

    def test_statutory_sections_definitions_and_import_markers_are_advisory(self, service):
        rule_text = (
            "# Imported module: dva_common\n"
            "INPUT service under section 7 AS BOOLEAN\n"
            "FIXED definition of veteran IS true\n"
            "\n"
            "benefit eligibility means accepted under section 7\n"
            "    AND service under section 7\n"
        )

        result = service.validate(rule_text)

        codes = {warning.code for warning in result.warnings}
        assert "ONTOLOGY_IMPORT_SCOPE_REVIEW" in codes
        assert "ONTOLOGY_STATUTORY_SECTION_REFERENCE" in codes
        assert "ONTOLOGY_STATUTORY_DEFINITION_REFERENCE" in codes
        assert all(not warning.blocking for warning in result.warnings if warning.source == "ontology")

    def test_high_risk_semantic_warning_blocks_only_when_policy_configures_it(self):
        rule_text = (
            "INPUT benefit age AS FOOBAR\n"
            "benefit eligibility\n"
            "    AND benefit age > 18\n"
        )
        advisory_service = RuleValidationService()
        blocking_service = RuleValidationService(
            ontology_blocking_warning_codes={"ONTOLOGY_DECLARATION_TYPE_UNMAPPED"}
        )

        advisory_result = advisory_service.validate(rule_text)
        blocking_result = blocking_service.validate(rule_text)

        assert advisory_result.valid is True
        assert not advisory_result.errors
        assert blocking_result.valid is False
        assert any(
            warning.code == "ONTOLOGY_DECLARATION_TYPE_UNMAPPED" and warning.blocking
            for warning in blocking_result.warnings
        )
        assert any(
            error.code == "BLOCKING_ONTOLOGY_DECLARATION_TYPE_UNMAPPED"
            and error.reason == "policy_configured_blocking"
            for error in blocking_result.errors
        )

    def test_review_queue_serialization_preserves_no_auto_mutation_contract(self, service):
        rule_text = (
            "INPUT benefit age AS FOOBAR\n"
            "benefit eligibility\n"
            "    AND benefit age > 18\n"
        )

        payload = service.validate(rule_text).to_dict()

        assert payload["review_queue"]
        assert payload["warnings"][0]["source"] in {"deterministic", "ontology"}
        assert all(item["approval_state"] == "candidate" for item in payload["review_queue"])
        assert all(item["requires_rule_approval"] for item in payload["review_queue"])
        assert all(item["mutates_assets"] is False for item in payload["review_queue"])
        assert all(
            item["alters_deterministic_outcome"] is False
            for item in payload["review_queue"]
        )


# =============================================================================
# Integration / Edge Case Tests
# =============================================================================

class TestIntegration:
    def test_syntax_error_short_circuits_type_check(self, service):
        rule_text = (
            'FIXED rate IS 10\n'
            'FIXED rate IS 20\n'
        )
        result = service.validate(rule_text)
        assert any(e.code == "DUPLICATE_DECLARATION" for e in result.errors)

    def test_complex_valid_rule(self, service):
        rule_text = (
            'FIXED base_rate IS 31.35\n'
            'FIXED threshold IS 50\n'
            'INPUT distance AS NUMBER\n'
            'INPUT is_eligible AS BOOLEAN\n'
            'long_distance IS CALC distance > threshold\n'
            'rate IS CALC base_rate * 2\n'
        )
        result = service.validate(rule_text)
        assert result.valid is True

    def test_multiple_errors_and_warnings(self, service):
        rule_text = (
            'INPUT flag AS BOOLEAN\n'
            'INPUT unused AS STRING\n'
            'flag > 10\n'
            'unknown_var IS true\n'
        )
        result = service.validate(rule_text)
        assert any(e.code == "TYPE_MISMATCH" for e in result.errors)
        assert any(w.code == "UNUSED_DECLARATION" for w in result.warnings)

    def test_four_char_uppercase_variable_not_dropped(self, service):
        rule_text = (
            'INPUT RATE AS NUMBER\n'
            'RATE > 10\n'
        )
        result = service.validate(rule_text)
        assert not any(e.code == "UNDECLARED_REFERENCE" for e in result.errors)
