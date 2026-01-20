from enum import Enum


class DependencyTypeStringMatcher(Enum):
    AND_MATCHER = r'(.*)?(AND\s)(.*)?'
    OR_MATCHER = r'(.*)?(OR\s)(.*)?'
    NOT_MATCHER = r'(.*)?(NOT)(.*)?'
    KNOWN_MATCHER = r'(.*)?(KNOWN)(.*)?'
    MANDATORY_MATCHER = r'(.*)?(MANDATORY)(.*)?'
    OPTIONALLY_MATCHER = r'(.*)?(OPTIONALLY)(.*)?'
    POSSIBLY_MATCHER = r'(.*)?(POSSIBLY)(.*)?'

    @staticmethod
    def get_all_line_matchers() -> list:
        return list(map(lambda c: c.value, DependencyTypeStringMatcher))

    @staticmethod
    def get_all_line_enums() -> list:
        return list(map(lambda c: c, DependencyTypeStringMatcher))
