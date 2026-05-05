"""
Dependency Type Module.
Defines dependency type constants using bit flags.
Implements access levels and strong typing where appropriate.
"""

import json
from typing import List


class DependencyType:
    """
    DependencyType defines dependency relationship types using bit flags.
    Implements private class constants with public accessors.
    
    Access Levels:
    - Public: Static API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Class constants (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Class Constants (Name Mangling)
    # -------------------------------------------------------------------------
    __MANDATORY_DEPENDENCY: int = 64    # 1000000
    __OPTIONAL_DEPENDENCY: int = 32     # 0100000
    __POSSIBLE_DEPENDENCY: int = 16     # 0010000
    __AND_DEPENDENCY: int = 8           # 0001000
    __OR_DEPENDENCY: int = 4            # 0000100
    __NOT_DEPENDENCY: int = 2           # 0000010
    __KNOWN_DEPENDENCY: int = 1         # 0000001
    __dependency_array: List[int] = []

    # -------------------------------------------------------------------------
    # Public Access Level: Static API Methods (Getters)
    # -------------------------------------------------------------------------
    @classmethod
    def get_mandatory(cls) -> int:
        """
        Public API: Returns MANDATORY dependency type value.
        
        Returns:
            MANDATORY dependency bit flag
        """
        return cls.__MANDATORY_DEPENDENCY

    @classmethod
    def get_optional(cls) -> int:
        """
        Public API: Returns OPTIONAL dependency type value.
        
        Returns:
            OPTIONAL dependency bit flag
        """
        return cls.__OPTIONAL_DEPENDENCY

    @classmethod
    def get_possible(cls) -> int:
        """
        Public API: Returns POSSIBLE dependency type value.
        
        Returns:
            POSSIBLE dependency bit flag
        """
        return cls.__POSSIBLE_DEPENDENCY

    @classmethod
    def get_and(cls) -> int:
        """
        Public API: Returns AND dependency type value.
        
        Returns:
            AND dependency bit flag
        """
        return cls.__AND_DEPENDENCY

    @classmethod
    def get_or(cls) -> int:
        """
        Public API: Returns OR dependency type value.
        
        Returns:
            OR dependency bit flag
        """
        return cls.__OR_DEPENDENCY

    @classmethod
    def get_not(cls) -> int:
        """
        Public API: Returns NOT dependency type value.
        
        Returns:
            NOT dependency bit flag
        """
        return cls.__NOT_DEPENDENCY

    @classmethod
    def get_known(cls) -> int:
        """
        Public API: Returns KNOWN dependency type value.
        
        Returns:
            KNOWN dependency bit flag
        """
        return cls.__KNOWN_DEPENDENCY

    # -------------------------------------------------------------------------
    # Public Access Level: Static API Methods (Array Management)
    # -------------------------------------------------------------------------
    @classmethod
    def populating_dependency(cls) -> None:
        """
        Public API: Populates the dependency array with all types.
        """
        cls.__dependency_array.append(cls.get_and())
        cls.__dependency_array.append(cls.get_or())
        cls.__dependency_array.append(cls.get_not())
        cls.__dependency_array.append(cls.get_known())
        cls.__dependency_array.append(cls.get_mandatory())
        cls.__dependency_array.append(cls.get_optional())
        cls.__dependency_array.append(cls.get_possible())

    @classmethod
    def get_dependency_array(cls) -> List[int]:
        """
        Public API: Returns the dependency array.
        
        Returns:
            List of all dependency type values
        """
        return cls.__dependency_array

    # -------------------------------------------------------------------------
    # Special Methods
    # -------------------------------------------------------------------------
    def __repr__(self) -> str:
        """
        Public API: String representation of the object.
        
        Returns:
            JSON string representation
        """
        return json.dumps({
            "mandatory": self.__MANDATORY_DEPENDENCY,
            "optional": self.__OPTIONAL_DEPENDENCY,
            "possible": self.__POSSIBLE_DEPENDENCY,
            "and": self.__AND_DEPENDENCY,
            "or": self.__OR_DEPENDENCY,
            "not": self.__NOT_DEPENDENCY,
            "known": self.__KNOWN_DEPENDENCY
        })
