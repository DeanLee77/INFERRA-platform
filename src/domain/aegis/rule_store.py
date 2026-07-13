"""AEGIS rule-store helpers shared by API routes and runtime gates."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from src.domain.imports.import_matchers import extract_imports
from src.services.rule_service import RuleService
from src.services.rule_validation_service import ValidationResult

AEGIS_PRODUCT = "AEGIS"
AEGIS_RULE_STORE = "aegis-rule-store"


@dataclass
class AegisImportNode:
    name: str
    content_hash: str
    node_count: int
    depth: int
    direct_imports: list[str] = field(default_factory=list)


@dataclass
class AegisImportTree:
    imports: list[AegisImportNode]
    missing: list[str]
    has_cycles: bool
    import_tree_hash: str


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def rule_version_hash(rule_text: str) -> str:
    return "sha256:" + hashlib.sha256(rule_text.encode("utf-8")).hexdigest()


def validation_to_dict(result: ValidationResult) -> dict[str, Any]:
    return {
        "valid": result.valid,
        "errors": [
            {
                "code": error.code,
                "message": error.message,
                "line": error.line,
                "nodeName": error.node_name,
                "waiverId": error.waiver_id,
            }
            for error in result.errors
        ],
        "warnings": [
            {
                "code": warning.code,
                "message": warning.message,
                "line": warning.line,
                "nodeName": warning.node_name,
                "waiverId": warning.waiver_id,
            }
            for warning in result.warnings
        ],
    }


def validation_status(result: ValidationResult) -> str:
    return "valid" if result.valid else "invalid"


def count_source_nodes(rule_text: str) -> int:
    count = 0
    ignored_prefixes = ("#", "//", "IMPORT:", "RULE SET:")
    for raw_line in rule_text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith(ignored_prefixes):
            continue
        count += 1
    return count


def build_import_tree(service: RuleService, rule_name: str, rule_text: str | None = None) -> AegisImportTree:
    root_text = rule_text if rule_text is not None else service.get_rule_text(rule_name)
    imports: list[AegisImportNode] = []
    missing: list[str] = []
    visited: set[str] = set()
    visiting: set[str] = set()
    has_cycles = False

    def load_text(module_name: str) -> str | None:
        if module_name == rule_name:
            return root_text
        try:
            return service.get_rule_text(module_name)
        except LookupError:
            if module_name not in missing:
                missing.append(module_name)
            return None

    def visit(module_name: str, depth: int) -> None:
        nonlocal has_cycles
        if module_name in visiting:
            has_cycles = True
            return
        if module_name in visited:
            return
        module_text = load_text(module_name)
        if module_text is None:
            return
        visiting.add(module_name)
        direct_imports = extract_imports(module_text)
        for child_name in direct_imports:
            visit(child_name, depth + 1)
        visiting.remove(module_name)
        visited.add(module_name)

        if module_name != rule_name:
            imports.append(
                AegisImportNode(
                    name=module_name,
                    content_hash=rule_version_hash(module_text),
                    node_count=count_source_nodes(module_text),
                    depth=depth,
                    direct_imports=direct_imports,
                )
            )

    visit(rule_name, 0)
    payload = {
        "product": AEGIS_PRODUCT,
        "store": AEGIS_RULE_STORE,
        "ruleName": rule_name,
        "imports": [
            {
                "name": entry.name,
                "contentHash": entry.content_hash,
                "depth": entry.depth,
                "directImports": entry.direct_imports,
            }
            for entry in sorted(imports, key=lambda item: (item.depth, item.name))
        ],
        "missing": sorted(missing),
        "hasCycles": has_cycles,
    }
    return AegisImportTree(
        imports=sorted(imports, key=lambda item: (item.depth, item.name)),
        missing=sorted(missing),
        has_cycles=has_cycles,
        import_tree_hash=stable_hash(payload),
    )


def build_policy_integrity(
    service: RuleService,
    rule_name: str,
    rule_text: str,
    latest_file_id: int | None,
) -> dict[str, Any]:
    validation = service.validate_draft_rule(rule_text=rule_text, rule_name=rule_name)
    import_tree = build_import_tree(service, rule_name, rule_text)
    return {
        "product": AEGIS_PRODUCT,
        "store": AEGIS_RULE_STORE,
        "ruleName": rule_name,
        "latestFileId": latest_file_id,
        "ruleVersionHash": rule_version_hash(rule_text),
        "importTreeHash": import_tree.import_tree_hash,
        "validationStatus": validation_status(validation),
        "missingImports": import_tree.missing,
        "hasImportCycles": import_tree.has_cycles,
    }
