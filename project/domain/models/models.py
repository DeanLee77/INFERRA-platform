"""
Database Models for PALOS Analysis.
Implements access levels and strong typing where appropriate.
Note: SQLAlchemy columns must remain public class attributes for ORM mapping.
"""

import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from operator import attrgetter

from sqlalchemy_serializer import SerializerMixin
from sqlalchemy_serializer import Serializer
from project import db


class User(db.Model, SerializerMixin):
    """
    User model for database persistence.
    
    Access Levels:
    - Public: SQLAlchemy ORM columns and API methods
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    
    Note: SQLAlchemy columns must remain public for ORM mapping.
    """
    
    # -------------------------------------------------------------------------
    # Public Access Level: SQLAlchemy ORM Requirements
    # -------------------------------------------------------------------------
    __tablename__ = 'user'
    serialize_rules = ()
    
    user_id = db.Column(db.BigInteger, primary_key=True)
    email = db.Column(db.String)
    password = db.Column(db.String)

    def __init__(self, email: str, password: str):
        """
        Public Constructor: Initializes User model.
        
        Args:
            email: User email address
            password: User password
        """
        self.email = email
        self.password = password

    def serialize(self) -> Dict[str, Any]:
        """
        Public API: Serializes the model instance.
        
        Returns:
            Dictionary representation of the model
        """
        d = Serializer.serialize(self)
        return d

    def get_date_time(self) -> Optional[datetime]:
        """
        Public API: Retrieves creation date.
        
        Returns:
            datetime object or None if not available
        """
        # Added safety check for attribute existence
        if hasattr(self, 'created_date') and self.created_date:
            return datetime.fromtimestamp(self.created_date)
        return None


class Rule(db.Model, SerializerMixin):
    """
    Rule model for database persistence.
    
    Access Levels:
    - Public: SQLAlchemy ORM columns and API methods
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    
    Note: SQLAlchemy columns must remain public for ORM mapping.
    """
    
    # -------------------------------------------------------------------------
    # Public Access Level: SQLAlchemy ORM Requirements
    # -------------------------------------------------------------------------
    __tablename__ = 'rule'
    serialize_rules = ('-related_models.rule', )
    
    rule_id = db.Column(db.BigInteger, primary_key=True)
    name = db.Column(db.String)
    category = db.Column(db.String)
    description = db.Column(db.String)
    
    # Public Relationships
    rule_files = db.relationship('File', backref='rule', lazy='dynamic')
    rule_histories = db.relationship('History', backref='rule', lazy='dynamic')

    def __init__(self, rule_name: Optional[str] = None, rule_category: Optional[str] = None,
                 rule_description: Optional[str] = None,
                 new_rule_files: Optional[List['File']] = None, 
                 new_rule_histories: Optional[List['History']] = None):
        """
        Public Constructor: Initializes Rule model.
        
        Args:
            rule_name: Name of the rule
            rule_category: Category of the rule
            rule_description: Description of the rule
            new_rule_files: List of associated files
            new_rule_histories: List of associated histories
        """
        self.name = rule_name
        self.category = rule_category
        self.description = rule_description
        self.rule_files = new_rule_files or []
        self.rule_histories = new_rule_histories or []

    def serialize(self) -> Dict[str, Any]:
        """
        Public API: Serializes the model instance.
        
        Returns:
            Dictionary representation of the model
        """
        d = Serializer.serialize(self)
        return d

    def add_file(self, file: 'File') -> None:
        """
        Public API: Adds a file to the rule.
        
        Args:
            file: File object to add
        """
        self.rule_files.append(file)

    def get_latest_file(self) -> Optional['File']:
        """
        Public API: Retrieves the latest file.
        
        Returns:
            Latest File object or None
        """
        files = self.rule_files.all()
        if files:
            # TODO: Logic improvement needed for timestamp comparison
            return files[-1]
        return None

    def get_latest_history(self) -> Optional['History']:
        """
        Public API: Retrieves the latest history.
        
        Returns:
            Latest History object or None
        """
        histories = self.rule_histories.all()
        if histories:
            # TODO: Logic improvement needed for timestamp comparison
            return histories[-1]
        return None


class File(db.Model, SerializerMixin):
    """
    File model for database persistence.
    
    Access Levels:
    - Public: SQLAlchemy ORM columns and API methods
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    
    Note: SQLAlchemy columns must remain public for ORM mapping.
    """
    
    # -------------------------------------------------------------------------
    # Public Access Level: SQLAlchemy ORM Requirements
    # -------------------------------------------------------------------------
    __tablename__ = 'file'
    serialize_rules = ()
    
    file_id = db.Column(db.BigInteger, primary_key=True)
    rule_id = db.Column(db.BigInteger, db.ForeignKey('rule.rule_id'))
    created_date = db.Column(db.TIMESTAMP, nullable=False, default=datetime.now)
    files = db.Column(db.LargeBinary)

    def __init__(self, rule_id: Optional[int] = None, files: Optional[bytearray] = None):
        """
        Public Constructor: Initializes File model.
        
        Args:
            rule_id: Associated rule ID
            files: File content as bytearray
        """
        self.rule_id = rule_id
        self.files = files

    def serialize(self) -> Dict[str, Any]:
        """
        Public API: Serializes the model instance.
        
        Returns:
            Dictionary representation of the model
        """
        d = Serializer.serialize(self)
        return d

    def get_date_time(self) -> Optional[datetime]:
        """
        Public API: Retrieves creation date.
        
        Returns:
            datetime object or None if not available
        """
        if hasattr(self, 'created_date') and self.created_date:
            return datetime.fromtimestamp(self.created_date)
        return None


class History(db.Model, SerializerMixin):
    """
    History model for database persistence.
    
    Access Levels:
    - Public: SQLAlchemy ORM columns and API methods
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    
    Note: SQLAlchemy columns must remain public for ORM mapping.
    """
    
    # -------------------------------------------------------------------------
    # Public Access Level: SQLAlchemy ORM Requirements
    # -------------------------------------------------------------------------
    __tablename__ = 'history'
    serialize_rules = ()
    
    history_id = db.Column(db.BigInteger, primary_key=True)
    rule_id = db.Column(db.BigInteger, db.ForeignKey('rule.rule_id'))
    created_date = db.Column(db.TIMESTAMP, nullable=False, default=datetime.now)
    history = db.Column(db.JSON)

    def __init__(self, rule_id: int, history: Dict[str, Any]):
        """
        Public Constructor: Initializes History model.
        
        Args:
            rule_id: Associated rule ID
            history: History data as dictionary
        """
        self.rule_id = rule_id
        self.history = history

    def serialize(self) -> Dict[str, Any]:
        """
        Public API: Serializes the model instance.
        
        Returns:
            Dictionary representation of the model
        """
        d = Serializer.serialize(self)
        return d

    def get_date_time(self) -> Optional[datetime]:
        """
        Public API: Retrieves creation date.
        
        Returns:
            datetime object or None if not available
        """
        if hasattr(self, 'created_date') and self.created_date:
            return datetime.fromtimestamp(self.created_date)
        return None

    def get_history_dict(self) -> Dict[str, Any]:
        """
        Public API: Retrieves history as dictionary.
        
        Returns:
            Dictionary representation of history data
        """
        history_map: Dict[str, Any] = dict()
        history_json = self.history
        
        # Added safety check for JSON loading if stored as string
        if isinstance(history_json, str):
            try:
                history_map = json.loads(history_json)
            except json.JSONDecodeError:
                pass
        elif isinstance(history_json, dict):
            history_map = history_json
        
        return history_map