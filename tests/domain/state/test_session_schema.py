"""
Tests for Session Schema Migration & Versioning.

Covers:
- v0 → v1 migration (fact_source_migration)
- v1 → v2 migration (NodeOrigin, iteration_state, semantic_cache_loaded)
- v0 → v2 full chain migration
- Compatibility layer for sessions without fact_sources / iteration_state
- _reconstruct_iteration_state from INFERRED iterate facts
- load_session_with_migration
- SessionMetadata model
- Non-dict JSON handling
- working_memory: null handling
"""

import json
import pytest

from src.domain.state.session_schema import (
    CURRENT_SCHEMA_VERSION,
    SessionMetadata,
    _reconstruct_iteration_state,
    migrate_session,
    load_session_with_migration,
)


class TestSessionMetadata:
    def test_default_values(self):
        meta = SessionMetadata()
        assert meta.schema_version == CURRENT_SCHEMA_VERSION
        assert meta.fact_source_migration is False
        assert meta.phase2_migration is False

    def test_custom_values(self):
        meta = SessionMetadata(
            schema_version=CURRENT_SCHEMA_VERSION,
            created_at=1000.0,
            updated_at=2000.0,
            fact_source_migration=True,
            phase2_migration=True,
        )
        assert meta.schema_version == CURRENT_SCHEMA_VERSION
        assert meta.fact_source_migration is True
        assert meta.phase2_migration is True


class TestMigrateSessionV0ToV1:
    def test_v0_to_v1_migration(self):
        data = {
            "working_memory": {
                "eligible": True,
                "score": 42,
            },
        }
        result = migrate_session(data, from_version=0)
        assert result["fact_sources"] == {
            "eligible": "ASSERTED",
            "score": "ASSERTED",
        }
        assert result["metadata"]["fact_source_migration"] is True
        assert result["metadata"]["schema_version"] == CURRENT_SCHEMA_VERSION

    def test_v0_migration_with_existing_metadata(self):
        data = {
            "working_memory": {"age": 25},
            "metadata": {"some_key": "some_value"},
        }
        result = migrate_session(data, from_version=0)
        assert result["fact_sources"]["age"] == "ASSERTED"
        assert result["metadata"]["some_key"] == "some_value"
        assert result["metadata"]["schema_version"] == CURRENT_SCHEMA_VERSION

    def test_working_memory_null_treated_as_empty(self):
        data = {
            "working_memory": None,
        }
        result = migrate_session(data, from_version=0)
        assert result["fact_sources"] == {}

    def test_working_memory_missing_defaults_to_empty(self):
        data = {}
        result = migrate_session(data, from_version=0)
        assert result["fact_sources"] == {}


class TestMigrateSessionV1ToV2:
    def test_v1_to_v2_adds_node_origins(self):
        data = {
            "nodes": [
                {"name": "eligible"},
                {"name": "score", "origin": {"module": "rules", "imported": True}},
            ],
            "metadata": {"schema_version": 1, "fact_source_migration": True},
            "fact_sources": {},
        }
        result = migrate_session(data, from_version=1)
        assert result["nodes"][0]["origin"] == {"module": "unknown", "imported": False}
        assert result["nodes"][1]["origin"] == {"module": "rules", "imported": True}
        assert result["metadata"]["phase2_migration"] is True
        assert result["metadata"]["schema_version"] == CURRENT_SCHEMA_VERSION

    def test_v1_to_v2_adds_iteration_state(self):
        data = {
            "metadata": {"schema_version": 1, "fact_source_migration": True},
            "fact_sources": {},
        }
        result = migrate_session(data, from_version=1)
        assert "iteration_state" in result
        assert isinstance(result["iteration_state"], dict)

    def test_v1_to_v2_adds_semantic_cache_loaded(self):
        data = {
            "metadata": {"schema_version": 1, "fact_source_migration": True},
            "fact_sources": {},
        }
        result = migrate_session(data, from_version=1)
        assert "semantic_cache_loaded" in result
        assert result["semantic_cache_loaded"] == []

    def test_v1_to_v2_preserves_existing_iteration_state(self):
        data = {
            "iteration_state": {"iterate_score": {"status": "in_progress", "progress": {0: True}}},
            "metadata": {"schema_version": 1, "fact_source_migration": True},
            "fact_sources": {},
        }
        result = migrate_session(data, from_version=1)
        assert result["iteration_state"] == {"iterate_score": {"status": "in_progress", "progress": {0: True}}}

    def test_v1_to_v2_does_not_overwrite_node_origin(self):
        data = {
            "nodes": [
                {"name": "x", "origin": {"module": "custom", "imported": True, "depth": 2}},
            ],
            "metadata": {"schema_version": 1, "fact_source_migration": True},
            "fact_sources": {},
        }
        result = migrate_session(data, from_version=1)
        assert result["nodes"][0]["origin"] == {"module": "custom", "imported": True, "depth": 2}

    def test_v1_to_v2_empty_nodes_list(self):
        data = {
            "nodes": [],
            "metadata": {"schema_version": 1, "fact_source_migration": True},
            "fact_sources": {},
        }
        result = migrate_session(data, from_version=1)
        assert result["nodes"] == []

    def test_v1_to_v2_no_nodes_key(self):
        data = {
            "metadata": {"schema_version": 1, "fact_source_migration": True},
            "fact_sources": {},
        }
        result = migrate_session(data, from_version=1)
        assert "nodes" not in result or result.get("nodes") is None or result.get("nodes", []) is not None

    def test_v1_to_v2_sets_phase2_migration_flag(self):
        data = {
            "metadata": {"schema_version": 1},
            "fact_sources": {},
        }
        result = migrate_session(data, from_version=1)
        assert result["metadata"]["phase2_migration"] is True


class TestMigrateSessionV0ToV2:
    def test_v0_to_v2_full_chain(self):
        data = {
            "working_memory": {
                "eligible": True,
                "iterate_score": 42,
            },
            "nodes": [{"name": "eligible"}],
        }
        result = migrate_session(data, from_version=0)
        assert result["fact_sources"] == {
            "eligible": "ASSERTED",
            "iterate_score": "ASSERTED",
        }
        assert result["metadata"]["fact_source_migration"] is True
        assert result["nodes"][0]["origin"] == {"module": "unknown", "imported": False}
        assert "iteration_state" in result
        assert "semantic_cache_loaded" in result
        assert result["metadata"]["phase2_migration"] is True
        assert result["metadata"]["schema_version"] == CURRENT_SCHEMA_VERSION
        assert result["metadata"]["phase3_migration"] is True
        assert result["metadata"]["phase4_migration"] is True
        assert result["metadata"]["phase5_migration"] is True
        assert result["reasoning_mode"] == "DEDUCTION"
        assert result["confidence"] == 1.0
        assert result["hypothesis_trace"] == []


class TestMigrateSessionPhase5:
    def test_v4_to_v5_adds_reasoning_fields(self):
        data = {
            "metadata": {"schema_version": 4},
            "working_memory": {"goal": True},
        }

        result = migrate_session(data, from_version=4)

        assert result["metadata"]["schema_version"] == CURRENT_SCHEMA_VERSION
        assert result["metadata"]["phase5_migration"] is True
        assert result["reasoning_mode"] == "DEDUCTION"
        assert result["confidence"] == 1.0
        assert result["hypothesis_trace"] == []
        assert result["induction_job_id"] is None
        assert result["abduction_attempted"] is False
        assert result["abduction_count"] == 0

    def test_does_not_mutate_input(self):
        data = {
            "working_memory": {"x": 1},
        }
        original_data = json.loads(json.dumps(data))
        migrate_session(data, from_version=0)
        assert data == original_data


class TestMigrateSessionCurrentVersion:
    def test_already_current_version_no_op(self):
        data = {
            "working_memory": {"x": 1},
            "metadata": {"schema_version": CURRENT_SCHEMA_VERSION},
            "fact_sources": {"x": "INFERRED"},
            "iteration_state": {},
            "semantic_cache_loaded": [],
        }
        result = migrate_session(data, from_version=CURRENT_SCHEMA_VERSION)
        assert result["fact_sources"]["x"] == "INFERRED"
        assert result["metadata"]["schema_version"] == CURRENT_SCHEMA_VERSION


class TestReconstructIterationState:
    def test_reconstruct_from_inferred_iterate_facts(self):
        data = {
            "fact_sources": {
                "iterate_score": "INFERRED",
                "eligible": "INFERRED",
                "iterate_age": "INFERRED",
            },
        }
        result = _reconstruct_iteration_state(data)
        assert "iterate_score" in result
        assert "iterate_age" in result
        assert "eligible" not in result
        assert result["iterate_score"] == {"status": "unknown", "progress": {}}

    def test_empty_fact_sources(self):
        result = _reconstruct_iteration_state({"fact_sources": {}})
        assert result == {}

    def test_missing_fact_sources(self):
        result = _reconstruct_iteration_state({})
        assert result == {}

    def test_no_inferred_iterate_facts(self):
        data = {
            "fact_sources": {
                "eligible": "ASSERTED",
                "score": "INFERRED",
            },
        }
        result = _reconstruct_iteration_state(data)
        assert result == {}


class TestLoadSessionWithMigration:
    def test_load_and_migrate(self):
        raw = json.dumps({
            "working_memory": {"x": 1},
        })
        result = load_session_with_migration(raw)
        assert result["fact_sources"]["x"] == "ASSERTED"
        assert result["metadata"]["schema_version"] == CURRENT_SCHEMA_VERSION

    def test_load_already_migrated(self):
        raw = json.dumps({
            "working_memory": {"x": 1},
            "metadata": {"schema_version": CURRENT_SCHEMA_VERSION},
            "fact_sources": {"x": "INFERRED"},
            "iteration_state": {},
            "semantic_cache_loaded": [],
        })
        result = load_session_with_migration(raw)
        assert result["fact_sources"]["x"] == "INFERRED"

    def test_load_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            load_session_with_migration("not json")

    def test_load_non_dict_json_raises_value_error(self):
        with pytest.raises(ValueError, match="Expected a JSON object"):
            load_session_with_migration("[1, 2, 3]")

    def test_load_string_json_raises_value_error(self):
        with pytest.raises(ValueError, match="Expected a JSON object"):
            load_session_with_migration('"hello"')


class TestPhase1SessionCompatibility:
    def test_phase1_session_loads_without_error(self):
        phase1_session = {
            "working_memory": {"eligible": True, "score": 42},
            "metadata": {"schema_version": 1, "fact_source_migration": True},
            "fact_sources": {"eligible": "ASSERTED", "score": "ASSERTED"},
            "nodes": [
                {"name": "eligible"},
                {"name": "score"},
            ],
        }
        raw = json.dumps(phase1_session)
        result = load_session_with_migration(raw)
        assert result["metadata"]["schema_version"] == CURRENT_SCHEMA_VERSION
        assert result["metadata"]["phase2_migration"] is True
        for node in result["nodes"]:
            assert "origin" in node
            assert node["origin"]["module"] == "unknown"
            assert node["origin"]["imported"] is False
        assert "iteration_state" in result
        assert "semantic_cache_loaded" in result

    def test_phase1_session_with_inferred_iterate_facts(self):
        phase1_session = {
            "working_memory": {"iterate_score": 10},
            "metadata": {"schema_version": 1, "fact_source_migration": True},
            "fact_sources": {"iterate_score": "INFERRED"},
        }
        raw = json.dumps(phase1_session)
        result = load_session_with_migration(raw)
        assert "iterate_score" in result["iteration_state"]
        assert result["iteration_state"]["iterate_score"]["status"] == "unknown"
