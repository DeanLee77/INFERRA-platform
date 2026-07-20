"""Executable tests for the private P0.2b dependency layer."""

import asyncio

import pytest

from inferra_core import DependencyType, FactValueType
from inferra_core._internal.domain.graph.hyper_adjacency_graph import (
    CyclicGraphError,
    HyperAdjacencyGraph,
)
from inferra_core._internal.domain.nodes.iterate_line import IterateLine
from inferra_core._internal.domain.nodes.node_id_utils import NodeIdContext
from inferra_core._internal.domain.nodes.node_set import (
    LegacyMatrixAdapterRequired,
    NodeSet,
)
from inferra_core._internal.domain.rule_parser import (
    RuleSetParser,
    RuleSetReader,
    RuleSetScanner,
)
from inferra_core._internal.domain.tokens import Tokenizer
from inferra_core._internal.services.rule_validation_service import RuleValidationService


PARSER_SOURCE = (
    "INPUT applicant age AS NUMBER\n"
    "INPUT citizenship confirmed AS BOOLEAN\n"
    "\n"
    "eligible\n"
    "    AND applicant age >= 18\n"
    "    AND citizenship confirmed\n"
)


def _parse(source: str, source_name: str = "eligibility_baseline") -> NodeSet:
    reader = RuleSetReader()
    reader.create()
    reader.set_file_with_text(source)
    parser = RuleSetParser()
    parser.create()
    parser.set_source_name(source_name)
    scanner = RuleSetScanner(reader, parser)
    scanner.scan_rule_set()
    return scanner.establish_node_set()


def test_core_parser_matches_the_frozen_parser_vector() -> None:
    node_set = _parse(PARSER_SOURCE)

    assert sorted(node_set.get_node_dictionary()) == [
        "applicant age >= 18",
        "citizenship confirmed",
        "eligible",
    ]
    assert {
        name: value.get_value_type().value
        for name, value in sorted(node_set.get_input_dictionary().items())
    } == {
        "applicant age": "DOUBLE",
        "citizenship confirmed": "BOOLEAN",
    }
    assert sorted(node_set.get_graph().edges()) == [
        ("eligible", "applicant age >= 18", 8),
        ("eligible", "citizenship confirmed", 8),
    ]
    assert {
        name: node.get_stable_node_id()
        for name, node in sorted(node_set.get_node_dictionary().items())
    } == {
        "applicant age >= 18": "8d4502c0f1005ba9",
        "citizenship confirmed": "b6c064bd32ddd2b5",
        "eligible": "d5a0c1f3944158ff",
    }
    repeated = _parse(PARSER_SOURCE)
    assert {
        name: node.get_stable_node_id()
        for name, node in repeated.get_node_dictionary().items()
    } == {
        name: node.get_stable_node_id()
        for name, node in node_set.get_node_dictionary().items()
    }


def test_node_identity_context_is_explicit_and_parse_local() -> None:
    first = NodeIdContext()
    second = NodeIdContext()

    assert first.generate_node_id("module", "rule", "value") == second.generate_node_id(
        "module", "rule", "value"
    )
    first.reset()
    assert first._active_ids == {}


def test_graph_traversal_and_cycle_detection_are_executable() -> None:
    graph = HyperAdjacencyGraph()
    graph.add_dependency_group("parent", DependencyType.get_and(), {"left", "right"})

    assert graph.get_children_flat("parent") == ("left", "right")
    assert tuple(graph.back_propagate("left")) == ("parent",)
    assert set(graph.topological_sort()) == {"parent", "left", "right"}

    graph.add_dependency_group("left", DependencyType.get_or(), {"parent"})
    with pytest.raises(CyclicGraphError):
        graph.topological_sort()


def test_core_rejects_platform_legacy_matrix_views() -> None:
    with pytest.warns(DeprecationWarning), pytest.raises(LegacyMatrixAdapterRequired):
        NodeSet().get_dependency_matrix()
    with pytest.warns(DeprecationWarning), pytest.raises(LegacyMatrixAdapterRequired):
        RuleSetParser().create_dependency_matrix()


def test_iterate_node_uses_explicit_progress_and_pure_quantifiers() -> None:
    node = IterateLine(
        parent_text="EXACTLY 2 item IN items",
        tokens=Tokenizer.get_tokens("EXACTLY 2 item IN items"),
    )
    node.initialise_progress(3)

    completion = [
        asyncio.run(
            node.feed_iterate_answer(
                f"{index}th item",
                answer,
                FactValueType.BOOLEAN,
            )
        )
        for index, answer in enumerate((True, True, False), start=1)
    ]

    assert completion == [False, False, True]
    assert node.get_progress() == (3, 3)
    assert node.self_evaluate({}).get_value() is True


def test_validation_is_deterministic_without_a_clock_and_cacheable_with_one() -> None:
    invalid_source = (
        "INPUT age AS NUMBER\n"
        "INPUT age AS BOOLEAN\n"
        "\n"
        "eligible\n"
        "    AND age >= 18\n"
    )
    deterministic = RuleValidationService(
        cache_maxsize=2,
        enable_node_set_validation=True,
        enable_ontology_advisory_validation=False,
    )
    result = deterministic.validate(invalid_source, "duplicate_declaration_baseline")

    assert result.valid is False
    assert [entry.code for entry in result.errors] == ["DUPLICATE_DECLARATION"]
    assert deterministic._cache == {}

    instant = [10.0]
    cached = RuleValidationService(
        cache_maxsize=1,
        cache_ttl_seconds=5,
        enable_node_set_validation=False,
        enable_ontology_advisory_validation=False,
        clock=lambda: instant[0],
    )
    first = cached.validate(invalid_source)
    assert len(cached._cache) == 1
    assert cached.validate(invalid_source) is first
    instant[0] = 16.0
    assert cached.validate(invalid_source) is not first
