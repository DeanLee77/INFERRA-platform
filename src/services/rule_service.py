import hashlib
import json
import re
from typing import Any, List, Optional, Set

import structlog

from src.adapters.outbound.ontology.fuseki_adapter import INF_NS, FusekiAdapter
from src.adapters.outbound.ontology.inferra_to_rdf_compiler import (
    COMPILER_VERSION,
    InferraToRdfCompiler,
)
from src.domain.exceptions import RuleValidationError
from src.domain.fact_values import FactValue, FactValueType
from src.domain.graph.graph_serialization import serialize_graph
from src.domain.imports.import_matchers import extract_imports
from src.domain.imports.import_resolver import (
    CircularImportError,
    ImportDepthExceededError,
    RuleLoadTimeoutError,
    RuleSetImportResolver,
)
from src.domain.state.feature_flags import FeatureFlags
from src.domain.models.rule import RuleEntity, RuleFileEntity
from src.domain.models.rule_file_payload import encode_rule_file_payload
from src.domain.nodes.node import Node
from src.domain.nodes.node_set import NodeSet
from src.domain.nodes.record import HistoryRecord
from src.domain.rule_parser.rule_set_parser import RuleSetParser
from src.domain.rule_parser.rule_set_reader import RuleSetReader
from src.domain.rule_parser.rule_set_scanner import RuleSetScanner
from src.ports.rule_repository_port import RuleRepositoryPort
from src.services.rule_validation_service import (
    RuleValidationService,
    ValidationError,
    ValidationResult,
)
from src.services.ontology_artifact_service import build_rule_set_ontology_artifact
from src.tasks.event_publisher import on_rule_updated
from src.tasks.rule_sync import (
    build_projection_source_hash,
    get_projection_metadata,
    list_rule_dead_letters,
)


log = structlog.get_logger()


class RuleService:
    def __init__(
        self,
        repository: RuleRepositoryPort,
        validation_service: Optional[RuleValidationService] = None,
    ):
        self._repository = repository
        self._validation_service = validation_service or RuleValidationService()

    def get_rule_by_name(self, rule_name: str) -> RuleEntity:
        rule = self._repository.find_rule_by_rule_name(rule_name)
        if rule is None:
            raise LookupError(f"Rule '{rule_name}' was not found")
        return rule

    def get_rule_file_or_raise(self, rule_name: str) -> RuleFileEntity:
        rule_file = self._repository.find_rule_text_by_rule_name(rule_name)
        if rule_file is None or rule_file.files is None:
            raise LookupError(f"Rule '{rule_name}' was not found or has no stored file")
        return rule_file

    def decode_rule_file(self, rule_file: RuleFileEntity) -> str:
        try:
            return rule_file.decode_files()
        except (AttributeError, UnicodeDecodeError, ValueError) as exc:
            raise ValueError("Stored rule file could not be decoded as UTF-8") from exc

    def get_rule_text(self, rule_name: str) -> str:
        return self.decode_rule_file(self.get_rule_file_or_raise(rule_name))

    def build_rule_set_parser(
        self,
        rule_name: str,
        history_dict: dict[str, HistoryRecord] | None = None,
    ) -> RuleSetParser:
        """Build a RuleSetParser for the given rule.
        
        Args:
            rule_name: Name of the rule to parse
            history_dict: Optional history dictionary for ML-enhanced inference
            
        Returns:
            RuleSetParser with parsed NodeSet
        """
        if not rule_name:
            raise ValueError("ruleName is required")

        rule_text = self.get_rule_text(rule_name)

        parse_text = self._build_import_aware_rule_text(rule_name, rule_text)
        rule_set_parser = self._parse_rule_text(rule_name, parse_text, history_dict)

        if not rule_set_parser.get_node_set().get_sorted_node_list():
            raise ValueError(f"Rule '{rule_name}' could not be parsed into a valid node set")

        return rule_set_parser

    def get_rule_tree_data(self, rule_name: str) -> str:
        rule_text = self.get_rule_text(rule_name)
        self.build_rule_set_parser(rule_name)
        return rule_text

    def get_latest_rule_file(self, rule_name: str) -> RuleFileEntity:
        return self.get_rule_file_or_raise(rule_name)

    def get_rule_graph_data(self, rule_name: str) -> dict[str, Any]:
        latest_file = self.get_latest_rule_file(rule_name)
        rule_text = self.decode_rule_file(latest_file)
        expanded_rule_text = self._build_import_aware_rule_text(rule_name, rule_text)
        graph_json = latest_file.decode_graph_json()
        source = "stored"

        if graph_json is None:
            parser = self._parse_rule_text(rule_name, expanded_rule_text)
            graph = parser.get_node_set().get_graph()
            if graph is None:
                raise ValueError("Parsed rule set did not produce a dependency graph")
            graph_json = serialize_graph(graph)
            source = "generated"

        graph_payload = json.loads(graph_json)
        return {
            "rule_name": rule_name,
            "source": source,
            "rule_text": rule_text,
            "expanded_rule_text": expanded_rule_text,
            "schema_version": graph_payload.get("schema_version", 1),
            "nodes": graph_payload.get("nodes", []),
            "edges": graph_payload.get("edges", []),
        }

    def get_rule_graph_data_for_text(self, rule_name: str, rule_text: str) -> dict[str, Any]:
        expanded_rule_text = (
            self._build_import_aware_rule_text(rule_name, rule_text)
            if rule_name and extract_imports(rule_text)
            else rule_text
        )
        parser = self._parse_rule_text(rule_name, expanded_rule_text)
        graph = parser.get_node_set().get_graph()
        if graph is None:
            raise ValueError("Parsed rule set did not produce a dependency graph")
        graph_payload = json.loads(serialize_graph(graph))
        return {
            "rule_name": rule_name,
            "source": "draft",
            "rule_text": rule_text,
            "expanded_rule_text": expanded_rule_text,
            "schema_version": graph_payload.get("schema_version", 1),
            "nodes": graph_payload.get("nodes", []),
            "edges": graph_payload.get("edges", []),
        }

    def get_rule_ontology_data(self, rule_name: str) -> dict[str, Any]:
        rule_text = self.get_rule_text(rule_name)
        expanded_rule_text = self._build_import_aware_rule_text(rule_name, rule_text)
        triples = InferraToRdfCompiler.compile(expanded_rule_text, rule_name)
        unique_triples = sorted(set(triples))
        source_hash = build_projection_source_hash(expanded_rule_text)
        graph_uri = FusekiAdapter.rule_projection_graph_uri(rule_name)
        stored_triples, stored_triple_count, fuseki_error = self._read_stored_projection(graph_uri)
        metadata = get_projection_metadata(rule_name) or {}
        dead_letters = list_rule_dead_letters(rule_name, source_hash=source_hash, limit=10)
        status = self._build_projection_status(
            compiled_triples=unique_triples,
            stored_triples=stored_triples,
            stored_triple_count=stored_triple_count,
            source_hash=source_hash,
            metadata=metadata,
            dead_letters=dead_letters,
            fuseki_error=fuseki_error,
        )
        artifact = build_rule_set_ontology_artifact(
            rule_name=rule_name,
            triples=unique_triples,
            source_hash=source_hash,
            graph_uri=graph_uri,
            metadata=status,
        )
        return {
            "rule_name": rule_name,
            "source": "compiled",
            "triple_count": len(unique_triples),
            "source_hash": source_hash,
            "compiler_version": COMPILER_VERSION,
            "compiled_triple_count": len(unique_triples),
            "stored_triple_count": stored_triple_count,
            "graph_uri": graph_uri,
            **status,
            "artifact": artifact.metadata_dict(),
            "triples": [
                {"subject": subject, "predicate": predicate, "object": obj}
                for subject, predicate, obj in unique_triples
            ],
            **self._ontology_graph_from_triples(unique_triples),
        }

    def get_rule_ontology_artifact(self, rule_name: str) -> dict[str, Any]:
        ontology = self.get_rule_ontology_data(rule_name)
        triples = [
            (item["subject"], item["predicate"], item["object"])
            for item in ontology["triples"]
        ]
        artifact = build_rule_set_ontology_artifact(
            rule_name=rule_name,
            triples=triples,
            source_hash=ontology["source_hash"],
            graph_uri=ontology["graph_uri"],
            metadata=ontology,
        )
        return artifact.response_dict()

    def sync_rule_ontology(self, rule_name: str) -> dict[str, Any]:
        rule_text = self.get_rule_text(rule_name)
        expanded_rule_text = self._build_import_aware_rule_text(rule_name, rule_text)
        triples = InferraToRdfCompiler.compile(expanded_rule_text, rule_name)
        unique_triple_count = len(set(triples))
        source_hash = build_projection_source_hash(expanded_rule_text)
        graph_uri = FusekiAdapter.rule_projection_graph_uri(rule_name)
        task_id = on_rule_updated(rule_name, expanded_rule_text)
        return {
            "rule_name": rule_name,
            "status": "published" if task_id else "skipped",
            "sync_status": "syncing" if task_id else "unknown",
            "task_id": task_id,
            "triple_count": unique_triple_count,
            "source_hash": source_hash,
            "compiler_version": COMPILER_VERSION,
            "compiled_triple_count": unique_triple_count,
            "stored_triple_count": None,
            "graph_uri": graph_uri,
        }

    def sync_rule_collection_ontology(self, rule_name: str) -> dict[str, Any]:
        rule_text = self.get_rule_text(rule_name)
        names = self._rule_collection_names(rule_name, rule_text)
        return self._sync_rule_names(names)

    def sync_all_rule_ontologies(self) -> dict[str, Any]:
        names = [
            str(rule.get("rule_name") or rule.get("name") or "")
            for rule in self.list_rules()
            if rule.get("rule_name") or rule.get("name")
        ]
        return self._sync_rule_names(names)

    @staticmethod
    def _ontology_graph_from_triples(triples: list[tuple[str, str, str]]) -> dict[str, Any]:
        node_map: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, str | None]] = []
        in_degree: dict[str, int] = {}
        out_degree: dict[str, int] = {}

        def ensure_node(uri: str) -> dict[str, Any]:
            node = node_map.setdefault(uri, {"uri": uri, "name": None, "types": []})
            return node

        for subject, predicate, obj in triples:
            ensure_node(subject)
            if predicate == f"{INF_NS}name":
                node_map[subject]["name"] = obj
                continue
            if predicate.endswith("#type"):
                node = ensure_node(subject)
                if obj not in node["types"]:
                    node["types"].append(obj)
                continue
            if obj.startswith(("http://", "https://", "urn:")):
                ensure_node(obj)
                out_degree[subject] = out_degree.get(subject, 0) + 1
                in_degree[obj] = in_degree.get(obj, 0) + 1
                edges.append({
                    "subject": subject,
                    "predicate": predicate,
                    "object": obj,
                    "predicate_key": RuleService._ontology_value_key(predicate),
                    "dependency_type": RuleService._ontology_dependency_type(predicate),
                })

        max_degree = 0
        for uri, node in node_map.items():
            incoming = in_degree.get(uri, 0)
            outgoing = out_degree.get(uri, 0)
            degree = incoming + outgoing
            max_degree = max(max_degree, degree)
            node["type_key"] = RuleService._ontology_node_type_key(node["types"])
            node["in_degree"] = incoming
            node["out_degree"] = outgoing
            node["degree"] = degree

        for node in node_map.values():
            node["layout_weight"] = (
                round(float(node["degree"]) / float(max_degree), 4)
                if max_degree > 0
                else 0.0
            )

        return {"nodes": list(node_map.values()), "edges": edges}

    @staticmethod
    def _ontology_node_type_key(types: list[str]) -> str | None:
        type_keys = [RuleService._ontology_value_key(type_uri) for type_uri in types]
        for key in (
            "rule_set",
            "input_declaration",
            "fixed_declaration",
            "iterate_rule",
            "and_rule",
            "or_rule",
            "conclusion",
            "rule_node",
        ):
            if key in type_keys:
                return key
        return type_keys[0] if type_keys else None

    @staticmethod
    def _ontology_dependency_type(predicate: str) -> str | None:
        key = RuleService._ontology_value_key(predicate)
        if key == "and_depends_on":
            return "AND"
        if key == "or_depends_on":
            return "OR"
        if key == "not_depends_on":
            return "NOT"
        if key == "mandatory_depends_on":
            return "MANDATORY"
        if key == "known_depends_on":
            return "KNOWN"
        if key == "optional_depends_on":
            return "OPTIONALLY"
        if key == "possible_depends_on":
            return "POSSIBLY"
        if key in {"contains_node", "declares"}:
            return "MANDATORY"
        return None

    @staticmethod
    def _ontology_value_key(value: str) -> str:
        fragment = re.split(r"[/#:]", value.rstrip("/#:"), maxsplit=0)[-1] or value
        fragment = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", fragment)
        return re.sub(r"[^a-zA-Z0-9]+", "_", fragment).strip("_").lower() or "unknown"

    @staticmethod
    def _read_stored_projection(graph_uri: str) -> tuple[list[tuple[str, str, str]], int, str | None]:
        try:
            stored_triple_count = FusekiAdapter.get_named_graph_triple_count(graph_uri)
            stored_triples = (
                FusekiAdapter.get_named_graph_all_triples(graph_uri)
                if stored_triple_count > 0
                else []
            )
            return stored_triples, stored_triple_count, None
        except Exception as exc:
            log.warning(
                "ontology_projection_read_failed",
                graph_uri=graph_uri,
                error=str(exc),
            )
            return [], 0, str(exc)

    @staticmethod
    def _build_projection_status(
        compiled_triples: list[tuple[str, str, str]],
        stored_triples: list[tuple[str, str, str]],
        stored_triple_count: int,
        source_hash: str,
        metadata: dict[str, Any],
        dead_letters: list[dict[str, Any]],
        fuseki_error: str | None,
    ) -> dict[str, Any]:
        dead_letter = dead_letters[0] if dead_letters else None
        metadata_status = metadata.get("sync_status")
        metadata_source_hash = metadata.get("source_hash")
        metadata_compiler_version = metadata.get("compiler_version")
        metadata_matches_source = metadata_source_hash == source_hash
        metadata_failure = metadata if metadata_matches_source else {}

        base = {
            "sync_timestamp": metadata.get("sync_timestamp"),
            "dead_letter_visible": bool(dead_letter or metadata_failure.get("dead_letter_visible")),
            "dead_letter_id": (
                (dead_letter or {}).get("dead_letter_id")
                or metadata_failure.get("dead_letter_id")
            ),
            "last_error_code": (
                (dead_letter or {}).get("last_error_code")
                or metadata_failure.get("last_error_code")
            ),
            "last_error_summary": (
                (dead_letter or {}).get("last_error_summary")
                or metadata_failure.get("last_error_summary")
            ),
            "job_id": metadata.get("job_id"),
        }

        def finish(sync_status: str, integrity_status: str, mismatch_reason: str | None = None) -> dict[str, Any]:
            return {
                **base,
                "sync_status": sync_status,
                "integrity_status": integrity_status,
                "integrity_mismatch_reason": mismatch_reason,
            }

        if dead_letter is not None:
            return finish("dead_lettered", "fail", "dead_lettered")

        if metadata_status in {"dead_lettered", "failed"} and metadata_matches_source:
            return finish(str(metadata_status), "fail", str(metadata_status))

        if metadata_status == "syncing" and metadata_matches_source:
            return finish("syncing", "unknown", None)

        if fuseki_error is not None:
            base["last_error_code"] = base["last_error_code"] or "FUSEKI_QUERY_FAILED"
            base["last_error_summary"] = base["last_error_summary"] or " ".join(fuseki_error.split())[:300]
            return finish("failed", "unknown", "fuseki_query_failed")

        if stored_triple_count == 0:
            return finish("missing", "missing", "stored_graph_missing")

        if metadata_source_hash != source_hash:
            reason = "source_hash_mismatch" if metadata_source_hash else "projection_metadata_missing"
            return finish("stale", "fail", reason)

        if metadata_compiler_version != COMPILER_VERSION:
            return finish("stale", "fail", "compiler_version_mismatch")

        compiled_triple_set = set(compiled_triples)
        stored_triple_set = set(stored_triples)

        if stored_triple_count != len(compiled_triple_set):
            return finish("stale", "fail", "triple_count_mismatch")

        if stored_triple_set != compiled_triple_set:
            return finish("stale", "fail", "triple_content_mismatch")

        return finish("current", "pass", None)

    def _rule_collection_names(self, rule_name: str, rule_text: str) -> list[str]:
        names = [rule_name]
        if not extract_imports(rule_text):
            return names
        for imported_name, _ in self._load_imported_rule_texts(rule_name, rule_text):
            if imported_name not in names:
                names.append(imported_name)
        return names

    def _sync_rule_names(self, names: list[str]) -> dict[str, Any]:
        seen: set[str] = set()
        items: list[dict[str, Any]] = []
        for name in names:
            if not name or name in seen:
                continue
            seen.add(name)
            try:
                items.append(self.sync_rule_ontology(name))
            except Exception as exc:
                items.append(
                    {
                        "rule_name": name,
                        "status": "failed",
                        "sync_status": "failed",
                        "task_id": None,
                        "triple_count": 0,
                        "source_hash": None,
                        "compiler_version": COMPILER_VERSION,
                        "compiled_triple_count": 0,
                        "stored_triple_count": None,
                        "graph_uri": FusekiAdapter.rule_projection_graph_uri(name),
                        "last_error_code": "SYNC_REQUEST_FAILED",
                        "last_error_summary": " ".join(str(exc).split())[:300],
                    }
                )

        failed = sum(1 for item in items if item["status"] == "failed")
        published = sum(1 for item in items if item["status"] == "published")
        skipped = sum(1 for item in items if item["status"] == "skipped")
        status = "failed" if failed == len(items) and items else "partial_failed" if failed else "published" if published else "skipped"
        return {
            "status": status,
            "requested_count": len(items),
            "published_count": published,
            "skipped_count": skipped,
            "failed_count": failed,
            "items": items,
        }

    def get_latest_rule_history(self, rule_name: str) -> dict[str, Any]:
        result = self._repository.find_rule_by_rule_name_with_latest_history(rule_name)
        if result is None or result.get("rule") is None:
            raise LookupError(f"Rule '{rule_name}' was not found")

        history = result.get("history")
        if history is None:
            raise LookupError(f"Rule '{rule_name}' has no stored history")

        return result

    def list_rules(self) -> list[dict[str, Any]]:
        return self._repository.find_all_rules()

    def update_rule(self, old_rule_name: str, new_rule_name: str, new_rule_category: str) -> RuleEntity:
        updated = self._repository.update_rule_name_and_category(
            old_rule_name,
            new_rule_name,
            new_rule_category,
        )
        if not updated:
            raise LookupError(f"Rule '{old_rule_name}' was not found")

        rule = self._repository.find_rule_by_rule_name(new_rule_name)
        if rule is None:
            raise RuntimeError(f"Updated rule '{new_rule_name}' could not be reloaded")
        return rule

    def create_rule(self, name: str, category: str, description: str) -> RuleEntity:
        self._repository.create_rule(
            {
                "rule_name": name,
                "rule_category": category,
                "rule_description": description,
            }
        )
        rule = self._repository.find_rule_by_rule_name(name)
        if rule is None:
            raise RuntimeError(f"Rule '{name}' could not be created")
        return rule

    def save_converted_rule(
        self,
        name: str,
        category: str,
        description: str,
        rule_text: str,
        bypass_validation: bool = False,
        waived_error_ids: Optional[List[str]] = None,
        target_node_name: Optional[str] = None,
    ) -> RuleEntity:
        if not bypass_validation:
            self._validate_rule_text(rule_text, name, waived_error_ids=waived_error_ids)

        rule_details = {
            "rule_name": name,
            "rule_category": category,
            "rule_description": description,
        }
        if target_node_name is not None:
            rule_details["target_node_name"] = target_node_name

        rule_id = self._repository.create_rule(rule_details)
        self._repository.create_rule_file(
            rule_id,
            self._encode_rule_file(rule_text, name, require_graph=not bypass_validation),
        )
        self._publish_rule_updated(name, rule_text)

        rule = self._repository.find_rule_by_rule_name(name)
        if rule is None:
            raise RuntimeError(f"Converted rule '{name}' could not be loaded")
        return rule

    def create_rule_file(
        self,
        rule_name: str,
        rule_text: str,
        bypass_validation: bool = False,
        waived_error_ids: Optional[List[str]] = None,
    ) -> str:
        if not bypass_validation:
            self._validate_rule_text(rule_text, rule_name, waived_error_ids=waived_error_ids)

        rule_id = self._repository.find_id_by_name(rule_name)
        if rule_id is None:
            raise LookupError(f"Rule '{rule_name}' was not found")

        self._repository.create_rule_file(
            rule_id,
            self._encode_rule_file(rule_text, rule_name, require_graph=not bypass_validation),
        )
        self._publish_rule_updated(rule_name, rule_text)
        return self.get_rule_text(rule_name)

    def _publish_rule_updated(self, rule_name: str, rule_text: str) -> None:
        """Publish async ontology sync without making rule persistence fragile."""
        try:
            on_rule_updated(rule_name, self._build_import_aware_rule_text(rule_name, rule_text))
        except Exception as exc:
            log.warning(
                "rule_updated_event_publish_failed",
                rule_name=rule_name,
                error=str(exc),
            )

    def get_history_for_ml_inference(
        self,
        rule_name: str,
    ) -> dict[str, HistoryRecord] | None:
        """Get the history dictionary for ML-enhanced inference.
        
        Args:
            rule_name: Name of the rule
            
        Returns:
            HistoryRecord dictionary or None if no history exists
        """
        result = self._repository.find_rule_by_rule_name_with_latest_history(rule_name)
        if result is None:
            return None
        return self._history_records_from_payload(result.get("history"))

    def _history_records_from_payload(
        self,
        history_payload: Any,
    ) -> dict[str, HistoryRecord] | None:
        if history_payload is None:
            return None
        if not isinstance(history_payload, dict):
            return {}

        records: dict[str, HistoryRecord] = {}
        for node_name, raw_record in history_payload.items():
            if isinstance(raw_record, HistoryRecord):
                records[str(node_name)] = raw_record
                continue
            if not isinstance(raw_record, dict):
                continue

            records[str(node_name)] = HistoryRecord(
                name=str(node_name),
                true_count=self._history_count(
                    raw_record.get("true", raw_record.get("true_count", 0)),
                ),
                false_count=self._history_count(
                    raw_record.get("false", raw_record.get("false_count", 0)),
                ),
            )
        return records

    @staticmethod
    def _history_count(value: Any) -> int:
        if isinstance(value, bool):
            return int(value)
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    def save_session_history(self, rule_name: str, working_memory: dict[str, FactValue]) -> None:
        """
        Persist assessment working memory as rule history for future inference runs.

        Args:
            rule_name: Name of the rule whose history is being updated
            working_memory: Current assessment working memory
        """
        rule = self.get_rule_by_name(rule_name)
        history: dict[str, Any] = {}

        for work_item, fact_value in working_memory.items():
            item_history: dict[str, str] = {}

            if fact_value.get_value_type() == FactValueType.BOOLEAN:
                if fact_value.get_value() is True:
                    item_history["true"] = "1"
                    item_history["false"] = "0"
                else:
                    item_history["true"] = "0"
                    item_history["false"] = "1"
            else:
                item_history["true"] = "1"
                item_history["false"] = "0"

            item_history["type"] = str(fact_value.get_value_type())
            history[work_item] = item_history

        self._repository.create_rule_history(rule.rule_id, history)

    def _validate_rule_text(
        self,
        rule_text: str,
        rule_name: str,
        waived_error_ids: Optional[List[str]] = None,
    ) -> None:
        """Validate rule text before persistence. Raises RuleValidationError on failure.

        Args:
            rule_text: Rule text to validate
            rule_name: Name of the rule (for error reporting)
            waived_error_ids: Validation error waiver IDs approved by a human reviewer.

        Raises:
            RuleValidationError: When unwaived validation errors remain or unknown waiver IDs are supplied.
        """
        validation_text = self._build_import_aware_rule_text(rule_name, rule_text)
        result = self._validation_service.validate(validation_text, rule_name)
        if result.valid:
            return

        actual_error_ids: Set[str] = {e.waiver_id for e in result.errors}
        waived: Set[str] = set(waived_error_ids or ())

        unknown = waived - actual_error_ids
        if unknown:
            raise RuleValidationError(
                errors=list(result.errors),
                rule_name=rule_name,
                unknown_waiver_ids=sorted(unknown),
            )

        remaining_ids = actual_error_ids - waived
        if remaining_ids:
            raise RuleValidationError(
                errors=[e for e in result.errors if e.waiver_id in remaining_ids],
                rule_name=rule_name,
            )

    def validate_draft_rule(self, rule_text: str, rule_name: str = "") -> ValidationResult:
        """Validate unsaved draft text with the same import view used by save."""
        try:
            validation_text = (
                self._build_import_aware_rule_text(rule_name, rule_text)
                if rule_name and extract_imports(rule_text)
                else rule_text
            )
        except RuleValidationError as exc:
            return ValidationResult(valid=False, errors=tuple(exc.errors))

        return self._validation_service.validate(validation_text, rule_name)

    def _build_import_aware_rule_text(self, rule_name: str, rule_text: str) -> str:
        """Return a transient merged rule view for validation and parsing.

        Persisted rule text remains unchanged. The merge only lets the legacy
        single-file validator/runtime parser see declarations and rule
        conclusions supplied by IMPORT: modules.
        """
        if not extract_imports(rule_text):
            return rule_text

        imported_texts = self._load_imported_rule_texts(rule_name, rule_text)
        if not imported_texts:
            return rule_text

        sections: list[str] = []
        for module_name, imported_text in imported_texts:
            cleaned_text = self._strip_modular_directives(imported_text).strip()
            if cleaned_text:
                sections.append(f"# Imported module: {module_name}\n{cleaned_text}")

        cleaned_root_text = self._strip_modular_directives(rule_text).strip()
        if cleaned_root_text:
            sections.append(f"# Root module: {rule_name}\n{cleaned_root_text}")
        return "\n\n".join(sections) + "\n"

    def _strip_modular_directives(self, rule_text: str) -> str:
        return "\n".join(
            line for line in rule_text.splitlines()
            if not line.startswith("IMPORT:") and not line.startswith("RULE SET:")
        )

    def _load_imported_rule_texts(
        self,
        rule_name: str,
        rule_text: str,
    ) -> list[tuple[str, str]]:
        def load_rule(module_name: str) -> str:
            if module_name == rule_name:
                return rule_text
            return self.get_rule_text(module_name)

        resolver = RuleSetImportResolver(
            rule_loader=load_rule,
            feature_flags=FeatureFlags(modular_imports=True),
        )

        try:
            resolved = resolver.resolve(rule_name)
        except CircularImportError as exc:
            raise RuleValidationError(
                errors=[
                    ValidationError(
                        code="CIRCULAR_IMPORT",
                        message=str(exc),
                        node_name=rule_name,
                    )
                ],
                rule_name=rule_name,
            ) from exc
        except ImportDepthExceededError as exc:
            raise RuleValidationError(
                errors=[
                    ValidationError(
                        code="IMPORT_DEPTH_EXCEEDED",
                        message=str(exc),
                        node_name=exc.module_name,
                    )
                ],
                rule_name=rule_name,
            ) from exc
        except RuleLoadTimeoutError as exc:
            raise RuleValidationError(
                errors=[
                    ValidationError(
                        code="IMPORT_LOAD_TIMEOUT",
                        message=str(exc),
                        node_name=exc.module_name,
                    )
                ],
                rule_name=rule_name,
            ) from exc

        imported_texts: list[tuple[str, str]] = []
        for module_name in resolved:
            if module_name == rule_name:
                continue
            try:
                imported_texts.append((module_name, self.get_rule_text(module_name)))
            except LookupError as exc:
                raise RuleValidationError(
                    errors=[
                        ValidationError(
                            code="UNRESOLVED_IMPORT",
                            message=f"Imported rule '{module_name}' could not be loaded",
                            node_name=module_name,
                        )
                    ],
                    rule_name=rule_name,
                ) from exc

        return imported_texts

    def _parse_rule_text(
        self,
        rule_name: str,
        rule_text: str,
        history_dict: dict[str, HistoryRecord] | None = None,
    ) -> RuleSetParser:
        rule_set_reader = RuleSetReader()
        rule_set_reader.create()

        rule_set_parser = RuleSetParser()
        rule_set_parser.create()
        rule_set_parser.set_source_name(rule_name)

        rule_set_reader.set_file_with_text(rule_text)
        rule_set_scanner = RuleSetScanner(rule_set_reader, rule_set_parser)
        rule_set_scanner.scan_rule_set()
        rule_set_scanner.establish_node_set(history_dict)
        return rule_set_parser

    def _encode_rule_file(
        self,
        rule_text: str,
        rule_name: str,
        require_graph: bool,
    ) -> bytearray:
        try:
            parse_text = self._build_import_aware_rule_text(rule_name, rule_text)
            parser = self._parse_rule_text(rule_name, parse_text)
            graph = parser.get_node_set().get_graph()
            if graph is None:
                raise ValueError("Parsed rule set did not produce a dependency graph")
            source_hash = hashlib.sha256(rule_text.encode("utf-8")).hexdigest()
            return encode_rule_file_payload(
                rule_text=rule_text,
                graph_json=serialize_graph(graph),
                source_hash=source_hash,
            )
        except Exception:
            if require_graph:
                raise
            return bytearray(rule_text, "utf-8")

    def get_target_node_names(self, rule_name: str) -> list[str]:
        node_set = self.build_rule_set_parser(rule_name).get_node_set()
        target_nodes = self._get_parentless_nodes(node_set)
        return [node.get_node_name() for node in target_nodes]

    def get_target_node_names_for_text(self, rule_name: str, rule_text: str) -> list[str]:
        """Return exported target nodes for an unsaved draft rule text."""
        parse_text = (
            self._build_import_aware_rule_text(rule_name, rule_text)
            if rule_name and extract_imports(rule_text)
            else rule_text
        )
        node_set = self._parse_rule_text(rule_name, parse_text).get_node_set()
        target_nodes = self._get_parentless_nodes(node_set)
        return [node.get_node_name() for node in target_nodes]

    def get_node_names(self, rule_name: str) -> list[str]:
        """Return every node name in the persisted rule dependency graph."""
        graph = self.get_rule_graph_data(rule_name)
        return [
            str(node.get("name")).strip()
            for node in graph.get("nodes", [])
            if str(node.get("name") or "").strip()
        ]

    def get_node_names_for_text(self, rule_name: str, rule_text: str) -> list[str]:
        """Return every node name in an unsaved draft dependency graph."""
        graph = self.get_rule_graph_data_for_text(rule_name, rule_text)
        return [
            str(node.get("name")).strip()
            for node in graph.get("nodes", [])
            if str(node.get("name") or "").strip()
        ]

    def _get_parentless_nodes(self, node_set: NodeSet) -> list[Node]:
        graph = node_set.get_graph()
        node_dict = node_set.get_node_dictionary()
        if graph is None:
            return [
                node for node in node_set.get_sorted_node_list()
                if getattr(node, "_node_id", None) == 0
            ]

        parentless_names = [
            name for name in node_dict
            if graph.has_node(name) and not graph.get_parent_edges(name)
        ]

        def _sort_key(name: str) -> tuple[int, str]:
            runtime_id = graph.lookup_by_name(name)
            if not isinstance(runtime_id, int):
                node_runtime_id = getattr(node_dict[name], "_node_id", None)
                runtime_id = node_runtime_id if isinstance(node_runtime_id, int) else 10**9
            return runtime_id, name

        return [node_dict[name] for name in sorted(parentless_names, key=_sort_key)]
