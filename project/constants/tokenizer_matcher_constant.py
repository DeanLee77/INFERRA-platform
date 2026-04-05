"""
Tokenizer Matcher Constants.
Defines regex patterns used for tokenizing input in PALOS analysis.
Implements access levels and strong typing where appropriate.
"""

from enum import Enum
from typing import List, Dict, Pattern, Optional
import re

class TokenizerMatcherConstant(Enum):
    """
    Enum containing regex matchers.
    Members are Public (API).
    """
    # -------------------------------------------------------------------------
    # Public Access Level: Enum Members (API Surface)
    # -------------------------------------------------------------------------
    SPACE_MATCHER = r"^\s+"
    RULE_SET_MATCHER = r"^(RULE SET:)"
    ITERATE_MATCHER = r"^(ITERATE:(\s*)LIST OF)(.)"
    CALCULATION_MATCHER = r"^(IS CALC\s*\().*\)$"
    QUOTED_MATCHER = r'^(?:"[^"]*"|"[^"]*")'
    URL_MATCHER = r"(http|ftp|https):\/\/([\w\-_]+(?:(?:\.[\w\-_]+)+))([\w\-\.,@?^=%&:/~\+#]*[\w\-\@?^=%&/~\+#])?"
    GUID_MATCHER = r"[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}"
    HASH_MATCHER = r"([-]?)([0-9a-f]{10,})(?!\\-)*"
    DATE_MATCHER = r"((?:0?[1-9]|[12][0-9]|3[01])/(?:0?[1-9]|1[0-2])/(?:[0-9]{2,4})|(?:[0-9]{2,4})/(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12][0-9]|3[01])|(?:0?[1-9]|[12][0-9]|3[01])(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December)\s*(?:,\s*)?(?:[0-9]{2,4})|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December)\s+(?:0?[1-9]|[12][0-9]|3[01])(?:st|nd|rd|th)?\s*(?:,\s*)?(?:[0-9]{2,4})|(?:[0-9]{2,4})\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December)\s+(?:0?[1-9]|[12][0-9]|3[01])(?:st|nd|rd|th)?(?:,\s*)?|(?:[0-9]{2,4})-(?:0?[1-9]|1[0-2])-(?:0?[1-9]|[12][0-9]|3[01]))"
    DECIMAL_NUMBER_MATCHER = r"([\d]+\.\d+)(%)?(?!\d)"
    OPERATOR_MATCHER = r"^([<>=]+)"
    NUMBER_MATCHER = r"^\d+(?:%)?(?!.\d|\s*(?:/|-)\s*\d+|\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December|[0-3]?0-9?))"
    PARAGRAPH_MATCHER = r"^(?:[Pp]aragraphs?)\s+\d+(?:\(\d+\))?(?:\([a-zA-Z]+\))?(?:\s+to\s+\([a-zA-Z]+\))?"
    SECTION_MATCHER = r"^(?!\d+$)(?!\d+\.\d+$)(?!\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{4})(?!\d{4}[\/\.\-]\d{1,2}[\/\.\-]\d{1,2})(?!\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})(?!(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?\s*(?:,\s*)?\d{4})(?!\d{4}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?)(?:(?:Section|section|Subsection|subsection|s|S)\s+(?:\d+(?:\.\d+)*\w*(?:\(\w+\))*|\(\w+\))|\d+[A-Z]+\d*(?:\(\w+\))*(?:\.\d+)*|\d+[A-Z]?\d*(?:\(\w+\))*(?:\.\d+)*|\d+(?:\.\d+)+|s\.\s+\w+\d*[A-Z]?\d*(?:\(\w+\))*|ss\.\s+\d+(?:,\s*\d+)*|s\s+\d+(?:\(\w+\))*|sub\s+\d+(?:\(\w+\))*|subsec\s+\d+(?:\(\w+\))*|par\s+\d+(?:\(\w+\))*|Pt\s+\d+|Sch\s+\d+|sub\s+\(\w+\)|subsec\s+\(\w+\))"
    FUNCTION_MATCHER = r"^([A-Z]+[a-zA-Z]*\s*\().*\)"
    UPPER_MATCHER = r"^([A-Z][A-Z\s_:'',\.]*?)(?=\s+IS CALC|\s+[a-z]|\s+\d|\s+[\"]|\s+[A-Z][a-z]|\s*[<>=]|\s*\(|$)"
    MIXED_MATCHER = r"^(?!(?:[Ss][Ee][Cc][Tt][Ii][Oo][Nn]|[Ss][Uu][Bb][Ss][Ee][Cc][Tt][Ii][Oo][Nn])(?:\s|$)|[Ss][Uu][Bb][Ss][Ee][Cc][Tt][Ii][Oo][Nn]\s+\d+|[Ss][Uu][Bb][Ss][Ee][Cc][Tt][Ii][Oo][Nn]\s+\d+\(\w+\)|s\s+\d+\(\w+\)|Section\s+\d+|section\s+\d+|Subsection\s+\d+|sub\s+\d+|subsec\s+\d+|subsection\s+\d+\(\w+\)|subsection\s+\d+|s\.\s+\w+\d*[A-Z]?\d*|ss\.\s+\d+|s\s+\d+|sub\s+\d+|subsec\s+\d+|subsection\s+\(\w+\)|sub\s+\(\w+\)|subsec\s+\(\w+\))(?:(?:[A-Z][a-zA-Z-'',\.\s\(\)]*?)|(?:[a-z]+[A-Z][a-zA-Z-'',\.\s\(\)]*?))(?=\s*[Ss][Uu][Bb][Ss][Ee][Cc][Tt][Ii][Oo][Nn]\s+\(\w+\)|[Ss][Uu][Bb][Ss][Ee][Cc][Tt][Ii][Oo][Nn]\s+\d+\(\w+\)|[Ss][Uu][Bb][Ss][Ee][Cc][Tt][Ii][Oo][Nn]\s+\d+|s\s+\d+\(\w+\)|Section\s+\d+|section\s+\d+|Subsection\s+\d+|sub\s+\d+|subsec\s+\d+|subsection\s+\d+\(\w+\)|subsection\s+\d+|subsection\s+\(\w+\)|sub\s+\(\w+\)|subsec\s+\(\w+\)|\s+[A-Z]{2,}|\s*[<>=]|\s+\d|\s*[\"]|$)|^(?:[A-Z][a-zA-Z-'',\.\s]*?\s*)+\((?:[a-zA-Z\s]+)\)\s*Act\s+\d{4}"
    LOWER_MATCHER = r"([a-z][a-zA-Z-'',\.\s\(\)]*?)(?=\s+(?:IS CALC|is calc|[Ss][Ee][Cc][Tt][Ii][Oo][Nn]|[Ss][Uu][Bb][Ss][Ee][Cc][Tt][Ii][Oo][Nn]|[Pp]aragraphs?)\s+|\s+[A-Z]|\s*[<>=]|\s+\d|\s*[\"]|$)(?!\d)"

    # -------------------------------------------------------------------------
    # Private Access Level: Internal State (Encapsulation)
    # -------------------------------------------------------------------------
    __compiled_cache: Dict[str, Pattern] = {}

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods
    # -------------------------------------------------------------------------
    @staticmethod
    def get_all_matcher() -> List[str]:
        """
        Public API: Returns all matcher regex strings.
        """
        return TokenizerMatcherConstant._extract_values()

    @staticmethod
    def get_all_enums() -> List['TokenizerMatcherConstant']:
        """
        Public API: Returns all Enum members.
        """
        return TokenizerMatcherConstant._extract_enums()

    @staticmethod
    def get_compiled_matcher(name: str) -> Optional[Pattern]:
        """
        Public API: Returns a compiled regex pattern with caching.
        """
        return TokenizerMatcherConstant._get_compiled_pattern(name)

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    @staticmethod
    def _extract_values() -> List[str]:
        """
        Protected Helper: Extracts values from Enum.
        Intended for internal use or subclassing.
        """
        return [member.value for member in TokenizerMatcherConstant]

    @staticmethod
    def _extract_enums() -> List['TokenizerMatcherConstant']:
        """
        Protected Helper: Extracts Enum members.
        Intended for internal use or subclassing.
        """
        return list(TokenizerMatcherConstant)

    @classmethod
    def _get_compiled_pattern(cls, name: str) -> Optional[Pattern]:
        """
        Protected Method: Accesses compiled patterns with caching logic.
        """
        if name in cls.__compiled_cache:
            return cls.__compiled_cache[name]
        
        try:
            matcher = cls[name]
            pattern = re.compile(matcher.value)
            cls.__compiled_cache[name] = pattern
            return pattern
        except KeyError:
            return None

    # -------------------------------------------------------------------------
    # Private Access Level: Internal Utilities (Double Underscore)
    # -------------------------------------------------------------------------
    @staticmethod
    def __get_cache_key(name: str) -> str:
        """
        Private Helper: Generates cache key.
        Name-mangled to enforce encapsulation.
        """
        return f"tokenizer_{name}"