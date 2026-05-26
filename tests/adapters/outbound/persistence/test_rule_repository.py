"""
Unit tests for RuleRepositoryImpl.

Tests database operations against mocked SQLAlchemy sessions,
covering CRUD operations for rules, files, and history.
"""

import pytest
from unittest.mock import MagicMock, patch

from src.adapters.outbound.persistence.rule_repository import RuleRepositoryImpl
from src.adapters.outbound.persistence.models import RuleORM
from src.domain.models.rule import RuleEntity


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def rule_repository(mock_db_session):
    """Create a RuleRepositoryImpl instance with mock DB."""
    return RuleRepositoryImpl(mock_db_session)


# =============================================================================
# find_id_by_name
# =============================================================================

class TestFindIdByName:
    """Tests for RuleRepositoryImpl.find_id_by_name."""

    def test_found(self, rule_repository, mock_db_session):
        """Returns rule_id when rule exists."""
        mock_rule = MagicMock()
        mock_rule.rule_id = 42
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = mock_rule

        result = rule_repository.find_id_by_name("Test Rule")

        assert result == 42

    def test_not_found(self, rule_repository, mock_db_session):
        """Returns None when rule doesn't exist."""
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = None

        result = rule_repository.find_id_by_name("NonExistent")

        assert result is None


# =============================================================================
# find_rule_by_rule_name
# =============================================================================

class TestFindRuleByRuleName:
    """Tests for RuleRepositoryImpl.find_rule_by_rule_name."""

    def test_found(self, rule_repository, mock_db_session):
        """Returns RuleEntity when rule exists."""
        mock_orm = MagicMock(spec=RuleORM)
        mock_orm.rule_id = 1
        mock_orm.name = "Test Rule"
        mock_orm.category = "TestCategory"
        mock_orm.description = "TestDesc"
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = mock_orm

        result = rule_repository.find_rule_by_rule_name("Test Rule")

        assert isinstance(result, RuleEntity)
        assert result.name == "Test Rule"
        assert result.category == "TestCategory"

    def test_not_found(self, rule_repository, mock_db_session):
        """Returns None when rule doesn't exist."""
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = None

        result = rule_repository.find_rule_by_rule_name("NonExistent")

        assert result is None

    def test_empty_name_returns_none(self, rule_repository, mock_db_session):
        """Returns None for empty rule name without querying DB."""
        result = rule_repository.find_rule_by_rule_name("")

        assert result is None
        mock_db_session.query.assert_not_called()


# =============================================================================
# find_all_rules
# =============================================================================

class TestFindAllRules:
    """Tests for RuleRepositoryImpl.find_all_rules."""

    def test_returns_list(self, rule_repository, mock_db_session):
        """Returns list of rule dicts."""
        # Use spec=RuleORM to get real attribute access
        r1 = MagicMock(spec=RuleORM)
        r1.rule_id = 1
        r1.name = "Rule 1"
        r1.category = "Category 1"
        r1.description = "Desc 1"
        r2 = MagicMock(spec=RuleORM)
        r2.rule_id = 2
        r2.name = "Rule 2"
        r2.category = "Category 2"
        r2.description = "Desc 2"

        mock_db_session.query.return_value.all.return_value = [r1, r2]

        result = rule_repository.find_all_rules()

        assert len(result) == 2
        assert result[0]["name"] == "Rule 1"
        assert result[1]["name"] == "Rule 2"

    def test_empty_list(self, rule_repository, mock_db_session):
        """Returns empty list when no rules exist."""
        mock_db_session.query.return_value.all.return_value = []

        result = rule_repository.find_all_rules()

        assert result == []


# =============================================================================
# create_rule
# =============================================================================

class TestCreateRule:
    """Tests for RuleRepositoryImpl.create_rule."""

    def test_create_success(self, rule_repository, mock_db_session):
        """Creates rule and returns new ID."""
        rule_repository.find_id_by_name = MagicMock(return_value=None)

        # Simulate SQLAlchemy assigning the ID after add/commit
        def _assign_id(instance):
            instance.rule_id = 1
        mock_db_session.add.side_effect = _assign_id

        result = rule_repository.create_rule({
            "rule_name": "New Rule",
            "rule_category": "Test Category",
            "rule_description": "Test description",
        })

        assert result == 1
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

    def test_create_already_exists(self, rule_repository, mock_db_session):
        """Returns existing ID when rule already exists."""
        rule_repository.find_id_by_name = MagicMock(return_value=1)

        result = rule_repository.create_rule({
            "rule_name": "Existing Rule",
            "rule_category": "Category",
            "rule_description": "Description",
        })

        assert result == 1
        mock_db_session.add.assert_not_called()

    def test_create_missing_name_raises(self, rule_repository, mock_db_session):
        """Raises ValueError when rule_name is missing."""
        with pytest.raises(ValueError, match="rule_name is required"):
            rule_repository.create_rule({
                "rule_category": "Category",
                "rule_description": "Description",
            })


# =============================================================================
# update_rule_name_and_category
# =============================================================================

class TestUpdateRuleNameAndCategory:
    """Tests for RuleRepositoryImpl.update_rule_name_and_category."""

    def test_update_success(self, rule_repository, mock_db_session):
        """Returns True when rule is updated."""
        mock_db_session.query.return_value.filter_by.return_value.update.return_value = 1

        result = rule_repository.update_rule_name_and_category("Old Name", "New Name", "New Category")

        assert result is True
        mock_db_session.commit.assert_called_once()

    def test_update_not_found(self, rule_repository, mock_db_session):
        """Returns False when rule doesn't exist."""
        mock_db_session.query.return_value.filter_by.return_value.update.return_value = 0

        result = rule_repository.update_rule_name_and_category("NonExistent", "New Name", "New Category")

        assert result is False


# =============================================================================
# create_rule_file
# =============================================================================

class TestCreateRuleFile:
    """Tests for RuleRepositoryImpl.create_rule_file."""

    def test_create_success(self, rule_repository, mock_db_session):
        """Creates file record and commits."""
        rule_repository.create_rule_file(1, bytearray(b"file content"))

        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

    def test_create_missing_rule_id_raises(self, rule_repository, mock_db_session):
        """Raises ValueError when rule_id is None."""
        with pytest.raises(ValueError, match="rule_id is required"):
            rule_repository.create_rule_file(None, bytearray(b"content"))

    def test_create_missing_file_raises(self, rule_repository, mock_db_session):
        """Raises ValueError when file content is None."""
        with pytest.raises(ValueError, match="new_file is required"):
            rule_repository.create_rule_file(1, None)


# =============================================================================
# create_rule_history
# =============================================================================

class TestCreateRuleHistory:
    """Tests for RuleRepositoryImpl.create_rule_history."""

    def test_create_success(self, rule_repository, mock_db_session):
        """Creates history record and commits."""
        rule_repository.create_rule_history(1, {"data": "history"})

        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

    def test_create_missing_rule_id_raises(self, rule_repository, mock_db_session):
        """Raises ValueError when rule_id is None."""
        with pytest.raises(ValueError, match="rule_id is required"):
            rule_repository.create_rule_history(None, {"data": "history"})

    def test_create_missing_history_raises(self, rule_repository, mock_db_session):
        """Raises ValueError when history is None."""
        with pytest.raises(ValueError, match="history payload is required"):
            rule_repository.create_rule_history(1, None)


# =============================================================================
# find_rule_text_by_rule_name
# =============================================================================

class TestFindRuleTextByRuleName:
    def test_found(self, rule_repository, mock_db_session):
        mock_rule = MagicMock(spec=RuleORM)
        mock_file = MagicMock()
        mock_file.file_id = 10
        mock_file.rule_id = 1
        mock_file.files = b"rule text content"
        mock_rule.get_latest_file.return_value = mock_file
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = mock_rule
        result = rule_repository.find_rule_text_by_rule_name("Test Rule")
        assert result is not None
        assert result.files == b"rule text content"

    def test_rule_not_found(self, rule_repository, mock_db_session):
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = None
        result = rule_repository.find_rule_text_by_rule_name("Missing")
        assert result is None

    def test_no_file_for_rule(self, rule_repository, mock_db_session):
        mock_rule = MagicMock(spec=RuleORM)
        mock_rule.get_latest_file.return_value = None
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = mock_rule
        result = rule_repository.find_rule_text_by_rule_name("NoFileRule")
        assert result is None


# =============================================================================
# find_rule_by_rule_name_with_latest_history
# =============================================================================

class TestFindRuleByNameWithLatestHistory:
    def test_found_with_history(self, rule_repository, mock_db_session):
        mock_rule = MagicMock(spec=RuleORM)
        mock_rule.rule_id = 1
        mock_rule.name = "Test"
        mock_rule.category = "Cat"
        mock_rule.description = "Desc"
        mock_history = MagicMock()
        mock_history.history = {"key": "val"}
        mock_rule.get_latest_history.return_value = mock_history
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = mock_rule
        result = rule_repository.find_rule_by_rule_name_with_latest_history("Test")
        assert result is not None
        assert result['history'] == {"key": "val"}
        assert result['rule'].name == "Test"

    def test_found_no_history(self, rule_repository, mock_db_session):
        mock_rule = MagicMock(spec=RuleORM)
        mock_rule.rule_id = 1
        mock_rule.name = "Test"
        mock_rule.category = "Cat"
        mock_rule.description = "Desc"
        mock_rule.get_latest_history.return_value = None
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = mock_rule
        result = rule_repository.find_rule_by_rule_name_with_latest_history("Test")
        assert result is not None
        assert result['history'] is None

    def test_not_found(self, rule_repository, mock_db_session):
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = None
        result = rule_repository.find_rule_by_rule_name_with_latest_history("Missing")
        assert result is None


# =============================================================================
# update_rule_name_and_category — error paths
# =============================================================================

class TestUpdateRuleNameAndCategoryErrorPaths:
    def test_sqlalchemy_error_rollback_and_reraise(self, rule_repository, mock_db_session):
        from sqlalchemy.exc import SQLAlchemyError
        mock_db_session.query.return_value.filter_by.return_value.update.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            rule_repository.update_rule_name_and_category("Old", "New", "Cat")
        mock_db_session.rollback.assert_called_once()


# =============================================================================
# create_rule — error paths
# =============================================================================

class TestCreateRuleErrorPaths:
    def test_sqlalchemy_error_rollback_and_reraise(self, rule_repository, mock_db_session):
        from sqlalchemy.exc import SQLAlchemyError
        rule_repository.find_id_by_name = MagicMock(return_value=None)
        mock_db_session.add.side_effect = SQLAlchemyError("insert error")
        with pytest.raises(SQLAlchemyError):
            rule_repository.create_rule({
                "rule_name": "New Rule",
                "rule_category": "Cat",
                "rule_description": "Desc",
            })
        mock_db_session.rollback.assert_called_once()


# =============================================================================
# create_rule_file — error paths
# =============================================================================

class TestCreateRuleFileErrorPaths:
    def test_sqlalchemy_error_rollback_and_reraise(self, rule_repository, mock_db_session):
        from sqlalchemy.exc import SQLAlchemyError
        mock_db_session.add.side_effect = SQLAlchemyError("file insert error")
        with pytest.raises(SQLAlchemyError):
            rule_repository.create_rule_file(1, bytearray(b"content"))
        mock_db_session.rollback.assert_called_once()


# =============================================================================
# create_rule_history — error paths
# =============================================================================

class TestCreateRuleHistoryErrorPaths:
    def test_sqlalchemy_error_rollback_and_reraise(self, rule_repository, mock_db_session):
        from sqlalchemy.exc import SQLAlchemyError
        mock_db_session.add.side_effect = SQLAlchemyError("history insert error")
        with pytest.raises(SQLAlchemyError):
            rule_repository.create_rule_history(1, {"data": "history"})
        mock_db_session.rollback.assert_called_once()


# =============================================================================
# _to_rule_entity / _to_file_entity
# =============================================================================

class TestEntityConversion:
    def test_to_rule_entity(self, rule_repository):
        orm = MagicMock(spec=RuleORM)
        orm.rule_id = 1
        orm.name = "Test"
        orm.category = "Cat"
        orm.description = "Desc"
        result = rule_repository._to_rule_entity(orm)
        assert result.rule_id == 1
        assert result.name == "Test"
        assert result.category == "Cat"
        assert result.description == "Desc"

    def test_to_file_entity(self, rule_repository):
        from src.adapters.outbound.persistence.models import FileORM
        orm = MagicMock(spec=FileORM)
        orm.file_id = 10
        orm.rule_id = 1
        orm.files = b"content"
        result = rule_repository._to_file_entity(orm)
        assert result.file_id == 10
        assert result.rule_id == 1
        assert result.files == b"content"
