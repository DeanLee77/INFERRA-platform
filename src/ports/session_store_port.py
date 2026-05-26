"""
Session Store Port Module.
Abstract interface for inference session storage.
"""

from abc import ABCMeta, abstractmethod
from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.inference.session import InferenceSession


class SessionStorePort(metaclass=ABCMeta):
    """
    Abstract interface for session storage.
    
    This port defines the contract for session persistence, allowing
    different implementations (in-memory, Redis, database, etc.)
    to be swapped without changing business logic.
    
    Implementations should be thread-safe for concurrent access.
    """
    
    @abstractmethod
    def get(self, session_id: str) -> Optional['InferenceSession']:
        """
        Retrieve a session by its ID.
        
        Args:
            session_id: The unique session identifier
            
        Returns:
            InferenceSession if found, None otherwise
        """
        pass  # pragma: no cover
    
    @abstractmethod
    def save(self, session: 'InferenceSession') -> None:
        """
        Save or update a session.

        Implementations that support optimistic concurrency should compare
        `session.version` against the currently persisted version and raise
        ConcurrentModificationError when the caller is stale. A successful
        update may increment `session.version`.
        
        Args:
            session: The session to save
        """
        pass  # pragma: no cover
    
    @abstractmethod
    def delete(self, session_id: str) -> bool:
        """
        Delete a session by its ID.
        
        Args:
            session_id: The unique session identifier
            
        Returns:
            True if session was deleted, False if not found
        """
        pass  # pragma: no cover
    
    @abstractmethod
    def exists(self, session_id: str) -> bool:
        """
        Check if a session exists.
        
        Args:
            session_id: The unique session identifier
            
        Returns:
            True if session exists, False otherwise
        """
        pass  # pragma: no cover
    
    @abstractmethod
    def list_sessions(self) -> List[str]:
        """
        List all active session IDs.
        
        Returns:
            List of session IDs
        """
        pass  # pragma: no cover
    
    @abstractmethod
    def clear_expired(self, max_age_seconds: int) -> int:
        """
        Remove sessions that have exceeded the maximum age.
        
        Args:
            max_age_seconds: Maximum session age in seconds
            
        Returns:
            Number of sessions removed
        """
        pass  # pragma: no cover
    
    @abstractmethod
    def clear_all(self) -> None:
        """
        Remove all sessions.
        
        Useful for testing or shutdown cleanup.
        """
        pass  # pragma: no cover
