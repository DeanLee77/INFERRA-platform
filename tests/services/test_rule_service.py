"""
Tests for the RuleService.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from src.services.rule_service import RuleService
from src.domain.exceptions import RuleValidationError
from src.domain.fact_values import FactValue, FactValueType
from src.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph
from src.domain.models import RuleEntity, RuleFileEntity
from src.domain.models.rule_file_payload import PAYLOAD_TYPE
from src.domain.nodes.node_set import NodeSet
from src.services.rule_validation_service import RuleValidationService


@pytest.fixture
def mock_rule_repository():
    """Create a mock rule repository."""
    return MagicMock()


@pytest.fixture
def rule_service(mock_rule_repository):
    """Create a RuleService instance."""
    return RuleService(mock_rule_repository)


class TestRuleService:
    """Tests for RuleService."""
    
    def test_get_rule_by_name_success(self, rule_service, mock_rule_repository):
        """Test getting a rule by name."""
        mock_rule = RuleEntity(rule_id=1, name="Test Rule", category="Test Category", description="Test description")
        mock_rule_repository.find_rule_by_rule_name.return_value = mock_rule
        
        result = rule_service.get_rule_by_name("Test Rule")
        
        assert result == mock_rule
        assert result.name == "Test Rule"
        mock_rule_repository.find_rule_by_rule_name.assert_called_once_with("Test Rule")
    
    def test_get_rule_by_name_not_found(self, rule_service, mock_rule_repository):
        """Test error when rule not found."""
        mock_rule_repository.find_rule_by_rule_name.return_value = None
        
        with pytest.raises(LookupError, match="was not found"):
            rule_service.get_rule_by_name("NonExistent Rule")
    
    def test_get_rule_text_success(self, rule_service, mock_rule_repository):
        """Test getting rule text."""
        mock_file = RuleFileEntity(file_id=1, rule_id=1, files=b"rule content")
        mock_rule_repository.find_rule_text_by_rule_name.return_value = mock_file
        
        result = rule_service.get_rule_text("Test Rule")
        
        assert result == "rule content"
        mock_rule_repository.find_rule_text_by_rule_name.assert_called_once_with("Test Rule")
    
    def test_get_rule_text_not_found(self, rule_service, mock_rule_repository):
        """Test error when rule text not found."""
        mock_rule_repository.find_rule_text_by_rule_name.return_value = None
        
        with pytest.raises(LookupError, match="was not found or has no stored file"):
            rule_service.get_rule_text("NonExistent Rule")
    
    def test_list_rules(self, rule_service, mock_rule_repository):
        """Test listing all rules."""
        mock_rules = [
            {'rule_id': 1, 'name': 'Rule 1', 'category': 'Category 1', 'description': 'Desc 1'},
            {'rule_id': 2, 'name': 'Rule 2', 'category': 'Category 2', 'description': 'Desc 2'},
        ]
        mock_rule_repository.find_all_rules.return_value = mock_rules
        
        result = rule_service.list_rules()
        
        assert result == mock_rules
        mock_rule_repository.find_all_rules.assert_called_once()
    
    def test_update_rule_success(self, rule_service, mock_rule_repository):
        """Test updating a rule."""
        mock_rule = RuleEntity(rule_id=1, name="New Rule", category="New Category", description="Description")
        mock_rule_repository.update_rule_name_and_category.return_value = True
        mock_rule_repository.find_rule_by_rule_name.return_value = mock_rule
        
        result = rule_service.update_rule("Old Rule", "New Rule", "New Category")
        
        assert result.name == "New Rule"
        mock_rule_repository.update_rule_name_and_category.assert_called_once_with("Old Rule", "New Rule", "New Category")
    
    def test_update_rule_not_found(self, rule_service, mock_rule_repository):
        """Test error when updating non-existent rule."""
        mock_rule_repository.update_rule_name_and_category.return_value = False
        
        with pytest.raises(LookupError, match="was not found"):
            rule_service.update_rule("NonExistent", "New Name", "New Category")
    
    def test_create_rule_success(self, rule_service, mock_rule_repository):
        """Test creating a rule."""
        mock_rule = RuleEntity(rule_id=1, name="New Rule", category="Test Category", description="Test description")
        mock_rule_repository.create_rule.return_value = 1
        mock_rule_repository.find_rule_by_rule_name.return_value = mock_rule
        
        result = rule_service.create_rule("New Rule", "Test Category", "Test description")
        
        assert result == mock_rule
        mock_rule_repository.create_rule.assert_called_once()
    
    def test_save_converted_rule_success(self, rule_service, mock_rule_repository):
        """Test saving a converted rule."""
        mock_rule = RuleEntity(rule_id=1, name="Converted Rule", category="Category", description="Description")
        mock_rule_repository.create_rule.return_value = 1
        mock_rule_repository.find_rule_by_rule_name.return_value = mock_rule

        result = rule_service.save_converted_rule(
            "Converted Rule", "Category", "Description",
            GRAPH_RULE_TEXT,
        )

        assert result == mock_rule
        mock_rule_repository.create_rule.assert_called_once()
        mock_rule_repository.create_rule_file.assert_called_once()
        _, file_payload = mock_rule_repository.create_rule_file.call_args.args
        stored = RuleFileEntity(files=bytes(file_payload))
        assert stored.decode_files() == GRAPH_RULE_TEXT
        graph_payload = json.loads(stored.decode_graph_json())
        assert graph_payload["schema_version"] == 1
        assert graph_payload["nodes"]
    
    def test_create_rule_file_success(self, rule_service, mock_rule_repository):
        """Test creating a rule file."""
        mock_file = RuleFileEntity(file_id=1, rule_id=1, files=b"INPUT age AS NUMBER\nage > 18\n")
        mock_rule_repository.find_id_by_name.return_value = 1
        mock_rule_repository.find_rule_text_by_rule_name.return_value = mock_file

        result = rule_service.create_rule_file(
            "Test Rule", "INPUT age AS NUMBER\nage > 18\n",
        )

        assert result == "INPUT age AS NUMBER\nage > 18\n"
        mock_rule_repository.create_rule_file.assert_called_once()
    
    def test_create_rule_file_rule_not_found(self, rule_service, mock_rule_repository):
        """Test error when creating file for non-existent rule."""
        mock_rule_repository.find_id_by_name.return_value = None
        
        with pytest.raises(LookupError, match="was not found"):
            rule_service.create_rule_file("NonExistent", "content")

    def test_get_rule_tree_data_returns_text_after_parser_validation(self, rule_service, mock_rule_repository):
        mock_file = RuleFileEntity(file_id=1, rule_id=1, files=GRAPH_RULE_TEXT.encode("utf-8"))
        mock_rule_repository.find_rule_text_by_rule_name.return_value = mock_file

        assert rule_service.get_rule_tree_data("Test Rule") == GRAPH_RULE_TEXT
    
    def test_get_history_for_ml_inference_success(self, rule_service, mock_rule_repository):
        """Test getting history for ML inference."""
        mock_rule_repository.find_rule_by_rule_name_with_latest_history.return_value = {
            'rule': RuleEntity(rule_id=1, name="Test Rule"),
            'history': {'data': 'history'}
        }
        
        result = rule_service.get_history_for_ml_inference("Test Rule")
        
        assert result == {'data': 'history'}
        mock_rule_repository.find_rule_by_rule_name_with_latest_history.assert_called_once_with("Test Rule")
    
    def test_get_history_for_ml_inference_no_history(self, rule_service, mock_rule_repository):
        """Test getting history when none exists."""
        mock_rule_repository.find_rule_by_rule_name_with_latest_history.return_value = None
        
        result = rule_service.get_history_for_ml_inference("Test Rule")
        
        assert result is None
    
    def test_build_rule_set_parser_empty_rule_name(self, rule_service, mock_rule_repository):
        """Test error when rule name is empty."""
        with pytest.raises(ValueError, match="ruleName is required"):
            rule_service.build_rule_set_parser("")
    
    def test_build_rule_set_parser_success(self, rule_service, mock_rule_repository):
        """Test building rule set parser."""
        mock_file = RuleFileEntity(file_id=1, rule_id=1, files=b"rule content")
        mock_rule_repository.find_rule_text_by_rule_name.return_value = mock_file
        
        with patch("src.services.rule_service.RuleSetReader") as mock_reader, \
             patch("src.services.rule_service.RuleSetParser") as mock_parser, \
             patch("src.services.rule_service.RuleSetScanner") as mock_scanner:
            
            mock_parser_instance = MagicMock()
            mock_parser_instance.get_node_set.return_value.get_sorted_node_list.return_value = [MagicMock()]
            mock_parser.return_value = mock_parser_instance
            
            result = rule_service.build_rule_set_parser("Test Rule")
            
            assert result == mock_parser_instance
            mock_scanner.return_value.scan_rule_set.assert_called_once()
            mock_scanner.return_value.establish_node_set.assert_called_once()

    def test_build_rule_set_parser_merges_imports_before_parsing(self, rule_service, mock_rule_repository):
        """Imported declarations are visible to the runtime parser."""
        root_file = RuleFileEntity(file_id=1, rule_id=1, files=IMPORT_ROOT_RULE_TEXT.encode("utf-8"))
        imported_file = RuleFileEntity(file_id=2, rule_id=2, files=IMPORT_COMMON_RULE_TEXT.encode("utf-8"))

        def find_rule_text(name):
            return imported_file if name == "common_rule" else root_file

        mock_rule_repository.find_rule_text_by_rule_name.side_effect = find_rule_text

        with patch("src.services.rule_service.RuleSetReader") as mock_reader, \
             patch("src.services.rule_service.RuleSetParser") as mock_parser, \
             patch("src.services.rule_service.RuleSetScanner") as mock_scanner:

            mock_parser_instance = MagicMock()
            mock_parser_instance.get_node_set.return_value.get_sorted_node_list.return_value = [MagicMock()]
            mock_parser.return_value = mock_parser_instance

            result = rule_service.build_rule_set_parser("root_rule")

            assert result == mock_parser_instance
            merged_text = mock_reader.return_value.set_file_with_text.call_args.args[0]
            assert "INPUT imported age AS NUMBER" in merged_text
            assert "eligible for imported benefit" in merged_text
            assert "IMPORT: common_rule" not in merged_text
            mock_scanner.return_value.scan_rule_set.assert_called_once()
            mock_scanner.return_value.establish_node_set.assert_called_once()

    def test_save_session_history_persists_history_through_repository(self, rule_service, mock_rule_repository):
        """Test saving session history via the service layer."""
        mock_rule = RuleEntity(rule_id=7, name="Test Rule", category="Test", description="Desc")
        mock_rule_repository.find_rule_by_rule_name.return_value = mock_rule

        working_memory = {
            "eligible": FactValue(True, FactValueType.BOOLEAN),
            "score": FactValue(3, FactValueType.INTEGER),
        }

        rule_service.save_session_history("Test Rule", working_memory)

        mock_rule_repository.create_rule_history.assert_called_once_with(
            7,
            {
                "eligible": {
                    "true": "1",
                    "false": "0",
                    "type": str(FactValueType.BOOLEAN),
                },
                "score": {
                    "true": "1",
                    "false": "0",
                    "type": str(FactValueType.INTEGER),
                },
            },
        )


# =============================================================================
# Validation Gate Unit Tests
# =============================================================================

VALID_RULE_TEXT = "INPUT age AS NUMBER\nage > 18\n"
GRAPH_RULE_TEXT = (
    "INPUT claimant has service AS BOOLEAN\n"
    "eligible for benefit\n"
    "    AND claimant has service\n"
)
IMPORT_ROOT_RULE_TEXT = (
    "IMPORT: common_rule\n"
    "eligible for imported benefit\n"
    "    AND imported age >= minimum imported age\n"
)
IMPORT_COMMON_RULE_TEXT = (
    "INPUT imported age AS NUMBER\n"
    "FIXED minimum imported age IS 18\n"
)
INVALID_RULE_TEXT_DUPLICATE = "INPUT x AS NUMBER\nINPUT x AS NUMBER\n"
INVALID_RULE_TEXT_CYCLE = "INPUT a AS NUMBER\nINPUT b AS NUMBER\na IS CALC b + 1\nb IS CALC a + 1\n"
INVALID_RULE_TEXT_EMPTY = ""


class TestValidationGateSaveConvertedRule:
    """Unit tests: RuleValidationService gates save_converted_rule()."""

    def test_valid_rule_passes_gate(self, rule_service, mock_rule_repository):
        """Valid rule text is persisted without errors."""
        mock_rule = RuleEntity(rule_id=1, name="valid_rule", category="cat", description="desc")
        mock_rule_repository.create_rule.return_value = 1
        mock_rule_repository.find_rule_by_rule_name.return_value = mock_rule

        result = rule_service.save_converted_rule(
            "valid_rule", "cat", "desc", VALID_RULE_TEXT,
        )

        assert result == mock_rule
        mock_rule_repository.create_rule.assert_called_once()
        mock_rule_repository.create_rule_file.assert_called_once()

    def test_imported_declarations_satisfy_save_validation(self, rule_service, mock_rule_repository):
        """A root rule can persist with declarations supplied by IMPORT modules."""
        mock_rule = RuleEntity(rule_id=1, name="root_rule", category="cat", description="desc")
        imported_file = RuleFileEntity(file_id=2, rule_id=2, files=IMPORT_COMMON_RULE_TEXT.encode("utf-8"))
        mock_rule_repository.create_rule.return_value = 1
        mock_rule_repository.find_rule_by_rule_name.return_value = mock_rule
        mock_rule_repository.find_rule_text_by_rule_name.return_value = imported_file

        result = rule_service.save_converted_rule(
            "root_rule", "cat", "desc", IMPORT_ROOT_RULE_TEXT,
        )

        assert result == mock_rule
        mock_rule_repository.create_rule.assert_called_once()
        mock_rule_repository.create_rule_file.assert_called_once()
        _, file_payload = mock_rule_repository.create_rule_file.call_args.args
        stored = RuleFileEntity(files=bytes(file_payload))
        assert stored.decode_files() == IMPORT_ROOT_RULE_TEXT

        graph_payload = json.loads(stored.decode_graph_json())
        node_names = {node["name"] for node in graph_payload["nodes"]}
        assert "imported age >= minimum imported age" in node_names
        assert "eligible for imported benefit" in node_names
        assert "IMPORT: common_rule" not in node_names

    def test_missing_import_blocks_save_with_structured_error(self, rule_service, mock_rule_repository):
        """Missing imports fail before repository writes and surface a precise code."""
        mock_rule_repository.find_rule_text_by_rule_name.return_value = None

        with pytest.raises(RuleValidationError) as exc_info:
            rule_service.save_converted_rule(
                "root_rule",
                "cat",
                "desc",
                "IMPORT: missing_rule\n"
                "eligible for imported benefit\n"
                "    AND imported age >= minimum imported age\n",
            )

        assert any(error.code == "UNRESOLVED_IMPORT" for error in exc_info.value.errors)
        mock_rule_repository.create_rule.assert_not_called()
        mock_rule_repository.create_rule_file.assert_not_called()

    def test_duplicate_declaration_blocked(self, rule_service, mock_rule_repository):
        """Rule with duplicate INPUT declarations is blocked before persistence."""
        with pytest.raises(RuleValidationError) as exc_info:
            rule_service.save_converted_rule(
                "bad_rule", "cat", "desc", INVALID_RULE_TEXT_DUPLICATE,
            )

        assert any(e.code == "DUPLICATE_DECLARATION" for e in exc_info.value.errors)
        # Repository must NOT be called
        mock_rule_repository.create_rule.assert_not_called()
        mock_rule_repository.create_rule_file.assert_not_called()

    def test_cyclic_dependency_blocked(self, rule_service, mock_rule_repository):
        """Rule with cyclic dependencies is blocked before persistence."""
        with pytest.raises(RuleValidationError) as exc_info:
            rule_service.save_converted_rule(
                "cyclic_rule", "cat", "desc", INVALID_RULE_TEXT_CYCLE,
            )

        assert any(e.code == "CYCLIC_DEPENDENCY" for e in exc_info.value.errors)
        mock_rule_repository.create_rule.assert_not_called()

    def test_empty_rule_text_blocked(self, rule_service, mock_rule_repository):
        """Empty rule text is blocked before persistence."""
        with pytest.raises(RuleValidationError) as exc_info:
            rule_service.save_converted_rule(
                "empty_rule", "cat", "desc", INVALID_RULE_TEXT_EMPTY,
            )

        assert any(e.code == "EMPTY_RULE" for e in exc_info.value.errors)
        mock_rule_repository.create_rule.assert_not_called()

    def test_bypass_validation_skips_gate(self, rule_service, mock_rule_repository):
        """bypass_validation=True skips validation — for migration scripts only."""
        mock_rule = RuleEntity(rule_id=1, name="legacy", category="cat", description="desc")
        mock_rule_repository.create_rule.return_value = 1
        mock_rule_repository.find_rule_by_rule_name.return_value = mock_rule

        # This text would normally fail validation
        result = rule_service.save_converted_rule(
            "legacy", "cat", "desc", "some garbage text",
            bypass_validation=True,
        )

        assert result == mock_rule
        mock_rule_repository.create_rule.assert_called_once()

    def test_bypass_validation_still_keeps_decoded_rule_text_stable(self, rule_service, mock_rule_repository):
        mock_rule = RuleEntity(rule_id=1, name="legacy", category="cat", description="desc")
        mock_rule_repository.create_rule.return_value = 1
        mock_rule_repository.find_rule_by_rule_name.return_value = mock_rule

        rule_service.save_converted_rule(
            "legacy",
            "cat",
            "desc",
            "some garbage text",
            bypass_validation=True,
        )

        _, file_payload = mock_rule_repository.create_rule_file.call_args.args
        stored = RuleFileEntity(files=bytes(file_payload))
        assert stored.decode_files() == "some garbage text"

    def test_encode_rule_file_requires_graph_for_valid_persistence(self, rule_service):
        parser = MagicMock()
        parser.get_node_set.return_value.get_graph.return_value = None
        rule_service._parse_rule_text = MagicMock(return_value=parser)

        with pytest.raises(ValueError, match="dependency graph"):
            rule_service._encode_rule_file("rule text", "rule", require_graph=True)

    def test_encode_rule_file_can_fall_back_for_bypass_migration(self, rule_service):
        parser = MagicMock()
        parser.get_node_set.return_value.get_graph.return_value = None
        rule_service._parse_rule_text = MagicMock(return_value=parser)

        assert rule_service._encode_rule_file("rule text", "rule", require_graph=False) == bytearray(
            b"rule text"
        )

    def test_error_carries_rule_name(self, rule_service, mock_rule_repository):
        """RuleValidationError carries the rule name for traceability."""
        with pytest.raises(RuleValidationError) as exc_info:
            rule_service.save_converted_rule(
                "my_rule", "cat", "desc", INVALID_RULE_TEXT_DUPLICATE,
            )

        assert exc_info.value.rule_name == "my_rule"

    def test_to_dict_structured_errors(self, rule_service, mock_rule_repository):
        """RuleValidationError.to_dict() returns structured error details."""
        with pytest.raises(RuleValidationError) as exc_info:
            rule_service.save_converted_rule(
                "my_rule", "cat", "desc", INVALID_RULE_TEXT_DUPLICATE,
            )

        d = exc_info.value.to_dict()
        assert d["success"] is False
        assert d["detail"]["rule_name"] == "my_rule"
        assert len(d["detail"]["errors"]) > 0
        assert d["detail"]["errors"][0]["code"] == "DUPLICATE_DECLARATION"


class TestValidationGateCreateRuleFile:
    """Unit tests: RuleValidationService gates create_rule_file()."""

    def test_valid_rule_file_passes_gate(self, rule_service, mock_rule_repository):
        """Valid rule text is persisted without errors."""
        mock_file = RuleFileEntity(file_id=1, rule_id=1, files=b"INPUT age AS NUMBER\nage > 18\n")
        mock_rule_repository.find_id_by_name.return_value = 1
        mock_rule_repository.find_rule_text_by_rule_name.return_value = mock_file

        result = rule_service.create_rule_file("Test Rule", VALID_RULE_TEXT)

        assert result is not None
        mock_rule_repository.create_rule_file.assert_called_once()
        _, file_payload = mock_rule_repository.create_rule_file.call_args.args
        payload = json.loads(bytes(file_payload).decode("utf-8"))
        assert payload["type"] == PAYLOAD_TYPE
        assert payload["rule_text"] == VALID_RULE_TEXT
        assert payload["graph"]["schema_version"] == 1

    def test_invalid_rule_file_blocked(self, rule_service, mock_rule_repository):
        """Invalid rule text is blocked before persistence."""
        with pytest.raises(RuleValidationError) as exc_info:
            rule_service.create_rule_file("Test Rule", INVALID_RULE_TEXT_DUPLICATE)

        assert any(e.code == "DUPLICATE_DECLARATION" for e in exc_info.value.errors)
        mock_rule_repository.create_rule_file.assert_not_called()

    def test_cyclic_rule_file_blocked(self, rule_service, mock_rule_repository):
        """Cyclic rule file is blocked before persistence."""
        with pytest.raises(RuleValidationError) as exc_info:
            rule_service.create_rule_file("Test Rule", INVALID_RULE_TEXT_CYCLE)

        assert any(e.code == "CYCLIC_DEPENDENCY" for e in exc_info.value.errors)
        mock_rule_repository.create_rule_file.assert_not_called()

    def test_bypass_validation_skips_gate(self, rule_service, mock_rule_repository):
        """bypass_validation=True skips validation for migration scripts."""
        mock_file = RuleFileEntity(file_id=1, rule_id=1, files=b"legacy content")
        mock_rule_repository.find_id_by_name.return_value = 1
        mock_rule_repository.find_rule_text_by_rule_name.return_value = mock_file

        result = rule_service.create_rule_file(
            "Test Rule", "some garbage text",
            bypass_validation=True,
        )

        assert result is not None
        mock_rule_repository.create_rule_file.assert_called_once()

    def test_rule_not_found_still_raises_lookup_error(self, rule_service, mock_rule_repository):
        """After validation passes, LookupError for missing rule still works."""
        mock_rule_repository.find_id_by_name.return_value = None

        with pytest.raises(LookupError, match="was not found"):
            rule_service.create_rule_file("NonExistent", VALID_RULE_TEXT)


class TestValidationWaivers:
    def test_save_converted_rule_stores_when_all_errors_are_waived(self, rule_service, mock_rule_repository):
        mock_rule = RuleEntity(rule_id=1, name="waived", category="cat", description="desc")
        mock_rule_repository.create_rule.return_value = 1
        mock_rule_repository.find_rule_by_rule_name.return_value = mock_rule
        rule_service._encode_rule_file = MagicMock(return_value=bytearray(b"stored"))

        result = rule_service.save_converted_rule(
            "waived",
            "cat",
            "desc",
            INVALID_RULE_TEXT_DUPLICATE,
            waived_error_ids=["DUPLICATE_DECLARATION:x"],
        )

        assert result == mock_rule
        mock_rule_repository.create_rule_file.assert_called_once()

    def test_save_converted_rule_rejects_unknown_waiver_id(self, rule_service, mock_rule_repository):
        with pytest.raises(RuleValidationError) as exc_info:
            rule_service.save_converted_rule(
                "bad_waiver",
                "cat",
                "desc",
                INVALID_RULE_TEXT_DUPLICATE,
                waived_error_ids=["DUPLICATE_DECLARATION:x", "UNKNOWN:ghost"],
            )

        assert exc_info.value.unknown_waiver_ids == ["UNKNOWN:ghost"]
        mock_rule_repository.create_rule.assert_not_called()

    def test_save_converted_rule_rejects_partial_waiver(self, rule_service, mock_rule_repository):
        rule_text = "INPUT a AS NUMBER\nINPUT a AS NUMBER\nINPUT b AS NUMBER\nINPUT b AS NUMBER\n"

        with pytest.raises(RuleValidationError) as exc_info:
            rule_service.save_converted_rule(
                "partial_waiver",
                "cat",
                "desc",
                rule_text,
                waived_error_ids=["DUPLICATE_DECLARATION:a"],
            )

        assert [error.waiver_id for error in exc_info.value.errors] == ["DUPLICATE_DECLARATION:b"]
        mock_rule_repository.create_rule.assert_not_called()

    def test_create_rule_file_stores_when_all_errors_are_waived(self, rule_service, mock_rule_repository):
        mock_file = RuleFileEntity(file_id=1, rule_id=1, files=b"stored")
        mock_rule_repository.find_id_by_name.return_value = 1
        mock_rule_repository.find_rule_text_by_rule_name.return_value = mock_file
        rule_service._encode_rule_file = MagicMock(return_value=bytearray(b"stored"))

        result = rule_service.create_rule_file(
            "waived_file",
            INVALID_RULE_TEXT_DUPLICATE,
            waived_error_ids=["DUPLICATE_DECLARATION:x"],
        )

        assert result == "stored"
        mock_rule_repository.create_rule_file.assert_called_once()


class TestValidationGateNotAppliedToCreateRule:
    """Unit tests: create_rule() is NOT gated (no rule text to validate)."""

    def test_create_rule_no_validation(self, rule_service, mock_rule_repository):
        """create_rule() creates metadata-only rule without validation."""
        mock_rule = RuleEntity(rule_id=1, name="New Rule", category="cat", description="desc")
        mock_rule_repository.create_rule.return_value = 1
        mock_rule_repository.find_rule_by_rule_name.return_value = mock_rule

        result = rule_service.create_rule("New Rule", "cat", "desc")

        assert result == mock_rule
        mock_rule_repository.create_rule.assert_called_once()


class TestValidationGateCustomServiceInjection:
    """Unit tests: custom RuleValidationService can be injected."""

    def test_custom_validation_service_is_used(self, mock_rule_repository):
        """Injected validation service is used instead of default."""
        custom_service = MagicMock(spec=RuleValidationService)
        custom_service.validate.return_value = RuleValidationService().validate(VALID_RULE_TEXT, "test")

        svc = RuleService(mock_rule_repository, validation_service=custom_service)
        mock_rule = RuleEntity(rule_id=1, name="test", category="cat", description="desc")
        mock_rule_repository.create_rule.return_value = 1
        mock_rule_repository.find_rule_by_rule_name.return_value = mock_rule

        svc.save_converted_rule("test", "cat", "desc", VALID_RULE_TEXT)

        custom_service.validate.assert_called_once_with(VALID_RULE_TEXT, "test")


# =============================================================================
# Additional Coverage Tests
# =============================================================================


class TestGetRuleFileOrRaise:
    def test_returns_file_when_found(self, rule_service, mock_rule_repository):
        mock_file = RuleFileEntity(file_id=1, rule_id=1, files=b"content")
        mock_rule_repository.find_rule_text_by_rule_name.return_value = mock_file
        result = rule_service.get_rule_file_or_raise("Test Rule")
        assert result == mock_file

    def test_raises_when_file_is_none(self, rule_service, mock_rule_repository):
        mock_rule_repository.find_rule_text_by_rule_name.return_value = None
        with pytest.raises(LookupError, match="was not found or has no stored file"):
            rule_service.get_rule_file_or_raise("Test Rule")

    def test_raises_when_files_attribute_is_none(self, rule_service, mock_rule_repository):
        mock_file = RuleFileEntity(file_id=1, rule_id=1, files=None)
        mock_rule_repository.find_rule_text_by_rule_name.return_value = mock_file
        with pytest.raises(LookupError, match="was not found or has no stored file"):
            rule_service.get_rule_file_or_raise("Test Rule")


class TestDecodeRuleFile:
    def test_decode_success(self, rule_service):
        mock_file = RuleFileEntity(file_id=1, rule_id=1, files=b"hello world")
        result = rule_service.decode_rule_file(mock_file)
        assert result == "hello world"

    def test_decode_attribute_error(self, rule_service):
        mock_file = MagicMock()
        mock_file.decode_files.side_effect = AttributeError("no decode")
        with pytest.raises(ValueError, match="could not be decoded"):
            rule_service.decode_rule_file(mock_file)

    def test_decode_unicode_error(self, rule_service):
        mock_file = MagicMock()
        mock_file.decode_files.side_effect = UnicodeDecodeError("utf-8", b"", 0, 1, "invalid")
        with pytest.raises(ValueError, match="could not be decoded"):
            rule_service.decode_rule_file(mock_file)

    def test_decode_value_error(self, rule_service):
        mock_file = MagicMock()
        mock_file.decode_files.side_effect = ValueError("bad value")
        with pytest.raises(ValueError, match="could not be decoded"):
            rule_service.decode_rule_file(mock_file)


class TestGetRuleTextErrors:
    def test_get_rule_text_rule_not_found(self, rule_service, mock_rule_repository):
        mock_rule_repository.find_rule_text_by_rule_name.return_value = None
        with pytest.raises(LookupError, match="was not found"):
            rule_service.get_rule_text("NonExistent")


class TestGetLatestRuleFile:
    def test_returns_file(self, rule_service, mock_rule_repository):
        mock_file = RuleFileEntity(file_id=1, rule_id=1, files=b"latest")
        mock_rule_repository.find_rule_text_by_rule_name.return_value = mock_file
        result = rule_service.get_latest_rule_file("Test Rule")
        assert result == mock_file


class TestGetLatestRuleHistory:
    def test_success(self, rule_service, mock_rule_repository):
        mock_rule = RuleEntity(rule_id=1, name="Rule")
        mock_rule_repository.find_rule_by_rule_name_with_latest_history.return_value = {
            'rule': mock_rule,
            'history': {'key': 'value'},
        }
        result = rule_service.get_latest_rule_history("Rule")
        assert result['history'] == {'key': 'value'}

    def test_rule_not_found(self, rule_service, mock_rule_repository):
        mock_rule_repository.find_rule_by_rule_name_with_latest_history.return_value = None
        with pytest.raises(LookupError, match="was not found"):
            rule_service.get_latest_rule_history("Missing")

    def test_rule_is_none(self, rule_service, mock_rule_repository):
        mock_rule_repository.find_rule_by_rule_name_with_latest_history.return_value = {
            'rule': None, 'history': None
        }
        with pytest.raises(LookupError, match="was not found"):
            rule_service.get_latest_rule_history("Missing")

    def test_no_history(self, rule_service, mock_rule_repository):
        mock_rule = RuleEntity(rule_id=1, name="Rule")
        mock_rule_repository.find_rule_by_rule_name_with_latest_history.return_value = {
            'rule': mock_rule, 'history': None
        }
        with pytest.raises(LookupError, match="has no stored history"):
            rule_service.get_latest_rule_history("Rule")


class TestUpdateRuleReloadFailure:
    def test_update_rule_cannot_reload(self, rule_service, mock_rule_repository):
        mock_rule_repository.update_rule_name_and_category.return_value = True
        mock_rule_repository.find_rule_by_rule_name.return_value = None
        with pytest.raises(RuntimeError, match="could not be reloaded"):
            rule_service.update_rule("Old", "New", "Cat")


class TestCreateRuleReloadFailure:
    def test_create_rule_cannot_reload(self, rule_service, mock_rule_repository):
        mock_rule_repository.create_rule.return_value = 1
        mock_rule_repository.find_rule_by_rule_name.return_value = None
        with pytest.raises(RuntimeError, match="could not be created"):
            rule_service.create_rule("New", "Cat", "Desc")


class TestSaveConvertedRuleReloadFailure:
    def test_save_converted_rule_cannot_reload(self, rule_service, mock_rule_repository):
        mock_rule_repository.create_rule.return_value = 1
        mock_rule_repository.find_rule_by_rule_name.return_value = None
        with pytest.raises(RuntimeError, match="could not be loaded"):
            rule_service.save_converted_rule("R", "C", "D", "some text", bypass_validation=True)


class TestSaveSessionHistoryNonBoolean:
    def test_non_boolean_fact_value(self, rule_service, mock_rule_repository):
        mock_rule = RuleEntity(rule_id=7, name="Test Rule", category="Test", description="Desc")
        mock_rule_repository.find_rule_by_rule_name.return_value = mock_rule
        working_memory = {
            "score": FactValue(3, FactValueType.INTEGER),
        }
        rule_service.save_session_history("Test Rule", working_memory)
        call_args = mock_rule_repository.create_rule_history.call_args[0]
        assert call_args[0] == 7
        assert call_args[1]["score"]["true"] == "1"
        assert call_args[1]["score"]["false"] == "0"
        assert call_args[1]["score"]["type"] == str(FactValueType.INTEGER)

    def test_boolean_false_fact_value(self, rule_service, mock_rule_repository):
        mock_rule = RuleEntity(rule_id=7, name="Test Rule", category="Test", description="Desc")
        mock_rule_repository.find_rule_by_rule_name.return_value = mock_rule
        working_memory = {
            "eligible": FactValue(False, FactValueType.BOOLEAN),
        }
        rule_service.save_session_history("Test Rule", working_memory)
        call_args = mock_rule_repository.create_rule_history.call_args[0]
        assert call_args[1]["eligible"]["true"] == "0"
        assert call_args[1]["eligible"]["false"] == "1"


class TestBuildRuleSetParserInvalidNodeSet:
    def test_empty_node_set_raises(self, rule_service, mock_rule_repository):
        mock_file = RuleFileEntity(file_id=1, rule_id=1, files=b"rule content")
        mock_rule_repository.find_rule_text_by_rule_name.return_value = mock_file
        with patch("src.services.rule_service.RuleSetReader") as mock_reader, \
             patch("src.services.rule_service.RuleSetParser") as mock_parser, \
             patch("src.services.rule_service.RuleSetScanner"):
            mock_parser_instance = MagicMock()
            mock_parser_instance.get_node_set.return_value.get_sorted_node_list.return_value = []
            mock_parser.return_value = mock_parser_instance
            with pytest.raises(ValueError, match="could not be parsed"):
                rule_service.build_rule_set_parser("Test Rule")


class TestGetTargetNodeNames:
    @patch("src.services.rule_service.RuleSetReader")
    @patch("src.services.rule_service.RuleSetParser")
    @patch("src.services.rule_service.RuleSetScanner")
    def test_returns_node_names(self, mock_scanner, mock_parser, mock_reader, rule_service, mock_rule_repository):
        mock_file = RuleFileEntity(file_id=1, rule_id=1, files=b"rule content")
        mock_rule_repository.find_rule_text_by_rule_name.return_value = mock_file
        mock_parser_instance = MagicMock()
        mock_node_set = MagicMock()
        mock_node = MagicMock()
        mock_node.get_node_name.return_value = "target_node"
        graph = HyperAdjacencyGraph()
        graph.register_node("target_node", {"runtime_id": 0})
        mock_node_set.get_graph.return_value = graph
        mock_node_set.get_node_dictionary.return_value = {"target_node": mock_node}
        mock_parser_instance.get_node_set.return_value = mock_node_set
        mock_parser.return_value = mock_parser_instance
        result = rule_service.get_target_node_names("Test Rule")
        assert result == ["target_node"]

    def test_get_parentless_nodes_falls_back_to_runtime_root_without_graph(self, rule_service):
        root = MagicMock()
        root._node_id = 0
        child = MagicMock()
        child._node_id = 1
        node_set = NodeSet()
        node_set.set_sorted_node_list([child, root])
        node_set.set_graph(None)

        assert rule_service._get_parentless_nodes(node_set) == [root]

    def test_get_parentless_nodes_sorts_by_node_runtime_id_when_graph_has_no_id(self, rule_service):
        node_a = MagicMock()
        node_a._node_id = 7
        node_b = MagicMock()
        node_b._node_id = 2
        graph = MagicMock()
        graph.has_node.return_value = True
        graph.get_parent_edges.return_value = set()
        graph.lookup_by_name.return_value = None
        node_set = MagicMock()
        node_set.get_graph.return_value = graph
        node_set.get_node_dictionary.return_value = {"a": node_a, "b": node_b}

        assert rule_service._get_parentless_nodes(node_set) == [node_b, node_a]


class TestGetHistoryForMlInferenceEdgeCases:
    def test_result_with_no_history_key(self, rule_service, mock_rule_repository):
        mock_rule_repository.find_rule_by_rule_name_with_latest_history.return_value = {
            'rule': RuleEntity(rule_id=1, name="Test"),
        }
        result = rule_service.get_history_for_ml_inference("Test")
        assert result is None

    def test_result_none_rule(self, rule_service, mock_rule_repository):
        mock_rule_repository.find_rule_by_rule_name_with_latest_history.return_value = {
            'rule': None, 'history': {'k': 'v'}
        }
        result = rule_service.get_history_for_ml_inference("Test")
        assert result == {'k': 'v'}
