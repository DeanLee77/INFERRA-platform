"""
Dependency Type String Matcher.
Defines logical dependency patterns.
Implements access levels and strong typing where appropriate.
"""

from enum import Enum
from typing import List

class DependencyTypeStringMatcher(Enum):
    """
    Enum containing dependency matchers.
    Members are Public (API).
    """
    # -------------------------------------------------------------------------
    # Public Access Level: Enum Members (API Surface)
    # -------------------------------------------------------------------------
    AND_MATCHER = r'(.)?(AND\s)(.)?'
    OR_MATCHER = r'(.)?(OR\s)(.)?'
    NOT_MATCHER = r'(.)?(NOT)(.)?'
    KNOWN_MATCHER = r'(.)?(KNOWN)(.)?'
    MANDATORY_MATCHER = r'(.)?(MANDATORY)(.)?'
    OPTIONALLY_MATCHER = r'(.)?(OPTIONALLY)(.)?'
    POSSIBLY_MATCHER = r'(.)?(POSSIBLY)(.)?'

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    @staticmethod
    def _get_all_line_matchers() -> List[str]:
        """
        Protected Helper: Internal utility to extract values.
        Prefers direct Enum iteration if overridden.
        """
        return [member.value for member in DependencyTypeStringMatcher]

    @staticmethod
    def _get_all_line_enums() -> List['DependencyTypeStringMatcher']:
        """
        Protected Helper: Internal utility to extract enums.
        """
        return list(DependencyTypeStringMatcher)

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods
    # -------------------------------------------------------------------------
    @staticmethod
    def get_all_line_matchers() -> List[str]:
        """
        Public API: Returns all dependency matcher strings.
        """
        return DependencyTypeStringMatcher._get_all_line_matchers()

    @staticmethod
    def get_all_line_enums() -> List['DependencyTypeStringMatcher']:
        """
        Public API: Returns all dependency matcher enums.
        """
        return DependencyTypeStringMatcher._get_all_line_enums()