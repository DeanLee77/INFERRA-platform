from src.domain.fact_values import FactValue
from src.domain.reasoning.trace_extractor import TraceExtractor, TracePattern


def test_trace_pattern_is_immutable():
    pattern = TracePattern(
        pattern_id="tp_1",
        fact_names=("income",),
        decision_path=("income",),
        frequency=1,
    )

    try:
        pattern.frequency = 2
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("TracePattern should be frozen")


def test_extract_from_dict_builds_stable_pattern_from_working_memory():
    extractor = TraceExtractor()
    session_data = {
        "working_memory": {
            "eligible": FactValue(True),
            "score": FactValue(42),
            "review_needed": False,
        },
        "metadata": {"rule_name": "benefits"},
    }

    first = extractor.extract_from_dict(session_data)
    second = extractor.extract_from_dict(session_data)

    assert first == second
    assert first[0].pattern_id.startswith("tp_")
    assert first[0].fact_names == ("eligible", "review_needed", "score")
    assert first[0].decision_path == ("eligible", "review_needed")
    assert first[0].rule_name == "benefits"


def test_extract_from_dict_returns_empty_without_working_memory():
    assert TraceExtractor().extract_from_dict({"metadata": {}}) == []


def test_merge_patterns_combines_frequency_and_sorts():
    extractor = TraceExtractor()
    patterns = [
        TracePattern("tp_a", ("a",), ("a",), 1, "rule"),
        TracePattern("tp_b", ("a",), ("a",), 2, "rule"),
        TracePattern("tp_c", ("b",), ("b",), 1, "rule"),
    ]

    merged = extractor._merge_patterns(patterns)

    assert len(merged) == 2
    assert merged[0].fact_names == ("a",)
    assert merged[0].frequency == 3


def test_extract_from_invalid_prov_o_trace_returns_empty():
    assert TraceExtractor().extract("not rdf", session_id="s1") == []


def test_extract_returns_empty_for_blank_trace():
    assert TraceExtractor().extract("  ") == []


def test_extract_parses_turtle_conclusions_and_merges_sessions():
    trace = """
        @prefix inf: <https://inferra.local/ns#> .
        @prefix prov: <http://www.w3.org/ns/prov#> .
        @prefix ex: <https://example.test/> .

        ex:c1 a inf:Conclusion ;
            inf:name "approved" ;
            inf:value "true" ;
            prov:wasGeneratedBy ex:s1 .

        ex:c2 a inf:Conclusion ;
            inf:name "eligible" ;
            inf:value "false" ;
            prov:wasGeneratedBy ex:s1 .

        ex:c3 a inf:Conclusion ;
            inf:value "ignored" ;
            prov:wasGeneratedBy ex:s2 .
    """

    patterns = TraceExtractor().extract(trace, session_id="fallback", rule_name="rule")

    assert len(patterns) == 1
    assert patterns[0].fact_names == ("approved", "eligible")
    assert patterns[0].rule_name == "rule"


def test_extract_from_dict_ignores_empty_fact_names_and_dict_values():
    patterns = TraceExtractor().extract_from_dict(
        {"working_memory": {"": True, "flag": {"value": "true"}}},
        rule_name="rule",
    )

    assert patterns[0].fact_names == ("flag",)
    assert patterns[0].decision_path == ("flag",)


def test_pattern_from_items_returns_none_without_fact_names():
    assert TraceExtractor()._pattern_from_items([("", True)], session_id="s1", rule_name="rule") is None
