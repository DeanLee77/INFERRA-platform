"""
Line Matcher Constants.
Defines patterns for line-level analysis.
Implements access levels and strong typing where appropriate.
"""

from enum import Enum
from typing import List

class LineMatcherConstant(Enum):
    """
    Enum containing line matchers.
    Members are Public (API).
    """
    # -------------------------------------------------------------------------
    # Public Access Level: Enum Members (API Surface)
    # -------------------------------------------------------------------------
    META_PATTERN_MATCHER = r"(^U)([MLU]*)([Q(No)(Da)ML(De)(Se)(Ha)(U(rl)?)(Id)]*$)"
    VALUE_CONCLUSION_MATCHER = r"(^[(Se)(No)LMU]+)([MLQ(No)(Da)(De)(Se)(Ha)(Url)(Id)(Fu)(Pa)]*$)(?!C)"
    EXPRESSION_CONCLUSION_MATCHER = r"(^[LMU(No)(Da)(Se)]+)(C)"
    COMPARISON_MATCHER = r"(^[(Se)MLU(Da)(No)]+)(O)([MLUQ(No)(Da)(De)(Se)(Ha)(Url)(Id)(Fu)(Pa)]*$)"
    ITERATE_MATCHER = r"(^[(Se)MLU(No)(Da)]+)(I)([MLU]+$)"
    WARNING_MATCHER = r"WARNING"

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    @staticmethod
    def _get_all_line_matchers() -> List[str]:
        """
        Protected Helper: Internal utility to extract values.
        """
        return [member.value for member in LineMatcherConstant]

    @staticmethod
    def _get_all_line_enums() -> List['LineMatcherConstant']:
        """
        Protected Helper: Internal utility to extract enums.
        """
        return list(LineMatcherConstant)

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods
    # -------------------------------------------------------------------------
    @staticmethod
    def get_all_line_matchers() -> List[str]:
        """
        Public API: Returns all line matcher strings.
        """
        return LineMatcherConstant._get_all_line_matchers()

    @staticmethod
    def get_all_line_enums() -> List['LineMatcherConstant']:
        """
        Public API: Returns all line matcher enums.
        """
        return LineMatcherConstant._get_all_line_enums()