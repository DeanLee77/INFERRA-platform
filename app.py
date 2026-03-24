import base64
import os
import json
import requests
import tempfile
from typing import Any
from flask import Response
from project import create_app, jsonify, request
from project.domain.create_file import CreateFile
from project.domain.models import Rule, History
from project.domain.update_rule_details import UpdateRuleDescription
from project.fact_values import FactValue
from project.fact_values.fact_value_type import FactValueType
from project.inference import InferenceEngine, Assessment
from project.nodes import HistoryRecord, LineType
# from project.repository import RuleRepository
from project.rule_parser import RuleSetReader, RuleSetScanner
from project.rule_parser.rule_set_parser import RuleSetParser
from project.inference import TopologicalSort
from project.repository import find_rule_by_rule_name, create_rule_file
from project.repository import find_rule_text_by_rule_name
from project.repository import find_all_rules
from project.repository import update_rule_name_and_category
from project.repository import create_rule
from project.repository import find_id_by_name
from project.repository import create_rule_history
from project.loggers import Logger

from utils import validate_file, convert_file_to_markdown, transform_to_nadia_rules_stream
from openai import OpenAI
from dotenv import load_dotenv

logging: Logger = Logger.get_logger(__name__)

app = create_app()
session = requests.session()
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=dotenv_path)

RULE_PREFIX_URL = '/service/rule/'
INFERENCE_PREFIX_URL = '/service/inference/'
FILE_PREFIX_URL = '/service/file/'
MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH"))
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL")
OPENROUTER_TIMEOUT = os.getenv("OPENROUTER_TIMEOUT") # seconds

app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH


def _json_error(message: str, status_code: int = 400):
    logging.warning("API error (%s): %s", status_code, message)
    return jsonify({"success": False, "error": message}), status_code


def _require_arg(name: str) -> str:
    value = request.args.get(name)
    if value is None or str(value).strip() == "":
        raise ValueError(f"Missing required query parameter: {name}")
    return value


def _require_json_body() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if payload is None:
        raise ValueError("Request body must be valid JSON")
    return payload


def _require_json_fields(payload: dict[str, Any], *field_names: str) -> list[Any]:
    missing_fields = [field for field in field_names if payload.get(field) is None]
    if missing_fields:
        raise ValueError(f"Missing required field(s): {', '.join(missing_fields)}")
    return [payload[field] for field in field_names]


def _get_session_object(name: str):
    try:
        return getattr(session, name)
    except AttributeError as exc:
        raise LookupError(f"Session object '{name}' is not initialised") from exc


def _get_rule_file_or_raise(rule_name: str):
    rule_file = find_rule_text_by_rule_name(rule_name)
    if rule_file is None or rule_file.files is None:
        raise LookupError(f"Rule '{rule_name}' was not found or has no stored file")
    return rule_file


def _decode_rule_file(rule_file) -> str:
    try:
        return rule_file.files.decode('utf-8')
    except (AttributeError, UnicodeDecodeError) as exc:
        raise ValueError("Stored rule file could not be decoded as UTF-8") from exc


@app.route(f"{RULE_PREFIX_URL}searchRuleByName")
def search_rule_by_name(nadia_rule_name: str):  # put application's code here
    return find_rule_by_rule_name(nadia_rule_name)


############################################################# Done
@app.route(f"{RULE_PREFIX_URL}findRuleTreeDataByName")
def find_rule_tree_data_by_name():
    try:
        nadia_rule_name = _require_arg('ruleName')
        logging.info(f'THIS IS RULE NAME: {nadia_rule_name}')
        temp_rule = _get_rule_file_or_raise(nadia_rule_name)
        rule_text = _decode_rule_file(temp_rule)
        _set_rule_set_parser(nadia_rule_name)
        return {"ruleTreeData": rule_text}
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except LookupError as exc:
        return _json_error(str(exc), 404)
    except Exception as exc:
        logging.exception("Failed to fetch rule tree data: %s", exc)
        return _json_error("Failed to build rule tree data", 500)

@app.route(f"{RULE_PREFIX_URL}findRuleTextByName")
def find_rule_text_by_name():
    try:
        nadia_rule_name = _require_arg('ruleName')
        logging.info(f'THIS IS RULE NAME: {nadia_rule_name}')
        temp_rule = _get_rule_file_or_raise(nadia_rule_name)
        return {"ruleText": _decode_rule_file(temp_rule)}
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except LookupError as exc:
        return _json_error(str(exc), 404)
    except Exception as exc:
        logging.exception("Failed to fetch rule text: %s", exc)
        return _json_error("Failed to fetch rule text", 500)

@app.route(f"{RULE_PREFIX_URL}findTheLatestRuleFileByName")
def get_the_latest_rule_file_by_name():
    ###### ##################       Current
    nadia_rule_name = request.args.get('ruleName')
    return find_rule_text_by_rule_name(nadia_rule_name)


@app.route(f"{RULE_PREFIX_URL}findTheLatestRuleHistoryByName")
def get_the_latest_rule_history_by_name(nadia_rule_name):
    temp_rule = find_rule_by_rule_name(nadia_rule_name)
    if temp_rule is not None:
        return temp_rule.get_the_latest_history()
    return None


############################################################# Done
@app.route(f"{RULE_PREFIX_URL}findAllRules")
def get_all_rules():
    response = json.dumps(find_all_rules(), indent=4)
    # response.headers.add('Access-Control-Allow-Origin', '*')
    # return find_all_rules()
    return response
    # return jsonify({'rule_list': rule_list})


@app.route(f"{RULE_PREFIX_URL}updateRule", methods=['POST'])
def update_rule():
    try:
        payload = _require_json_body()
        old_rule_name, new_rule_name, new_rule_category = _require_json_fields(
            payload, 'oldRuleName', 'newRuleName', 'newRuleCategory'
        )
        updated = update_rule_name_and_category(old_rule_name, new_rule_name, new_rule_category)
        if not updated:
            return _json_error(f"Rule '{old_rule_name}' was not found", 404)

        rule_from_database = find_rule_by_rule_name(new_rule_name)
        if rule_from_database is None:
            return _json_error(f"Updated rule '{new_rule_name}' could not be reloaded", 500)

        return jsonify({
            "newRuleName": rule_from_database.name,
            "newCategory": rule_from_database.category,
        })
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        logging.exception("Failed to update rule: %s", exc)
        return _json_error("Failed to update rule", 500)


@app.route(f"{RULE_PREFIX_URL}createNewRule", methods=['POST'])
def create_new_rule():
    try:
        payload = _require_json_body()
        new_rule_name, new_rule_category, new_rule_description = _require_json_fields(
            payload, 'name', 'category', 'description'
        )

        create_rule(rule_details={
            'rule_name': new_rule_name,
            'rule_category': new_rule_category,
            'rule_description': new_rule_description,
        })

        rule_from_database = find_rule_by_rule_name(new_rule_name)
        if rule_from_database is None:
            return _json_error(f"Rule '{new_rule_name}' could not be created", 500)

        return json.dumps({
            "ruleName": rule_from_database.name,
            "category": rule_from_database.category,
            "description": rule_from_database.description,
        })
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        logging.exception("Failed to create rule: %s", exc)
        return _json_error("Failed to create rule", 500)

@app.route(f"{RULE_PREFIX_URL}saveConvertedRule", methods=['POST'])
def save_converted_rule():
    try:
        payload = _require_json_body()
        converted_rule_name, converted_rule_category, converted_rule_description, rule_text = _require_json_fields(
            payload, 'name', 'category', 'description', 'ruleText'
        )
        converted_rule_text_byte_array = bytearray(rule_text, 'utf-8')

        rule_id = create_rule(
            rule_details={
                'rule_name': converted_rule_name,
                'rule_category': converted_rule_category,
                'rule_description': converted_rule_description,
            }
        )

        create_rule_file(rule_id, converted_rule_text_byte_array)
        rule_from_database = find_rule_by_rule_name(converted_rule_name)
        if rule_from_database is None:
            return _json_error(f"Converted rule '{converted_rule_name}' could not be loaded", 500)

        return json.dumps({
            "ruleName": rule_from_database.name,
            "category": rule_from_database.category,
            "description": rule_from_database.description,
        })
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        logging.exception("Failed to save converted rule: %s", exc)
        return _json_error("Failed to save converted rule", 500)


@app.post(f"{RULE_PREFIX_URL}createFile")
def create_file():
    try:
        payload = _require_json_body()
        rule_name, rule_text = _require_json_fields(payload, 'ruleName', 'ruleText')
        rule_text_byte_array = bytearray(rule_text, 'utf-8')

        rule_id = find_id_by_name(rule_name)
        if rule_id is None:
            return _json_error(f"Rule '{rule_name}' was not found", 404)

        create_rule_file(rule_id, rule_text_byte_array)
        rule_file_from_database = _get_rule_file_or_raise(rule_name)
        return jsonify({"ruleText": _decode_rule_file(rule_file_from_database)})
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except LookupError as exc:
        return _json_error(str(exc), 404)
    except Exception as exc:
        logging.exception("Failed to create rule file: %s", exc)
        return _json_error("Failed to create rule file", 500)


@app.route(f"{RULE_PREFIX_URL}updateHistory", methods=['POST'])
def update_history():
    try:
        payload = _require_json_body()
        rule_name, target_goal_node_name = _require_json_fields(payload, 'ruleName', 'targetNodeName')

        inference_engine: InferenceEngine = _get_session_object(f'inferenceEngine-{target_goal_node_name}')
        working_memory: dict = inference_engine.get_assessment_state().get_working_memory()

        rule_history: History = None
        temp_rule = find_rule_by_rule_name(rule_name)
        if temp_rule is None:
            return _json_error(f"Rule '{rule_name}' was not found", 404)

        rule_history = temp_rule.get_the_latest_history()

        parent_temp_history: json = {}

        if rule_history is not None:
            target_history: json = rule_history.history or {}
            record_list = list()

            filtered_dict = dict()

        # this is for the case of rules in workingMemory.
        # Hence, the rules should be checked if it is in history list or not.
        # if it is in the history list then history record should be fetched and update record according to
        # the workingMemory,
        # and if is not in the history list then create a new record, and insert the new record into the history list.
            for each_rule_key in working_memory.keys():
                if each_rule_key not in inference_engine.get_node_set().get_fact_dictionary().keys():
                    for history_key in target_history:
                        if history_key == each_rule_key:
                            filtered_dict[history_key] = target_history[history_key]

                        # filtered_list.append({history_key: target_history[history_key]})

                    record = HistoryRecord()
                    record.set_name(each_rule_key)

                    if filtered_dict.get(each_rule_key) is not None:
                        record.set_false_count(int(filtered_dict.get(each_rule_key).get('false', 0)))
                        record.set_true_count(int(filtered_dict.get(each_rule_key).get('true', 0)))
                # if len(filtered_list) > 0:
                #     print(each_rule_key)
                #     record.set_false_count(int(filtered_list[0].get(each_rule_key).get('false')))
                #     record.set_true_count(int(filtered_list[0].get(each_rule_key).get('true')))

                    fact_value: FactValue = working_memory[each_rule_key]

                    if fact_value.get_value_type().value == FactValueType.BOOLEAN.value:
                        record.set_type(str(fact_value.get_value_type().value).lower())
                        if fact_value.get_value() is True:
                            record.increment_true_count()
                        else:
                            record.increment_false_count()
                    else:
                        record.set_type(str(fact_value.get_value_type()).lower())
                        record.increment_true_count()

                    record_list.append(record)

        # this is for the case of rules that are not Boolean type and is in history list but not currently being asked.
        # Hence, the record for the rule should be incremented for 'FALSE' due to it is equivalent to 'FALSE' case
        # for propositional rules.

            for key, history_item in target_history.items():
                if key not in working_memory.keys():
                    record = HistoryRecord()
                    record.set_name(key)
                    record.set_false_count(int(history_item.get('false', 0)))
                    record.set_true_count(int(history_item.get('true', 0)))
                    if str(history_item.get('type', '')).lower() != 'boolean':
                        record.increment_false_count()
                    record_list.append(record)

            for each_record in record_list:
                temp_history = {}
                temp_history["true"] = str(each_record.get_true_count())
                temp_history["false"] = str(each_record.get_false_count())
                temp_history["type"] = each_record.get_type()

                parent_temp_history[each_record.get_name()] = temp_history
        else:  # case of the rule file has never been used so that there is a no record history.
            for work_item in working_memory.keys():
                fact_value: FactValue = working_memory.get(work_item)
                temp_history: json = {}

                if fact_value.get_value_type().value == FactValueType.BOOLEAN.value:
                    if fact_value.get_value() is True:
                        temp_history["true"] = "1"
                        temp_history["false"] = "0"
                    else:
                        temp_history["true"] = "0"
                        temp_history["false"] = "1"
                else:
                    temp_history["true"] = "1"
                    temp_history["false"] = "0"

                temp_history["type"] = str(working_memory.get(work_item).get_value_type())
                parent_temp_history[work_item] = temp_history

        create_rule_history(temp_rule.rule_id, parent_temp_history)

        return {"update": "done"}
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except LookupError as exc:
        return _json_error(str(exc), 404)
    except Exception as exc:
        logging.exception("Failed to update history: %s", exc)
        return _json_error("Failed to update history", 500)


@app.route(f"{INFERENCE_PREFIX_URL}viewSummary")
def view_summary():
    try:
        _require_arg('ruleName')
        target_goal_node_name = _require_arg('targetNodeName')
        inference_engine: InferenceEngine = _get_session_object(f'inferenceEngine-{target_goal_node_name}')
        temp_summary_list = list()
        temp_assessment_state = inference_engine.get_assessment_state()
        temp_working_memory = temp_assessment_state.get_working_memory()
        for summary_item in temp_assessment_state.get_summary_list():
            fact_value = temp_working_memory.get(summary_item)
            if fact_value is None:
                continue
            summary_json = {"nodeText": summary_item, "nodeValue": str(fact_value.get_value())}
            temp_summary_list.append(summary_json)

        for each_key, fact_value in temp_working_memory.items():
            if each_key not in inference_engine.get_assessment_state().get_summary_list():
                summary_json = {"nodeText": each_key}
                if isinstance(fact_value.get_value(), list):
                    fact_list = [each_fact.get_value() for each_fact in fact_value.get_value()]
                    summary_json['nodeValue'] = json.dumps(fact_list)
                else:
                    summary_json['nodeValue'] = str(fact_value.get_value())
                temp_summary_list.append(summary_json)

        return temp_summary_list
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except LookupError as exc:
        return _json_error(str(exc), 404)
    except Exception as exc:
        logging.exception("Failed to build summary: %s", exc)
        return _json_error("Failed to build summary", 500)


# TODO: this API still needs further work
@app.route(f"{INFERENCE_PREFIX_URL}editAnswer", methods=['POST'])
def edit_answer(question: json):
    try:
        payload = _require_json_body()
        nadia_rule_name, question_name = _require_json_fields(payload, 'ruleName', 'question')
        inference_engine: InferenceEngine = _get_session_object(f'inferenceEngine-{nadia_rule_name}')
        assessment: Assessment = _get_session_object(f'assessment-{nadia_rule_name}')

        inference_engine.edit_answer(question_name)
        object_node: json = {}
        temp_working_memory = inference_engine.get_assessment_state().get_working_memory()

        if temp_working_memory.get(assessment.get_goal_node().get_node_name()) is None \
                or inference_engine.get_assessment_state().all_mandatory_node_determined() is False:
            object_node['hasMoreQuestion'] = 'true'
        else:
            goal_node_name = assessment.get_goal_node().get_node_name()
            goal_type = inference_engine.find_type_of_element_to_be_asked(assessment.get_goal_node()).get(goal_node_name)
            object_node['hasMoreQuestion'] = 'false'
            object_node['goalRuleName'] = goal_node_name
            object_node['goalRuleValue'] = str(temp_working_memory.get(goal_node_name).get_value())
            object_node['goalRuleType'] = str(goal_type).lower() if goal_type is not None else 'unknown'

        return object_node
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except LookupError as exc:
        return _json_error(str(exc), 404)
    except Exception as exc:
        logging.exception("Failed to edit answer: %s", exc)
        return _json_error("Failed to edit answer", 500)


@app.route(f"{INFERENCE_PREFIX_URL}feedAnswer", methods=['POST'])
def feed_answer():
    try:
        payload = _require_json_body()
        _require_json_fields(payload, 'ruleName', 'targetNodeName', 'question', 'answer')
        target_goal_node_name = payload['targetNodeName']
        answer_entry = payload['answer']
        if not isinstance(answer_entry, dict):
            raise ValueError("answer must be an object")
        answer_type, answer_value = _require_json_fields(answer_entry, 'type', 'answer')

        inference_engine: InferenceEngine = _get_session_object('inferenceEngine-'+target_goal_node_name)
        assessment: Assessment = _get_session_object('assessment-'+target_goal_node_name)

        from project.fact_values import FactValueType
        try:
            fact_value_type: FactValueType = FactValueType[str(answer_type).upper()]
        except KeyError as exc:
            raise ValueError(f"Unsupported answer type: {answer_type}") from exc

        active_question_node = assessment.get_node_to_be_asked()
        if active_question_node is None:
            raise LookupError("No active question is set for this assessment")
        active_node = assessment.get_aux_node_to_be_asked() \
            if active_question_node.get_line_type() == LineType.ITERATE \
            else active_question_node
        inference_engine.feed_answer_to_node(
            active_node,
            payload['question'],
            str(answer_value),
            fact_value_type,
            assessment,
        )

        object_node = {}
        goal_fact = inference_engine.get_assessment_state().get_working_memory().get(
            assessment.get_goal_node().get_node_name()
        )
        if goal_fact is None or not inference_engine.get_assessment_state().all_mandatory_node_determined():
            object_node['hasMoreQuestion'] = 'true'
        else:
            goal_node_name: str = assessment.get_goal_node().get_node_name()
            goal_type = inference_engine.find_type_of_element_to_be_asked(assessment.get_goal_node()).get(goal_node_name)
            object_node['hasMoreQuestion'] = 'false'
            object_node['goalRuleName'] = goal_node_name
            object_node['goalRuleValue'] = str(goal_fact.get_value())
            object_node['goalRuleType'] = str(goal_type.value).lower() if goal_type is not None else 'unknown'
        logging.info(f'return node: {object_node}')
        return object_node
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except LookupError as exc:
        return _json_error(str(exc), 404)
    except Exception as exc:
        logging.exception("Failed to feed answer: %s", exc)
        return _json_error("Failed to feed answer", 500)


@app.route(f"{INFERENCE_PREFIX_URL}getNextQuestion")
def get_next_question():
    try:
        nadia_rule_name = _require_arg('targetRuleName')
        target_goal_node_name = _require_arg('targetNodeName')

        try:
            inference_engine: InferenceEngine = _get_session_object(f'inferenceEngine-{target_goal_node_name}')
        except LookupError:
            inference_engine = None

        if inference_engine is None or inference_engine.get_node_set().get_node_set_name() != nadia_rule_name:
            _reset_inferene_engine(
                nadia_rule_name=nadia_rule_name,
                target_goal_node_name=target_goal_node_name,
            )

        inference_engine = _get_session_object(f'inferenceEngine-{target_goal_node_name}')
        assessment: Assessment = _get_session_object(f'assessment-{target_goal_node_name}')

        next_question_node = inference_engine.get_next_question_with_goal_name(target_goal_node_name)
        if next_question_node is None:
            return []

        if assessment.get_node_to_be_asked() is not None and assessment.get_node_to_be_asked().get_line_type() == LineType.ITERATE:
            assessment.set_aux_node_to_be_asked(next_question_node)

        question_fact_value_type_dict: dict = inference_engine.find_type_of_element_to_be_asked(next_question_node)
        questionnaire: list = inference_engine.get_questions_from_node_to_be_asked(next_question_node)
        questionnaire_list = []
        for question in questionnaire:
            question_type = question_fact_value_type_dict.get(question)
            questionnaire_list.append({
                'questionText': question,
                'questionValueType': str(question_type.value).lower() if question_type is not None else 'unknown',
            })

        return questionnaire_list
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except LookupError as exc:
        return _json_error(str(exc), 404)
    except Exception as exc:
        logging.exception("Failed to get next question: %s", exc)
        return _json_error("Failed to get next question", 500)


@app.route(f"{INFERENCE_PREFIX_URL}setInferenceEngine")
def set_inference_engine():
    nadia_rule_name = request.args.get('ruleName')
    target_goal_node_name = request.args.get('targetNodeName')

    return _reset_inferene_engine(
        nadia_rule_name=nadia_rule_name, 
        target_goal_node_name=target_goal_node_name)


@app.route(f"{INFERENCE_PREFIX_URL}setMachineLearningInferenceEngine")
def set_machine_learning_inference_engine():
    nadia_rule_name = request.args.get('ruleName')
    target_goal_node_name = request.args.get('targetNodeName')
    
    temp_rule = find_rule_by_rule_name(nadia_rule_name)
    rule_history: History = None
    if temp_rule is not None:
        rule_history = temp_rule.get_the_latest_history()

    history_dict = dict()
    if rule_history is not None:
        history_dict = rule_history.history
    else:
        history_dict = None
    
    return _reset_inferene_engine(
        nadia_rule_name=nadia_rule_name, 
        target_goal_node_name=target_goal_node_name, 
        history_dict=history_dict)


@app.route(f"{FILE_PREFIX_URL}convert", methods=['POST'])
def convert_document():
    """Handle document conversion and transformation request"""
    try:
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        form_data = request.form  # Get form data
        file_type = form_data.get('type', '')
        fileName = file.filename

        
        # Validate file - pass form_data as parameter
        is_valid, error_msg = validate_file(file, form_data)
        if not is_valid:
            return jsonify({'success': False, 'error': error_msg}), 400
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        

        # Debug info (can remove later)
        logging.info(f'Received file: {file.filename}')
        logging.info(f'File type: {form_data.get("type", "").lower()}')
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp_file:
            file.save(tmp_file.name)
            tmp_file_path = tmp_file.name

        # Additional check for empty file (double-check)
        if os.path.getsize(tmp_file_path) == 0:
            os.unlink(tmp_file_path)
            return jsonify({'success': False, 'error': 'Empty file'}), 400


        try:
            markdown_content = convert_file_to_markdown(tmp_file_path, file_type)
            
            # Stream the response directly from the generator
            return Response(
                transform_to_nadia_rules_stream(fileName, markdown_content),
                mimetype='text/plain',
                headers={
                    'Access-Control-Allow-Origin': '*',
                    'Cache-Control': 'no-cache',
                    'Transfer-Encoding': 'chunked'
                }
            )
        finally:
            # Clean up temporary files
            if os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
    except Exception as e:
        logging.exception("Document conversion failed: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route(f"{RULE_PREFIX_URL}targetNodeNameList", methods=['GET'])
def get_all_possible_target_node_name_list():
    try:
        rule_name = _require_arg('ruleName')
        node_set = _set_rule_set_parser(rule_name).get_node_set()
        targetNodeList = TopologicalSort.filling_s_list(
                node_set.get_node_dictionary(),
                node_set.get_node_id_dictionary(),
                list(),
                node_set.get_dependency_matrix().get_dependency_two_dimension_list())
        response_list = list(x.get_node_name() for x in targetNodeList)
        return json.dumps(response_list, indent=4)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except LookupError as exc:
        return _json_error(str(exc), 404)
    except Exception as exc:
        logging.exception("Failed to fetch target node names: %s", exc)
        return _json_error("Failed to fetch target node names", 500)
    
            
    



def _set_rule_set_parser(nadia_rule_name:str) -> RuleSetParser:
    if not nadia_rule_name:
        raise ValueError("nadia_rule_name is required")
    rule_text = _decode_rule_file(_get_rule_file_or_raise(nadia_rule_name))

    rule_set_reader = RuleSetReader()
    rule_set_reader.create()

    rule_set_parser = RuleSetParser()
    rule_set_parser.create()

    rule_set_reader.set_file_with_text(rule_text)
    rule_set_scanner = RuleSetScanner(rule_set_reader, rule_set_parser)
    rule_set_scanner.scan_rule_set()

    rule_set_scanner.establish_node_set()
    if not rule_set_parser.get_node_set().get_sorted_node_list():
        raise ValueError(f"Rule '{nadia_rule_name}' could not be parsed into a valid node set")

    return rule_set_parser
    
    
        

def _reset_inferene_engine(nadia_rule_name:str, target_goal_node_name: str, history_dict: dict=None):
    if not nadia_rule_name:
        raise ValueError("nadia_rule_name is required")
    rule_text = _decode_rule_file(_get_rule_file_or_raise(nadia_rule_name))

    rule_set_reader = RuleSetReader()
    rule_set_reader.create()

    rule_set_parser = RuleSetParser()
    rule_set_parser.create()

    rule_set_reader.set_file_with_text(rule_text)
    rule_set_scanner = RuleSetScanner(rule_set_reader, rule_set_parser)
    rule_set_scanner.scan_rule_set()

    if history_dict == None:
        rule_set_scanner.establish_node_set()
    else:
        rule_set_scanner.establish_node_set(history_dict)

    inference_engine = InferenceEngine(rule_set_parser.get_node_set())
    inference_engine.get_node_set().set_node_set_name(nadia_rule_name)
    if not rule_set_parser.get_node_set().get_sorted_node_list():
        raise ValueError(f"Rule '{nadia_rule_name}' did not produce any goal nodes")

    if target_goal_node_name != None:
        if target_goal_node_name not in rule_set_parser.get_node_set().get_node_dictionary():
            raise LookupError(f"Target node '{target_goal_node_name}' does not exist in rule '{nadia_rule_name}'")
        assessment = Assessment(rule_set_parser.get_node_set(), target_goal_node_name)
    else:
        target_goal_node_name = rule_set_parser.get_node_set().get_sorted_node_list()[0].get_node_name()
        logging.info(f'Currently target node name is not given for : {nadia_rule_name}. \n \
                     Setting target node : {target_goal_node_name}') 
        assessment = Assessment(rule_set_parser.get_node_set(), target_goal_node_name)
    
    inference_engine.add_assessment_into_assessment_list(assessment)
    # inference_engine.set_assessment(assessment)

    session.__setattr__('inferenceEngine-'+target_goal_node_name, inference_engine)
    session.__setattr__('assessment-'+target_goal_node_name, assessment)
    
    object_node = {}
    object_node['InferenceEngine'] = 'created'

    return jsonify(object_node)

    

if __name__ == '__main__':
    app.run()
