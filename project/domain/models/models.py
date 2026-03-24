import json
from sqlalchemy_serializer import SerializerMixin
from sqlalchemy_serializer import Serializer
from project import db
from datetime import datetime
from operator import attrgetter

class User(db.Model, SerializerMixin):
    __tablename__ = 'user'
    serialize_rules = ()

    user_id = db.Column(db.BigInteger, primary_key=True)
    email = db.Column(db.String)
    password = db.Column(db.String)


    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password

    def serialize(self):
        d = Serializer.serialize(self)
        return d

    def get_date_time(self):
        return datetime.fromtimestamp(self.created_date)


class Rule(db.Model, SerializerMixin):
    __tablename__ = 'rule'
    serialize_rules = ('-related_models.rule', )

    rule_id = db.Column(db.BigInteger, primary_key=True)
    name = db.Column(db.String)
    category = db.Column(db.String)
    description = db.Column(db.String)
    rule_files = db.relationship('File', backref='rule', lazy='dynamic')
    rule_histories = db.relationship('History', backref='rule', lazy='dynamic')

    def __init__(self, rule_name: str = None, rule_category: str = None,
                 rule_description: str = None,
                 new_rule_files: list = None, new_rule_histories: list = None):
        self.name = rule_name
        self.category = rule_category
        self.description = rule_description
        self.rule_files = new_rule_files or []
        self.rule_histories = new_rule_histories or []

    def serialize(self):
        d = Serializer.serialize(self)
        return d

    def add_file(self, file):
        self.rule_files.append(file)

    def get_the_latest_file(self):
        files = self.rule_files.all()
        if files:
            # TODO this logic needs improvement due to timestamp comparison may not be the best way to get the lastest one
            return files[-1]
            # return max(self.rule_files.all(), key=attrgetter('created_date'))
        return None

    def get_the_latest_history(self):
        files = self.rule_files.all()
        histories = self.rule_histories.all()
        if files and histories:

            ##TODO this logic needs improvement due to timestamp comparison may not be the best way to get the lastest one
            return histories[-1]
            # return max(self.rule_histories.all(), key=attrgetter('created_date'))
        return None


class File(db.Model, SerializerMixin):
    __tablename__ = 'file'
    serialize_rules = ()

    file_id = db.Column(db.BigInteger, primary_key=True)
    rule_id = db.Column(db.BigInteger, db.ForeignKey('rule.rule_id'))
    created_date = db.Column(db.TIMESTAMP, nullable=False, default=datetime.now())
    files = db.Column(db.LargeBinary)

    def serialize(self):
        d = Serializer.serialize(self)
        return d

    def __init__(self, rule_id: int = None, files: bytearray = None):
        self.rule_id = rule_id
        self.files = files

    def get_date_time(self):
        return datetime.fromtimestamp(self.created_date)


class History(db.Model, SerializerMixin):
    __tablename__ = 'history'
    serialize_rules = ()

    history_id = db.Column(db.BigInteger, primary_key=True)
    rule_id = db.Column(db.BigInteger, db.ForeignKey('rule.rule_id'))
    created_date = db.Column(db.TIMESTAMP, nullable=False, default=datetime.now())
    history = db.Column(db.JSON)

    def __init__(self, rule_id: int, history: json):
        self.rule_id = rule_id
        self.history = history

    def serialize(self):
        d = Serializer.serialize(self)
        return d

    def get_date_time(self):
        return datetime.fromtimestamp(self.created_date)

    def get_history_dict(self):
        history_map = dict()
        history_json = self.history
