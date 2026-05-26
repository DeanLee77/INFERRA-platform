"""
IterationPort contract test suite.

Parametrised over every concrete implementation of IterationPort.
Any new implementation must pass every test in this file — this is the
behavioural contract that guarantees interchangeability across the port.

Add new implementations to the IMPLEMENTATIONS list below.

Phase 2 §4.9b: Lifecycle tests — initialise() → record_answer() → evaluate() → get_progress()
"""

from typing import Type

import pytest

from src.domain.fact_values import FactValue, FactValueType
from src.domain.iterate.iteration_engine import IterationEngine
from src.domain.state import FactSource, LayeredFactStore
from src.ports.fact_store_port import FactStorePort
from src.ports.iteration_port import IterationPort


IMPLEMENTATIONS: list[Type[IterationPort]] = [
    IterationEngine,
]


def _create_engine(cls: Type[IterationPort]) -> IterationPort:
    if cls is IterationEngine:
        return cls(fact_store=LayeredFactStore())
    return cls()


@pytest.fixture(params=IMPLEMENTATIONS, ids=lambda cls: cls.__name__)
def engine(request) -> IterationPort:
    """Provide a fresh IterationPort implementation for each test."""
    return _create_engine(request.param)


# ===================================================================
# 1. initialise — context creation & idempotency
# ===================================================================


def test_initialise_creates_context(engine):
    engine.initialise(list_size=5, quantifier="ALL", list_name="items")
    assert engine.get_progress() == (0, 5)


def test_initialise_idempotent_on_same_list_size(engine):
    engine.initialise(list_size=5, quantifier="ALL", list_name="items")
    engine.initialise(list_size=5, quantifier="ALL", list_name="items")
    assert engine.get_progress() == (0, 5)


def test_initialise_with_different_list_size_reinitialises(engine):
    engine.initialise(list_size=3, quantifier="ALL", list_name="items")
    engine.initialise(list_size=7, quantifier="SOME", list_name="items")
    assert engine.get_progress() == (0, 7)


def test_initialise_with_same_size_different_quantifier_reinitialises(engine):
    engine.initialise(list_size=3, quantifier="ALL", list_name="items")
    engine._ctx.progress[1] = True
    engine.initialise(list_size=3, quantifier="NONE", list_name="items")
    assert engine.get_progress() == (0, 3)
    assert engine._ctx.quantifier == "NONE"


def test_double_initialise_is_idempotent(engine):
    engine.initialise(list_size=5, quantifier="ALL", list_name="items")
    engine.initialise(list_size=5, quantifier="ALL", list_name="items")
    assert engine.get_progress() == (0, 5)


# ===================================================================
# 2. record_answer — progress tracking & completion
# ===================================================================


@pytest.mark.asyncio
async def test_record_answer_increments_progress(engine):
    engine.initialise(list_size=3, quantifier="ALL", list_name="items")
    done = await engine.record_answer(1, "1st item question", True, FactValueType.BOOLEAN)
    assert done is False
    assert engine.get_progress() == (1, 3)


@pytest.mark.asyncio
async def test_record_answer_returns_true_when_complete(engine):
    engine.initialise(list_size=2, quantifier="ALL", list_name="items")
    await engine.record_answer(1, "1st question", True, FactValueType.BOOLEAN)
    done = await engine.record_answer(2, "2nd question", False, FactValueType.BOOLEAN)
    assert done is True


@pytest.mark.asyncio
async def test_record_answer_boolean_true(engine):
    engine.initialise(list_size=1, quantifier="ALL", list_name="items")
    await engine.record_answer(1, "q1", True, FactValueType.BOOLEAN)
    result = engine.evaluate()
    assert result.get_value() is True


@pytest.mark.asyncio
async def test_record_answer_boolean_false(engine):
    engine.initialise(list_size=1, quantifier="ALL", list_name="items")
    await engine.record_answer(1, "q1", False, FactValueType.BOOLEAN)
    result = engine.evaluate()
    assert result.get_value() is False


@pytest.mark.asyncio
async def test_record_answer_string_true(engine):
    engine.initialise(list_size=1, quantifier="ALL", list_name="items")
    await engine.record_answer(1, "q1", "true", FactValueType.STRING)
    result = engine.evaluate()
    assert result.get_value() is True


@pytest.mark.asyncio
async def test_record_answer_string_false(engine):
    engine.initialise(list_size=1, quantifier="ALL", list_name="items")
    await engine.record_answer(1, "q1", "false", FactValueType.STRING)
    result = engine.evaluate()
    assert result.get_value() is False


@pytest.mark.asyncio
async def test_record_answer_boolean_string_false(engine):
    engine.initialise(list_size=1, quantifier="ALL", list_name="items")
    await engine.record_answer(1, "q1", "false", FactValueType.BOOLEAN)
    result = engine.evaluate()
    assert result.get_value() is False


# ===================================================================
# 3. evaluate — quantifier evaluation
# ===================================================================


def test_evaluate_before_completion_raises(engine):
    engine.initialise(list_size=3, quantifier="ALL", list_name="items")
    with pytest.raises(RuntimeError):
        engine.evaluate()


def test_evaluate_quantifier_all_all_true(engine):
    engine.initialise(list_size=3, quantifier="ALL", list_name="items")
    for i in range(1, 4):
        engine._ctx.progress[i] = True
    assert engine.evaluate().get_value() is True


def test_evaluate_quantifier_all_one_false(engine):
    engine.initialise(list_size=3, quantifier="ALL", list_name="items")
    engine._ctx.progress = {1: True, 2: False, 3: True}
    assert engine.evaluate().get_value() is False


def test_evaluate_quantifier_none_all_false(engine):
    engine.initialise(list_size=3, quantifier="NONE", list_name="items")
    engine._ctx.progress = {1: False, 2: False, 3: False}
    assert engine.evaluate().get_value() is True


def test_evaluate_quantifier_none_one_true(engine):
    engine.initialise(list_size=3, quantifier="NONE", list_name="items")
    engine._ctx.progress = {1: False, 2: True, 3: False}
    assert engine.evaluate().get_value() is False


def test_evaluate_quantifier_some_at_least_one_true(engine):
    engine.initialise(list_size=3, quantifier="SOME", list_name="items")
    engine._ctx.progress = {1: False, 2: True, 3: False}
    assert engine.evaluate().get_value() is True


def test_evaluate_quantifier_some_all_false(engine):
    engine.initialise(list_size=3, quantifier="SOME", list_name="items")
    engine._ctx.progress = {1: False, 2: False, 3: False}
    assert engine.evaluate().get_value() is False


def test_evaluate_quantifier_numeric(engine):
    engine.initialise(list_size=5, quantifier="2", list_name="items")
    engine._ctx.progress = {1: True, 2: True, 3: False, 4: False, 5: False}
    assert engine.evaluate().get_value() is True


def test_evaluate_quantifier_numeric_wrong_count(engine):
    engine.initialise(list_size=5, quantifier="3", list_name="items")
    engine._ctx.progress = {1: True, 2: True, 3: False, 4: False, 5: False}
    assert engine.evaluate().get_value() is False


# ===================================================================
# 4. get_progress — answered/total tracking
# ===================================================================


def test_get_progress_before_initialise(engine):
    assert engine.get_progress() == (0, 0)


def test_get_progress_returns_answered_total(engine):
    engine.initialise(list_size=5, quantifier="ALL", list_name="items")
    assert engine.get_progress() == (0, 5)


# ===================================================================
# 5. reset_iterate_context — clearing & reinitialisation
# ===================================================================


def test_reset_iterate_context_clears_progress(engine):
    engine.initialise(list_size=3, quantifier="ALL", list_name="items")
    engine._ctx.progress = {1: True, 2: False}
    engine.reset_iterate_context()
    assert engine.get_progress() == (0, 3)


def test_reset_iterate_context_noop_without_context(engine):
    engine.reset_iterate_context()
    assert engine.get_progress() == (0, 0)


# ===================================================================
# 6. record_answer after completion — noop
# ===================================================================


@pytest.mark.asyncio
async def test_record_after_completion_is_noop(engine):
    engine.initialise(list_size=1, quantifier="ALL", list_name="items")
    done = await engine.record_answer(1, "q1", True, FactValueType.BOOLEAN)
    assert done is True
    done2 = await engine.record_answer(2, "q2", False, FactValueType.BOOLEAN)
    assert engine.get_progress() == (1, 1)


# ===================================================================
# 7. record_answer skips ASSERTED override (truth-maintenance)
# ===================================================================


@pytest.mark.asyncio
async def test_record_answer_skips_asserted_override(engine):
    engine.initialise(list_size=1, quantifier="ALL", list_name="items")
    done = await engine.record_answer(1, "q1", True, FactValueType.BOOLEAN)
    assert done is True
