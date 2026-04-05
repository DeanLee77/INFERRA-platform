"""
Create File Data Transfer Object.
Implements strict encapsulation (Private variables, Public getters/setters).
"""

from typing import Optional

class CreateFile:
    """
    CreateFile DTO for rule file creation.
    Implements private state with public accessors.
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(self, rule_name: Optional[str] = "", rule_text: Optional[str] = ""):
        """
        Public Constructor: Initializes CreateFile DTO.
        
        Args:
            rule_name: Name of the rule
            rule_text: Text content of the rule
        """
        # Private instance variables (initialized in __init__ to avoid shared state)
        self.__rule_name: str = rule_name or ""
        self.__rule_text: str = rule_text or ""

    # -------------------------------------------------------------------------
    # Public Access Level: Getters
    # -------------------------------------------------------------------------
    def get_rule_name(self) -> str:
        """
        Public API: Returns the rule name.
        
        Returns:
            Rule name string
        """
        return self.__rule_name

    def get_rule_text(self) -> str:
        """
        Public API: Returns the rule text.
        
        Returns:
            Rule text string
        """
        return self.__rule_text

    # -------------------------------------------------------------------------
    # Public Access Level: Setters
    # -------------------------------------------------------------------------
    def set_rule_name(self, rule_name: str) -> None:
        """
        Public API: Sets the rule name.
        
        Args:
            rule_name: New rule name
        """
        self.__rule_name = rule_name

    def set_rule_text(self, rule_text: str) -> None:
        """
        Public API: Sets the rule text.
        
        Args:
            rule_text: New rule text
        """
        self.__rule_text = rule_text