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

    @property
    def waiver_id(self) -> str:
        """Stable identifier the frontend can use for human-review waivers."""
        if self.node_name:
            return f"{self.code}:{self.node_name}"
        if self.line is not None:
            return f"{self.code}:line_{self.line}"
        return self.code

    def to_dict(self) -> dict:
        result = {"code": self.code, "message": self.message, "waiver_id": self.waiver_id}
        if self.line is not None:
            result["line"] = self.line
        if self.node_name is not None:
            result["node_name"] = self.node_name
        return result


@dataclass(frozen=True)
class ValidationError(ValidationEntry):
    """A single validation error."""

    def __repr__(self) -> str:
        return f"ValidationError(code={self.code!r}, message={self.message!r}, line={self.line})"


@dataclass(frozen=True)
class ValidationWarning(ValidationEntry):
    """A single validation warning."""

    def __repr__(self) -> str:
        return f"ValidationWarning(code={self.code!r}, message={self.message!r}, line={self.line})"


@dataclass(frozen=True)
class ValidationResult:
    """Result of a validation run. Errors and warnings are tuples (immutable)."""
    valid: bool
    errors: Tuple[ValidationError, ...] = ()
    warnings: Tuple[ValidationWarning, ...] = ()

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
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
    _ITERATE_PATTERN = re.compile(r"^(.+?)\s+FOR\s+.+$")
    _COMMENT_PATTERN = re.compile(r"^(#|//)")
    _INDENTED_LINE_PATTERN = re.compile(r"^(\s+)(.+)$")
    _QUANTIFIER_PATTERN = re.compile(
        r"^(?:(?:AND|OR)\b\s*)?"
        r"(?:(?:MANDATORY|OPTIONALLY|POSSIBLY)\b\s*)?"
        r"(?:(?:NOT|KNOWN)\b\s*)*"
        r"(?:(?:NEEDS|WANTS)\b\s*)?",
        re.IGNORECASE,
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

    def __init__(
        self,
        cache_maxsize: int = 512,
        cache_ttl_seconds: int = 300,
        enable_node_set_validation: bool = True,
    ):
        self._cache: OrderedDict[str, Tuple[float, ValidationResult]] = OrderedDict()
        self._cache_maxsize = cache_maxsize
        self._cache_ttl = cache_ttl_seconds
        self._enable_node_set_validation = enable_node_set_validation
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

        parsed = self._check_syntax(rule_text, errors, warnings)
        if errors:
            result = ValidationResult(valid=False, errors=tuple(errors), warnings=tuple(warnings))
            self._set_cached(content_hash, result)
            return result

        self._check_type_consistency(parsed, errors, warnings)

        self._check_dag_cycles(parsed, errors)

        if self._enable_node_set_validation:
            self._check_node_set_declarations(rule_text, rule_name, errors, warnings)

        result = ValidationResult(valid=len(errors) == 0, errors=tuple(errors), warnings=tuple(warnings))
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
        rules: List[dict] = []
        rule_stack: List[dict] = []
        in_list = False
        list_var_name = ""
        line_number = 0

        for raw_line in rule_text.splitlines():
            line_number += 1
            stripped = raw_line.strip()

            if not stripped or self._COMMENT_PATTERN.match(stripped):
                in_list = False
                continue

            if in_list and stripped.startswith("ITEM"):
                continue

            indent_match = self._INDENTED_LINE_PATTERN.match(raw_line)
            if indent_match:
                indent = len(indent_match.group(1))
                child_text = indent_match.group(2).strip()
                child_clean = self._QUANTIFIER_PATTERN.sub("", child_text).strip()
                if child_clean:
                    self._parse_rule_line(
                        child_clean,
                        line_number,
                        declarations,
                        rules,
                        errors,
                        indent=indent,
                        is_indented=True,
                        rule_stack=rule_stack,
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
                in_list = "AS LIST" in stripped
                list_var_name = var_name if in_list else ""
                continue

            in_list = False
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
            "rules": rules,
            "lines": line_number,
        }

    _KEYWORDS = frozenset({
        "IS", "AS", "CALC", "FOR", "ALL", "NONE", "SOME",
        "AND", "OR", "NOT", "KNOWN", "MANDATORY", "OPTIONALLY", "POSSIBLY",
        "NEEDS", "WANTS", "ITEM", "INPUT", "FIXED", "IF",
        "IN", "LIST", "TRUE", "FALSE",
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
    ) -> None:
        def _append_rule(rule: dict) -> None:
            rule["indent"] = indent
            rule["is_indented"] = is_indented
            rule["has_children"] = False
            if rule_stack is not None:
                while rule_stack and rule_stack[-1]["indent"] >= indent:
                    rule_stack.pop()
                if rule_stack:
                    rule_stack[-1]["has_children"] = True
                rule_stack.append(rule)
            rules.append(rule)

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

        iter_match = self._ITERATE_PATTERN.match(text)
        if iter_match:
            var_name = iter_match.group(1).strip()
            refs = self._extract_references(text, var_name)
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

        rule_conclusion_names = self._collect_rule_conclusion_names(rules)
        reference_entries = self._collect_reference_entries(rules, declarations, rule_conclusion_names)
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
    # Check 3: Import Resolution (Phase 2 Placeholder)
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # Check 4: DAG Cycle Check
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
