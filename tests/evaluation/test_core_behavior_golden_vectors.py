"""Golden semantic vectors that must survive the inferra-core extraction."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pytest

from src.domain.fact_values import FactValue, FactValueType
from src.domain.imports.import_resolver import RuleSetImportResolver
from src.domain.inference.assessment import Assessment
from src.domain.inference.inference_engine import InferenceEngine
from src.domain.iterate.iteration_engine import IterationEngine
from src.domain.rule_parser.rule_set_parser import RuleSetParser
from src.domain.rule_parser.rule_set_reader import RuleSetReader
from src.domain.rule_parser.rule_set_scanner import RuleSetScanner
from src.domain.session.inference_context import InferenceContext
from src.domain.state import FactSource, LayeredFactStore
from src.domain.state.feature_flags import FEATURE_FLAG_SPECS, FeatureFlags
from src.domain.trace.prov_o_trace_generator import ProvOTraceGenerator
from src.services.rule_validation_service import RuleValidationService


_VECTORS_PATH = Path(__file__).with_name("core_behavior_golden_vectors.json")


def _vectors() -> Dict[str, Any]:
    return json.loads(_VECTORS_PATH.read_text(encoding="utf-8"))


def _assert_golden(actual: Any, expected: Any) -> None:
    assert actual == expected, "Golden snapshot changed. Actual:\n" + json.dumps(
        actual, indent=2, sort_keys=True
    )


def _parse_node_set(rule_text: str, source_name: str):
    reader = RuleSetReader()
    reader.create()
    reader.set_file_with_text(rule_text)
    parser = RuleSetParser()
    parser.create()
    parser.set_source_name(source_name)
    scanner = RuleSetScanner(reader, parser)
    scanner.scan_rule_set()
    return scanner.establish_node_set()


def _explicit_feature_flags(**overrides: Any) -> FeatureFlags:
    values = {spec.key: spec.default for spec in FEATURE_FLAG_SPECS}
    values.update(overrides)
    return FeatureFlags(**values)


def _fact_snapshot(engine: InferenceEngine) -> Dict[str, Dict[str, Any]]:
    state = engine.get_assessment_state()
    return {
        name: {
            "value": fact.get_value(),
            "type": fact.get_value_type().value,
            "sources": sorted(source.value for source in state.get_fact_sources(name)),
        }
        for name, fact in sorted(state.get_working_memory().items())
    }


def test_rule_parser_golden_vector() -> None:
    case = _vectors()["parser"]
    node_set = _parse_node_set(case["rule_text"], case["source_name"])
    graph = node_set.get_graph()
    actual = {
        "source_sha256": hashlib.sha256(case["rule_text"].encode("utf-8")).hexdigest(),
        "node_names": sorted(node_set.get_node_dictionary()),
        "input_types": {
            name: value.get_value_type().value
            for name, value in sorted(node_set.get_input_dictionary().items())
        },
        "edges": [
            {"parent": parent, "child": child, "dependency_type": dependency_type}
            for parent, child, dependency_type in sorted(graph.edges())
        ],
        "stable_node_ids": {
            name: node.get_stable_node_id()
            for name, node in sorted(node_set.get_node_dictionary().items())
        },
    }
    _assert_golden(actual, case["expected"])


def test_diagnostic_golden_vector() -> None:
    case = _vectors()["diagnostics"]
    service = RuleValidationService(
        cache_maxsize=1,
        cache_ttl_seconds=60,
        enable_node_set_validation=True,
        enable_ontology_advisory_validation=False,
    )
    result = service.validate(case["rule_text"], rule_name=case["rule_name"])
    actual = {
        "source_sha256": hashlib.sha256(case["rule_text"].encode("utf-8")).hexdigest(),
        "result": result.to_dict(),
    }
    _assert_golden(actual, case["expected"])


def test_inference_golden_vector() -> None:
    case = _vectors()["inference"]
    node_set = _parse_node_set(case["rule_text"], case["source_name"])
    node_dictionary = node_set.get_node_dictionary()
    node_set.set_sorted_node_list(
        [node_dictionary[name] for name in case["preferred_order"]]
    )
    engine = InferenceEngine(node_set, feature_flags=_explicit_feature_flags())
    assessment = Assessment(node_set, case["target"])
    engine.add_assessment_into_assessment_list(assessment)

    asked = []
    while True:
        node = engine.get_next_question(assessment)
        if node is None:
            break
        questions = engine.get_questions_from_node_to_be_asked(node)
        assert len(questions) == 1
        question = questions[0]
        asked.append(question)
        assert question in case["answers"], f"No golden answer for {question!r}"
        engine.feed_answer_to_node(
            assessment.get_node_to_be_asked(),
            question,
            case["answers"][question],
            FactValueType.BOOLEAN,
            assessment,
        )

    actual = {
        "source_sha256": hashlib.sha256(case["rule_text"].encode("utf-8")).hexdigest(),
        "asked": asked,
        "facts": _fact_snapshot(engine),
        "inclusive": sorted(engine.get_assessment_state().get_inclusive_list()),
        "mandatory": sorted(engine.get_assessment_state().get_mandatory_list()),
        "branch_prune_trace": [
            {
                "node_name": event["nodeName"],
                "action": event["action"],
                "reason": event["reason"],
            }
            for event in engine.get_branch_prune_trace()
        ],
    }
    _assert_golden(actual, case["expected"])


def test_import_resolution_golden_vector() -> None:
    case = _vectors()["imports"]

    def loader(name: str) -> str:
        return case["sources"][name]

    resolver = RuleSetImportResolver(
        rule_loader=loader,
        feature_flags=_explicit_feature_flags(modular_imports=True),
    )
    resolved = resolver.resolve(case["root"])
    actual = {
        "source_hashes": {
            name: hashlib.sha256(source.encode("utf-8")).hexdigest()
            for name, source in sorted(case["sources"].items())
        },
        "resolution_order": list(resolved),
        "origins": {
            name: {
                "module": origin.module,
                "imported": origin.imported,
                "depth": origin.depth,
            }
            for name, origin in resolved.items()
        },
    }
    _assert_golden(actual, case["expected"])


@pytest.mark.asyncio
async def test_iteration_golden_vector() -> None:
    case = _vectors()["iteration"]
    results = []
    for index, vector in enumerate(case["cases"]):
        store = LayeredFactStore(clock=lambda: 1000.0 + index)
        engine = IterationEngine(store)
        answers = vector["answers"]
        engine.initialise(
            list_size=len(answers),
            quantifier=vector["quantifier"],
            list_name=f"items-{index}",
        )
        completion_flags = []
        for answer_index, answer in enumerate(answers, start=1):
            completion_flags.append(
                await engine.record_answer(
                    answer_index,
                    f"item-{answer_index}",
                    answer,
                    FactValueType.BOOLEAN,
                )
            )
        results.append(
            {
                "quantifier": vector["quantifier"],
                "answers": answers,
                "completion_flags": completion_flags,
                "progress": list(engine.get_progress()),
                "result": engine.evaluate().get_value(),
            }
        )
    _assert_golden({"cases": results}, case["expected"])


def _semantic_graph_digest(serialized: str, data_format: str) -> Dict[str, Any]:
    rdflib = pytest.importorskip("rdflib")
    graph = rdflib.Graph()
    graph.parse(data=serialized, format=data_format)
    canonical = "\n".join(
        sorted(f"{subject.n3()} {predicate.n3()} {obj.n3()} ." for subject, predicate, obj in graph)
    )
    return {
        "triple_count": len(graph),
        "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def test_provenance_golden_vector() -> None:
    case = _vectors()["provenance"]
    store = LayeredFactStore(clock=lambda: 1000.0)
    for item in case["facts"]:
        store.set_fact(
            item["name"],
            FactValue(item["value"]),
            source=FactSource(item["source"]),
        )
    context = InferenceContext(
        session_id=case["session_id"],
        rule_name=case["rule_name"],
        target=case["target"],
        mandatory=[],
        fact_store=store,
        started_at=datetime(2026, 7, 17, tzinfo=timezone.utc),
        iteration_count=case["iteration_count"],
        ontology_profile=case["ontology_profile"],
        ontology_profile_source=case["ontology_profile_source"],
        ontology_flags=case["ontology_flags"],
    )
    generator = ProvOTraceGenerator()
    turtle = generator.generate(context, output_format="turtle")
    json_ld = generator.generate(context, output_format="json-ld")
    actual = {
        "turtle": _semantic_graph_digest(turtle, "turtle"),
        "json_ld": _semantic_graph_digest(json_ld, "json-ld"),
    }
    _assert_golden(actual, case["expected"])
