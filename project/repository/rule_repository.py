import json
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
    return Rule.query.filter_by(name=rule_name).first()


def find_rule_text_by_rule_name(rule_name: str) -> Rule:
    return Rule.query.filter_by(name=rule_name).first().get_the_latest_file()

def find_rule_text_by_rule_id(rule_id:int) -> Rule:
    return Rule.query.filter_by(rule_id=rule_id).first().get_the_latest_file()


def find_all_rules():
    my_list = list()
    # all_rules = Rule.query.all()
    for each_rule in Rule.query.all():
        my_list.append(each_rule.to_dict(rules=('-rule_files', '-rule_histories')))
    return my_list


def update_rule_name_and_category(old_rule_name: str, new_rule_name: str, new_category: str):
    Rule.query.filter_by(name=old_rule_name).update(dict(name=new_rule_name, category=new_category))
    db.session.commit()


def create_rule(rule_details={}):
    rule_id = find_id_by_name(rule_details['rule_name'])
    if rule_id is None:
        rule = Rule(**rule_details)
        db.session.add(rule)
        db.session.commit()
    return rule_id


def create_rule_file(rule_id: int, new_file: bytearray):
    existing_file: File = find_rule_text_by_rule_id(rule_id)
    if existing_file is None or (existing_file is not None and existing_file.files != new_file):
        logging.info(f"Creating new file for rule_id={rule_id}")
        new_file_record = File(rule_id=rule_id, files=new_file)
        db.session.add(new_file_record)
        db.session.commit()
        


def create_rule_history(rule_id: int, history: json):
    history = History(rule_id, history)
    db.session.add(history)
    db.session.commit()
