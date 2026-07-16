import copy
import hashlib
import json
from pathlib import Path


FIXTURE_PATH = Path(__file__).with_name("reasoning_run_review_fixtures.json")
REPO_ROOT = Path(__file__).resolve().parents[3]

REQUIRED_RESULT_STATES = {
    "running",
    "success",
    "needs_review",
    "abstain",
    "contradiction",
    "error",
}
REQUIRED_STAGES = ("parse", "retrieve", "reason", "verify", "summarize", "receipt")
CHECK_STATUSES = {"pass", "fail", "skipped", "unavailable"}


def build_reasoning_run_review_fixture() -> dict:
    return copy.deepcopy(_load_fixture())


def build_reasoning_run_review_run(result_state: str) -> dict:
    fixture = _load_fixture()
    for run in fixture["runs"]:
        if run["result_state"] == result_state:
            return copy.deepcopy(run)

    allowed_states = ", ".join(sorted(REQUIRED_RESULT_STATES))
    raise ValueError(f"Unknown result_state '{result_state}'. Expected one of: {allowed_states}")


def validate_reasoning_run_review_fixture(fixture: dict | None = None) -> list[str]:
    fixture = fixture or _load_fixture()
    errors: list[str] = []
    states = {run.get("result_state") for run in fixture.get("runs", [])}

    if states != REQUIRED_RESULT_STATES:
        errors.append(f"Expected result states {sorted(REQUIRED_RESULT_STATES)}, got {sorted(states)}")

    _validate_source_rule_examples(fixture, errors)

    for run in fixture.get("runs", []):
        state = run.get("result_state", "<unknown>")
        _validate_stage_keys(run, state, errors)
        _validate_check_statuses(run, state, errors)
        _validate_actions(fixture, run, state, errors)
        _validate_claim_evidence(run, state, errors)
        _validate_export_seed(run, state, errors)

    return errors


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _validate_stage_keys(run: dict, state: str, errors: list[str]) -> None:
    stage_keys = [item.get("key") for item in run.get("stage", {}).get("items", [])]
    if stage_keys != list(REQUIRED_STAGES):
        errors.append(f"{state}: expected stages {list(REQUIRED_STAGES)}, got {stage_keys}")


def _validate_check_statuses(run: dict, state: str, errors: list[str]) -> None:
    invalid = {
        check.get("status")
        for check in run.get("checks", [])
        if check.get("status") not in CHECK_STATUSES
    }
    if invalid:
        errors.append(f"{state}: invalid check statuses {sorted(invalid)}")


def _validate_actions(fixture: dict, run: dict, state: str, errors: list[str]) -> None:
    expected = fixture["state_action_matrix"].get(state)
    if not expected:
        errors.append(f"{state}: missing state action matrix")
        return
    if run.get("allowed_actions") != expected:
        errors.append(f"{state}: allowed actions do not match state action matrix")


def _validate_source_rule_examples(fixture: dict, errors: list[str]) -> None:
    examples = fixture.get("source_rule_examples", [])
    if not examples:
        errors.append("fixture: missing source rule examples")
        return

    for example in examples:
        example_id = example.get("id", "<unknown>")
        path = example.get("path")
        if not path or not path.endswith(".txt"):
            errors.append(f"{example_id}: source rule example must be a .txt path")
            continue

        source_path = (REPO_ROOT / path).resolve()
        try:
            source_path.relative_to(REPO_ROOT)
        except ValueError:
            errors.append(f"{example_id}: source rule example path escapes repository")
            continue

        if not source_path.exists():
            errors.append(f"{example_id}: source rule example does not exist at {path}")
            continue

        expected_hash = example.get("sha256")
        actual_hash = _source_rule_example_hash(source_path)
        if expected_hash != actual_hash:
            errors.append(f"{example_id}: source rule example hash mismatch")


def _source_rule_example_hash(source_path: Path) -> str:
    """Hash logical UTF-8 content independently of checkout line endings."""
    content = source_path.read_text(encoding="utf-8")
    canonical_content = content.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(canonical_content.encode("utf-8")).hexdigest()


def _validate_claim_evidence(run: dict, state: str, errors: list[str]) -> None:
    evidence_ids = {item.get("id") for item in run.get("evidence", [])}
    for claim in run.get("claims", []):
        links = claim.get("evidence_links", {})
        linked_ids = set(links.get("supporting", []))
        linked_ids.update(links.get("conflicting", []))
        linked_ids.update(links.get("missing", []))
        availability = claim.get("evidence_availability", {})
        if not linked_ids and availability.get("status") != "none_available":
            errors.append(f"{state}: claim {claim.get('id')} has no evidence link or none reason")
        missing_evidence_refs = linked_ids - evidence_ids
        if missing_evidence_refs:
            errors.append(
                f"{state}: claim {claim.get('id')} links unknown evidence {sorted(missing_evidence_refs)}"
            )


def _validate_export_seed(run: dict, state: str, errors: list[str]) -> None:
    seed = run.get("evaluation_case_export_seed", {})
    required_seed_fields = {
        "question",
        "evidence_refs",
        "result_state",
        "checks",
        "trace_metadata",
        "user_correction_notes",
    }
    missing = required_seed_fields - set(seed)
    if missing:
        errors.append(f"{state}: export seed missing {sorted(missing)}")
    if seed.get("result_state") != state:
        errors.append(f"{state}: export seed result_state mismatch")
