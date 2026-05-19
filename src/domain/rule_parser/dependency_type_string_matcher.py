from enum import Enum
from typing import List


class DependencyTypeStringMatcher(Enum):
    AND_MATCHER = r'(.)?(AND\s)(.)?'
    OR_MATCHER = r'(.)?(OR\s)(.)?'
    NOT_MATCHER = r'(.)?(NOT)(.)?'
    KNOWN_MATCHER = r'(.)?(KNOWN)(.)?'
    MANDATORY_MATCHER = r'(.)?(MANDATORY)(.)?'
    OPTIONALLY_MATCHER = r'(.)?(OPTIONALLY)(.)?'
    POSSIBLY_MATCHER = r'(.)?(POSSIBLY)(.)?'

    @staticmethod
    def _get_all_line_matchers() -> List[str]:
        return [member.value for member in DependencyTypeStringMatcher]

    @staticmethod
    def _get_all_line_enums() -> List['DependencyTypeStringMatcher']:
        return list(DependencyTypeStringMatcher)

    @staticmethod
    def get_all_line_matchers() -> List[str]:
        return DependencyTypeStringMatcher._get_all_line_matchers()

    @staticmethod
    def get_all_line_enums() -> List['DependencyTypeStringMatcher']:
        return DependencyTypeStringMatcher._get_all_line_enums()
