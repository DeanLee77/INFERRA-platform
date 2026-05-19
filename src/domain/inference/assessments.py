"""
Assessments Collection Module.
Manages multiple Assessment instances in INFERRA analysis.
Implements access levels and strong typing where appropriate.
"""

from typing import Dict, Optional
from .assessment import Assessment


class Assessments:
    """
    Assessments class manages a collection of Assessment instances.
    Implements private state with public accessors.
    
    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(self):
        """
        Public Constructor: Initializes Assessments collection.
        
        Note: Instance variable initialized in __init__ to avoid shared state
        across instances (critical bug fix from class-level declaration).
        """
        # Private instance variable (initialized in __init__ to avoid shared state)
        self.__assessments_dict: Dict[str, Assessment] = {}

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Getters)
    # -------------------------------------------------------------------------
    def get_assessments_dict(self) -> Dict[str, Assessment]:
        """
        Public API: Returns the assessments dictionary.
        
        Returns:
            Dictionary mapping assessment names to Assessment objects
        """
        return self.__assessments_dict

    def get_assessment(self, assessment_name: str) -> Optional[Assessment]:
        """
        Public API: Gets an assessment by name.
        
        Args:
            assessment_name: Name of the assessment to retrieve
            
        Returns:
            Assessment object or None if not found
        """
        return self.__assessments_dict.get(assessment_name)

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Setters)
    # -------------------------------------------------------------------------
    def set_assessments_list(self, assessments_dict: Dict[str, Assessment]) -> None:
        """
        Public API: Sets the assessments dictionary.
        
        Args:
            assessments_dict: Dictionary mapping assessment names to Assessment objects
        """
        self.__assessments_dict = assessments_dict

    def add_assessment(self, assessment: Assessment) -> None:
        """
        Public API: Adds an assessment to the collection.
        
        Args:
            assessment: Assessment object to add
        """
        if assessment is not None:
            assessment_name = assessment.get_assessment_name()
            if assessment_name:
                self.__assessments_dict[assessment_name] = assessment

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    def _assessment_exists(self, assessment_name: str) -> bool:
        """
        Protected Helper: Checks if assessment exists in collection.
        
        Args:
            assessment_name: Name of the assessment to check
            
        Returns:
            True if assessment exists, False otherwise
        """
        return assessment_name in self.__assessments_dict

    def _remove_assessment(self, assessment_name: str) -> Optional[Assessment]:
        """
        Protected Helper: Removes an assessment from collection.
        
        Args:
            assessment_name: Name of the assessment to remove
            
        Returns:
            Removed Assessment object or None if not found
        """
        return self.__assessments_dict.pop(assessment_name, None)

    def _clear_all_assessments(self) -> None:
        """
        Protected Helper: Clears all assessments from collection.
        """
        self.__assessments_dict.clear()

    def _get_assessment_count(self) -> int:
        """
        Protected Helper: Returns the number of assessments in collection.
        
        Returns:
            Number of assessments
        """
        return len(self.__assessments_dict)
