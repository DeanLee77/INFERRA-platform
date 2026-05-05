"""Tests for import matchers — IMPORT_MATCHER, extract_imports, extract_rule_set_name."""

from src.domain.imports.import_matchers import (
    extract_imports,
    extract_rule_set_name,
)


class TestExtractImports:
    def test_no_imports(self):
        assert extract_imports("SOME RULE\n  AND child") == []

    def test_single_import(self):
        text = "IMPORT: common_rules\nSOME RULE\n  AND child"
        assert extract_imports(text) == ["common_rules"]

    def test_multiple_imports(self):
        text = "IMPORT: mod_a\nIMPORT: mod_b\nSOME RULE"
        assert extract_imports(text) == ["mod_a", "mod_b"]

    def test_import_with_spaces(self):
        text = "IMPORT:   spaced_name  \nRULE"
        assert extract_imports(text) == ["spaced_name"]

    def test_import_not_at_line_start(self):
        text = "  IMPORT: not_a_real_import\nRULE"
        assert extract_imports(text) == []

    def test_import_in_comment_context(self):
        text = "IMPORT: lib_math\n# IMPORT: commented_out\nRULE"
        assert extract_imports(text) == ["lib_math"]


class TestExtractRuleSetName:
    def test_no_header(self):
        assert extract_rule_set_name("RULE\n  AND child") == ""

    def test_with_header(self):
        text = "RULE SET: my_rules\nRULE\n  AND child"
        assert extract_rule_set_name(text) == "my_rules"

    def test_header_with_spaces(self):
        text = "RULE SET:   spaced_name  \nRULE"
        assert extract_rule_set_name(text) == "spaced_name"
