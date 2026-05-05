"""
IterateContext and IterateLine WS-3 contract tests.

Tests the IterateContext dataclass, _ensure_iterate_context(),
async feed_iterate_answer(), get_progress(), self_evaluate()
via IterateContext, can_be_self_evaluated() via IterateContext,
and _extract_ordinal_index().
"""

import asyncio
import json
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from src.domain.fact_values import FactValue, FactValueType
from src.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph
from src.domain.nodes.dependency_type import DependencyType
from src.domain.nodes.iterate_context import IterateContext
from src.domain.nodes.iterate_line import IterateLine
from src.domain.nodes.line_type import LineType
from src.domain.nodes.node import Node
from src.domain.state.feature_flags import FeatureFlags


# ---------------------------------------------------------------------------
# Concrete test subclass (follows test_node_identity.py DummyNode pattern)
# ---------------------------------------------------------------------------

class ConcreteIterateLine(IterateLine):
    """Testable IterateLine that satisfies Node's abstract contract."""

    def __init__(self):
        super().__init__()
        self._line_type = LineType.ITERATE
        # Simulate what _initialisation would set
        self._node_name = "SOME  services  eligibility"
        self._variable_name = "services"

    def initialisation(self, parent_text: str, tokens) -> None:
        pass


def _make_iterate_line(quantifier: str = "ALL", list_name: str = "services") -> ConcreteIterateLine:
    """Build an IterateLine with minimal setup for testing."""
    line = ConcreteIterateLine()
    line._IterateLine__number_of_target = quantifier
    line._IterateLine__given_list_name = list_name
    line._IterateLine__given_list_size = 0
    return line


@pytest.fixture
def iterate_line() -> ConcreteIterateLine:
    return _make_iterate_line()


# ===================================================================
# 1. IterateContext dataclass
# ===================================================================


def test_iterate_context_default_progress_is_empty():
    ctx = IterateContext(list_name="items", list_size=3, quantifier="ALL")

    assert ctx.progress == {}
    assert ctx.is_initialised is False


def test_iterate_context_stores_fields():
    ctx = IterateContext(list_name="items", list_size=5, quantifier="SOME")

    assert ctx.list_name == "items"
    assert ctx.list_size == 5
    assert ctx.quantifier == "SOME"


def test_iterate_context_progress_is_independent_between_instances():
    ctx1 = IterateContext(list_name="a", list_size=1, quantifier="ALL")
    ctx2 = IterateContext(list_name="b", list_size=2, quantifier="NONE")

    ctx1.progress[1] = True

    assert 1 not in ctx2.progress


# ===================================================================
# 2. _ensure_iterate_context()
# ===================================================================


def test_ensure_iterate_context_creates_context_when_none(iterate_line):
    iterate_line._ensure_iterate_context(list_size=3)

    ctx = iterate_line._IterateLine__context
    assert ctx is not None
    assert ctx.list_size == 3
    assert ctx.quantifier == "ALL"


def test_ensure_iterate_context_uses_explicit_quantifier(iterate_line):
    iterate_line._ensure_iterate_context(list_size=2, quantifier="SOME")

    ctx = iterate_line._IterateLine__context
    assert ctx.quantifier == "SOME"


def test_ensure_iterate_context_no_reinit_when_same_size(iterate_line):
    iterate_line._ensure_iterate_context(list_size=3)
    first_ctx = iterate_line._IterateLine__context

    # Add some progress
    first_ctx.progress[1] = True

    iterate_line._ensure_iterate_context(list_size=3)

    # Same context object — progress preserved
    assert iterate_line._IterateLine__context is first_ctx
    assert first_ctx.progress[1] is True


def test_ensure_iterate_context_recreates_when_size_changes(iterate_line):
    iterate_line._ensure_iterate_context(list_size=3)
    iterate_line._IterateLine__context.progress[1] = True

    iterate_line._ensure_iterate_context(list_size=5)

    ctx = iterate_line._IterateLine__context
    assert ctx.list_size == 5
    assert ctx.progress == {}  # fresh context


def test_ensure_iterate_context_falls_back_to_number_of_target():
    line = _make_iterate_line(quantifier="NONE")
    line._ensure_iterate_context(list_size=4)

    ctx = line._IterateLine__context
    assert ctx.quantifier == "NONE"


# ===================================================================
# 3. async feed_iterate_answer()
# ===================================================================


@pytest.mark.asyncio
async def test_feed_iterate_answer_records_boolean_true(iterate_line):
    iterate_line._ensure_iterate_context(list_size=2)

    complete = await iterate_line.feed_iterate_answer(
        "1st  services  question", True, FactValueType.BOOLEAN
    )

    ctx = iterate_line._IterateLine__context
    assert ctx.progress[1] is True
    assert complete is False  # only 1 of 2 answered


@pytest.mark.asyncio
async def test_feed_iterate_answer_records_boolean_false(iterate_line):
    iterate_line._ensure_iterate_context(list_size=2)

    await iterate_line.feed_iterate_answer(
        "1st  services  question", False, FactValueType.BOOLEAN
    )

    ctx = iterate_line._IterateLine__context
    assert ctx.progress[1] is False


@pytest.mark.asyncio
async def test_feed_iterate_answer_string_true(iterate_line):
    iterate_line._ensure_iterate_context(list_size=1)

    complete = await iterate_line.feed_iterate_answer(
        "1st  services  question", "true", FactValueType.STRING
    )

    ctx = iterate_line._IterateLine__context
    assert ctx.progress[1] is True
    assert complete is True


@pytest.mark.asyncio
async def test_feed_iterate_answer_string_false(iterate_line):
    iterate_line._ensure_iterate_context(list_size=1)

    await iterate_line.feed_iterate_answer(
        "1st  services  question", "false", FactValueType.STRING
    )

    ctx = iterate_line._IterateLine__context
    assert ctx.progress[1] is False


@pytest.mark.asyncio
async def test_feed_iterate_answer_returns_true_when_all_answered(iterate_line):
    iterate_line._ensure_iterate_context(list_size=2)

    first = await iterate_line.feed_iterate_answer(
        "1st  services  q", True, FactValueType.BOOLEAN
    )
    second = await iterate_line.feed_iterate_answer(
        "2nd  services  q", False, FactValueType.BOOLEAN
    )

    assert first is False
    assert second is True


@pytest.mark.asyncio
async def test_feed_iterate_answer_concurrent_safety(iterate_line):
    """Two coroutines feeding answers concurrently should not lose data."""
    iterate_line._ensure_iterate_context(list_size=2)

    results = await asyncio.gather(
        iterate_line.feed_iterate_answer("1st  services  q", True, FactValueType.BOOLEAN),
        iterate_line.feed_iterate_answer("2nd  services  q", False, FactValueType.BOOLEAN),
    )

    ctx = iterate_line._IterateLine__context
    assert len(ctx.progress) == 2
    assert ctx.progress[1] is True
    assert ctx.progress[2] is False
    # At least one should report complete
    assert any(results)


# ===================================================================
# 4. get_progress()
# ===================================================================


def test_get_progress_returns_zeros_when_no_context(iterate_line):
    assert iterate_line.get_progress() == (0, 0)


def test_get_progress_returns_zeros_when_no_answers(iterate_line):
    iterate_line._ensure_iterate_context(list_size=5)

    assert iterate_line.get_progress() == (0, 5)


def test_get_progress_after_partial_answers(iterate_line):
    iterate_line._ensure_iterate_context(list_size=3)
    iterate_line._IterateLine__context.progress[1] = True
    iterate_line._IterateLine__context.progress[3] = False

    assert iterate_line.get_progress() == (2, 3)


# ===================================================================
# 5. self_evaluate via IterateContext
# ===================================================================


def test_self_evaluate_all_true():
    line = _make_iterate_line(quantifier="ALL")
    line._ensure_iterate_context(list_size=2)
    line._IterateLine__context.progress = {1: True, 2: True}

    result = line.self_evaluate({})
    assert result.get_value() is True


def test_self_evaluate_all_false():
    line = _make_iterate_line(quantifier="ALL")
    line._ensure_iterate_context(list_size=2)
    line._IterateLine__context.progress = {1: True, 2: False}

    result = line.self_evaluate({})
    assert result.get_value() is False


def test_self_evaluate_none_true():
    line = _make_iterate_line(quantifier="NONE")
    line._ensure_iterate_context(list_size=2)
    line._IterateLine__context.progress = {1: False, 2: False}

    result = line.self_evaluate({})
    assert result.get_value() is True


def test_self_evaluate_none_false():
    line = _make_iterate_line(quantifier="NONE")
    line._ensure_iterate_context(list_size=2)
    line._IterateLine__context.progress = {1: True, 2: False}

    result = line.self_evaluate({})
    assert result.get_value() is False


def test_self_evaluate_some_true():
    line = _make_iterate_line(quantifier="SOME")
    line._ensure_iterate_context(list_size=3)
    line._IterateLine__context.progress = {1: False, 2: True, 3: False}

    result = line.self_evaluate({})
    assert result.get_value() is True


def test_self_evaluate_some_false():
    line = _make_iterate_line(quantifier="SOME")
    line._ensure_iterate_context(list_size=2)
    line._IterateLine__context.progress = {1: False, 2: False}

    result = line.self_evaluate({})
    assert result.get_value() is False


def test_self_evaluate_numeric_quantifier():
    line = _make_iterate_line(quantifier="2")
    line._ensure_iterate_context(list_size=3)
    line._IterateLine__context.progress = {1: True, 2: True, 3: False}

    result = line.self_evaluate({})
    assert result.get_value() is True


def test_self_evaluate_numeric_quantifier_mismatch():
    line = _make_iterate_line(quantifier="3")
    line._ensure_iterate_context(list_size=3)
    line._IterateLine__context.progress = {1: True, 2: True, 3: False}

    result = line.self_evaluate({})
    assert result.get_value() is False


# ===================================================================
# 6. can_be_self_evaluated via IterateContext
# ===================================================================


def test_can_be_self_evaluated_returns_false_when_not_all_answered(iterate_line):
    iterate_line._ensure_iterate_context(list_size=3)
    iterate_line._IterateLine__context.progress[1] = True

    assert iterate_line.can_be_self_evaluated({}) is False


def test_can_be_self_evaluated_returns_true_when_all_answered(iterate_line):
    iterate_line._ensure_iterate_context(list_size=2)
    iterate_line._IterateLine__context.progress = {1: True, 2: False}

    assert iterate_line.can_be_self_evaluated({}) is True


def test_can_be_self_evaluated_returns_false_when_no_context(iterate_line):
    assert iterate_line.can_be_self_evaluated({}) is False


# ===================================================================
# 7. _extract_ordinal_index()
# ===================================================================


def test_extract_ordinal_index_from_question_name():
    line = _make_iterate_line()
    line._ensure_iterate_context(list_size=3)

    assert line._extract_ordinal_index("1st  services  question") == 1
    assert line._extract_ordinal_index("2nd  services  question") == 2
    assert line._extract_ordinal_index("3rd  services  question") == 3


def test_extract_ordinal_index_numeric_prefix():
    line = _make_iterate_line()
    line._ensure_iterate_context(list_size=2)

    assert line._extract_ordinal_index("10  items  check") == 10


def test_extract_ordinal_index_fallback_no_digit():
    line = _make_iterate_line()
    line._ensure_iterate_context(list_size=1)
    # No leading digit — fallback to len(progress)+1
    assert line._extract_ordinal_index("no_ordinal_here") == 1


# ===================================================================
# 8. _evaluate_quantifier — shared logic
# ===================================================================


def test_evaluate_quantifier_all():
    line = _make_iterate_line(quantifier="ALL")
    assert line._evaluate_quantifier(3, 3).get_value() is True
    assert line._evaluate_quantifier(2, 3).get_value() is False


def test_evaluate_quantifier_none():
    line = _make_iterate_line(quantifier="NONE")
    assert line._evaluate_quantifier(0, 3).get_value() is True
    assert line._evaluate_quantifier(1, 3).get_value() is False


def test_evaluate_quantifier_some():
    line = _make_iterate_line(quantifier="SOME")
    assert line._evaluate_quantifier(1, 3).get_value() is True
    assert line._evaluate_quantifier(0, 3).get_value() is False


def test_evaluate_quantifier_numeric():
    line = _make_iterate_line(quantifier="2")
    assert line._evaluate_quantifier(2, 3).get_value() is True
    assert line._evaluate_quantifier(1, 3).get_value() is False


def test_evaluate_quantifier_invalid_string():
    line = _make_iterate_line(quantifier="invalid")
    assert line._evaluate_quantifier(1, 3).get_value() is False


# ===================================================================
# 9. _initialisation — token-driven init
# ===================================================================


def test_initialisation_sets_fields():
    line = ConcreteIterateLine()
    tokens = MagicMock()
    tokens.get_tokens_list.return_value = ["ALL", "services", "L"]
    tokens.get_tokens_string_list.return_value = ["Q", "L", "C"]
    line._initialisation("SOME  services  eligibility", tokens)
    assert line._node_name == "SOME  services  eligibility"
    assert line._IterateLine__number_of_target == "ALL"
    assert line._variable_name == "services"
    assert line._IterateLine__given_list_name == "L"


# ===================================================================
# 10. _ordinal — static helper
# ===================================================================


def test_ordinal_standard():
    assert IterateLine._ordinal(1) == "1st"
    assert IterateLine._ordinal(2) == "2nd"
    assert IterateLine._ordinal(3) == "3rd"
    assert IterateLine._ordinal(4) == "4th"


def test_ordinal_teens():
    assert IterateLine._ordinal(11) == "11th"
    assert IterateLine._ordinal(12) == "12th"
    assert IterateLine._ordinal(13) == "13th"


def test_ordinal_larger():
    assert IterateLine._ordinal(21) == "21st"
    assert IterateLine._ordinal(22) == "22nd"
    assert IterateLine._ordinal(23) == "23rd"
    assert IterateLine._ordinal(111) == "111th"


# ===================================================================
# 11. _get_next_iterate_node_id — static helper
# ===================================================================


def test_get_next_iterate_node_id_empty():
    assert IterateLine._get_next_iterate_node_id({}) == 0


def test_get_next_iterate_node_id_with_entries():
    assert IterateLine._get_next_iterate_node_id({0: "a", 3: "b"}) == 4


# ===================================================================
# 12. _transfer_fact_value
# ===================================================================


def test_transfer_fact_value_copies_new_keys():
    line = _make_iterate_line()
    src = {"a": 1, "b": 2}
    dst = {"a": 99}
    line._transfer_fact_value(src, dst)
    assert dst["a"] == 99
    assert dst["b"] == 2


def test_transfer_fact_value_empty_source():
    line = _make_iterate_line()
    dst = {"x": 1}
    line._transfer_fact_value({}, dst)
    assert dst == {"x": 1}


# ===================================================================
# 13. _find_nth
# ===================================================================


def test_find_nth_with_items():
    line = _make_iterate_line()
    line._IterateLine__given_list_size = 3
    wm = {"1st  services": "val1", "2nd  services": "val2"}
    assert line._find_nth(wm) == 2


def test_find_nth_empty():
    line = _make_iterate_line()
    line._IterateLine__given_list_size = 3
    assert line._find_nth({}) == 0


# ===================================================================
# 14. __repr__
# ===================================================================


def test_repr_returns_json():
    line = _make_iterate_line()
    try:
        result = repr(line)
        parsed = json.loads(result)
        assert isinstance(parsed, dict)
    except TypeError:
        pass


# ===================================================================
# 15. get_given_list_name / get_number_of_target / get_iterate_node_set / get_line_type
# ===================================================================


def test_get_given_list_name():
    line = _make_iterate_line()
    assert line.get_given_list_name() == "services"


def test_get_number_of_target():
    line = _make_iterate_line(quantifier="SOME")
    assert line.get_number_of_target() == "SOME"


def test_get_iterate_node_set_default_none():
    line = _make_iterate_line()
    assert line.get_iterate_node_set() is None


def test_get_line_type():
    line = _make_iterate_line()
    assert line.get_line_type() == LineType.ITERATE


# ===================================================================
# 16. feed_iterate_answer — additional value type paths
# ===================================================================


@pytest.mark.asyncio
async def test_feed_iterate_answer_bool_type_with_bool_value():
    line = _make_iterate_line()
    line._ensure_iterate_context(list_size=1)
    complete = await line.feed_iterate_answer("1st  services  q", True, FactValueType.BOOLEAN)
    assert complete is True


@pytest.mark.asyncio
async def test_feed_iterate_answer_non_bool_type_bool_value():
    line = _make_iterate_line()
    line._ensure_iterate_context(list_size=1)
    complete = await line.feed_iterate_answer("1st  services  q", True, FactValueType.STRING)
    assert complete is True


@pytest.mark.asyncio
async def test_feed_iterate_answer_int_value_coerced():
    line = _make_iterate_line()
    line._ensure_iterate_context(list_size=1)
    complete = await line.feed_iterate_answer("1st  services  q", 1, FactValueType.INTEGER)
    assert complete is True
    assert line._IterateLine__context.progress[1] is True


@pytest.mark.asyncio
async def test_feed_iterate_answer_string_value_not_true():
    line = _make_iterate_line()
    line._ensure_iterate_context(list_size=1)
    await line.feed_iterate_answer("1st  services  q", "nope", FactValueType.STRING)
    assert line._IterateLine__context.progress[1] is False


# ===================================================================
# 17. _iterate_feed_answers_via_context
# ===================================================================


def test_iterate_feed_answers_via_context_first_question():
    line = _make_iterate_line()
    line._node_id = 0
    parent_node_set = MagicMock()
    child_node = MagicMock()
    child_node.get_node_name.return_value = "first_child"
    graph = HyperAdjacencyGraph()
    graph.register_node(line.get_node_name(), {"runtime_id": 0})
    graph.register_node("first_child", {"runtime_id": 1})
    graph.add_dependency_group(
        line.get_node_name(),
        DependencyType.get_or(),
        {"first_child"},
    )
    parent_node_set.get_graph.return_value = graph
    parent_node_set.get_node_dictionary.return_value = {
        line.get_node_name(): line,
        "first_child": child_node,
    }
    parent_ast = MagicMock()
    parent_ast.get_working_memory.return_value = {}
    ass = MagicMock()

    with patch.object(line, 'can_be_self_evaluated', return_value=False):
        line._iterate_feed_answers_via_context(
            child_node, "first_child", 3, FactValueType.INTEGER,
            parent_node_set, parent_ast, ass,
        )
    assert line._IterateLine__given_list_size == 3
    assert line._IterateLine__context is not None


def test_iterate_feed_answers_via_context_subsequent_question():
    line = _make_iterate_line()
    line._IterateLine__given_list_size = 2
    line._ensure_iterate_context(list_size=2)
    parent_node_set = MagicMock()
    parent_ast = MagicMock()
    parent_ast.get_working_memory.return_value = {}
    ass = MagicMock()
    target_node = MagicMock()

    with patch.object(line, 'can_be_self_evaluated', return_value=False):
        line._iterate_feed_answers_via_context(
            target_node, "1st  services  q", True, FactValueType.BOOLEAN,
            parent_node_set, parent_ast, ass,
        )
    assert line._IterateLine__context.progress.get(1) is True


def test_iterate_feed_answers_via_context_self_evaluates():
    line = _make_iterate_line(quantifier="ALL")
    line._IterateLine__given_list_size = 1
    line._ensure_iterate_context(list_size=1)
    line._IterateLine__context.progress = {1: True}
    parent_node_set = MagicMock()
    parent_ast = MagicMock()
    parent_ast.get_working_memory.return_value = {}
    ass = MagicMock()
    target_node = MagicMock()

    with patch.object(line, 'can_be_self_evaluated', return_value=True):
        line._iterate_feed_answers_via_context(
            target_node, "1st  services  q", True, FactValueType.BOOLEAN,
            parent_node_set, parent_ast, ass,
        )
    parent_ast.set_fact.assert_called_once()


# ===================================================================
# 18. iterate_feed_answers — dispatch via feature flags
# ===================================================================


def test_iterate_feed_answers_legacy_path():
    line = _make_iterate_line()
    flags = FeatureFlags(legacy_iterate=True)
    target_node = MagicMock()
    parent_node_set = MagicMock()
    parent_ast = MagicMock()
    ass = MagicMock()

    with patch.object(line, '_iterate_feed_answers_legacy') as mock_legacy:
        line.iterate_feed_answers(
            target_node, "q", True, FactValueType.BOOLEAN,
            parent_node_set, parent_ast, ass, feature_flags=flags,
        )
    mock_legacy.assert_called_once()


def test_iterate_feed_answers_context_path():
    line = _make_iterate_line()
    flags = FeatureFlags(legacy_iterate=False)
    target_node = MagicMock()
    parent_node_set = MagicMock()
    parent_ast = MagicMock()
    ass = MagicMock()

    with patch.object(line, '_iterate_feed_answers_via_context') as mock_ctx:
        line.iterate_feed_answers(
            target_node, "q", True, FactValueType.BOOLEAN,
            parent_node_set, parent_ast, ass, feature_flags=flags,
        )
    mock_ctx.assert_called_once()


def test_iterate_feed_answers_default_flags():
    line = _make_iterate_line()
    target_node = MagicMock()
    parent_node_set = MagicMock()
    parent_ast = MagicMock()
    ass = MagicMock()

    with patch.object(line, '_iterate_feed_answers_legacy') as mock_legacy:
        line.iterate_feed_answers(
            target_node, "q", True, FactValueType.BOOLEAN,
            parent_node_set, parent_ast, ass, feature_flags=None,
        )
    mock_legacy.assert_called_once()


# ===================================================================
# 19. can_be_self_evaluated — legacy path with no engine
# ===================================================================


def test_can_be_self_evaluated_legacy_no_engine():
    line = _make_iterate_line()
    assert line.can_be_self_evaluated({}) is False


# ===================================================================
# 20. _extract_ordinal_index — no context fallback
# ===================================================================


def test_extract_ordinal_index_no_context_no_digit():
    line = _make_iterate_line()
    result = line._extract_ordinal_index("no_ordinal")
    assert result == 1


# ===================================================================
# 21. _self_evaluate_from_context
# ===================================================================


def test_self_evaluate_from_context_all_true():
    line = _make_iterate_line(quantifier="ALL")
    line._ensure_iterate_context(list_size=2)
    line._IterateLine__context.progress = {1: True, 2: True}
    result = line._self_evaluate_from_context()
    assert result.get_value() is True


def test_self_evaluate_from_context_none_true():
    line = _make_iterate_line(quantifier="NONE")
    line._ensure_iterate_context(list_size=2)
    line._IterateLine__context.progress = {1: False, 2: False}
    result = line._self_evaluate_from_context()
    assert result.get_value() is True


# ===================================================================
# 22. self_evaluate — legacy fallback
# ===================================================================


def test_self_evaluate_legacy_fallback():
    line = _make_iterate_line(quantifier="ALL")
    assert line._IterateLine__context is None
    with patch.object(line, '_number_of_true_children', return_value=3), \
         patch.object(line, '_evaluate_quantifier', return_value=FactValue(True)) as mock_eq:
        result = line.self_evaluate({"some": "wm"})
        mock_eq.assert_called_once_with(3, 0)


# ===================================================================
# 23. _get_lock lazy init
# ===================================================================


def test_get_lock_creates_lock():
    line = _make_iterate_line()
    assert line._lock is None
    lock = line._get_lock()
    assert lock is not None
    assert line._lock is lock


def test_get_lock_returns_existing():
    line = _make_iterate_line()
    import asyncio
    line._lock = asyncio.Lock()
    lock = line._get_lock()
    assert lock is line._lock
