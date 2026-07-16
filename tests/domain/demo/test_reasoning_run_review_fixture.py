import pytest

from src.domain.demo.reasoning_run_review_fixture import REPO_ROOT
from src.domain.demo.reasoning_run_review_fixture import (
    CHECK_STATUSES,
    REQUIRED_RESULT_STATES,
    REQUIRED_STAGES,
    build_reasoning_run_review_fixture,
    build_reasoning_run_review_run,
    validate_reasoning_run_review_fixture,
    _source_rule_example_hash,
)


def _runs_by_state() -> dict[str, dict]:
    fixture = build_reasoning_run_review_fixture()
    return {run["result_state"]: run for run in fixture["runs"]}


def test_reasoning_run_review_fixture_covers_required_states_and_stages():
    fixture = build_reasoning_run_review_fixture()
    runs_by_state = {run["result_state"]: run for run in fixture["runs"]}

    assert set(fixture["required_result_states"]) == REQUIRED_RESULT_STATES
    assert set(runs_by_state) == REQUIRED_RESULT_STATES
    assert validate_reasoning_run_review_fixture(fixture) == []

    for state, run in runs_by_state.items():
        assert [stage["key"] for stage in run["stage"]["items"]] == list(REQUIRED_STAGES), state
        assert {check["status"] for check in run["checks"]}.issubset(CHECK_STATUSES), state
        assert run["question"]
        assert run["data_policy"] if "data_policy" in run else fixture["data_policy"]["synthetic_only"]


def test_source_rule_examples_are_txt_files_grounded_in_reference_examples():
    fixture = build_reasoning_run_review_fixture()

    source_examples = fixture["source_rule_examples"]
    assert {source["id"] for source in source_examples} == {
        "example_mrca_master_convergence",
        "example_drca_master_convergence",
        "example_vea_service_options",
    }

    for source in source_examples:
        path = REPO_ROOT / source["path"]
        assert source["path"].startswith("docs/reference/examples/")
        assert source["path"].endswith(".txt")
        assert path.exists()
        assert source["fact_source"] == "ASSERTED"
        assert source["origin_module"] == "docs.reference.examples"
        assert len(source["sha256"]) == 64


def test_source_rule_example_hash_is_line_ending_independent(tmp_path):
    lf_path = tmp_path / "lf.txt"
    crlf_path = tmp_path / "crlf.txt"
    lf_path.write_bytes(b"first\nsecond\n")
    crlf_path.write_bytes(b"first\r\nsecond\r\n")

    assert _source_rule_example_hash(lf_path) == _source_rule_example_hash(crlf_path)


@pytest.mark.parametrize("state", sorted(REQUIRED_RESULT_STATES))
def test_state_actions_match_workflow_matrix(state):
    fixture = build_reasoning_run_review_fixture()
    run = build_reasoning_run_review_run(state)

    assert run["allowed_actions"] == fixture["state_action_matrix"][state]


def test_claims_link_to_evidence_or_explicitly_report_none_available():
    fixture = build_reasoning_run_review_fixture()

    for run in fixture["runs"]:
        evidence_ids = {item["id"] for item in run["evidence"]}
        for claim in run["claims"]:
            links = claim["evidence_links"]
            linked_ids = set(links["supporting"] + links["conflicting"] + links["missing"])
            assert linked_ids or claim["evidence_availability"]["status"] == "none_available"
            assert linked_ids.issubset(evidence_ids)
            assert claim["fact_source"]
            assert claim["origin_module"]
            assert claim["import_metadata"]["import_id"]


def test_contradiction_pairs_claims_and_disables_unqualified_acceptance():
    run = build_reasoning_run_review_run("contradiction")
    contradiction = run["contradictions"][0]
    claim_ids = {claim["id"] for claim in run["claims"]}

    assert contradiction["claim_a"] in claim_ids
    assert contradiction["claim_b"] in claim_ids
    assert contradiction["unqualified_accept_disabled"] is True
    assert "accept_internal_use" in run["allowed_actions"]["disallowed"]
    assert run["allowed_actions"]["primary"] == "resolve_contradiction"


def test_abstain_has_no_pseudo_answer_and_keeps_recovery_actions():
    run = build_reasoning_run_review_run("abstain")

    assert run["conclusion"]["text"] is None
    assert run["conclusion"]["display_mode"] == "abstention"
    assert "add_evidence" == run["allowed_actions"]["primary"]
    assert "revise_scope" in run["allowed_actions"]["secondary"]
    assert "answer_headline" in run["allowed_actions"]["disallowed"]


def test_needs_review_surfaces_uncertainty_before_accept_with_caveat():
    run = build_reasoning_run_review_run("needs_review")

    assert run["conclusion"]["uncertainty_reasons"]
    assert run["resolution_policy"]["show_uncertainty_before_accept_with_caveat"] is True
    assert run["allowed_actions"]["primary"] == "review_evidence"
    assert "accept_with_caveat" in run["allowed_actions"]["secondary"]
    assert "accept_internal_use" in run["allowed_actions"]["disallowed"]


def test_success_keeps_residual_uncertainty_and_provenance_access():
    run = build_reasoning_run_review_run("success")

    assert run["allowed_actions"]["primary"] == "accept_internal_use"
    assert run["conclusion"]["confidence_band"] == "high"
    assert run["conclusion"]["uncertainty_reasons"]
    assert run["trace"]["graph_available"] is True
    assert run["trace"]["timeline_available"] is True
    assert run["trace"]["raw_trace_available"] is True
    assert "inspect_trace" in run["allowed_actions"]["secondary"]


@pytest.mark.parametrize("state", sorted(REQUIRED_RESULT_STATES))
def test_correction_and_export_seed_preserve_review_evidence(state):
    run = build_reasoning_run_review_run(state)
    seed = run["evaluation_case_export_seed"]

    assert run["revision_lineage"]["preserves_original_run"] is True
    assert run["revision_lineage"]["original_run_id"]
    assert run["revision_lineage"]["diff_summary"]
    assert seed["question"] == run["question"]
    assert seed["result_state"] == state
    assert isinstance(seed["evidence_refs"], list)
    assert seed["checks"]
    assert {"rule_hash", "graph_hash"}.issubset(seed["trace_metadata"])
    assert "user_correction_notes" in seed


def test_fixture_rejects_unknown_state_with_allowed_values():
    with pytest.raises(ValueError) as exc:
        build_reasoning_run_review_run("unsupported")

    message = str(exc.value)
    assert "unsupported" in message
    for state in REQUIRED_RESULT_STATES:
        assert state in message
