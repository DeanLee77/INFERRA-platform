from __future__ import annotations

import hashlib
import warnings

import pytest

from src.domain.nodes import node_id_utils
from src.domain.nodes.node_id_utils import (
    generate_node_id,
    generate_node_id_legacy,
    reset_parse_context,
    validate_no_existing_collisions,
)


@pytest.fixture(autouse=True)
def _isolate_parse_context():
    reset_parse_context()
    yield
    reset_parse_context()


def test_generate_node_id_is_deterministic_for_same_inputs():
    reset_parse_context()
    first = generate_node_id("Eligibility Module", "applicant_rule", "is_eligible")

    reset_parse_context()
    second = generate_node_id("Eligibility Module", "applicant_rule", "is_eligible")

    assert first == second


def test_generate_node_id_returns_16_char_hex():
    node_id = generate_node_id("Module", "rule", "var")

    assert len(node_id) == 16
    assert all(c in "0123456789abcdef" for c in node_id)


def test_generate_node_id_matches_sha256_prefix():
    content = "Module:rule:var:::"
    expected = hashlib.sha256(content.encode()).hexdigest()[:16]

    assert generate_node_id("Module", "rule", "var") == expected


def test_generate_node_id_differs_when_any_input_changes():
    base = generate_node_id("Module", "rule", "var")
    reset_parse_context()
    diff_module = generate_node_id("OtherModule", "rule", "var")
    reset_parse_context()
    diff_rule = generate_node_id("Module", "other_rule", "var")
    reset_parse_context()
    diff_var = generate_node_id("Module", "rule", "other_var")
    reset_parse_context()
    diff_text = generate_node_id("Module", "rule", "var", normalized_text="some text")
    reset_parse_context()
    diff_parent = generate_node_id("Module", "rule", "var", parent_module_path="parent")
    reset_parse_context()
    diff_ns = generate_node_id("Module", "rule", "var", import_namespace="common@1.0")

    assert len({base, diff_module, diff_rule, diff_var, diff_text, diff_parent, diff_ns}) == 7


def test_generate_node_id_with_import_namespace():
    sid = generate_node_id("mod", "rule", "var", import_namespace="common_rules@2.1.0")
    assert len(sid) == 16

    reset_parse_context()
    sid_local = generate_node_id("mod", "rule", "var", import_namespace="")
    reset_parse_context()
    sid_no_ns = generate_node_id("mod", "rule", "var")

    assert sid != sid_local
    assert sid_local == sid_no_ns


def test_generate_node_id_with_parent_module_path():
    sid = generate_node_id("mod", "rule", "var", parent_module_path="parent_mod")
    reset_parse_context()
    sid_no_parent = generate_node_id("mod", "rule", "var")

    assert sid != sid_no_parent


def test_generate_node_id_with_normalized_text():
    sid = generate_node_id("mod", "rule", "var", normalized_text="applicant IS eligible")
    reset_parse_context()
    sid_no_text = generate_node_id("mod", "rule", "var")

    assert sid != sid_no_text


def test_collision_resolution_appends_monotonic_counter(monkeypatch):
    fixed_prefix = "deadbeefcafebabe"

    class _FakeHash:
        def hexdigest(self):
            return fixed_prefix + "0" * 48

    def _fake_sha256(_payload):
        return _FakeHash()

    monkeypatch.setattr(node_id_utils.hashlib, "sha256", _fake_sha256)

    first = generate_node_id("M", "r", "v1")
    second = generate_node_id("M", "r", "v2")
    third = generate_node_id("M", "r", "v3")

    assert first == fixed_prefix
    assert second == f"{fixed_prefix}:1"
    assert third == f"{fixed_prefix}:2"


def test_reset_parse_context_clears_active_ids():
    generate_node_id("Module", "rule", "var")
    ctx = node_id_utils._get_context()
    assert len(ctx._active_ids) > 0

    reset_parse_context()

    assert len(ctx._active_ids) == 0


def test_generate_node_id_is_idempotent_within_same_session():
    first = generate_node_id("Module", "rule", "var")
    second = generate_node_id("Module", "rule", "var")

    assert first == second
    assert ":" not in second


def test_reset_parse_context_allows_same_id_to_be_regenerated_without_suffix():
    first = generate_node_id("Module", "rule", "var")

    reset_parse_context()
    second = generate_node_id("Module", "rule", "var")

    assert first == second
    assert ":" not in second


def test_validate_no_existing_collisions_passes_when_disjoint():
    generate_node_id("Module", "rule", "var")

    validate_no_existing_collisions({"unrelated_persisted_id"})


def test_validate_no_existing_collisions_raises_on_overlap():
    new_id = generate_node_id("Module", "rule", "var")

    with pytest.raises(ValueError, match="Hash ID collision"):
        validate_no_existing_collisions({new_id})


def test_validate_no_existing_collisions_passes_with_empty_set():
    generate_node_id("Module", "rule", "var")

    validate_no_existing_collisions(set())


def test_line_number_deprecated():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        generate_node_id("Module", "rule", "var", line_number=5)
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "line_number is deprecated" in str(w[0].message)


def test_generate_node_id_legacy():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        sid = generate_node_id_legacy("Module", "rule", 5, "var")
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
    assert len(sid) == 16
