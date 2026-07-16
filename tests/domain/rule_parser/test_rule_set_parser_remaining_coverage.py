from unittest.mock import MagicMock

import pytest

import src.domain.rule_parser.rule_set_parser as parser_module
from src.domain.fact_values import FactValueType
from src.domain.graph.dependency_type import DependencyType
from src.domain.nodes import node_id_utils
from src.domain.rule_parser.rule_set_parser import RuleSetParser


class _ConcreteRuleSetParser(RuleSetParser):
    pass


@pytest.fixture(autouse=True)
def _reset_node_ids():
    node_id_utils.reset_parse_context()
    yield
    node_id_utils.reset_parse_context()


@pytest.fixture
def parser():
    value = _ConcreteRuleSetParser()
    value.create()
    return value


def test_handle_parent_reports_metadata_warning(parser, monkeypatch):
    tokens = MagicMock()
    tokens.get_tokens_list.return_value = ["FIXED"]
    metadata_node = MagicMock()
    metadata_node.get_fact_value.return_value.get_value.return_value = "WARNING"
    warning = MagicMock()

    monkeypatch.setattr(parser, "_handle_type_parent", MagicMock(return_value=False))
    monkeypatch.setattr(parser_module.Tokenizer, "get_tokens", MagicMock(return_value=tokens))
    monkeypatch.setattr(
        parser_module,
        "MetadataLine",
        MagicMock(return_value=metadata_node),
    )
    monkeypatch.setattr(parser, "handle_warning", warning)
    monkeypatch.setattr(parser, "_parent_node_data_set", MagicMock())
    monkeypatch.setattr(parser, "_register_collection_input", MagicMock())

    parser.handle_parent("FIXED broken AS UNSUPPORTED", 4, MagicMock())

    warning.assert_called_once_with("FIXED broken AS UNSUPPORTED")


def test_handle_parent_reports_warning_matcher(parser, monkeypatch):
    tokens = MagicMock()
    tokens.get_tokens_list.return_value = ["unmatched"]
    tokens.get_tokens_string.return_value = "warning-token-stream"
    matcher = MagicMock()
    matcher.match.side_effect = [None, None, object()]
    warning = MagicMock()

    monkeypatch.setattr(parser, "_handle_type_parent", MagicMock(return_value=False))
    monkeypatch.setattr(parser_module.Tokenizer, "get_tokens", MagicMock(return_value=tokens))
    monkeypatch.setattr(parser_module.re, "compile", MagicMock(return_value=matcher))
    monkeypatch.setattr(parser, "handle_warning", warning)
    monkeypatch.setattr(parser, "_parent_node_data_set", MagicMock())

    parser.handle_parent("unmatched warning", 5, MagicMock())

    warning.assert_called_once_with("unmatched warning")


def test_dependency_graph_skips_nameless_and_registers_external_id_nodes(
    parser,
    monkeypatch,
):
    nameless = MagicMock()
    nameless.get_node_name.return_value = ""
    external = MagicMock()
    external.get_node_name.return_value = "external-node"
    external.get_stable_node_id.return_value = None
    external._node_id = "external-id"
    nodes = {"nameless": nameless, "external": external}
    node_set = MagicMock()
    node_set.get_node_dictionary.return_value = nodes
    parser.set_node_set(node_set)
    monkeypatch.setattr(parser, "_handling_virtual_node", MagicMock(return_value=nodes))

    builder = MagicMock()
    builder.graph = MagicMock()
    monkeypatch.setattr(
        parser_module,
        "GraphDependencyBuilder",
        MagicMock(return_value=builder),
    )

    graph = parser.create_dependency_graph()

    assert graph is builder.graph
    builder.graph.register_node.assert_called_once_with(
        "external-node",
        {"module": "__unknown_module__"},
    )
    node_set.set_graph.assert_called_once_with(builder.graph)


def test_declaration_children_cover_invalid_fields_item_types_and_warning(parser, monkeypatch):
    warning = MagicMock()
    monkeypatch.setattr(parser, "handle_warning", warning)

    assert parser._handle_declaration_child("TYPE Person", "not a field") is True
    assert parser._handle_declaration_child(
        "INPUT people AS COLLECTION OF Person",
        "ITEM TYPE Employee",
    ) is True
    assert parser.get_node_set().get_collection_dictionary()["people"]["item_type"] == (
        "Employee"
    )
    assert parser._handle_declaration_child(
        "INPUT people AS COLLECTION OF Person",
        "not a collection declaration",
    ) is True

    assert warning.call_args_list == [
        (("not a field",),),
        (("not a collection declaration",),),
    ]


def test_declaration_parsers_and_field_types_cover_fallbacks(parser):
    assert parser._parse_field_declaration("not a field") is None
    assert parser._parse_item_type("ITEM TYPE Person") == "Person"
    assert parser._parse_item_type("not an item type") is None

    expected = {
        "INTEGER": FactValueType.INTEGER,
        "URL": FactValueType.URL,
        "HASH": FactValueType.HASH,
        "GUID": FactValueType.GUID,
        "CUSTOM": FactValueType.UNKNOWN,
    }
    assert {
        field_type: parser._field_type_from_text(field_type)
        for field_type in expected
    } == expected


def test_statement_child_reports_warning_kind(parser, monkeypatch):
    tokens = MagicMock()
    tokens.get_tokens_string.return_value = "warning-token-stream"
    matches = iter([None, None, None, None, object()])
    warning = MagicMock()

    monkeypatch.setattr(parser_module.Tokenizer, "get_tokens", MagicMock(return_value=tokens))
    monkeypatch.setattr(
        parser_module.re,
        "match",
        MagicMock(side_effect=lambda *_args, **_kwargs: next(matches)),
    )
    monkeypatch.setattr(parser, "handle_warning", warning)

    parser._handle_statement_child("parent", "warning child", 0, 8)

    warning.assert_called_once_with("warning child")


def test_statement_child_warns_when_existing_child_has_no_parent(parser, monkeypatch):
    child = MagicMock()
    node_set = MagicMock()
    node_set.get_next_node_id.return_value = 2
    node_set.get_node_dictionary.return_value = {"child": child}
    parser.set_node_set(node_set)
    warning = MagicMock()

    monkeypatch.setattr(parser_module.Tokenizer, "get_tokens", MagicMock())
    monkeypatch.setattr(parser, "handle_warning", warning)

    parser._handle_statement_child("missing-parent", "child", DependencyType.get_and(), 9)

    warning.assert_called_once_with("missing-parent")


def test_dependency_matrix_size_reads_parent_and_child_runtime_ids(parser):
    parser.get_node_set().set_node_dictionary({})
    parent = MagicMock()
    parent._node_id = 4
    child = MagicMock()
    child._node_id = 7
    dependency = MagicMock()
    dependency.get_parent_node.return_value = parent
    dependency.get_child_node.return_value = child

    assert parser._get_dependency_matrix_size([dependency]) == 8


def test_dependency_modifiers_include_optional_and_possible_bits(parser):
    optional = parser._handle_not_known_man_opt_pos(
        "AND OPTIONALLY",
        DependencyType.get_and(),
    )
    possible = parser._handle_not_known_man_opt_pos(
        "OR POSSIBLY",
        DependencyType.get_or(),
    )

    assert optional & DependencyType.get_optional()
    assert possible & DependencyType.get_possible()
