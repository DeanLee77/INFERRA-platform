import pytest

from src.domain.inference.legacy_orchestrator import LegacyOrchestrator


class _Node:
    def __init__(self, name):
        self._name = name

    def get_node_name(self):
        return self._name


class _NodeSet:
    def __init__(self, goal):
        self._goal = goal

    def get_default_goal_node(self):
        return self._goal


class _State:
    def __init__(self, working_memory, mandatory_done):
        self._working_memory = working_memory
        self._mandatory_done = mandatory_done

    def get_working_memory(self):
        return self._working_memory

    def all_mandatory_node_determined(self):
        return self._mandatory_done


class _Engine:
    def __init__(self, node_set=None, state=None):
        self._node_set = node_set
        self._state = state

    def get_node_set(self):
        return self._node_set

    def get_assessment_state(self):
        return self._state


@pytest.mark.asyncio
async def test_legacy_orchestrator_pending_without_node_set():
    result = await LegacyOrchestrator(_Engine()).run_convergence_loop("s1")

    assert result.converged is False
    assert result.reason == "PENDING"
    assert result.session_id == "s1"


@pytest.mark.asyncio
async def test_legacy_orchestrator_pending_without_goal_node():
    engine = _Engine(node_set=_NodeSet(goal=None))

    result = await LegacyOrchestrator(engine).run_convergence_loop("s1")

    assert result.converged is False
    assert result.reason == "PENDING"


@pytest.mark.asyncio
async def test_legacy_orchestrator_goal_reached_when_goal_in_working_memory_and_mandatory_done():
    goal = _Node("eligible")
    engine = _Engine(
        node_set=_NodeSet(goal),
        state=_State({"eligible": True}, mandatory_done=True),
    )

    result = await LegacyOrchestrator(engine).run_convergence_loop("s1")

    assert result.converged is True
    assert result.reason == "GOAL_REACHED"


@pytest.mark.asyncio
async def test_legacy_orchestrator_pending_when_goal_missing_or_mandatory_open():
    goal = _Node("eligible")
    engine = _Engine(
        node_set=_NodeSet(goal),
        state=_State({"eligible": True}, mandatory_done=False),
    )

    result = await LegacyOrchestrator(engine).run_convergence_loop("s1")

    assert result.converged is False
    assert result.reason == "PENDING"
