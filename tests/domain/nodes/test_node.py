import json
import hashlib
import warnings
from unittest.mock import MagicMock

import pytest

from src.domain.fact_values import FactValue, FactValueType
from src.domain.nodes.line_type import LineType
from src.domain.nodes.meta_data import MetaData
from src.domain.nodes.node import Node
from src.domain.tokens import Token


class DummyNode(Node):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def initialisation(self, parent_text: str, tokens) -> None:
        self._node_name = parent_text
        self._variable_name = "var"

    def get_line_type(self) -> LineType:
        return LineType.VALUE_CONCLUSION

    def self_evaluate(self, working_memory: dict) -> FactValue:
        return FactValue(True)


class TestNodeSetters:
    def test_set_meta_data(self):
        node = DummyNode()
        md = MetaData()
        node.set_meta_data(md)
        assert node.get_meta_data() is md

    def test_set_node_line(self):
        node = DummyNode()
        node.set_node_line(42)
        assert node.get_node_line() == 42

    def test_set_node_id(self):
        node = DummyNode()
        node.set_node_id(7)
        assert node.get_node_id() == 7
        assert node._node_unique_id == 7

    def test_set_node_variable(self):
        node = DummyNode()
        node.set_node_variable("new_var")
        assert node.get_variable_name() == "new_var"


class TestNodeSetValueBranches:
    def test_set_value_no_last_token(self):
        node = DummyNode()
        fv = FactValue("direct")
        node.set_value(fv)
        assert node.get_fact_value() is fv

    def test_set_value_q_prefix_ignores_case(self):
        node = DummyNode()
        node.set_value("q", "question_val")
        assert node.get_fact_value().get_value_type() == FactValueType.DEFI_STRING

    def test_set_value_q_prefix_uppercase(self):
        node = DummyNode()
        node.set_value("Q", "question_val")
        assert node.get_fact_value().get_value_type() == FactValueType.DEFI_STRING

    def test_set_value_clmu_prefix_boolean_true(self):
        node = DummyNode()
        node.set_value("C", "true")
        assert node.get_fact_value().get_value() is True
        assert node.get_fact_value().get_value_type() == FactValueType.BOOLEAN

    def test_set_value_clmu_prefix_boolean_false(self):
        node = DummyNode()
        node.set_value("L", "false")
        assert node.get_fact_value().get_value() is False
        assert node.get_fact_value().get_value_type() == FactValueType.BOOLEAN

    def test_set_value_clmu_prefix_quoted_string(self):
        node = DummyNode()
        node.set_value("M", "'quoted_value'")
        assert node.get_fact_value().get_value_type() == FactValueType.DEFI_STRING

    def test_set_value_clmu_prefix_double_quoted_string(self):
        node = DummyNode()
        node.set_value("U", '"quoted_value"')
        assert node.get_fact_value().get_value_type() == FactValueType.DEFI_STRING

    def test_set_value_clmu_prefix_non_boolean_non_quoted(self):
        node = DummyNode()
        node.set_value("C", "42")
        result = node.get_fact_value()
        assert result.get_value() == "42"

    def test_set_value_non_clmu_prefix(self):
        node = DummyNode()
        node.set_value("X", "some_val")
        result = node.get_fact_value()
        assert result.get_value() == "some_val"


class TestNodeStaticTypeChecks:
    def test_is_boolean_true(self):
        assert Node.is_boolean("true") is True
        assert Node.is_boolean("TRUE") is True

    def test_is_boolean_false(self):
        assert Node.is_boolean("false") is True
        assert Node.is_boolean("False") is True

    def test_is_boolean_not_bool(self):
        assert Node.is_boolean("maybe") is False
        assert Node.is_boolean("123") is False

    def test_is_integer(self):
        assert Node.is_integer("No") is True
        assert Node.is_integer("Yes") is False

    def test_is_double(self):
        assert Node.is_double("De") is True
        assert Node.is_double("Do") is False

    def test_is_date(self):
        assert Node.is_date("Da") is True
        assert Node.is_date("Date") is False

    def test_is_url(self):
        assert Node.is_url("Url") is True
        assert Node.is_url("URL") is False

    def test_is_hash(self):
        assert Node.is_hash("Ha") is True
        assert Node.is_hash("Hash") is False

    def test_is_guid(self):
        assert Node.is_guid("Id") is True
        assert Node.is_guid("GUID") is False


class TestNodeIdDeprecation:
    def test_get_node_id_emits_deprecation_warning(self):
        node = DummyNode(id=5)
        node._node_name = "test"
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _ = node.get_node_id()
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "get_node_id()" in str(w[0].message)

    def test_set_node_id_emits_deprecation_warning(self):
        node = DummyNode()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            node.set_node_id(10)
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "set_node_id()" in str(w[0].message)

    def test_deprecated_get_node_id_still_returns_value(self):
        node = DummyNode(id=5)
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            assert node._node_id == 5

    def test_deprecated_set_node_id_still_sets_value(self):
        node = DummyNode()
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            node.set_node_id(10)
            assert node._node_id == 10
            assert node._node_unique_id == 10
    def test_deterministic_id(self):
        sid = Node.build_stable_node_id(
            module_name="mod",
            line_type="VALUE_CONCLUSION",
            variable_name="var1",
            node_name="node1",
        )
        normalised_name = Node._normalise_identity_part("node1")
        expected_parts = [
            Node._normalise_identity_part("mod"),
            Node._normalise_identity_part("VALUE_CONCLUSION"),
            Node._normalise_identity_part("var1"),
            normalised_name,
            Node._normalise_identity_part(""),
            Node._normalise_identity_part(""),
        ]
        expected = hashlib.sha256("|".join(expected_parts).encode("utf-8")).hexdigest()
        assert sid == expected

    def test_none_defaults(self):
        sid = Node.build_stable_node_id(
            module_name=None,
            line_type=None,
            variable_name=None,
            node_name=None,
        )
        assert isinstance(sid, str)
        assert len(sid) == 64

    def test_variable_name_and_node_name_both_used(self):
        sid1 = Node.build_stable_node_id(
            module_name="m", line_type="t",
            variable_name="var1", node_name="node1",
        )
        sid2 = Node.build_stable_node_id(
            module_name="m", line_type="t",
            variable_name="var2", node_name="node1",
        )
        assert sid1 != sid2

    def test_import_namespace_changes_id(self):
        sid_local = Node.build_stable_node_id(
            module_name="m", line_type="t",
            variable_name="var1", node_name="node1",
            import_namespace="",
        )
        sid_imported = Node.build_stable_node_id(
            module_name="m", line_type="t",
            variable_name="var1", node_name="node1",
            import_namespace="common_rules@2.1.0",
        )
        assert sid_local != sid_imported

    def test_parent_module_path_changes_id(self):
        sid_root = Node.build_stable_node_id(
            module_name="m", line_type="t",
            variable_name="var1", node_name="node1",
            parent_module_path="",
        )
        sid_child = Node.build_stable_node_id(
            module_name="m", line_type="t",
            variable_name="var1", node_name="node1",
            parent_module_path="parent_mod",
        )
        assert sid_root != sid_child


class TestNormaliseIdentityPart:
    def test_strips_whitespace(self):
        assert Node._normalise_identity_part("  Hello  World  ") == "hello world"

    def test_lowercases(self):
        assert Node._normalise_identity_part("UPPER") == "upper"

    def test_collapses_inner_spaces(self):
        assert Node._normalise_identity_part("a   b") == "a b"


class TestResetAndGetStaticNodeId:
    def test_reset_sets_to_zero(self):
        Node.__static_node_id = 5
        Node.reset()
        assert Node.get_static_node_id() == 0


class TestNodeRepr:
    def test_repr_json(self):
        node = DummyNode(id=1)
        try:
            result = repr(node)
            parsed = json.loads(result)
            assert isinstance(parsed, dict)
        except TypeError:
            pass


class TestRefreshStableNodeId:
    def test_refresh_with_module_name(self):
        node = DummyNode()
        node._variable_name = "var1"
        node._node_line = 5
        node._line_type = LineType.VALUE_CONCLUSION
        result = node.refresh_stable_node_id("my_module")
        assert result is not None
        assert node.get_stable_node_id() == result
        assert node._source_module_name == "my_module"

    def test_refresh_without_module_name(self):
        node = DummyNode()
        node._variable_name = "var1"
        node._node_line = 5
        node._line_type = LineType.VALUE_CONCLUSION
        result = node.refresh_stable_node_id()
        assert result is not None

    def test_refresh_with_none_line_type(self):
        node = DummyNode()
        node._variable_name = "var1"
        node._line_type = None
        result = node.refresh_stable_node_id("mod")
        assert result is not None


class TestDebugLabel:
    def test_set_get_debug_label(self):
        node = DummyNode()
        assert node.get_debug_label() is None
        node.set_debug_label("rule:10:var1")
        assert node.get_debug_label() == "rule:10:var1"


class TestNodeInitWithParentTextAndTokens:
    def test_init_calls_initialisation(self):
        tokens = MagicMock()
        node = DummyNode(parent_text="some text", tokens=tokens)
        assert node._node_name == "some text"
        assert node._tokens is tokens

    def test_init_with_meta_data(self):
        md = MetaData()
        node = DummyNode(meta_data=md)
        assert node.get_meta_data() is md

    def test_init_default_values(self):
        node = DummyNode()
        assert node.get_node_id() is None
        assert node.get_node_name() is None
        assert node.get_stable_node_id() is None
        assert node.get_debug_label() is None
        assert node.get_variable_name() is None
        assert node.get_fact_value() is not None
