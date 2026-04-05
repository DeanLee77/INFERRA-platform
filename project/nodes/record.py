"""
History Record Module.
Tracks historical data for topological sort optimization.
Implements access levels and strong typing where appropriate.
"""

import json
from typing import Optional
from project.loggers import Logger

# Protected Module-Level Logger (Access Level: Protected)
_logger: Logger = Logger.get_logger(__name__)


class HistoryRecord:
    """
    HistoryRecord tracks true/false counts for rule optimization.
    Implements private state with public accessors.
    
    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(
        self,
        name: Optional[str] = None,
        type: Optional[str] = None,
        true_count: Optional[int] = None,
        false_count: Optional[int] = None,
    ):
        """
        Public Constructor: Initializes HistoryRecord.
        
        Args:
            name: Record name
            type: Record type
            true_count: Count of true outcomes
            false_count: Count of false outcomes
        """
        # Private instance variables (initialized in __init__ to avoid shared state)
        self.__name: Optional[str] = name
        self.__type: Optional[str] = type
        self.__true_count: int = true_count if true_count is not None else 0
        self.__false_count: int = false_count if false_count is not None else 0
        
        _logger.info(
            "Generating Record : "
            "Name-" + str(name) + ", "
            "Type-" + str(type) + ", "
            "True Count-" + str(true_count) + ", "
            "False Count-" + str(false_count)
        )

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Getters)
    # -------------------------------------------------------------------------
    def get_name(self) -> Optional[str]:
        """
        Public API: Returns the record name.
        
        Returns:
            Name string or None
        """
        return self.__name

    def get_type(self) -> Optional[str]:
        """
        Public API: Returns the record type.
        
        Returns:
            Type string or None
        """
        return self.__type

    def get_true_count(self) -> int:
        """
        Public API: Returns the true count.
        
        Returns:
            True count integer
        """
        return self.__true_count

    def get_false_count(self) -> int:
        """
        Public API: Returns the false count.
        
        Returns:
            False count integer
        """
        return self.__false_count

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Setters)
    # -------------------------------------------------------------------------
    def set_name(self, name: str) -> None:
        """
        Public API: Sets the record name.
        
        Args:
            name: Name to set
        """
        self.__name = name

    def set_type(self, type: str) -> None:
        """
        Public API: Sets the record type.
        
        Args:
            type: Type to set
        """
        self.__type = type

    def set_true_count(self, true_count: int) -> None:
        """
        Public API: Sets the true count.
        
        Args:
            true_count: True count to set
        """
        self.__true_count = true_count

    def set_false_count(self, false_count: int) -> None:
        """
        Public API: Sets the false count.
        
        Args:
            false_count: False count to set
        """
        self.__false_count = false_count

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Modifiers)
    # -------------------------------------------------------------------------
    def add_true_count(self, true_count: int) -> None:
        """
        Public API: Adds to the true count.
        
        Args:
            true_count: Amount to add
        """
        self.__true_count += true_count

    def increment_true_count(self) -> None:
        """
        Public API: Increments the true count by 1.
        """
        self.__true_count = self.__true_count + 1

    def add_false_count(self, false_count: int) -> None:
        """
        Public API: Adds to the false count.
        
        Args:
            false_count: Amount to add
        """
        self.__false_count += false_count

    def increment_false_count(self) -> None:
        """
        Public API: Increments the false count by 1.
        """
        self.__false_count = self.__false_count + 1

    # -------------------------------------------------------------------------
    # Special Methods
    # -------------------------------------------------------------------------
    def __repr__(self) -> str:
        """
        Public API: String representation of the object.
        
        Returns:
            JSON string representation
        """
        return json.dumps(self.__dict__)