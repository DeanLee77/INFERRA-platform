"""
Metadata Module.
Handles metadata for rules in PALOS analysis.
Implements access levels and strong typing where appropriate.
"""

import re
from typing import Optional, List, Tuple
from project.loggers import Logger

# Protected Module-Level Logger (Access Level: Protected)
_logger: Logger = Logger.get_logger(__name__)

# Protected Module-Level Constant (Access Level: Protected)
_META_DATA_TYPES: List[Tuple[str, str]] = [
    ('# Reference', '_reference'),
    ('# Section', '_origin'),
    ('# Original', '_statement')
]


class MetaData:
    """
    MetaData class stores metadata information for rules.
    Implements private state with public accessors.
    
    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(self, reference: Optional[str] = None, 
                 origin: Optional[str] = None, 
                 statement: Optional[str] = None):
        """
        Public Constructor: Initializes MetaData.
        
        Args:
            reference: Reference metadata
            origin: Origin metadata
            statement: Statement metadata
        """
        # Private instance variables (initialized in __init__ to avoid shared state)
        self.__reference: Optional[str] = reference
        self.__origin: Optional[str] = origin
        self.__statement: Optional[str] = statement

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Getters)
    # -------------------------------------------------------------------------
    def get_reference(self) -> Optional[str]:
        """
        Public API: Returns the reference metadata.
        
        Returns:
            Reference string or None
        """
        return self.__reference

    def get_origin(self) -> Optional[str]:
        """
        Public API: Returns the origin metadata.
        
        Returns:
            Origin string or None
        """
        return self.__origin

    def get_statement(self) -> Optional[str]:
        """
        Public API: Returns the statement metadata.
        
        Returns:
            Statement string or None
        """
        return self.__statement

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Setters)
    # -------------------------------------------------------------------------
    def set_reference(self, reference: str) -> None:
        """
        Public API: Sets the reference metadata.
        
        Args:
            reference: Reference string to set
        """
        self.__reference = reference

    def set_origin(self, origin: str) -> None:
        """
        Public API: Sets the origin metadata.
        
        Args:
            origin: Origin string to set
        """
        self.__origin = origin

    def set_statement(self, statement: str) -> None:
        """
        Public API: Sets the statement metadata.
        
        Args:
            statement: Statement string to set
        """
        self.__statement = statement

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Utilities)
    # -------------------------------------------------------------------------
    def instantiate_attrs(self, line: str) -> None:
        """
        Public API: Instantiates attributes from a metadata line.
        
        Args:
            line: Metadata line to parse
        """
        for meta_type, attr in _META_DATA_TYPES:
            if line.startswith(meta_type):
                # Extract content after the metadata type and optional colon/space
                content = line[len(meta_type):].lstrip(': ').strip()
                setattr(self, f'_{MetaData.__name__}__{attr[1:]}', content)
                break

    # -------------------------------------------------------------------------
    # Public Access Level: Static Methods
    # -------------------------------------------------------------------------
    @staticmethod
    def is_meta_data(line: str) -> bool:
        """
        Public API: Checks if a line contains metadata.
        
        Args:
            line: Line to check
            
        Returns:
            True if line contains metadata, False otherwise
        """
        return any(meta_type in line for meta_type, _ in _META_DATA_TYPES)