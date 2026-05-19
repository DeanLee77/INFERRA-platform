import hashlib
from typing import Any, List, Optional, Set

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
from src.domain.rule_parser.rule_set_parser import RuleSetParser
from src.domain.rule_parser.rule_set_reader import RuleSetReader
from src.domain.rule_parser.rule_set_scanner import RuleSetScanner
from src.ports.rule_repository_port import RuleRepositoryPort
from src.services.rule_validation_service import RuleValidationService, ValidationError


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

    def build_rule_set_parser(self, rule_name: str, history_dict: dict | None = None) -> RuleSetParser:
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
    ) -> RuleEntity:
        if not bypass_validation:
            self._validate_rule_text(rule_text, name, waived_error_ids=waived_error_ids)

        rule_id = self._repository.create_rule(
            {
                "rule_name": name,
                "rule_category": category,
                "rule_description": description,
            }
        )
        self._repository.create_rule_file(
            rule_id,
            self._encode_rule_file(rule_text, name, require_graph=not bypass_validation),
        )

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
        return self.get_rule_text(rule_name)

    def get_history_for_ml_inference(self, rule_name: str) -> dict | None:
        """Get the history dictionary for ML-enhanced inference.
        
        Args:
            rule_name: Name of the rule
            
        Returns:
            History dictionary or None if no history exists
        """
        result = self._repository.find_rule_by_rule_name_with_latest_history(rule_name)
        if result is None:
            return None
        return result.get("history")

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
        history_dict: dict | None = None,
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
