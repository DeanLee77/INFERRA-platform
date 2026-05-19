from src.domain.fact_values import FactValue
from src.domain.nodes.node_set import NodeSet
from src.domain.rule_parser.rule_set_parser import RuleSetParser
from src.domain.rule_parser.rule_set_reader import RuleSetReader
from src.domain.rule_parser.rule_set_scanner import RuleSetScanner
from src.services.declaration_validator import (
    DUPLICATE_DECLARATION,
    DeclarationFinding,
    DeclarationValidationResult,
    NULL_NODESET,
    SELF_REFERENTIAL_RULE,
    UNUSED_DECLARATION,
    DeclarationValidator,
    validate_declarations,
)


def _parse(rule_text: str, rule_name: str = "validator_rule") -> NodeSet:
    reader = RuleSetReader()
    reader.create()
    parser = RuleSetParser()
    parser.create()
    parser.set_source_name(rule_name)
    reader.set_file_with_text(rule_text)
    scanner = RuleSetScanner(reader, parser)
    scanner.scan_rule_set()
    scanner.establish_node_set()
    return parser.get_node_set()


def test_declaration_validator_accepts_graph_referenced_input():
    node_set = _parse(
        "INPUT age AS NUMBER\n"
        "eligible\n"
        "    age > 18\n"
    )

    result = DeclarationValidator().validate(node_set)

    assert result.valid is True
    assert not any(w.code == UNUSED_DECLARATION and w.node_name == "age" for w in result.warnings)


def test_declaration_validator_warns_for_unused_declaration():
    node_set = _parse(
        "INPUT age AS NUMBER\n"
        "eligible\n"
    )

    result = validate_declarations(node_set)

    assert result.valid is True
    assert any(w.code == UNUSED_DECLARATION and w.node_name == "age" for w in result.warnings)


def test_declaration_validator_detects_duplicate_input_fixed_declarations():
    node_set = NodeSet()
    node_set.set_input_dictionary({"flag": FactValue(True)})
    node_set.set_fact_dictionary({"FLAG": FactValue(False)})

    result = DeclarationValidator().validate(node_set)

    assert result.valid is False
    assert any(error.code == DUPLICATE_DECLARATION for error in result.errors)


def test_declaration_validator_detects_graph_self_reference():
    node_set = _parse(
        "INPUT flag AS BOOLEAN\n"
        "flag\n"
        "    flag\n"
    )

    result = DeclarationValidator().validate(node_set)

    assert result.valid is False
    assert any(error.code == SELF_REFERENTIAL_RULE for error in result.errors)


def test_declaration_result_to_dict_includes_optional_fields():
    finding = DeclarationFinding("CODE", "message", line=3, node_name="node")
    result = DeclarationValidationResult(valid=False, errors=(finding,), warnings=(finding,))

    assert result.to_dict() == {
        "valid": False,
        "errors": [{"code": "CODE", "message": "message", "line": 3, "node_name": "node"}],
        "warnings": [{"code": "CODE", "message": "message", "line": 3, "node_name": "node"}],
    }


def test_declaration_validator_rejects_null_nodeset():
    result = DeclarationValidator().validate(None)

    assert result.valid is False
    assert result.errors[0].code == NULL_NODESET


def test_validate_rule_text_skips_when_parser_raises():
    result = DeclarationValidator().validate_rule_text(None)

    assert result.valid is True


def test_declaration_validator_handles_missing_graph_child_and_safe_helpers():
    class Graph:
        def get_children_flat(self, _node_name):
            return ["missing child"]

    class NodeSetLike:
        def get_input_dictionary(self):
            return {}

        def get_fact_dictionary(self):
            return {}

        def get_node_dictionary(self):
            return {"parent": object()}

        def get_graph(self):
            return Graph()

    validator = DeclarationValidator()
    result = validator.validate(NodeSetLike())

    assert result.valid is False
    assert result.errors[0].node_name == "missing child"
    assert validator._safe_mapping(object(), "missing") == {}
    assert validator._line_number(None) is None
    assert validator._looks_like_reference(None) is False
    assert validator._looks_like_reference("") is False


def test_declaration_validator_handles_empty_reference_and_metadata_nodes():
    class MetaType:
        value = "INPUT"

    class MetaNode:
        def get_meta_type(self):
            return MetaType()

        def get_variable_name(self):
            return "declared"

        def get_node_line(self):
            return 7

    class NodeSetLike:
        def get_input_dictionary(self):
            return {}

        def get_fact_dictionary(self):
            return {}

        def get_node_dictionary(self):
            return {"meta": MetaNode(), "blank": object()}

        def get_graph(self):
            return None

    class BlankReferenceValidator(DeclarationValidator):
        def _extract_node_references(self, node):
            return (" ",) if type(node).__name__ == "object" else ()

    result = BlankReferenceValidator().validate(NodeSetLike())

    assert result.valid is True
    assert result.warnings[0].node_name == "declared"
