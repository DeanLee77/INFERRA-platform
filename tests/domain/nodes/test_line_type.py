from unittest.mock import patch
from src.domain.nodes.line_type import LineType
from src.domain.nodes.metadata_line import MetadataLine
from src.domain.nodes.value_conclusion_line import ValueConclusionLine
from src.domain.nodes.expression_conclusion_line import ExprConclusionLine
from src.domain.nodes.comparison_line import ComparisonLine
from src.domain.nodes.iterate_line import IterateLine


class TestLineTypeValues:
    def test_meta_value(self):
        assert LineType.META.value == "META"

    def test_value_conclusion_value(self):
        assert LineType.VALUE_CONCLUSION.value == "VALUE_CONCLUSION"

    def test_expr_conclusion_value(self):
        assert LineType.EXPR_CONCLUSION.value == "EXPR_CONCLUSION"

    def test_comparison_value(self):
        assert LineType.COMPARISON.value == "COMPARISON"

    def test_iterate_value(self):
        assert LineType.ITERATE.value == "ITERATE"

    def test_warning_value(self):
        assert LineType.WARNING.value == "WARNING"


class TestGetAllValues:
    def test_returns_all_values(self):
        values = LineType.get_all_values()
        assert len(values) == 6
        assert "META" in values
        assert "VALUE_CONCLUSION" in values
        assert "EXPR_CONCLUSION" in values
        assert "COMPARISON" in values
        assert "ITERATE" in values
        assert "WARNING" in values


class TestGetAppropriateNodeType:
    @patch.dict('sys.modules', {
        'src.domain.nodes': type('M', (), {
            'MetadataLine': MetadataLine,
            'ValueConclusionLine': ValueConclusionLine,
            'ExprConclusionLine': ExprConclusionLine,
            'ComparisonLine': ComparisonLine,
        }),
    })
    def test_meta_returns_metadata_line(self):
        result = LineType.get_appropriate_node_type("META")
        assert result is MetadataLine

    @patch.dict('sys.modules', {
        'src.domain.nodes': type('M', (), {
            'MetadataLine': MetadataLine,
            'ValueConclusionLine': ValueConclusionLine,
            'ExprConclusionLine': ExprConclusionLine,
            'ComparisonLine': ComparisonLine,
        }),
    })
    def test_iterate_returns_iterate_line(self):
        result = LineType.get_appropriate_node_type("ITERATE")
        assert result is IterateLine

    @patch.dict('sys.modules', {
        'src.domain.nodes': type('M', (), {
            'MetadataLine': MetadataLine,
            'ValueConclusionLine': ValueConclusionLine,
            'ExprConclusionLine': ExprConclusionLine,
            'ComparisonLine': ComparisonLine,
        }),
    })
    def test_comparison_returns_comparison_line(self):
        result = LineType.get_appropriate_node_type("COMPARISON")
        assert result is ComparisonLine

    @patch.dict('sys.modules', {
        'src.domain.nodes': type('M', (), {
            'MetadataLine': MetadataLine,
            'ValueConclusionLine': ValueConclusionLine,
            'ExprConclusionLine': ExprConclusionLine,
            'ComparisonLine': ComparisonLine,
        }),
    })
    def test_expr_conclusion_returns_expr_conclusion_line(self):
        result = LineType.get_appropriate_node_type("EXPR_CONCLUSION")
        assert result is ExprConclusionLine

    @patch.dict('sys.modules', {
        'src.domain.nodes': type('M', (), {
            'MetadataLine': MetadataLine,
            'ValueConclusionLine': ValueConclusionLine,
            'ExprConclusionLine': ExprConclusionLine,
            'ComparisonLine': ComparisonLine,
        }),
    })
    def test_value_conclusion_returns_value_conclusion_line(self):
        result = LineType.get_appropriate_node_type("VALUE_CONCLUSION")
        assert result is ValueConclusionLine

    @patch.dict('sys.modules', {
        'src.domain.nodes': type('M', (), {
            'MetadataLine': MetadataLine,
            'ValueConclusionLine': ValueConclusionLine,
            'ExprConclusionLine': ExprConclusionLine,
            'ComparisonLine': ComparisonLine,
        }),
    })
    def test_unknown_returns_none(self):
        result = LineType.get_appropriate_node_type("UNKNOWN")
        assert result is None

    @patch.dict('sys.modules', {
        'src.domain.nodes': type('M', (), {
            'MetadataLine': MetadataLine,
            'ValueConclusionLine': ValueConclusionLine,
            'ExprConclusionLine': ExprConclusionLine,
            'ComparisonLine': ComparisonLine,
        }),
    })
    def test_empty_string_returns_none(self):
        result = LineType.get_appropriate_node_type("")
        assert result is None
