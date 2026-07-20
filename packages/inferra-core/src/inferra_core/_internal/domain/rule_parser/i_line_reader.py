"""
I Line Reader Interface Module.
Abstract interface for reading rule lines from various sources.
Implements access levels and strong typing where appropriate.
"""

from abc import ABCMeta, abstractmethod


class ILineReader(metaclass=ABCMeta):
    """
    ILineReader abstract interface for reading rule lines.
    
    Access Levels:
    - Public: Abstract API methods for implementation
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Public Access Level: Abstract API Methods
    # -------------------------------------------------------------------------
    @abstractmethod
    def get_next_line(self) -> str:
        """
        Public API: Gets the next line from the input source.
        
        Returns:
            Next line as string
            
        Raises:
            RuntimeError: If no lines to read
        """
        pass  # pragma: no cover
