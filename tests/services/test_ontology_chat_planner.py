from src.services.ontology_chat_planner import _planner_context_payload, _planner_prompt


def test_planner_prompt_guides_answer_fact_queries_away_from_case_run():
    payload = _planner_context_payload(
        question=(
            "Show the user-provided answers and fact values in this case run, "
            "including question name, value, fact source, and related node name."
        ),
        selected_graphs=["http://inferra.ai/schema#case-run/rule/example/full-semantic/case-a"],
        graph_counts={
            "http://inferra.ai/schema#case-run/rule/example/full-semantic/case-a": 123
        },
        row_limit=100,
        timeout_seconds=10,
        predicate_summary=[],
        sample_triples=[],
        case_run_metadata=[],
    )

    recipes = payload["query_recipes"]
    answer_recipe = next(
        recipe
        for recipe in recipes
        if recipe["intent"] == "user_provided_answers_and_fact_values"
    )
    prompt = _planner_prompt(payload)

    assert "inf:CaseFact" in answer_recipe["sparql_shape"]
    assert "inf:SemanticQuestionStrategyTrace" in answer_recipe["sparql_shape"]
    assert '"asserted"' in answer_recipe["sparql_shape"]
    assert "Never use rdf:type inf:CaseRun" in prompt
    assert "questionName, value, factSource, or nodeName" in prompt
