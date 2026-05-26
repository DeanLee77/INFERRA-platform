"""
Session Schema Migration & Versioning.

All persisted sessions carry a schema version for forward-compatible
migration. This module provides the version constant, metadata model,
and migration logic for pre-FactSource sessions.

Phase 1 WS-5: One-time migration tags all existing facts as ASSERTED
(the safe default).

Phase 2: v1→v2 adds NodeOrigin defaults on nodes, iteration_state,
and semantic_cache_loaded tracking.
"""

import copy
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

import structlog

from src.domain.state.fact_source import FactSource

_logger = structlog.get_logger("inferra.session_schema")

CURRENT_SCHEMA_VERSION = 5
_KNOWN_FACT_SOURCE_VALUES = frozenset(source.value for source in FactSource)


class SessionMetadata(BaseModel):
    """Metadata carried by every persisted session."""
    schema_version: int = Field(default=CURRENT_SCHEMA_VERSION, description="Session schema version")
    created_at: float = Field(default=0.0, description="Unix epoch creation timestamp")
    updated_at: float = Field(default=0.0, description="Unix epoch last-update timestamp")
    fact_source_migration: bool = Field(
        default=False,
        description="True once migrated to FactSource tagging",
    )
    phase2_migration: bool = Field(
        default=False,
        description="True once migrated to Phase 2 schema (NodeOrigin, iteration_state, semantic_cache_loaded)",
    )
    phase3_migration: bool = False
    phase4_migration: bool = False
    phase5_migration: bool = False


def _safe_working_memory(data: Dict[str, Any]) -> Dict:
    """Return working_memory as a dict, handling None and non-dict values."""
    wm = data.get("working_memory")
    if wm is None:
        return {}
    if not isinstance(wm, dict):
        _logger.warning("working_memory_not_dict", type=type(wm).__name__)
        return {}
    return wm


def _reconstruct_iteration_state(data: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort reconstruction of iterate state from INFERRED facts."""
    fact_sources = data.get("fact_sources", {})
    iteration_state: Dict[str, Any] = {}
    for name, source in fact_sources.items():
        if _normalise_fact_source_value(source) == FactSource.INFERRED.value and "iterate" in name.lower():
            iteration_state[name] = {"status": "unknown", "progress": {}}
    return iteration_state


def _normalise_fact_source_value(source: Any) -> str:
    if isinstance(source, FactSource):
        return source.value
    if isinstance(source, str) and source in _KNOWN_FACT_SOURCE_VALUES:
        return source
    return FactSource.INFERRED.value


def _normalise_fact_sources(data: Dict[str, Any]) -> None:
    """Keep persisted fact-source maps forward-compatible with future enum values."""
    fact_sources = data.get("fact_sources")
    if not isinstance(fact_sources, dict):
        return
    for name, source in list(fact_sources.items()):
        normalised = _normalise_fact_source_value(source)
        if normalised != source:
            _logger.warning(
                "fact_source_defaulted_to_inferred",
                fact_name=name,
                original_source=source,
                default_source=normalised,
            )
        fact_sources[name] = normalised


def migrate_session(data: Dict[str, Any], from_version: int = 0) -> Dict[str, Any]:
    """
    Migrate a session dict to the current schema version.

    Returns a NEW dict; the input is not mutated.

    Migration steps:
    - v0 → v1: Tag all existing working_memory facts as ASSERTED.
                Add fact_sources dict. Set metadata.fact_source_migration.
    - v1 → v2: Add NodeOrigin defaults on nodes (module="unknown",
                imported=False). Add iteration_state dict. Add
                semantic_cache_loaded list. Set metadata.phase2_migration.

    Args:
        data: Raw session dict (deserialised from JSON)
        from_version: Schema version of the input data

    Returns:
        Migrated session dict (new copy)
    """
    if from_version >= CURRENT_SCHEMA_VERSION:
        return copy.deepcopy(data)

    result = copy.deepcopy(data)

    if from_version < 1:
        working_memory = _safe_working_memory(result)
        result["fact_sources"] = {
            name: "ASSERTED" for name in working_memory
        }
        result.setdefault("metadata", {})
        result["metadata"]["fact_source_migration"] = True
        _logger.info("migrated_session_v0_to_v1")

    if from_version < 2:
        for node in result.get("nodes", []):
            if isinstance(node, dict):
                node.setdefault("origin", {"module": "unknown", "imported": False})
        result.setdefault("iteration_state", {})
        if "iteration_state" not in result or not result["iteration_state"]:
            result["iteration_state"] = _reconstruct_iteration_state(result)
        result.setdefault("semantic_cache_loaded", [])
        result.setdefault("metadata", {})
        result["metadata"]["phase2_migration"] = True
        _logger.info("migrated_session_v1_to_v2")

    if from_version < 3:
        result.setdefault("iteration_count", 0)
        result.setdefault("ontology_delta", 0)
        result.setdefault("question_strategy_name", "conservative")
        result.setdefault("convergence_trace", [])
        result.setdefault("ontology_pre_reasoned", False)
        result.setdefault("prov_o_trace", None)
        result.setdefault("metadata", {})
        result["metadata"]["phase3_migration"] = True
        _logger.info("migrated_session_v2_to_v3")

    if from_version < 4:
        result.setdefault("owner_id", None)
        result.setdefault("feature_flags", {})
        result.setdefault("api_enrichment", {})
        result.setdefault("metadata", {})
        result["metadata"]["phase4_migration"] = True
        _logger.info("migrated_session_v3_to_v4")

    if from_version < 5:
        result.setdefault("reasoning_mode", "DEDUCTION")
        result.setdefault("confidence", 1.0)
        result.setdefault("hypothesis_trace", [])
        result.setdefault("induction_job_id", None)
        result.setdefault("abduction_attempted", False)
        result.setdefault("abduction_count", 0)
        result.setdefault("metadata", {})
        result["metadata"]["phase5_migration"] = True
        _logger.info("migrated_session_v4_to_v5")

    _normalise_fact_sources(result)
    result.setdefault("metadata", {})["schema_version"] = CURRENT_SCHEMA_VERSION
    return result


def load_session_with_migration(raw_json: str) -> Dict[str, Any]:
    """
    Load a session from JSON, applying migrations as needed.

    Args:
        raw_json: JSON string from persistence

    Returns:
        Migrated session dict

    Raises:
        ValueError: If the JSON is valid but not a dict
        json.JSONDecodeError: If the JSON is malformed
    """
    data = json.loads(raw_json)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object, got {type(data).__name__}")
    version = data.get("metadata", {}).get("schema_version", 0)
    if version < CURRENT_SCHEMA_VERSION:
        data = migrate_session(data, from_version=version)
    return data
