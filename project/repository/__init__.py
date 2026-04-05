"""
PALOS Rule Repository Package Initialization.
Defines the public API surface for the rule repository module.
"""

from .rule_repository import (
    find_id_by_name,
    find_rule_by_rule_name,
    find_rule_text_by_rule_name,
    find_rule_text_by_rule_id,
    find_all_rules,
    update_rule_name_and_category,
    create_rule,
    create_rule_file,
    create_rule_history
)

# Public Access Level: Explicitly define the public API surface
# Prevents internal implementation details from being accidentally imported
# Protected helpers (starting with _) are intentionally excluded
__all__ = [
    'find_id_by_name',
    'find_rule_by_rule_name',
    'find_rule_text_by_rule_name',
    'find_rule_text_by_rule_id',
    'find_all_rules',
    'update_rule_name_and_category',
    'create_rule',
    'create_rule_file',
    'create_rule_history'
]