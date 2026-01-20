from enum import Enum


class LineMatcherConstant(Enum):

    META_PATTERN_MATCHER = r"(^U)([MLU]*)([Q(No)(Da)ML(De)(Se)(Ha)(U(rl)?)(Id)]*$)"
    VALUE_CONCLUSION_MATCHER = r"(^[(Se)(No)LMU]+)([MLQ(No)(Da)(De)(Se)(Ha)(Url)(Id)(Fu)(Pa)]*$)(?!C)"
    EXPRESSION_CONCLUSION_MATCHER = r"(^[LMU(No)(Da)(Se)]+)(C)"
    COMPARISON_MATCHER = r"(^[(Se)MLU(Da)(No)]+)(O)([MLUQ(No)(Da)(De)(Se)(Ha)(Url)(Id)(Fu)(Pa)]*$)"
    ITERATE_MATCHER = r"(^[(Se)MLU(No)(Da)]+)(I)([MLU]+$)"
    WARNING_MATCHER = r"WARNING"

    @staticmethod
    def get_all_line_matchers() -> list:
        return list(map(lambda c: c.value, LineMatcherConstant))

    @staticmethod
    def get_all_line_enums() -> list:
        return list(map(lambda c: c, LineMatcherConstant))
