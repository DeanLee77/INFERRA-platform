"""
Update Rule Description Data Transfer Object.
Implements strict encapsulation (Private variables, Public getters/setters).
Note: This DTO is specifically for description updates only.
"""

from typing import Optional

class UpdateRuleDescription:
    """
    UpdateRuleDescription DTO for rule description updates only.
    Implements private state with public accessors.
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(self, rule_id: Optional[int] = None, 
                 new_description: Optional[str] = ""):
        """
        Public Constructor: Initializes UpdateRuleDescription DTO.
        
        Args:
            rule_id: ID of the rule to update
            new_description: New description text
        """
        # Private instance variables (initialized in __init__ to avoid shared state)
        self.__rule_id: Optional[int] = rule_id
        self.__newDescription: str = new_description or ""

    # -------------------------------------------------------------------------
    # Public Access Level: Getters
    # -------------------------------------------------------------------------
    def get_rule_id(self) -> Optional[int]:
        """
        Public API: Returns the rule ID.
        
        Returns:
            Rule ID or None
        """
        return self.__rule_id

    def get_new_description(self) -> str:
        """
        Public API: Returns the new description.
        
        Returns:
            New description string
        """
        return self.__newDescription

    # -------------------------------------------------------------------------
    # Public Access Level: Setters
    # -------------------------------------------------------------------------
    def set_rule_id(self, rule_id: int) -> None:
        """
        Public API: Sets the rule ID.
        
        Args:
            rule_id: Rule ID
        """
        self.__rule_id = rule_id

    def set_new_description(self, new_description: str) -> None:
        """
        Public API: Sets the new description.
        
        Args:
            new_description: New description text
        """
        self.__newDescription = new_description