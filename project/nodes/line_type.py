from enum import Enum

class LineType(Enum):
    META = "META"
    VALUE_CONCLUSION = "VALUE_CONCLUSION"
    EXPR_CONCLUSION = "EXPR_CONCLUSION"
    COMPARISON = "COMPARISON"
    ITERATE = "ITERATE"
    WARNING = "WARNING"

    @staticmethod
    def get_all_values():
        return list(map(lambda c: c.value, LineType))
    
    @staticmethod
    def get_appropriate_node_type(node_type:str):
        from . import MetadataLine, ValueConclusionLine, ExprConclusionLine, ComparisonLine
        from nodes.iterate_line import IterateLine
        
        if node_type is LineType.META:
            return MetadataLine()
        elif node_type is LineType.ITERATE:
            return IterateLine()
        elif node_type is LineType.COMPARISON:
            return ComparisonLine()
        elif node_type is LineType.EXPR_CONCLUSION:
            return ExprConclusionLine()
        elif node_type is LineType.VALUE_CONCLUSION:
            return ValueConclusionLine()
