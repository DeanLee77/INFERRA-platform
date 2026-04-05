"""
Update Rule Details Data Transfer Object.
Implements strict encapsulation (Private variables, Public getters/setters).
"""

from typing import Optional

class UpdateRuleDetails:
    """
    UpdateRuleDetails DTO for rule detail updates.
    Implements private state with public accessors.
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(self, new_rule_name: Optional[str] = "", 
                 old_rule_name: Optional[str] = "", 
                 new_rule_category: Optional[str] = ""):
        """
        Public Constructor: Initializes UpdateRuleDetails DTO.
        
        Args:
            new_rule_name: New rule name
            old_rule_name: Old rule name
            new_rule_category: New rule category
        """
        # Private instance variables (initialized in __init__ to avoid shared state)
        self.__new_rule_name: str = new_rule_name or ""
        self.__old_rule_name: str = old_rule_name or ""
        self.__new_rule_category: str = new_rule_category or ""

    # -------------------------------------------------------------------------
    # Public Access Level: Getters
    # -------------------------------------------------------------------------
    def get_new_rule_name(self) -> str:
        """
        Public API: Returns the new rule name.
        
        Returns:
            New rule name string
        """
        return self.__new_rule_name

    def get_old_rule_name(self) -> str:
        """
        Public API: Returns the old rule name.
        
        Returns:
            Old rule name string
        """
        return self.__old_rule_name

    def get_new_category(self) -> str:
        """
        Public API: Returns the new category.
        
        Returns:
            New category string
        """
        return self.__new_rule_category

    # -------------------------------------------------------------------------
    # Public Access Level: Setters
    # -------------------------------------------------------------------------
    def set_new_rule_name(self, new_rule_name: str) -> None:
        """
        Public API: Sets the new rule name.
        
        Args:
            new_rule_name: New rule name
        """
        self.__new_rule_name = new_rule_name

    def set_old_rule_name(self, old_rule_name: str) -> None:
        """
        Public API: Sets the old rule name.
        
        Args:
            old_rule_name: Old rule name
        """
        self.__old_rule_name = old_rule_name

    def set_new_category(self, new_category: str) -> None:
        """
        Public API: Sets the new category.
        
        Args:
            new_category: New category
        """
        self.__new_rule_category = new_category