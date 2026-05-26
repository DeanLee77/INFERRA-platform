"""
Tests for InferraToRdfCompiler.

Validates RDF triple generation from rule text, including rule type
inference, child extraction, and quantifier detection.
"""

import pytest

from src.adapters.outbound.ontology.inferra_to_rdf_compiler import (
    INF_NS,
    InferraToRdfCompiler,
    _extract_children,
    _extract_quantifier,
    _infer_rule_type,
    _sanitize_uri,
)


class TestSanitizeUri:
    def test_simple_name(self):
        assert _sanitize_uri("my_rule") == "my_rule"

    def test_spaces_replaced(self):
        assert _sanitize_uri("my rule") == "my_rule"

    def test_special_chars_replaced(self):
        assert _sanitize_uri("rule#1!") == "rule_1_"


class TestInferRuleType:
    def test_and_rule(self):
        assert _infer_rule_type("goal AND dep1 dep2") == "AND"

    def test_or_rule(self):
        assert _infer_rule_type("goal OR dep1 dep2") == "OR"

    def test_iterate_rule(self):
        assert _infer_rule_type("ITERATE ALL services") == "ITERATE"

    def test_conclusion_default(self):
        assert _infer_rule_type("simple fact") == "CONCLUSION"


class TestExtractChildren:
    def test_extracts_indented_lines(self):
        text = "goal AND\n  dep1\n  dep2"
        assert _extract_children(text) == ["dep1", "dep2"]

    def test_skips_comments(self):
        text = "goal AND\n  # comment\n  dep1"
        assert _extract_children(text) == ["dep1"]

    def test_empty_children(self):
        text = "simple fact"
        assert _extract_children(text) == []


class TestExtractQuantifier:
    def test_all_quantifier(self):
        assert _extract_quantifier("ITERATE ALL services") == "ALL"

    def test_none_quantifier(self):
        assert _extract_quantifier("ITERATE NONE items") == "NONE"

    def test_some_quantifier(self):
        assert _extract_quantifier("ITERATE SOME items") == "SOME"

    def test_no_quantifier(self):
        assert _extract_quantifier("goal AND dep1") == ""


class TestInferraToRdfCompiler:
    def test_compile_and_rule(self):
        triples = InferraToRdfCompiler.compile("goal AND\n  dep1\n  dep2", "test_rule")
        subjects = {t[0] for t in triples}
        assert any(f"{INF_NS}rule/test_rule" in s for s in subjects)

    def test_compile_produces_type_triple(self):
        triples = InferraToRdfCompiler.compile("goal AND\n  dep1", "test_rule")
        types = [t for t in triples if t[1].endswith("#type") and t[2].endswith("Rule")]
        assert len(types) >= 1

    def test_compile_includes_source_text(self):
        rule_text = "goal AND\n  dep1"
        triples = InferraToRdfCompiler.compile(rule_text, "test_rule")
        source_triples = [t for t in triples if "sourceText" in t[1]]
        assert len(source_triples) == 1
        assert source_triples[0][2] == rule_text

    def test_compile_and_rule_has_dependencies(self):
        triples = InferraToRdfCompiler.compile("goal AND\n  dep1\n  dep2", "test_rule")
        dep_predicates = [t for t in triples if "andDependsOn" in t[1] or "orDependsOn" in t[1]]
        assert len(dep_predicates) == 2

    def test_compile_iterate_rule(self):
        triples = InferraToRdfCompiler.compile("ITERATE ALL services", "iterate_rule")
        types = [t for t in triples if "IterateRule" in t[2]]
        assert len(types) >= 1
        quantifiers = [t for t in triples if "quantifier" in t[1]]
        assert len(quantifiers) == 1
        assert quantifiers[0][2] == "ALL"

    def test_compile_rule_name_in_uri(self):
        triples = InferraToRdfCompiler.compile("simple fact", "my_rule")
        assert any("my_rule" in t[0] for t in triples)

    def test_compile_child_nodes_have_type(self):
        triples = InferraToRdfCompiler.compile("goal AND\n  dep1", "test_rule")
        node_names = [t[2] for t in triples if t[1].endswith("#name")]
        assert "dep1" in node_names
