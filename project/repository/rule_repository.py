"""
Rule Repository Module.
Handles database operations for PALOS rules, files, and history.
Implements access levels and strong typing where appropriate.
"""

import json
from typing import Any, Dict, List, Optional
from sqlalchemy.exc import SQLAlchemyError
from project.domain.models.models import Rule, File, History
from project import db
from project.loggers import Logger

# Protected Module-Level Logger (Access Level: Protected)
_logger: Logger = Logger.get_logger(__name__)


# -------------------------------------------------------------------------
# Public Access Level: API Functions (Rule Queries)
# -------------------------------------------------------------------------
def find_id_by_name(rule_name: str) -> Optional[int]:
    """
    Public API: Finds rule ID by name.
    
    Args:
        rule_name: Name of the rule to find
        
    Returns:
        Rule ID or None if not found
    """
    rule: Optional[Rule] = Rule.query.filter_by(name=rule_name).first()
    rule_id: Optional[int] = rule.rule_id if rule else None
    _logger.info(f"Found Rule ID: {rule_id}")
    return rule_id


def find_rule_by_rule_name(rule_name: str) -> Optional[Rule]:
    """
    Public API: Finds rule by name.
    
    Args:
        rule_name: Name of the rule to find
        
    Returns:
        Rule object or None if not found
    """
    if not rule_name:
        _logger.warning("find_rule_by_rule_name called without a rule name")
        return None
    return Rule.query.filter_by(name=rule_name).first()


def find_rule_text_by_rule_name(rule_name: str) -> Optional[File]:
    """
    Public API: Finds rule text (file) by rule name.
    
    Args:
        rule_name: Name of the rule
        
    Returns:
        File object or None if not found
    """
    rule: Optional[Rule] = find_rule_by_rule_name(rule_name)
    return rule.get_the_latest_file() if rule is not None else None


def find_rule_text_by_rule_id(rule_id: int) -> Optional[File]:
    """
    Public API: Finds rule text (file) by rule ID.
    
    Args:
        rule_id: ID of the rule
        
    Returns:
        File object or None if not found
    """
    if rule_id is None:
        _logger.warning("find_rule_text_by_rule_id called without a rule id")
        return None
    rule: Optional[Rule] = Rule.query.filter_by(rule_id=rule_id).first()
    return rule.get_the_latest_file() if rule is not None else None


def find_all_rules() -> List[Dict[str, Any]]:
    """
    Public API: Finds all rules in the database.
    
    Returns:
        List of rule dictionaries (excluding files and histories)
    """
    my_list: List[Dict[str, Any]] = list()
    for each_rule in Rule.query.all():
        my_list.append(each_rule.to_dict(rules=('-rule_files', '-rule_histories')))
    return my_list


# -------------------------------------------------------------------------
# Public Access Level: API Functions (Rule Updates)
# -------------------------------------------------------------------------
def update_rule_name_and_category(old_rule_name: str, new_rule_name: str, new_category: str) -> bool:
    """
    Public API: Updates rule name and category.
    
    Args:
        old_rule_name: Current rule name
        new_rule_name: New rule name
        new_category: New category
        
    Returns:
        True if update successful, False otherwise
        
    Raises:
        SQLAlchemyError: If database operation fails
    """
    try:
        updated_rows: int = Rule.query.filter_by(name=old_rule_name).update(
            dict(name=new_rule_name, category=new_category)
        )
        db.session.commit()
        return updated_rows > 0
    except SQLAlchemyError as exc:
        db.session.rollback()
        _logger.exception("Failed to update rule '%s': %s", old_rule_name, exc)
        raise


# -------------------------------------------------------------------------
# Public Access Level: API Functions (Rule Creation)
# -------------------------------------------------------------------------
def create_rule(rule_details: Dict[str, Any]) -> int:
    """
    Public API: Creates a new rule.
    
    Args:
        rule_details: Dictionary containing rule details (must include 'rule_name')
        
    Returns:
        Rule ID (existing or newly created)
        
    Raises:
        ValueError: If rule_name is not provided
        SQLAlchemyError: If database operation fails
    """
    rule_name: str = rule_details.get('rule_name')
    if not rule_name:
        raise ValueError("rule_name is required")
    
    rule_id: Optional[int] = find_id_by_name(rule_name)
    if rule_id is not None:
        return rule_id

    try:
        rule: Rule = Rule(**rule_details)
        db.session.add(rule)
        db.session.commit()
        return rule.rule_id
    except SQLAlchemyError as exc:
        db.session.rollback()
        _logger.exception("Failed to create rule '%s': %s", rule_name, exc)
        raise


def create_rule_file(rule_id: int, new_file: bytearray) -> None:
    """
    Public API: Creates a new rule file.
    
    Args:
        rule_id: ID of the rule
        new_file: File content as bytearray
        
    Raises:
        ValueError: If rule_id or new_file is None
        SQLAlchemyError: If database operation fails
    """
    if rule_id is None:
        raise ValueError("rule_id is required to create a rule file")
    if new_file is None:
        raise ValueError("new_file is required to create a rule file")
    
    existing_file: Optional[File] = find_rule_text_by_rule_id(rule_id)
    if existing_file is None or existing_file.files != new_file:
        try:
            _logger.info(f"Creating new file for rule_id={rule_id}")
            new_file_record: File = File(rule_id=rule_id, files=new_file)
            db.session.add(new_file_record)
            db.session.commit()
        except SQLAlchemyError as exc:
            db.session.rollback()
            _logger.exception("Failed to create file for rule_id=%s: %s", rule_id, exc)
            raise


def create_rule_history(rule_id: int, history: Dict[str, Any]) -> None:
    """
    Public API: Creates rule history record.
    
    Args:
        rule_id: ID of the rule
        history: History data as dictionary
        
    Raises:
        ValueError: If rule_id or history is None
        SQLAlchemyError: If database operation fails
    """
    if rule_id is None:
        raise ValueError("rule_id is required to create rule history")
    if history is None:
        raise ValueError("history payload is required")
    
    try:
        history_record: History = History(rule_id, history)
        db.session.add(history_record)
        db.session.commit()
    except SQLAlchemyError as exc:
        db.session.rollback()
        _logger.exception("Failed to create history for rule_id=%s: %s", rule_id, exc)
        raise


# -------------------------------------------------------------------------
# Protected Access Level: Internal Helpers (Single Underscore)
# -------------------------------------------------------------------------
def _validate_rule_name(rule_name: str) -> bool:
    """
    Protected Helper: Validates rule name format.
    
    Args:
        rule_name: Rule name to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not rule_name or len(rule_name.strip()) == 0:
        return False
    return True


def _log_database_operation(operation: str, rule_id: Optional[int] = None) -> None:
    """
    Protected Helper: Logs database operations for auditing.
    
    Args:
        operation: Operation type (CREATE, UPDATE, DELETE, QUERY)
        rule_id: Optional rule ID
    """
    if rule_id:
        _logger.info(f"Database operation: {operation}, rule_id: {rule_id}")
    else:
        _logger.info(f"Database operation: {operation}")