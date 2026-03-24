import json
from sqlalchemy.exc import SQLAlchemyError
from project.domain.models.models import Rule, File, History
from project import db
from project.loggers import Logger

logging: Logger = Logger.get_logger(__name__)



def find_id_by_name(rule_name: str) -> int:
    rule = Rule.query.filter_by(name=rule_name).first()
    rule_id = rule.rule_id if rule else None
    
    logging.info(f"Found Rule ID: {rule_id}")

    return rule_id


def find_rule_by_rule_name(rule_name: str) -> Rule:
    if not rule_name:
        logging.warning("find_rule_by_rule_name called without a rule name")
        return None
    return Rule.query.filter_by(name=rule_name).first()


def find_rule_text_by_rule_name(rule_name: str) -> Rule:
    rule = find_rule_by_rule_name(rule_name)
    return rule.get_the_latest_file() if rule is not None else None

def find_rule_text_by_rule_id(rule_id:int) -> Rule:
    if rule_id is None:
        logging.warning("find_rule_text_by_rule_id called without a rule id")
        return None

    rule = Rule.query.filter_by(rule_id=rule_id).first()
    return rule.get_the_latest_file() if rule is not None else None


def find_all_rules():
    my_list = list()
    # all_rules = Rule.query.all()
    for each_rule in Rule.query.all():
        my_list.append(each_rule.to_dict(rules=('-rule_files', '-rule_histories')))
    return my_list


def update_rule_name_and_category(old_rule_name: str, new_rule_name: str, new_category: str):
    try:
        updated_rows = Rule.query.filter_by(name=old_rule_name).update(
            dict(name=new_rule_name, category=new_category)
        )
        db.session.commit()
        return updated_rows > 0
    except SQLAlchemyError as exc:
        db.session.rollback()
        logging.exception("Failed to update rule '%s': %s", old_rule_name, exc)
        raise


def create_rule(rule_details={}):
    rule_name = rule_details.get('rule_name')
    if not rule_name:
        raise ValueError("rule_name is required")

    rule_id = find_id_by_name(rule_name)
    if rule_id is not None:
        return rule_id

    try:
        rule = Rule(**rule_details)
        db.session.add(rule)
        db.session.commit()
        return rule.rule_id
    except SQLAlchemyError as exc:
        db.session.rollback()
        logging.exception("Failed to create rule '%s': %s", rule_name, exc)
        raise


def create_rule_file(rule_id: int, new_file: bytearray):
    if rule_id is None:
        raise ValueError("rule_id is required to create a rule file")
    if new_file is None:
        raise ValueError("new_file is required to create a rule file")

    existing_file: File = find_rule_text_by_rule_id(rule_id)
    if existing_file is None or existing_file.files != new_file:
        try:
            logging.info(f"Creating new file for rule_id={rule_id}")
            new_file_record = File(rule_id=rule_id, files=new_file)
            db.session.add(new_file_record)
            db.session.commit()
        except SQLAlchemyError as exc:
            db.session.rollback()
            logging.exception("Failed to create file for rule_id=%s: %s", rule_id, exc)
            raise
        


def create_rule_history(rule_id: int, history: json):
    if rule_id is None:
        raise ValueError("rule_id is required to create rule history")
    if history is None:
        raise ValueError("history payload is required")

    try:
        history = History(rule_id, history)
        db.session.add(history)
        db.session.commit()
    except SQLAlchemyError as exc:
        db.session.rollback()
        logging.exception("Failed to create history for rule_id=%s: %s", rule_id, exc)
        raise
