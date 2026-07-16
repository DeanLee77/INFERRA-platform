"""Focused branch coverage for :mod:`rule_validation_service`."""

from src.services.declaration_validator import (
    DeclarationFinding,
    DeclarationValidationResult,
)
from src.services.rule_validation_service import (
    RuleValidationService,
    ValidationError,
    ValidationResult,
    ValidationWarning,
)


def test_validation_value_object_representations() -> None:
    error = ValidationError("BROKEN", "bad rule", line=3)
    warning = ValidationWarning("REVIEW", "check rule", line=4)
    result = ValidationResult(valid=False, errors=(error,), warnings=(warning,))

    assert repr(error) == "ValidationError(code='BROKEN', message='bad rule', line=3)"
    assert repr(warning) == "ValidationWarning(code='REVIEW', message='check rule', line=4)"
    assert repr(result) == "ValidationResult(valid=False, errors=1, warnings=1)"


def test_collection_field_and_item_type_metadata_are_parsed() -> None:
    service = RuleValidationService()
    errors = []
    warnings = []

    parsed = service._check_syntax(
        "\n".join(
            (
                "INPUT claims AS COLLECTION OF Claim",
                "  FIELD status AS LIST OF claim statuses",
                "  ITEM TYPE ReplacementClaim",
            )
        ),
        errors,
        warnings,
    )

    assert errors == []
    assert parsed["collection_fields"]["claims"]["status"] == "LIST"
    assert parsed["declaration_references"] == [
        {"name": "claim statuses", "line": 2}
    ]
    assert parsed["collections"]["claims"]["item_type"] == "ReplacementClaim"
    assert service._collect_declared_field_names(parsed) == {"status"}


def test_parser_ignores_standalone_declaration_metadata() -> None:
    service = RuleValidationService()
    rules = []
    errors = []

    service._parse_rule_line(
        "FIELD status AS TEXT",
        line_number=1,
        declarations={},
        rules=rules,
        errors=errors,
    )

    assert rules == []
    assert errors == []


def test_reference_helpers_cover_empty_and_non_conclusion_paths(monkeypatch) -> None:
    service = RuleValidationService()
    monkeypatch.setattr(service, "_is_rule_conclusion", lambda _rule: False)

    entries = service._collect_reference_entries(
        [
            {
                "line": 1,
                "kind": "VALUE_CONCLUSION",
                "raw": "  IS ",
                "variable_name": " ",
            }
        ],
        declarations={},
        rule_conclusion_names=set(),
    )

    assert entries == []
    helper_service = RuleValidationService()
    assert helper_service._is_rule_conclusion({"kind": "LIST_MEMBERSHIP"}) is False
    assert helper_service._find_known_phrase_references("claim", ("", "claim")) == [
        "claim"
    ]
    assert helper_service._comparison_rhs("claim = threshold", "") is None
    assert helper_service._comparison_rhs("claim = threshold", ">") is None
    assert helper_service._looks_like_variable_reference("   ") is False
    assert helper_service._looks_like_variable_reference("AND") is False
    assert helper_service._value_conclusion_rhs_references("", (), "result") == []
    assert helper_service._value_conclusion_rhs_references(
        "other result", (), "result"
    ) == ["other result"]


def test_rule_with_children_is_a_conclusion() -> None:
    service = RuleValidationService()

    assert service._is_rule_conclusion(
        {
            "kind": "PLAIN_STATEMENT",
            "is_indented": True,
            "has_children": True,
        }
    ) is True


def test_empty_and_duplicate_ontology_labels_are_ignored() -> None:
    service = RuleValidationService()
    label_index = {}
    warnings = []
    review_queue = []
    emitted = set()

    service._index_ontology_label(label_index, "   ", "declaration", 1)
    assert label_index == {}

    warning_args = {
        "code": "ONTOLOGY_DUPLICATE_LABEL",
        "message": "duplicate",
        "severity": "warning",
        "category": "duplicates",
        "target": "claim",
        "line": 2,
        "node_name": "claim",
    }
    service._add_ontology_warning(
        warnings,
        review_queue,
        emitted,
        **warning_args,
    )
    service._add_ontology_warning(
        warnings,
        review_queue,
        emitted,
        **warning_args,
    )

    assert len(warnings) == 1
    assert review_queue == []


def test_node_set_errors_are_adapted_without_duplicating_existing_errors() -> None:
    service = RuleValidationService()
    finding = DeclarationFinding(
        code="NULL_NODESET",
        message="parser returned no nodes",
        line=8,
        node_name="claim",
    )
    service._declaration_validator.validate_rule_text = lambda *_args: (
        DeclarationValidationResult(valid=False, errors=(finding,))
    )
    errors = []

    service._check_node_set_declarations("claim", "coverage", errors, [])
    service._check_node_set_declarations("claim", "coverage", errors, [])

    assert errors == [
        ValidationError(
            code="NULL_NODESET",
            message="parser returned no nodes",
            line=8,
            node_name="claim",
        )
    ]


def test_setting_an_existing_cache_entry_refreshes_it() -> None:
    service = RuleValidationService()
    first = ValidationResult(valid=True)
    replacement = ValidationResult(valid=False)

    service._set_cached("same-hash", first)
    service._set_cached("same-hash", replacement)

    assert service._cache["same-hash"][1] is replacement
