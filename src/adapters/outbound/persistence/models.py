import json
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import Column, BigInteger, String, LargeBinary, TIMESTAMP, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy_serializer import SerializerMixin, Serializer

from .database import Base


class UserORM(Base, SerializerMixin):
    __tablename__ = 'user'
    serialize_rules = ()

    user_id = Column(BigInteger, primary_key=True)
    email = Column(String)
    password = Column(String)

    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password


class RuleORM(Base, SerializerMixin):
    __tablename__ = 'rule'
    serialize_rules = ('-related_models.rule', )

    rule_id = Column(BigInteger, primary_key=True)
    name = Column(String)
    category = Column(String)
    description = Column(String)

    rule_files = relationship('FileORM', backref='rule', lazy='dynamic')
    rule_histories = relationship('HistoryORM', backref='rule', lazy='dynamic')

    def __init__(self, rule_name: Optional[str] = None, rule_category: Optional[str] = None,
                 rule_description: Optional[str] = None):
        self.name = rule_name
        self.category = rule_category
        self.description = rule_description

    def get_latest_file(self) -> Optional['FileORM']:
        files = self.rule_files.all()
        if files:
            return files[-1]
        return None

    def get_latest_history(self) -> Optional['HistoryORM']:
        histories = self.rule_histories.all()
        if histories:
            return histories[-1]
        return None


class FileORM(Base, SerializerMixin):
    __tablename__ = 'file'
    serialize_rules = ()

    file_id = Column(BigInteger, primary_key=True)
    rule_id = Column(BigInteger, ForeignKey('rule.rule_id'))
    created_date = Column(TIMESTAMP, nullable=False, default=datetime.now)
    files = Column(LargeBinary)

    def __init__(self, rule_id: Optional[int] = None, files: Optional[bytearray] = None):
        self.rule_id = rule_id
        self.files = files


class HistoryORM(Base, SerializerMixin):
    __tablename__ = 'history'
    serialize_rules = ()

    history_id = Column(BigInteger, primary_key=True)
    rule_id = Column(BigInteger, ForeignKey('rule.rule_id'))
    created_date = Column(TIMESTAMP, nullable=False, default=datetime.now)
    history = Column(JSON)

    def __init__(self, rule_id: int, history: Dict[str, Any]):
        self.rule_id = rule_id
        self.history = history
