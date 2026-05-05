"""
IMPORT_MATCHER and RULE_SET_MATCHER regex constants for import directives.

These patterns detect `IMPORT:` and `RULE SET:` directives in rule text,
enabling modular composition of rule sets.
"""

import re

IMPORT_MATCHER = re.compile(r"^IMPORT:\s*(.+)$", re.MULTILINE)
RULE_SET_HEADER_MATCHER = re.compile(r"^RULE SET:\s*(.+)$", re.MULTILINE)


def extract_imports(rule_text: str) -> list:
    """
    Extract all IMPORT directive target names from rule text.

    Args:
        rule_text: Full text content of the rule

    Returns:
        List of imported module names (preserving order of appearance)
    """
    return [m.group(1).strip() for m in IMPORT_MATCHER.finditer(rule_text)]


def extract_rule_set_name(rule_text: str) -> str:
    """
    Extract the RULE SET name from rule text header.

    Args:
        rule_text: Full text content of the rule

    Returns:
        Rule set name, or empty string if no RULE SET header found
    """
    m = RULE_SET_HEADER_MATCHER.search(rule_text)
    return m.group(1).strip() if m else ""
