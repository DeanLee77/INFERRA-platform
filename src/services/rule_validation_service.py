"""
Rule Validation Service Module.
Synchronous pre-save gate that validates rule text before persistence.
Implements content-hash caching with LRU eviction and TTL expiry.
"""

import hashlib
import re
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

import structlog

from src.domain.fact_values import FactValueType
from src.services.declaration_validator import DeclarationValidator

_logger = structlog.get_logger("inferra.rule_validation")


# =============================================================================
# Value Objects
# =============================================================================

@dataclass(frozen=True)
class ValidationEntry:
    """Base for a single validation error or warning."""
    code: str
    message: str
    line: Optional[int] = None
    node_name: Optional[str] = None
    severity: str = "warning"
    category: Optional[str] = None
    source: str = "deterministic"
    blocking: bool = False
    reason: Optional[str] = None
    review_required: bool = False
    review_item_id: Optional[str] = None

    @property
    def waiver_id(self) -> str:
        """Stable identifier the frontend can use for human-review waivers."""
        if self.node_name:
            return f"{self.code}:{self.node_name}"
        if self.line is not None:
            return f"{self.code}:line_{self.line}"
        return self.code

    def to_dict(self) -> dict:
        result = {
            "code": self.code,
            "message": self.message,
            "waiver_id": self.waiver_id,
            "severity": self.severity,
            "source": self.source,
            "blocking": self.blocking,
            "review_required": self.review_required,
        }
        if self.line is not None:
            result["line"] = self.line
        if self.node_name is not None:
            result["node_name"] = self.node_name
        if self.category is not None:
            result["category"] = self.category
        if self.reason is not None:
            result["reason"] = self.reason
        if self.review_item_id is not None:
            result["review_item_id"] = self.review_item_id
        return result


@dataclass(frozen=True)
class ValidationError(ValidationEntry):
    """A single validation error."""
    severity: str = "error"

    def __repr__(self) -> str:
        return f"ValidationError(code={self.code!r}, message={self.message!r}, line={self.line})"


@dataclass(frozen=True)
class ValidationWarning(ValidationEntry):
    """A single validation warning."""
    severity: str = "warning"

    def __repr__(self) -> str:
        return f"ValidationWarning(code={self.code!r}, message={self.message!r}, line={self.line})"


@dataclass(frozen=True)
class OntologyReviewQueueItem:
    """Human-review candidate for an ontology-suggested correction."""
    proposal_id: str
    warning_code: str
    action: str
    target: str
    rationale: str
    line: Optional[int] = None
    node_name: Optional[str] = None
    proposed_value: Optional[str] = None
    approval_state: str = "candidate"
    requires_rule_approval: bool = True
    mutates_assets: bool = False
    alters_deterministic_outcome: bool = False

    def to_dict(self) -> dict:
        result = {
            "proposal_id": self.proposal_id,
            "warning_code": self.warning_code,
            "action": self.action,
            "target": self.target,
            "rationale": self.rationale,
            "approval_state": self.approval_state,
            "requires_rule_approval": self.requires_rule_approval,
            "mutates_assets": self.mutates_assets,
            "alters_deterministic_outcome": self.alters_deterministic_outcome,
        }
        if self.line is not None:
            result["line"] = self.line
        if self.node_name is not None:
            result["node_name"] = self.node_name
        if self.proposed_value is not None:
            result["proposed_value"] = self.proposed_value
        return result


@dataclass(frozen=True)
class ValidationResult:
    """Result of a validation run. Errors and warnings are tuples (immutable)."""
    valid: bool
    errors: Tuple[ValidationError, ...] = ()
    warnings: Tuple[ValidationWarning, ...] = ()
    review_queue: Tuple[OntologyReviewQueueItem, ...] = ()

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "review_queue": [item.to_dict() for item in self.review_queue],
        }

    def __repr__(self) -> str:
        return f"ValidationResult(valid={self.valid}, errors={len(self.errors)}, warnings={len(self.warnings)})"


# =============================================================================
# Validation Service
# =============================================================================

class RuleValidationService:
    """
    Synchronous pre-save gate that validates rule text.

    Validation checks (Phase 1):
    1. Syntax & Tokeniser — line-by-line structural validation
    2. Type Consistency — INPUT/FIXED declarations vs rule block usage
    3. Import Resolution — placeholder (Phase 2: RuleSetImportResolver)
    4. DAG Cycle Check — dependency graph must be acyclic

    Content-hash cache:
    - Key: SHA-256 of rule_text
    - Value: (timestamp, ValidationResult)
    - Eviction: LRU when cache exceeds maxsize; TTL expiry (default 300s)
    """

    _FIXED_PATTERN = re.compile(r"^(FIXED)\s+(.+?)(?:\s+(IS|AS)\s+.+)$")
    _INPUT_PATTERN = re.compile(r"^(INPUT)\s+(.+?)(?:\s+(AS|IS)\s+.+)$")
    _VALUE_CONCLUSION_PATTERN = re.compile(r"^(.+?)\s+IS\s+.+$")
    _EXPR_CONCLUSION_PATTERN = re.compile(r"^(.+?)\s+IS\s+CALC\s+.+$")
    _COMPARISON_PATTERN = re.compile(r"^(.+?)\s*(<=|>=|<|>|=)\s*.+$")
    _ITERATE_PATTERN = re.compile(
        r"^(?P<quantifier>NOT\s+ALL|NOT\s+NONE|AT\s+LEAST\s+\d+|AT\s+MOST\s+\d+|EXACTLY\s+\d+|ALL|NONE|SOME)\s+"
        r"(?P<alias>.+?)\s+"
        r"IN\s+(?P<collection>.+)$",
        re.IGNORECASE,
    )
    _LEGACY_ITERATE_PATTERN = re.compile(r"^.+?\s+ITERATE:\s*LIST\s+OF\s+.+$", re.IGNORECASE)
    _BARE_NUMBER_ITERATE_PATTERN = re.compile(r"^\d+\s+.+?\s+IN\s+.+$", re.IGNORECASE)
    _EXACT_ITERATE_PATTERN = re.compile(r"^EXACT\s+\d+\s+.+?\s+IN\s+.+$", re.IGNORECASE)
    _TYPE_PATTERN = re.compile(r"^TYPE\s+(.+?)\s*$", re.IGNORECASE)
    _FIELD_PATTERN = re.compile(r"^FIELD\s+(.+?)\s+AS\s+(.+?)\s*$", re.IGNORECASE)
    _SIZE_FROM_PATTERN = re.compile(r"^SIZE\s+FROM\s+(.+?)\s*$", re.IGNORECASE)
    _ITEM_TYPE_PATTERN = re.compile(r"^ITEM\s+TYPE\s+(.+?)\s*$", re.IGNORECASE)
    _COMMENT_PATTERN = re.compile(r"^(#|//)")
    _INDENTED_LINE_PATTERN = re.compile(r"^(\s+)(.+)$")
    _QUANTIFIER_PATTERN = re.compile(
        r"^(?:(?:AND|OR)\b\s*)?"
        r"(?:(?:MANDATORY|OPTIONALLY|POSSIBLY)\b\s*)?"
        r"(?:(?:NOT|KNOWN)\b\s*)*"
        r"(?:(?:NEEDS|WANTS)\b\s*)?",
    )
    _IS_IN_LIST_PATTERN = re.compile(r"^(.+?)\s+IS\s+IN\s+LIST:\s*(.+)$")
    _APOSTROPHE_VARIANTS = str.maketrans({
        "\u2018": "'",
        "\u2019": "'",
        "\u201b": "'",
        "\u2032": "'",
        "\u02bc": "'",
        "`": "'",
    })

    _NUMERIC_OPERATORS = frozenset({">", ">=", "<", "<="})

    _NUMERIC_TYPES = frozenset({
        FactValueType.INTEGER.value,
        FactValueType.DOUBLE.value,
        FactValueType.DECIMAL.value,
    })
    _LEGAL_CONCEPT_TERMS = frozenset({
        "age",
        "asset",
        "benefit",
        "claim",
        "compensation",
        "disability",
        "eligibility",
        "eligible",
        "income",
        "pension",
        "residence",
        "service",
        "veteran",
    })
    _STATUTORY_REFERENCE_PATTERN = re.compile(
        r"\b(?:section|s)\s+\d+[A-Za-z]*(?:\([^)]+\))*",
        re.IGNORECASE,
    )
    _STATUTORY_DEFINITION_PATTERN = re.compile(
        r"\b(?:definition|defined term|means)\b",
        re.IGNORECASE,
    )
    _IMPORT_MARKER_PATTERN = re.compile(r"^# Imported module:\s*(.+)$", re.MULTILINE)

    def __init__(
        self,
        cache_maxsize: int = 512,
        cache_ttl_seconds: int = 300,
        enable_node_set_validation: bool = True,
        enable_ontology_advisory_validation: bool = True,
        ontology_blocking_warning_codes: Optional[Iterable[str]] = None,
    ):
        self._cache: OrderedDict[str, Tuple[float, ValidationResult]] = OrderedDict()
        self._cache_maxsize = cache_maxsize
        self._cache_ttl = cache_ttl_seconds
        self._enable_node_set_validation = enable_node_set_validation
        self._enable_ontology_advisory_validation = enable_ontology_advisory_validation
        self._ontology_blocking_warning_codes = frozenset(ontology_blocking_warning_codes or ())
        self._declaration_validator = DeclarationValidator()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def validate(self, rule_text: str, rule_name: str = "") -> ValidationResult:
        if not rule_text or not rule_text.strip():
            return ValidationResult(
                valid=False,
                errors=(ValidationError("EMPTY_RULE", "Rule text is empty"),),
            )

        content_hash = self._compute_content_hash(rule_text)
        cached = self._get_cached(content_hash)
        if cached is not None:
            _logger.debug("validation_cache_hit", rule_name=rule_name)
            return cached

        errors: List[ValidationError] = []
        warnings: List[ValidationWarning] = []
        review_queue: List[OntologyReviewQueueItem] = []

        parsed = self._check_syntax(rule_text, errors, warnings)
        if errors:
            result = ValidationResult(
                valid=False,
                errors=tuple(errors),
                warnings=tuple(warnings),
                review_queue=tuple(review_queue),
            )
            self._set_cached(content_hash, result)
            return result

        self._check_type_consistency(parsed, errors, warnings)
        self._check_same_level_and_or(parsed, warnings)

        self._check_dag_cycles(parsed, errors)

        if self._enable_node_set_validation:
            self._check_node_set_declarations(rule_text, rule_name, errors, warnings)

        if self._enable_ontology_advisory_validation:
            self._check_ontology_advisory_semantics(
                parsed,
                rule_text,
                warnings,
                review_queue,
            )

        blocking_errors = self._blocking_semantic_policy_errors(warnings)
        errors.extend(blocking_errors)

        valid = len(errors) == 0 and not any(w.blocking for w in warnings)
        result = ValidationResult(
            valid=valid,
            errors=tuple(errors),
            warnings=tuple(warnings),
            review_queue=tuple(review_queue),
        )
        self._set_cached(content_hash, result)
        _logger.info(
            "validation_complete",
            rule_name=rule_name,
            valid=result.valid,
            error_count=len(errors),
            warning_count=len(warnings),
        )
        return result

    def invalidate_cache(self) -> None:
        """Evict all cached validation results."""
        self._cache.clear()
        _logger.debug("validation_cache_invalidated")

    # -------------------------------------------------------------------------
    # Check 1: Syntax & Tokeniser
    # -------------------------------------------------------------------------

    def _check_syntax(
        self,
        rule_text: str,
        errors: List[ValidationError],
        warnings: List[ValidationWarning],
    ) -> Dict:
        declarations: Dict[str, dict] = {}
        type_fields: Dict[str, Dict[str, str]] = {}
        collection_fields: Dict[str, Dict[str, str]] = {}
        collections: Dict[str, dict] = {}
        declaration_references: List[dict] = []
        rules: List[dict] = []
        rule_stack: List[dict] = []
        in_list = False
        list_var_name = ""
        current_type = ""
        current_collection = ""
        line_number = 0

        for raw_line in rule_text.splitlines():
            line_number += 1
            stripped = raw_line.strip()

            if not stripped or self._COMMENT_PATTERN.match(stripped):
                in_list = False
                current_type = ""
                current_collection = ""
                continue

            if in_list and stripped.startswith("ITEM"):
                continue

            type_match = self._TYPE_PATTERN.match(stripped)
            if type_match:
                current_type = type_match.group(1).strip()
                current_collection = ""
                type_fields.setdefault(current_type, {})
                in_list = False
                continue

            indent_match = self._INDENTED_LINE_PATTERN.match(raw_line)
            if indent_match:
                indent = len(indent_match.group(1))
                child_text = indent_match.group(2).strip()
                field_match = self._FIELD_PATTERN.match(child_text)
                if current_type and field_match:
                    field_type_text = field_match.group(2).strip()
                    type_fields.setdefault(current_type, {})[
                        field_match.group(1).strip()
                    ] = self._normalise_declared_type(field_type_text)
                    option_list = self._field_option_list_from_text(field_type_text)
                    if option_list:
                        declaration_references.append({"name": option_list, "line": line_number})
                    continue
                if current_collection:
                    size_match = self._SIZE_FROM_PATTERN.match(child_text)
                    if size_match:
                        size_source = size_match.group(1).strip()
                        collections.setdefault(current_collection, {})["size_from"] = size_source
                        declaration_references.append({"name": size_source, "line": line_number})
                        continue
                    field_match = self._FIELD_PATTERN.match(child_text)
                    if field_match:
                        field_type_text = field_match.group(2).strip()
                        collection_fields.setdefault(current_collection, {})[
                            field_match.group(1).strip()
                        ] = self._normalise_declared_type(field_type_text)
                        option_list = self._field_option_list_from_text(field_type_text)
                        if option_list:
                            declaration_references.append({"name": option_list, "line": line_number})
                        continue
                    item_type_match = self._ITEM_TYPE_PATTERN.match(child_text)
                    if item_type_match:
                        collections.setdefault(current_collection, {})["item_type"] = item_type_match.group(1).strip()
                        continue
                child_clean = self._QUANTIFIER_PATTERN.sub("", child_text).strip()
                if child_clean:
                    dependency_keyword = self._dependency_keyword(child_text)
                    dependency_modifiers = self._dependency_modifiers(child_text)
                    self._parse_rule_line(
                        child_clean,
                        line_number,
                        declarations,
                        rules,
                        errors,
                        indent=indent,
                        is_indented=True,
                        rule_stack=rule_stack,
                        dependency_keyword=dependency_keyword,
                        dependency_modifiers=dependency_modifiers,
                    )
                continue

            fixed_match = self._FIXED_PATTERN.match(stripped)
            if fixed_match:
                var_name = fixed_match.group(2).strip()
                if var_name in declarations:
                    errors.append(ValidationError(
                        code="DUPLICATE_DECLARATION",
                        message=f"Variable '{var_name}' is declared more than once",
                        line=line_number,
                        node_name=var_name,
                    ))
                else:
                    declarations[var_name] = {
                        "type": "FIXED",
                        "value_type": self._extract_value_type(stripped, "FIXED"),
                        "line": line_number,
                        "meta": "FIXED",
                    }
                in_list = "AS LIST" in stripped or "IS LIST" in stripped
                list_var_name = var_name if in_list else ""
                current_type = ""
                current_collection = ""
                continue

            input_match = self._INPUT_PATTERN.match(stripped)
            if input_match:
                var_name = input_match.group(2).strip()
                if var_name in declarations:
                    errors.append(ValidationError(
                        code="DUPLICATE_DECLARATION",
                        message=f"Variable '{var_name}' is declared more than once",
                        line=line_number,
                        node_name=var_name,
                    ))
                else:
                    declarations[var_name] = {
                        "type": "INPUT",
                        "value_type": self._extract_value_type(stripped, "INPUT"),
                        "line": line_number,
                        "meta": "INPUT",
                    }
                collection_match = re.match(
                    r"^INPUT\s+(.+?)\s+AS\s+COLLECTION\s+OF\s+(.+?)\s*$",
                    stripped,
                    re.IGNORECASE,
                )
                if collection_match:
                    current_collection = collection_match.group(1).strip()
                    current_type = ""
                    collections[current_collection] = {"item_type": collection_match.group(2).strip()}
                else:
                    current_type = ""
                    current_collection = ""
                in_list = "AS LIST" in stripped and "AS COLLECTION" not in stripped
                list_var_name = var_name if in_list else ""
                continue

            in_list = False
            current_type = ""
            current_collection = ""
            self._parse_rule_line(
                stripped,
                line_number,
                declarations,
                rules,
                errors,
                indent=0,
                is_indented=False,
                rule_stack=rule_stack,
            )

        return {
            "declarations": declarations,
            "type_fields": type_fields,
            "collection_fields": collection_fields,
            "collections": collections,
            "declaration_references": declaration_references,
            "rules": rules,
            "lines": line_number,
        }

    _KEYWORDS = frozenset({
        "IS", "AS", "CALC", "FOR", "ALL", "NONE", "SOME", "AT", "LEAST", "MOST", "EXACT", "EXACTLY",
        "AND", "OR", "NOT", "KNOWN", "MANDATORY", "OPTIONALLY", "POSSIBLY",
        "NEEDS", "WANTS", "ITEM", "INPUT", "FIXED", "IF",
        "IN", "LIST", "TRUE", "FALSE", "TYPE", "FIELD", "COLLECTION",
        "OF", "SIZE", "FROM",
    })

    def _extract_references(self, raw: str, conclusion_var: str) -> List[str]:
        """
        Extract variable references from a rule line's raw text.

        Returns a list of potential variable names found in the text,
        excluding the conclusion variable itself and INFERRA keywords.
        Variable names that happen to be short uppercase (e.g., RATE,
        FLAG) are NOT excluded — only tokens in the _KEYWORDS set are
        filtered. This is a heuristic; false positives are possible for
        tokens that are neither declared nor rule conclusions (they'll
        trigger UNDECLARED_REFERENCE errors that can be reviewed).
        """
        tokens = re.findall(r'[A-Za-z_][A-Za-z0-9_]*', raw)
        refs = []
        for token in tokens:
            if token == conclusion_var:
                continue
            if token.upper() in self._KEYWORDS:
                continue
            refs.append(token)
        return refs

    def _parse_rule_line(
        self,
        text: str,
        line_number: int,
        declarations: Dict[str, dict],
        rules: List[dict],
        errors: List[ValidationError],
        indent: int = 0,
        is_indented: bool = False,
        rule_stack: Optional[List[dict]] = None,
        dependency_keyword: str = "",
        dependency_modifiers: Optional[List[str]] = None,
    ) -> None:
        def _append_rule(rule: dict) -> None:
            rule["indent"] = indent
            rule["is_indented"] = is_indented
            rule["has_children"] = False
            rule["dependency_keyword"] = dependency_keyword
            rule["dependency_modifiers"] = tuple(dependency_modifiers or ())
            if rule_stack is not None:
                while rule_stack and rule_stack[-1]["indent"] >= indent:
                    rule_stack.pop()
                if rule_stack:
                    rule_stack[-1]["has_children"] = True
            rule_stack.append(rule)
            rules.append(rule)

        if (
            self._TYPE_PATTERN.match(text)
            or self._FIELD_PATTERN.match(text)
            or self._SIZE_FROM_PATTERN.match(text)
            or self._ITEM_TYPE_PATTERN.match(text)
        ):
            return

        expr_match = self._EXPR_CONCLUSION_PATTERN.match(text)
        if expr_match:
            var_name = expr_match.group(1).strip()
            refs = self._extract_references(text, var_name)
            _append_rule({"line": line_number, "variable_name": var_name, "kind": "EXPR_CONCLUSION", "raw": text, "references": refs})
            return

        list_match = self._IS_IN_LIST_PATTERN.match(text)
        if list_match:
            var_name = list_match.group(1).strip()
            refs = self._extract_references(text, var_name)
            _append_rule({"line": line_number, "variable_name": var_name, "kind": "LIST_MEMBERSHIP", "raw": text, "references": refs})
            return

        comp_match = self._COMPARISON_PATTERN.match(text)
        if comp_match:
            var_name = comp_match.group(1).strip()
            operator = comp_match.group(2).strip()
            refs = self._extract_references(text, var_name)
            _append_rule({"line": line_number, "variable_name": var_name, "kind": "COMPARISON", "raw": text, "operator": operator, "references": refs})
            return

        if self._LEGACY_ITERATE_PATTERN.match(text):
            errors.append(ValidationError(
                code="INVALID_ITERATE_SYNTAX",
                message=(
                    "`ITERATE: LIST OF` is not valid INFERRA syntax. "
                    "Use `<quantifier> <item alias> IN <collection name>`."
                ),
                line=line_number,
                node_name=text,
            ))
            return

        if self._BARE_NUMBER_ITERATE_PATTERN.match(text):
            errors.append(ValidationError(
                code="INVALID_ITERATE_SYNTAX",
                message=(
                    "Bare numeric iterate quantifiers are not valid. "
                    "Use `AT LEAST <number> <item alias> IN <collection name>`."
                ),
                line=line_number,
                node_name=text,
            ))
            return

        if self._EXACT_ITERATE_PATTERN.match(text):
            errors.append(ValidationError(
                code="INVALID_ITERATE_SYNTAX",
                message=(
                    "`EXACT` is not valid INFERRA syntax. "
                    "Use `EXACTLY <number> <item alias> IN <collection name>`."
                ),
                line=line_number,
                node_name=text,
            ))
            return

        iter_match = self._ITERATE_PATTERN.match(text)
        if iter_match:
            var_name = iter_match.group("alias").strip()
            refs = [iter_match.group("collection").strip()]
            _append_rule({"line": line_number, "variable_name": var_name, "kind": "ITERATE", "raw": text, "references": refs})
            return

        vc_match = self._VALUE_CONCLUSION_PATTERN.match(text)
        if vc_match:
            var_name = vc_match.group(1).strip()
            refs = self._extract_references(text, var_name)
            _append_rule({"line": line_number, "variable_name": var_name, "kind": "VALUE_CONCLUSION", "raw": text, "references": refs})
            return

        var_name = text.strip()
        refs = self._extract_references(text, var_name)
        _append_rule({"line": line_number, "variable_name": var_name, "kind": "PLAIN_STATEMENT", "raw": text, "references": refs})

    def _extract_value_type(self, line: str, meta: str) -> str:
        as_match = re.search(r"\bAS\s+(\w+)", line)
        if as_match:
            type_str = as_match.group(1).strip().upper()
            type_map = {
                "BOOLEAN": FactValueType.BOOLEAN.value,
                "BOOL": FactValueType.BOOLEAN.value,
                "TEXT": FactValueType.TEXT.value,
                "STRING": FactValueType.STRING.value,
                "NUMBER": FactValueType.DOUBLE.value,
                "INTEGER": FactValueType.INTEGER.value,
                "INT": FactValueType.INTEGER.value,
                "DECIMAL": FactValueType.DECIMAL.value,
                "DOUBLE": FactValueType.DOUBLE.value,
                "DATE": FactValueType.DATE.value,
                "LIST": FactValueType.LIST.value,
                "COLLECTION": FactValueType.LIST.value,
                "URL": FactValueType.URL.value,
                "HASH": FactValueType.HASH.value,
                "GUID": FactValueType.GUID.value,
            }
            return type_map.get(type_str, "UNKNOWN")
        is_match = re.search(r"\bIS\s+(.+)$", line)
        if is_match:
            value_str = is_match.group(1).strip()
            if value_str.startswith('"') or value_str.startswith("'"):
                return FactValueType.STRING.value
            try:
                int(value_str)
                return FactValueType.INTEGER.value
            except ValueError:
                pass
            try:
                float(value_str)
                return FactValueType.DOUBLE.value
            except ValueError:
                pass
            if value_str.lower() in ("true", "false"):
                return FactValueType.BOOLEAN.value
        return "UNKNOWN"

    def _normalise_declared_type(self, raw_type: str) -> str:
        return self._extract_value_type(f"INPUT __field__ AS {raw_type}", "INPUT")

    def _field_option_list_from_text(self, raw_type: str) -> Optional[str]:
        match = re.match(r"^LIST\s+OF\s+(.+?)\s*$", raw_type or "", re.IGNORECASE)
        if match is None:
            return None
        return match.group(1).strip()

    def _dependency_keyword(self, child_text: str) -> str:
        match = re.match(r"^(AND|OR)\b", child_text.strip())
        if match is None:
            return ""
        return match.group(1).upper()

    def _dependency_modifiers(self, child_text: str) -> List[str]:
        modifiers: List[str] = []
        tokens = child_text.strip().split()
        while tokens:
            token = tokens.pop(0).upper()
            if token in {
                "AND",
                "OR",
                "NOT",
                "KNOWN",
                "MANDATORY",
                "OPTIONALLY",
                "POSSIBLY",
                "NEEDS",
                "WANTS",
            }:
                modifiers.append(token)
                continue
            break
        return modifiers

    # -------------------------------------------------------------------------
    # Check 2: Type Consistency
    # -------------------------------------------------------------------------

    def _check_type_consistency(
        self,
        parsed: Dict,
        errors: List[ValidationError],
        warnings: List[ValidationWarning],
    ) -> None:
        declarations = parsed["declarations"]
        rules = parsed["rules"]
        field_names = self._collect_declared_field_names(parsed)

        rule_conclusion_names = self._collect_rule_conclusion_names(rules)
        reference_entries = self._collect_reference_entries(rules, declarations, rule_conclusion_names)
        reference_entries.extend(parsed.get("declaration_references", []))
        exact_referenced_names = {entry["name"] for entry in reference_entries}
        discrepancy_declarations: Set[str] = set()

        for rule in rules:
            var_name = rule["variable_name"]

            if rule["kind"] == "COMPARISON":
                operator = rule.get("operator", "")
                decl = declarations.get(var_name)
                if decl and decl["value_type"] == FactValueType.BOOLEAN.value and operator in self._NUMERIC_OPERATORS:
                    errors.append(ValidationError(
                        code="TYPE_MISMATCH",
                        message=f"Variable '{var_name}' is declared as BOOLEAN but used with numeric operator '{operator}'",
                        line=rule["line"],
                        node_name=var_name,
                    ))

        declared_names = set(declarations.keys())
        declaration_discrepancy_index = self._build_declaration_discrepancy_index(declarations)

        for entry in reference_entries:
            var_name = entry["name"]
            if var_name in declared_names or var_name in rule_conclusion_names:
                continue
            if self._is_declared_collection_field_reference(var_name, field_names):
                continue

            declaration_match = self._find_declaration_discrepancy(
                var_name,
                declaration_discrepancy_index,
            )
            if declaration_match is not None:
                declared_name, declared_line = declaration_match
                discrepancy_declarations.add(declared_name)
                errors.append(ValidationError(
                    code="VARIABLE_NAME_DISCREPANCY",
                    message=(
                        f"Variable '{var_name}' is referenced but not declared. "
                        f"Did you mean declared variable '{declared_name}' from line {declared_line}?"
                    ),
                    line=entry["line"],
                    node_name=var_name,
                ))
                continue

            errors.append(ValidationError(
                code="UNDECLARED_REFERENCE",
                message=f"Variable '{var_name}' is referenced but not declared as INPUT or FIXED",
                line=entry["line"],
                node_name=var_name,
            ))

        for var_name in declared_names:
            if var_name not in exact_referenced_names and var_name not in discrepancy_declarations:
                warnings.append(ValidationWarning(
                    code="UNUSED_DECLARATION",
                    message=f"Variable '{var_name}' is declared but never referenced in rule blocks",
                    line=declarations[var_name]["line"],
                    node_name=var_name,
                ))

    def _collect_declared_field_names(self, parsed: Dict) -> Set[str]:
        field_names: Set[str] = set()
        for fields in parsed.get("type_fields", {}).values():
            field_names.update(fields.keys())
        for fields in parsed.get("collection_fields", {}).values():
            field_names.update(fields.keys())
        return field_names

    def _is_declared_collection_field_reference(self, name: str, field_names: Set[str]) -> bool:
        if "." not in name:
            return False
        field_name = name.split(".", 1)[1].strip()
        return field_name in field_names

    def _check_same_level_and_or(
        self,
        parsed: Dict,
        warnings: List[ValidationWarning],
    ) -> None:
        stack: List[dict] = []
        grouped: Dict[Tuple[int, int], dict] = {}

        for rule in parsed.get("rules", []):
            while stack and stack[-1]["indent"] >= rule["indent"]:
                stack.pop()

            if rule.get("is_indented") and stack:
                dependency_keyword = rule.get("dependency_keyword", "")
                if dependency_keyword in {"AND", "OR"}:
                    parent = stack[-1]
                    group_key = (parent["line"], rule["indent"])
                    group = grouped.setdefault(
                        group_key,
                        {
                            "parent": parent,
                            "keywords": set(),
                            "first_child_line": rule["line"],
                        },
                    )
                    group["keywords"].add(dependency_keyword)

            stack.append(rule)

        for group in grouped.values():
            if {"AND", "OR"}.issubset(group["keywords"]):
                parent = group["parent"]
                warnings.append(ValidationWarning(
                    code="MIXED_AND_OR_CHILDREN",
                    message=(
                        f"Rule '{parent['raw']}' mixes AND and OR children at the same level. "
                        "Create explicit grouping rules to avoid ambiguous semantics."
                    ),
                    line=group["first_child_line"],
                    node_name=parent["variable_name"],
                ))

    def _collect_rule_conclusion_names(self, rules: List[dict]) -> Set[str]:
        conclusion_names: Set[str] = set()
        for rule in rules:
            if rule.get("kind") == "LIST_MEMBERSHIP":
                continue
            if not rule.get("is_indented"):
                if rule.get("kind") != "COMPARISON":
                    conclusion_names.add(rule["variable_name"])
                continue
            if rule.get("has_children"):
                conclusion_names.add(rule["variable_name"])
            elif rule.get("kind") in {"EXPR_CONCLUSION", "VALUE_CONCLUSION"}:
                conclusion_names.add(rule["variable_name"])
        return conclusion_names

    def _collect_reference_entries(
        self,
        rules: List[dict],
        declarations: Dict[str, dict],
        rule_conclusion_names: Set[str],
    ) -> List[dict]:
        entries: List[dict] = []
        seen: Set[Tuple[str, int]] = set()
        declared_names = set(declarations.keys())
        known_names = declared_names | rule_conclusion_names

        for rule in rules:
            line = rule["line"]
            kind = rule["kind"]
            raw = rule["raw"]
            candidates: List[str] = []

            candidates.extend(self._find_known_phrase_references(raw, known_names))

            if kind == "COMPARISON":
                candidates.append(rule["variable_name"])
                rhs = self._comparison_rhs(raw, rule.get("operator", ""))
                if rhs is not None and self._looks_like_variable_reference(rhs):
                    candidates.append(rhs)
            elif kind == "LIST_MEMBERSHIP":
                list_match = self._IS_IN_LIST_PATTERN.match(raw)
                if list_match:
                    candidates.append(list_match.group(1).strip())
                    candidates.append(list_match.group(2).strip())
            elif kind == "EXPR_CONCLUSION":
                _, _, rhs = raw.partition(" IS CALC ")
                candidates.extend(
                    self._expression_rhs_references(
                        rhs,
                        known_names,
                        rule["variable_name"],
                    )
                )
            elif kind == "VALUE_CONCLUSION":
                if not self._is_rule_conclusion(rule):
                    candidates.append(rule["variable_name"])
                _, _, rhs = raw.partition(" IS ")
                candidates.extend(
                    self._value_conclusion_rhs_references(
                        rhs,
                        known_names,
                        rule["variable_name"],
                    )
                )
            elif kind == "ITERATE":
                candidates.append(rule["variable_name"])
            elif kind == "PLAIN_STATEMENT":
                if not self._is_rule_conclusion(rule):
                    candidates.append(rule["variable_name"])

            for candidate in candidates:
                cleaned = self._clean_reference_candidate(candidate)
                if not cleaned:
                    continue
                key = (cleaned, line)
                if key in seen:
                    continue
                seen.add(key)
                entries.append({"name": cleaned, "line": line})

        return entries

    def _is_rule_conclusion(self, rule: dict) -> bool:
        if rule.get("kind") == "LIST_MEMBERSHIP":
            return False
        if not rule.get("is_indented") and rule.get("kind") != "COMPARISON":
            return True
        if rule.get("has_children"):
            return True
        return rule.get("kind") in {"EXPR_CONCLUSION", "VALUE_CONCLUSION"}

    def _find_known_phrase_references(
        self,
        raw: str,
        known_names: Iterable[str],
    ) -> List[str]:
        references: List[str] = []
        for name in sorted(known_names, key=len, reverse=True):
            if not name:
                continue
            pattern = re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)")
            if pattern.search(raw):
                references.append(name)
        return references

    def _comparison_rhs(self, raw: str, operator: str) -> Optional[str]:
        if not operator:
            return None
        parts = raw.split(operator, 1)
        if len(parts) != 2:
            return None
        return parts[1].strip()

    def _looks_like_variable_reference(self, value: str) -> bool:
        candidate = value.strip()
        if not candidate:
            return False
        if candidate[0] in {"'", '"'}:
            return False
        if candidate.upper() in self._KEYWORDS:
            return False
        if candidate.lower() in {"true", "false"}:
            return False
        if re.fullmatch(r"-?\d+(?:\.\d+)?", candidate):
            return False
        return bool(re.search(r"[A-Za-z_]", candidate))

    def _token_references(self, raw: str, conclusion_var: str) -> List[str]:
        return [
            token
            for token in self._extract_references(raw, conclusion_var)
            if self._looks_like_variable_reference(token)
        ]

    def _value_conclusion_rhs_references(
        self,
        rhs: str,
        known_names: Iterable[str],
        conclusion_var: str,
    ) -> List[str]:
        if not rhs:
            return []

        condition_parts = re.split(r"\bIF\b", rhs, maxsplit=1, flags=re.IGNORECASE)
        if len(condition_parts) == 2:
            condition = condition_parts[1].strip()
            references = self._find_known_phrase_references(condition, known_names)
            references.extend(
                self._unknown_code_identifier_references(
                    condition,
                    references,
                    conclusion_var,
                )
            )
            return references

        if self._looks_like_variable_reference(rhs):
            return [rhs]
        return []

    def _expression_rhs_references(
        self,
        rhs: str,
        known_names: Iterable[str],
        conclusion_var: str,
    ) -> List[str]:
        references = self._find_known_phrase_references(rhs, known_names)
        references.extend(
            self._unknown_code_identifier_references(
                rhs,
                references,
                conclusion_var,
            )
        )
        return references

    def _unknown_code_identifier_references(
        self,
        raw: str,
        known_references: Iterable[str],
        conclusion_var: str,
    ) -> List[str]:
        residual = re.sub(r'"[^"]*"|\'[^\']*\'', " ", raw)
        for reference in sorted(set(known_references), key=len, reverse=True):
            residual = re.sub(
                r"(?<!\w)" + re.escape(reference) + r"(?!\w)",
                " ",
                residual,
            )

        return [
            token
            for token in self._token_references(residual, conclusion_var)
            if "_" in token or re.search(r"[a-z][A-Z]", token)
        ]

    def _clean_reference_candidate(self, value: str) -> str:
        cleaned = value.strip().rstrip(",.;")
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned

    def _build_declaration_discrepancy_index(
        self,
        declarations: Dict[str, dict],
    ) -> Dict[str, List[Tuple[str, int]]]:
        index: Dict[str, List[Tuple[str, int]]] = {}
        for name, declaration in declarations.items():
            normalized = self._normalise_variable_name_for_discrepancy(name)
            index.setdefault(normalized, []).append((name, declaration["line"]))
        return index

    def _find_declaration_discrepancy(
        self,
        reference_name: str,
        declaration_index: Dict[str, List[Tuple[str, int]]],
    ) -> Optional[Tuple[str, int]]:
        normalized = self._normalise_variable_name_for_discrepancy(reference_name)
        matches = declaration_index.get(normalized, [])
        if len(matches) == 1 and matches[0][0] != reference_name:
            return matches[0]
        return None

    def _normalise_variable_name_for_discrepancy(self, name: str) -> str:
        normalized = str(name).translate(self._APOSTROPHE_VARIANTS)
        normalized = re.sub(r"\s+", " ", normalized.strip()).lower()
        normalized = re.sub(r"^(?:the|a)\s+person(?=\b|'s\b)", "person", normalized)
        return normalized

    # -------------------------------------------------------------------------
    # Check 3: Ontology Advisory Semantics
    # -------------------------------------------------------------------------

    def _check_ontology_advisory_semantics(
        self,
        parsed: Dict,
        rule_text: str,
        warnings: List[ValidationWarning],
        review_queue: List[OntologyReviewQueueItem],
    ) -> None:
        declarations = parsed.get("declarations", {})
        rules = parsed.get("rules", [])
        field_names = self._collect_declared_field_names(parsed)
        rule_conclusion_names = self._collect_rule_conclusion_names(rules)
        reference_entries = self._collect_reference_entries(
            rules,
            declarations,
            rule_conclusion_names,
        )
        reference_entries.extend(parsed.get("declaration_references", []))
        exact_referenced_names = {entry["name"] for entry in reference_entries}
        emitted: Set[Tuple[str, str, int]] = set()

        for module_name in self._IMPORT_MARKER_PATTERN.findall(rule_text):
            module_name = module_name.strip()
            self._add_ontology_warning(
                warnings,
                review_queue,
                emitted,
                code="ONTOLOGY_IMPORT_SCOPE_REVIEW",
                message=(
                    f"Imported rule set '{module_name}' contributes ontology terms; "
                    "review imported declarations and dependencies before accepting semantic suggestions."
                ),
                severity="info",
                category="imports",
                node_name=module_name,
                reason="imported rule scope is advisory and may carry stale ontology context",
                review_action="review_imported_rule_scope",
                target=module_name,
            )

        has_statutory_anchor = bool(
            self._STATUTORY_REFERENCE_PATTERN.search(rule_text)
            or self._STATUTORY_DEFINITION_PATTERN.search(rule_text)
        )

        for name, declaration in declarations.items():
            line = declaration.get("line")
            if declaration.get("value_type") == "UNKNOWN":
                self._add_ontology_warning(
                    warnings,
                    review_queue,
                    emitted,
                    code="ONTOLOGY_DECLARATION_TYPE_UNMAPPED",
                    message=(
                        f"Declaration '{name}' has no ontology value-type mapping. "
                        "Confirm its legal concept and datatype before using ontology corrections."
                    ),
                    severity="high-risk",
                    category="declarations",
                    line=line,
                    node_name=name,
                    reason="declaration value type is unknown to the ontology projection",
                    review_action="map_declaration_datatype",
                    target=name,
                    proposed_value="approved ontology datatype mapping",
                )

            if name not in exact_referenced_names:
                self._add_ontology_warning(
                    warnings,
                    review_queue,
                    emitted,
                    code="ONTOLOGY_ORPHAN_CONCEPT",
                    message=(
                        f"Declaration '{name}' is not connected to any rule dependency; "
                        "treat delete or rewrite suggestions as human-review only."
                    ),
                    severity="info",
                    category="orphan_concepts",
                    line=line,
                    node_name=name,
                    reason="declared ontology concept is disconnected from deterministic rule logic",
                    review_action="review_orphan_concept",
                    target=name,
                )

            if self._STATUTORY_REFERENCE_PATTERN.search(name):
                self._add_ontology_warning(
                    warnings,
                    review_queue,
                    emitted,
                    code="ONTOLOGY_STATUTORY_SECTION_REFERENCE",
                    message=(
                        f"Declaration '{name}' looks like a statutory section reference. "
                        "Verify the ontology citation and temporal source before relying on it."
                    ),
                    severity="info",
                    category="sections",
                    line=line,
                    node_name=name,
                    reason="statutory section references need provenance review",
                    review_action="confirm_statutory_section_link",
                    target=name,
                )

            if self._STATUTORY_DEFINITION_PATTERN.search(name):
                self._add_ontology_warning(
                    warnings,
                    review_queue,
                    emitted,
                    code="ONTOLOGY_STATUTORY_DEFINITION_REFERENCE",
                    message=(
                        f"Declaration '{name}' looks like a statutory definition. "
                        "Confirm the definition source before approving ontology corrections."
                    ),
                    severity="info",
                    category="statutory_definitions",
                    line=line,
                    node_name=name,
                    reason="statutory definitions need source and temporal provenance",
                    review_action="confirm_statutory_definition_link",
                    target=name,
                )

            if self._looks_like_legal_concept(name) and not has_statutory_anchor:
                self._add_ontology_warning(
                    warnings,
                    review_queue,
                    emitted,
                    code="ONTOLOGY_LEGAL_CONCEPT_UNANCHORED",
                    message=(
                        f"Legal concept '{name}' has no statutory section or definition anchor in this rule text."
                    ),
                    severity="warning",
                    category="legal_concepts",
                    line=line,
                    node_name=name,
                    reason="legal concept lacks explicit statutory provenance",
                    review_action="attach_concept_provenance",
                    target=name,
                )

        declared_names = set(declarations.keys())
        known_names = declared_names | rule_conclusion_names
        for entry in reference_entries:
            name = entry["name"]
            if name in known_names or self._is_declared_collection_field_reference(name, field_names):
                continue
            self._add_ontology_warning(
                warnings,
                review_queue,
                emitted,
                code="ONTOLOGY_STALE_REFERENCE_CANDIDATE",
                message=(
                    f"Reference '{name}' is not connected to a current declaration or rule node; "
                    "review before accepting any rename or import suggestion."
                ),
                severity="high-risk",
                category="stale_references",
                line=entry.get("line"),
                node_name=name,
                reason="reference is absent from deterministic declaration and node indexes",
                review_action="review_reference_resolution",
                target=name,
            )

        for rule in rules:
            raw = str(rule.get("raw", ""))
            line = rule.get("line")
            node_name = str(rule.get("variable_name", ""))

            for section_match in self._STATUTORY_REFERENCE_PATTERN.findall(raw):
                self._add_ontology_warning(
                    warnings,
                    review_queue,
                    emitted,
                    code="ONTOLOGY_STATUTORY_SECTION_REFERENCE",
                    message=(
                        f"Rule line references '{section_match}'. Confirm the source version before ontology use."
                    ),
                    severity="info",
                    category="sections",
                    line=line,
                    node_name=node_name,
                    reason="statutory section references need source and temporal provenance",
                    review_action="confirm_statutory_section_link",
                    target=section_match,
                )

            if self._STATUTORY_DEFINITION_PATTERN.search(raw):
                self._add_ontology_warning(
                    warnings,
                    review_queue,
                    emitted,
                    code="ONTOLOGY_STATUTORY_DEFINITION_REFERENCE",
                    message=(
                        f"Rule node '{node_name}' appears to encode a statutory definition; "
                        "verify the source before accepting ontology corrections."
                    ),
                    severity="info",
                    category="statutory_definitions",
                    line=line,
                    node_name=node_name,
                    reason="statutory definitions need source and temporal provenance",
                    review_action="confirm_statutory_definition_link",
                    target=node_name,
                )

            dependency_modifiers = set(rule.get("dependency_modifiers", ()))
            if rule.get("is_indented") and dependency_modifiers.intersection({"NOT", "KNOWN"}):
                self._add_ontology_warning(
                    warnings,
                    review_queue,
                    emitted,
                    code="ONTOLOGY_DEPENDENCY_POLARITY_REVIEW",
                    message=(
                        f"Dependency '{raw}' uses ontology-sensitive polarity. "
                        "Do not let ontology suggestions override deterministic dependency semantics."
                    ),
                    severity="high-risk",
                    category="dependencies",
                    line=line,
                    node_name=node_name,
                    reason="negative or known-dependency semantics are policy-sensitive",
                    review_action="review_dependency_polarity",
                    target=node_name,
                )

        self._check_ontology_label_collisions(
            declarations,
            rules,
            warnings,
            review_queue,
            emitted,
        )

    def _check_ontology_label_collisions(
        self,
        declarations: Dict[str, dict],
        rules: List[dict],
        warnings: List[ValidationWarning],
        review_queue: List[OntologyReviewQueueItem],
        emitted: Set[Tuple[str, str, int]],
    ) -> None:
        label_index: Dict[str, List[dict]] = {}
        for name, declaration in declarations.items():
            self._index_ontology_label(
                label_index,
                name,
                "declaration",
                declaration.get("line"),
            )
        for rule in rules:
            self._index_ontology_label(
                label_index,
                str(rule.get("variable_name", "")),
                "rule_node",
                rule.get("line"),
            )

        for normalised, entries in label_index.items():
            if not normalised or len(entries) < 2:
                continue
            labels = {entry["label"] for entry in entries}
            origins = {entry["origin"] for entry in entries}
            first = entries[0]
            if len(labels) > 1:
                self._add_ontology_warning(
                    warnings,
                    review_queue,
                    emitted,
                    code="ONTOLOGY_CONTRADICTORY_LABEL",
                    message=(
                        "Ontology labels collapse to the same concept with different spelling: "
                        f"{', '.join(sorted(labels))}."
                    ),
                    severity="high-risk",
                    category="contradictory_labels",
                    line=first.get("line"),
                    node_name=first["label"],
                    reason="multiple labels normalise to the same ontology concept key",
                    review_action="disambiguate_ontology_label",
                    target=first["label"],
                )
            elif {"declaration", "rule_node"}.issubset(origins):
                self._add_ontology_warning(
                    warnings,
                    review_queue,
                    emitted,
                    code="ONTOLOGY_DUPLICATE_LABEL",
                    message=(
                        f"Ontology label '{first['label']}' appears as both a declaration and a rule node."
                    ),
                    severity="warning",
                    category="duplicates",
                    line=first.get("line"),
                    node_name=first["label"],
                    reason="the same ontology label has multiple deterministic roles",
                    review_action="review_duplicate_label_role",
                    target=first["label"],
                )

    def _index_ontology_label(
        self,
        label_index: Dict[str, List[dict]],
        label: str,
        origin: str,
        line: Optional[int],
    ) -> None:
        label = self._clean_reference_candidate(label)
        if not label:
            return
        normalised = self._normalise_variable_name_for_discrepancy(label)
        normalised = re.sub(r"[^a-z0-9]+", "", normalised)
        label_index.setdefault(normalised, []).append(
            {"label": label, "origin": origin, "line": line}
        )

    def _add_ontology_warning(
        self,
        warnings: List[ValidationWarning],
        review_queue: List[OntologyReviewQueueItem],
        emitted: Set[Tuple[str, str, int]],
        code: str,
        message: str,
        severity: str,
        category: str,
        target: str,
        line: Optional[int] = None,
        node_name: Optional[str] = None,
        reason: Optional[str] = None,
        review_action: Optional[str] = None,
        proposed_value: Optional[str] = None,
    ) -> None:
        key = (code, str(node_name or target), int(line or 0))
        if key in emitted:
            return
        emitted.add(key)

        proposal_id: Optional[str] = None
        if review_action is not None:
            proposal_id = self._ontology_review_proposal_id(code, target, line, review_action)
            review_queue.append(
                OntologyReviewQueueItem(
                    proposal_id=proposal_id,
                    warning_code=code,
                    action=review_action,
                    target=target,
                    rationale=reason or message,
                    line=line,
                    node_name=node_name,
                    proposed_value=proposed_value,
                )
            )

        warnings.append(
            ValidationWarning(
                code=code,
                message=message,
                line=line,
                node_name=node_name,
                severity=severity,
                category=category,
                source="ontology",
                blocking=code in self._ontology_blocking_warning_codes,
                reason=reason,
                review_required=proposal_id is not None,
                review_item_id=proposal_id,
            )
        )

    def _blocking_semantic_policy_errors(
        self,
        warnings: List[ValidationWarning],
    ) -> List[ValidationError]:
        errors: List[ValidationError] = []
        for warning in warnings:
            if not warning.blocking:
                continue
            errors.append(
                ValidationError(
                    code=f"BLOCKING_{warning.code}",
                    message=(
                        f"Ontology validation policy blocks this rule until '{warning.code}' is reviewed: "
                        f"{warning.message}"
                    ),
                    line=warning.line,
                    node_name=warning.node_name,
                    severity=warning.severity,
                    category=warning.category,
                    source=warning.source,
                    blocking=True,
                    reason="policy_configured_blocking",
                    review_required=warning.review_required,
                    review_item_id=warning.review_item_id,
                )
            )
        return errors

    def _ontology_review_proposal_id(
        self,
        code: str,
        target: str,
        line: Optional[int],
        action: str,
    ) -> str:
        digest = hashlib.sha256(
            f"{code}|{target}|{line or ''}|{action}".encode("utf-8")
        ).hexdigest()[:12]
        return f"ontology-review-{digest}"

    def _looks_like_legal_concept(self, label: str) -> bool:
        lowered = label.lower()
        return any(term in lowered for term in self._LEGAL_CONCEPT_TERMS)

    # -------------------------------------------------------------------------
    # Check 4: Import Resolution (Phase 2 Placeholder)
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # Check 5: DAG Cycle Check
    # -------------------------------------------------------------------------

    def _check_dag_cycles(
        self,
        parsed: Dict,
        errors: List[ValidationError],
    ) -> None:
        declarations = parsed["declarations"]
        rules = parsed["rules"]

        if not rules:
            return

        all_nodes: Set[str] = set()
        for decl_name in declarations:
            all_nodes.add(f"decl:{decl_name}")
        for rule in rules:
            all_nodes.add(f"rule:{rule['line']}")

        edges: Dict[str, Set[str]] = {n: set() for n in all_nodes}

        decl_node_map: Dict[str, str] = {
            name: f"decl:{name}" for name in declarations
        }

        rule_conclusion_map: Dict[str, List[str]] = {}
        for rule in rules:
            var_name = rule["variable_name"]
            rule_node = f"rule:{rule['line']}"
            rule_conclusion_map.setdefault(var_name, []).append(rule_node)

        for rule in rules:
            rule_node = f"rule:{rule['line']}"
            conclusion_var = rule["variable_name"]

            for ref in rule.get("references", []):
                if ref in decl_node_map:
                    edges[rule_node].add(decl_node_map[ref])
                if ref in rule_conclusion_map:
                    for dep_rule_node in rule_conclusion_map[ref]:
                        if dep_rule_node != rule_node:
                            edges[rule_node].add(dep_rule_node)

            if conclusion_var in decl_node_map:
                edges[rule_node].add(decl_node_map[conclusion_var])

        in_degree: Dict[str, int] = {n: len(edges[n]) for n in all_nodes}

        reverse: Dict[str, List[str]] = {n: [] for n in all_nodes}
        for node, deps in edges.items():
            for dep in deps:
                reverse[dep].append(node)

        queue: deque = deque(n for n in all_nodes if in_degree[n] == 0)
        visited_count = 0

        while queue:
            node = queue.popleft()
            visited_count += 1
            for dependent in reverse[node]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if visited_count != len(all_nodes):
            cycle_nodes = [n for n in all_nodes if in_degree[n] > 0]
            var_names = []
            for cn in cycle_nodes:
                if cn.startswith("decl:"):
                    var_names.append(cn[5:])
                elif cn.startswith("rule:"):
                    line = cn[5:]
                    matching = [r for r in rules if str(r["line"]) == line]
                    var_names.append(matching[0]["variable_name"] if matching else cn)
            errors.append(ValidationError(
                code="CYCLIC_DEPENDENCY",
                message=f"Cyclic dependency detected involving: {', '.join(sorted(set(var_names))[:5])}",
                node_name=", ".join(sorted(set(var_names))[:5]),
            ))

    def _check_node_set_declarations(
        self,
        rule_text: str,
        rule_name: str,
        errors: List[ValidationError],
        warnings: List[ValidationWarning],
    ) -> None:
        result = self._declaration_validator.validate_rule_text(rule_text, rule_name)
        high_confidence_codes = {"DUPLICATE_DECLARATION", "SELF_REFERENTIAL_RULE", "NULL_NODESET"}
        for error in result.errors:
            if error.code not in high_confidence_codes:
                continue
            validation_error = ValidationError(
                code=error.code,
                message=error.message,
                line=error.line,
                node_name=error.node_name,
            )
            if validation_error not in errors:
                errors.append(validation_error)

    # -------------------------------------------------------------------------
    # Cache Management
    # -------------------------------------------------------------------------

    def _compute_content_hash(self, rule_text: str) -> str:
        return hashlib.sha256(rule_text.encode("utf-8")).hexdigest()

    def _get_cached(self, content_hash: str) -> Optional[ValidationResult]:
        if content_hash in self._cache:
            ts, result = self._cache[content_hash]
            if time.time() - ts < self._cache_ttl:
                self._cache.move_to_end(content_hash)
                return result
            del self._cache[content_hash]
        return None

    def _set_cached(self, content_hash: str, result: ValidationResult) -> None:
        if content_hash in self._cache:
            self._cache.move_to_end(content_hash)
            self._cache[content_hash] = (time.time(), result)
            return
        if len(self._cache) >= self._cache_maxsize:
            self._cache.popitem(last=False)
        self._cache[content_hash] = (time.time(), result)
