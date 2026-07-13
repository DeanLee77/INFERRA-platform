"""
Tests for InferraToRdfCompiler.

Validates RDF triple generation from rule text, including rule type
inference, child extraction, and quantifier detection.
"""

import pytest

from src.adapters.outbound.ontology.inferra_to_rdf_compiler import (
    INF_NS,
    RDF_TYPE,
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

    def test_strips_dependency_prefixes(self):
        text = "goal\n    AND section 19 claim lodgement met\n    OR alternative path"
        assert _extract_children(text) == [
            "section 19 claim lodgement met",
            "alternative path",
        ]

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

    def test_exact_quantifier(self):
        assert _extract_quantifier("EXACT 2 item IN items") == "EXACTLY 2"

    def test_at_least_quantifier(self):
        assert _extract_quantifier("AT LEAST 2 item IN items") == "AT LEAST 2"

    def test_at_most_quantifier(self):
        assert _extract_quantifier("AT MOST 2 item IN items") == "AT MOST 2"

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

    def test_compile_rule_block_with_inferra_child_prefixes(self):
        triples = InferraToRdfCompiler.compile(
            "eligible for benefit\n"
            "    AND claimant has service\n"
            "    OR special pathway met\n",
            "test_rule",
        )
        assert any(t[1].endswith("andDependsOn") and t[2].endswith("claimant_has_service") for t in triples)
        assert any(t[1].endswith("orDependsOn") and t[2].endswith("special_pathway_met") for t in triples)
        assert any(t[1].endswith("name") and t[2] == "eligible for benefit" for t in triples)

    def test_compile_preserves_nested_virtual_branch_parentage(self):
        triples = InferraToRdfCompiler.compile(
            "benefit payable\n"
            "    AND pathway gateway virtual ONE\n"
            "        OR service pathway\n"
            "            AND qualifying service\n"
            "        OR special pathway\n"
            "            AND special circumstance\n",
            "test_rule",
        )

        root_uri = f"{INF_NS}rule/test_rule/node/benefit_payable"
        gateway_uri = f"{INF_NS}rule/test_rule/node/pathway_gateway_virtual_ONE"
        service_uri = f"{INF_NS}rule/test_rule/node/service_pathway"
        qualifying_uri = f"{INF_NS}rule/test_rule/node/qualifying_service"
        special_uri = f"{INF_NS}rule/test_rule/node/special_pathway"
        circumstance_uri = f"{INF_NS}rule/test_rule/node/special_circumstance"

        assert (root_uri, f"{INF_NS}andDependsOn", gateway_uri) in triples
        assert (gateway_uri, f"{INF_NS}orDependsOn", service_uri) in triples
        assert (service_uri, f"{INF_NS}andDependsOn", qualifying_uri) in triples
        assert (gateway_uri, f"{INF_NS}orDependsOn", special_uri) in triples
        assert (special_uri, f"{INF_NS}andDependsOn", circumstance_uri) in triples
        assert not any(
            subject == root_uri and obj in {service_uri, qualifying_uri, special_uri, circumstance_uri}
            for subject, _, obj in triples
        )

    def test_compile_preserves_not_all_iterate_quantifier_after_dependency_prefix(self):
        triples = InferraToRdfCompiler.compile(
            "eligibility\n"
            "    AND NOT ALL service period IN service history\n",
            "test_rule",
        )

        iterate_uri = f"{INF_NS}rule/test_rule/node/NOT_ALL_service_period_IN_service_history"

        assert (iterate_uri, f"{INF_NS}quantifier", "NOT ALL") in triples
        assert any(subject == iterate_uri and obj.endswith("IterateRule") for subject, _, obj in triples)

    def test_compile_declarations_and_imports(self):
        triples = InferraToRdfCompiler.compile(
            "IMPORT: common_rules\n"
            "FIXED threshold IS 10\n"
            "INPUT applicant age AS NUMBER\n"
            "\n"
            "eligible\n"
            "    AND applicant age >= threshold\n",
            "test_rule",
        )
        assert any(t[1].endswith("importsRuleSet") and t[2].endswith("common_rules") for t in triples)
        assert any(t[1].endswith("declares") and t[2].endswith("threshold") for t in triples)
        assert any(t[1].endswith("declares") and t[2].endswith("applicant_age") for t in triples)

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

    def test_compile_comparison_leaf_emits_operands_and_operator(self):
        triples = InferraToRdfCompiler.compile(
            "INPUT weeks of incapacity AS NUMBER\n"
            "FIXED initial incapacity period weeks IS NUMBER\n"
            "\n"
            "initial incapacity payable\n"
            "    AND weeks of incapacity <= initial incapacity period weeks\n",
            "test_rule",
        )

        comparison_uri = (
            f"{INF_NS}rule/test_rule/node/"
            "weeks_of_incapacity____initial_incapacity_period_weeks"
        )
        weeks_uri = f"{INF_NS}rule/test_rule/declaration/weeks_of_incapacity"
        threshold_uri = f"{INF_NS}rule/test_rule/declaration/initial_incapacity_period_weeks"

        assert (comparison_uri, f"{INF_NS}dependencyProperty", weeks_uri) in triples
        assert (comparison_uri, f"{INF_NS}operator", "<=") in triples
        assert (comparison_uri, f"{INF_NS}comparesTo", threshold_uri) in triples
        assert (comparison_uri, RDF_TYPE, f"{INF_NS}ComparisonNode") in triples

    def test_compile_list_items_stay_scoped_to_list_declaration(self):
        triples = InferraToRdfCompiler.compile(
            "FIXED DVA payment choice AS LIST\n"
            "    ITEM lump sum\n"
            "    ITEM periodic payments\n"
            "INPUT interim impairment points AS NUMBER\n"
            "\n"
            "ITEM orphaned payment option\n"
            "\n"
            "payment can be selected\n"
            "    AND interim impairment points >= 10\n",
            "test_rule",
        )

        list_uri = f"{INF_NS}rule/test_rule/declaration/DVA_payment_choice"
        interim_uri = f"{INF_NS}rule/test_rule/declaration/interim_impairment_points"
        comparison_uri = f"{INF_NS}rule/test_rule/node/interim_impairment_points____10"

        assert (list_uri, RDF_TYPE, f"{INF_NS}EnumList") in triples
        assert (list_uri, f"{INF_NS}hasItem", "lump sum") in triples
        assert (list_uri, f"{INF_NS}hasItem", "periodic payments") in triples
        assert (comparison_uri, f"{INF_NS}dependencyProperty", interim_uri) in triples
        assert not any(
            "ITEM_lump_sum" in subject
            or "ITEM_periodic_payments" in subject
            or "ITEM_orphaned_payment_option" in subject
            for subject, _, _ in triples
        )

    def test_compile_is_in_list_colon_and_plain_resolve_declared_enum_list(self):
        triples = InferraToRdfCompiler.compile(
            "INPUT service type AS LIST\n"
            "    ITEM warlike\n"
            "FIXED DVA operational service type AS LIST\n"
            "    ITEM warlike\n"
            "    ITEM non-warlike\n"
            "\n"
            "eligible\n"
            "    AND service type IS IN LIST: DVA operational service type\n"
            "    AND service type IS IN LIST DVA operational service type\n",
            "test_rule",
        )

        service_type_uri = f"{INF_NS}rule/test_rule/declaration/service_type"
        enum_uri = f"{INF_NS}rule/test_rule/declaration/DVA_operational_service_type"
        colon_comparison_uri = (
            f"{INF_NS}rule/test_rule/node/"
            "service_type_IS_IN_LIST__DVA_operational_service_type"
        )
        plain_comparison_uri = (
            f"{INF_NS}rule/test_rule/node/"
            "service_type_IS_IN_LIST_DVA_operational_service_type"
        )

        for comparison_uri in (colon_comparison_uri, plain_comparison_uri):
            assert (comparison_uri, f"{INF_NS}operator", "IS IN LIST") in triples
            assert (comparison_uri, f"{INF_NS}dependencyProperty", service_type_uri) in triples
            assert (comparison_uri, f"{INF_NS}comparesTo", enum_uri) in triples

        assert (enum_uri, RDF_TYPE, f"{INF_NS}EnumList") in triples

    def test_compile_and_not_uses_not_depends_on_without_child_not_modifier(self):
        triples = InferraToRdfCompiler.compile(
            "SRDP choice validated\n"
            "    AND SRDP election made\n"
            "    AND NOT VEA TPI election made\n",
            "test_rule",
        )

        root_uri = f"{INF_NS}rule/test_rule/node/SRDP_choice_validated"
        negated_uri = f"{INF_NS}rule/test_rule/node/VEA_TPI_election_made"

        assert (root_uri, f"{INF_NS}notDependsOn", negated_uri) in triples
        assert (root_uri, f"{INF_NS}andDependsOn", negated_uri) not in triples
        assert (negated_uri, f"{INF_NS}dependencyModifier", "NOT") not in triples

    def test_compile_attaches_comment_metadata_to_next_rule_node(self):
        triples = InferraToRdfCompiler.compile(
            "# Reference: MRCA s 199\n"
            "# Section: special rate disability pension\n"
            "# Original: A person is eligible only if the choice is valid.\n"
            "SRDP choice validated\n"
            "    AND SRDP election made\n",
            "test_rule",
        )

        node_uri = f"{INF_NS}rule/test_rule/node/SRDP_choice_validated"

        assert (node_uri, f"{INF_NS}statutoryReference", "MRCA s 199") in triples
        assert (node_uri, f"{INF_NS}statutorySection", "special rate disability pension") in triples
        assert (
            node_uri,
            f"{INF_NS}originalText",
            "A person is eligible only if the choice is valid.",
        ) in triples

    def test_compile_calc_node_and_needs_variables(self):
        triples = InferraToRdfCompiler.compile(
            "INPUT DRCA entitlement AS BOOLEAN\n"
            "INPUT VEA entitlement AS BOOLEAN\n"
            "\n"
            "primary governing act IS CALC choose_act(drca, vea)\n"
            "    NEEDS DRCA entitlement\n"
            "    NEEDS VEA entitlement\n",
            "test_rule",
        )

        calc_uri = f"{INF_NS}rule/test_rule/node/primary_governing_act"
        drca_uri = f"{INF_NS}rule/test_rule/declaration/DRCA_entitlement"
        vea_uri = f"{INF_NS}rule/test_rule/declaration/VEA_entitlement"

        assert (calc_uri, RDF_TYPE, f"{INF_NS}CalculationNode") in triples
        assert (calc_uri, f"{INF_NS}name", "primary governing act") in triples
        assert (calc_uri, f"{INF_NS}hasFormula", "choose_act(drca, vea)") in triples
        assert (calc_uri, f"{INF_NS}requiresVariable", drca_uri) in triples
        assert (calc_uri, f"{INF_NS}requiresVariable", vea_uri) in triples
