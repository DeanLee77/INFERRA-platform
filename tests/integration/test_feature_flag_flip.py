"""
Feature-flag flip integration tests — plan §5 / §6.

Verifies that:
1. Flags read at session creation are frozen for that session's lifetime.
2. Env-level changes after session creation do not leak into existing sessions.
3. LEGACY_ITERATE actually dispatches different code paths in IterateLine.
4. InferenceEngine keeps a graph backend available for Phase 2.5 graph-first runtime.

These tests confirm the wiring is real, not declarative — the §6 mid-session-flip
risk row depends on this behaviour being verifiable.
"""

from src.adapters.outbound.session.in_memory_session_store import InMemorySessionStore
from src.domain.fact_values import FactValue, FactValueType
from src.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph
from src.domain.inference.inference_engine import InferenceEngine
from src.domain.inference.session_service import InferenceSessionService
from src.domain.nodes.iterate_line import IterateLine
from src.domain.nodes.line_type import LineType
from src.domain.nodes.node import Node
from src.domain.nodes.node_set import NodeSet
from src.domain.state import feature_flags as feature_flags_module
from src.domain.state.feature_flags import FeatureFlags


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class _StubNode(Node):
    """Concrete Node that satisfies the abstract contract for testing."""

    def __init__(self, name: str):
        super().__init__(id=1)
        self._node_name = name
        self._variable_name = name
        self._line_type = LineType.VALUE_CONCLUSION

    def initialisation(self, parent_text, tokens):
        pass

    def get_line_type(self):
        return self._line_type

    def self_evaluate(self, working_memory):
        return FactValue(True)


class _StubIterateLine(IterateLine):
    """Concrete IterateLine implementing the abstract `initialisation`."""

    def initialisation(self, parent_text, tokens):
        pass


def _node_set_with_target(target_name: str = "is_eligible") -> NodeSet:
    """Build a minimal NodeSet whose node_dictionary contains the target name."""
    ns = NodeSet()
    ns.set_node_set_name("test_rule")
    ns.register_node(_StubNode(target_name))
    return ns


def _fresh_service() -> InferenceSessionService:
    return InferenceSessionService(InMemorySessionStore())


# ===========================================================================
# 1. Start-of-session stickiness
# ===========================================================================

class TestFlagFreezeAtSessionStart:
    """Session creation must snapshot + freeze flags so post-creation mutations don't leak."""

    def test_session_captures_flag_snapshot_at_creation(self, monkeypatch):
        monkeypatch.setattr(
            feature_flags_module,
            "_default_flags",
            FeatureFlags(
                use_hypergraph=False,
                legacy_iterate=True,
                layered_memory=True,
                ml_optimized_dfs=True,
                async_sync_enabled=True,
                modular_imports=True,
            ),
        )

        ns = _node_set_with_target()
        service = _fresh_service()
        session = service.create_session(
            rule_name="test_rule",
            target_node_name="is_eligible",
            node_set=ns,
        )

        assert session.feature_flags is not None
        assert session.feature_flags.is_frozen() is True
        assert session.feature_flags.use_hypergraph is False
        assert session.feature_flags.legacy_iterate is True
        assert session.feature_flags.ml_optimized_dfs is True
        assert session.feature_flags.async_sync_enabled is True
        assert session.feature_flags.modular_imports is True

    def test_post_creation_global_flag_change_does_not_leak_into_existing_session(self, monkeypatch):
        monkeypatch.setattr(
            feature_flags_module,
            "_default_flags",
            FeatureFlags(use_hypergraph=False, legacy_iterate=True, layered_memory=True),
        )

        ns = _node_set_with_target()
        service = _fresh_service()
        session_a = service.create_session(
            rule_name="test_rule",
            target_node_name="is_eligible",
            node_set=ns,
        )

        # "Admin" mutates the global flags after session A starts
        monkeypatch.setattr(
            feature_flags_module,
            "_default_flags",
            FeatureFlags(use_hypergraph=True, legacy_iterate=False, layered_memory=True),
        )

        # Session A keeps its frozen snapshot
        assert session_a.feature_flags.use_hypergraph is False
        assert session_a.feature_flags.legacy_iterate is True

        # Session B sees the new flags
        session_b = service.create_session(
            rule_name="test_rule",
            target_node_name="is_eligible",
            node_set=_node_set_with_target(),
        )
        assert session_b.feature_flags.use_hypergraph is True
        assert session_b.feature_flags.legacy_iterate is False

    def test_engine_and_session_share_the_same_frozen_flags(self, monkeypatch):
        monkeypatch.setattr(
            feature_flags_module,
            "_default_flags",
            FeatureFlags(use_hypergraph=True, legacy_iterate=False, layered_memory=True),
        )

        ns = _node_set_with_target()
        service = _fresh_service()
        session = service.create_session(
            rule_name="test_rule",
            target_node_name="is_eligible",
            node_set=ns,
        )

        engine_flags = session.inference_engine.get_feature_flags()
        assert engine_flags is session.feature_flags
        assert engine_flags.use_hypergraph is True
        assert engine_flags.legacy_iterate is False


# ===========================================================================
# 2. Graph backend construction
# ===========================================================================

class TestUseHypergraphSwitch:
    """The graph-first engine constructs a graph backend regardless of the legacy flag."""

    def test_default_false_still_builds_dependency_graph(self):
        ns = _node_set_with_target()
        flags = FeatureFlags(use_hypergraph=False, legacy_iterate=True, layered_memory=True)
        flags.freeze()

        engine = InferenceEngine(node_set=ns, feature_flags=flags)

        assert engine.get_dependency_graph() is not None

    def test_true_uses_node_set_canonical_hypergraph(self):
        ns = _node_set_with_target()
        flags = FeatureFlags(use_hypergraph=True, legacy_iterate=True, layered_memory=True)
        flags.freeze()

        engine = InferenceEngine(node_set=ns, feature_flags=flags)

        graph = engine.get_dependency_graph()
        assert graph is not None
        assert isinstance(graph, HyperAdjacencyGraph)
        assert graph is ns.get_graph()


# ===========================================================================
# 3. LEGACY_ITERATE dispatches between paths in IterateLine
# ===========================================================================

class TestLegacyIterateDispatch:
    """The flag selects between the legacy nested-engine path and the new IterateContext path."""

    def test_dispatch_picks_legacy_path_when_flag_true(self, monkeypatch):
        captured = {"legacy_called": False, "context_called": False}

        def fake_legacy(self, *args, **kwargs):
            captured["legacy_called"] = True

        def fake_context(self, *args, **kwargs):
            captured["context_called"] = True

        monkeypatch.setattr(IterateLine, "_iterate_feed_answers_legacy", fake_legacy)
        monkeypatch.setattr(IterateLine, "_iterate_feed_answers_via_context", fake_context)

        iterate = _StubIterateLine()
        flags = FeatureFlags(use_hypergraph=False, legacy_iterate=True, layered_memory=True)
        flags.freeze()

        iterate.iterate_feed_answers(
            target_node=None,
            question_name="q",
            node_value=1,
            node_value_type=FactValueType.INTEGER,
            parent_node_set=None,
            parent_ast=None,
            ass=None,
            feature_flags=flags,
        )

        assert captured["legacy_called"] is True
        assert captured["context_called"] is False

    def test_dispatch_picks_context_path_when_flag_false(self, monkeypatch):
        captured = {"legacy_called": False, "context_called": False}

        def fake_legacy(self, *args, **kwargs):
            captured["legacy_called"] = True

        def fake_context(self, *args, **kwargs):
            captured["context_called"] = True

        monkeypatch.setattr(IterateLine, "_iterate_feed_answers_legacy", fake_legacy)
        monkeypatch.setattr(IterateLine, "_iterate_feed_answers_via_context", fake_context)

        iterate = _StubIterateLine()
        flags = FeatureFlags(use_hypergraph=False, legacy_iterate=False, layered_memory=True)
        flags.freeze()

        iterate.iterate_feed_answers(
            target_node=None,
            question_name="q",
            node_value=1,
            node_value_type=FactValueType.INTEGER,
            parent_node_set=None,
            parent_ast=None,
            ass=None,
            feature_flags=flags,
        )

        assert captured["legacy_called"] is False
        assert captured["context_called"] is True

    def test_default_flags_dispatch_to_legacy(self, monkeypatch):
        """When no feature_flags arg is passed, default FeatureFlags() reads env defaults (legacy_iterate=true)."""
        captured = {"legacy_called": False, "context_called": False}
        monkeypatch.setattr(
            IterateLine, "_iterate_feed_answers_legacy",
            lambda self, *a, **k: captured.update(legacy_called=True),
        )
        monkeypatch.setattr(
            IterateLine, "_iterate_feed_answers_via_context",
            lambda self, *a, **k: captured.update(context_called=True),
        )
        monkeypatch.delenv("INFERRA_LEGACY_ITERATE", raising=False)

        iterate = _StubIterateLine()
        iterate.iterate_feed_answers(
            target_node=None,
            question_name="q",
            node_value=1,
            node_value_type=FactValueType.INTEGER,
            parent_node_set=None,
            parent_ast=None,
            ass=None,
        )

        assert captured["legacy_called"] is True


# ===========================================================================
# 4. Frozen-flag lifetime
# ===========================================================================

class TestFrozenFlagsImmutability:
    """Once frozen, the snapshot stays put — even if a fresh global instance is built."""

    def test_freeze_status_persists_through_session_lifetime(self, monkeypatch):
        monkeypatch.setattr(
            feature_flags_module,
            "_default_flags",
            FeatureFlags(use_hypergraph=False, legacy_iterate=True, layered_memory=True),
        )

        ns = _node_set_with_target()
        service = _fresh_service()
        session = service.create_session(
            rule_name="test_rule",
            target_node_name="is_eligible",
            node_set=ns,
        )

        assert session.feature_flags.is_frozen() is True

        # Building a fresh global FeatureFlags doesn't unfreeze the session's instance
        feature_flags_module._default_flags = FeatureFlags(use_hypergraph=True)
        assert session.feature_flags.is_frozen() is True
        assert session.feature_flags.use_hypergraph is False
