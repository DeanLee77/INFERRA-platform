import json

from flask import jsonify, Response, request, make_response

from project import create_app, session
from project.domain.create_file import CreateFile
from project.domain.models import Rule, History
from project.domain.update_rule_description import UpdateRuleDescription
from project.fact_values import FactValue
from project.fact_values.fact_value_type import FactValueType
from project.inference import InferenceEngine, Assessment
from project.nodes import HistoryRecord, LineType
# from project.repository import RuleRepository
from project.rule_parser import RuleSetReader, RuleSetScanner
from project.rule_parser.rule_set_parser import RuleSetParser
from project.repository import find_rule_by_rule_name, create_rule_file
from project.repository import find_rule_text_by_rule_name
from project.repository import find_all_rules
from project.repository import update_rule_name_and_category
from project.repository import create_rule
from project.repository import find_id_by_name
from project.repository import create_rule_history
from project.demo import build_decision_receipt, build_fixture_manifest

app = create_app()

rule_prefix_url = '/service/rule/'
inference_prefix_url = '/service/inference/'


@app.route(rule_prefix_url + 'syntheticDecisionReceiptFixture')
def get_synthetic_decision_receipt_fixture():
    response = jsonify(build_fixture_manifest())
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response


@app.route(inference_prefix_url + 'syntheticDecisionReceipt')
def get_synthetic_decision_receipt():
    case_id = request.args.get('caseId', 'certify-ready')
    try:
        response = jsonify(build_decision_receipt(case_id))
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
    except ValueError as error:
        return jsonify({"error": str(error)}), 400


@app.route(rule_prefix_url + 'searchRuleByName')
def search_rule_by_name(nadia_rule_name: str):  # put application's code here
    return find_rule_by_rule_name(nadia_rule_name)


############################################################# Done
@app.route(rule_prefix_url + 'findRuleTextByName')
def find_rule_text_by_name():
    nadia_rule_name = request.args.get('ruleName')
    temp_rule = find_rule_text_by_rule_name(nadia_rule_name)
    response = jsonify("{}")
    response.headers.add('Access-Control-Allow-Origin', '*')

    if temp_rule is not None:
        # rule_file = temp_rule.get_the_latest_file()
        # response = jsonify("{\"ruleText\":\"" + temp_rule.files.decode('utf-8') + "\"}")
        response = {"ruleText": temp_rule.files.decode('utf-8')}

        return response

    return response


@app.route(rule_prefix_url + 'findTheLatestRuleFileByName')
def get_the_latest_rule_file_by_name():
    ###### ##################       Current
    nadia_rule_name = request.args.get('ruleName')
    return find_rule_text_by_rule_name(nadia_rule_name)


@app.route(rule_prefix_url + 'findTheLatestRuleHistoryByName')
def get_the_latest_rule_history_by_name(nadia_rule_name):
    temp_rule = find_rule_by_rule_name(nadia_rule_name)
    if temp_rule is not None:
        return temp_rule.get_the_latest_history()
    return None


############################################################# Done
@app.route(rule_prefix_url + 'findAllRules')
def get_all_rules():
    response = json.dumps(find_all_rules(), indent=4)
    # response.headers.add('Access-Control-Allow-Origin', '*')
    # return find_all_rules()
    return response
    # return jsonify({'rule_list': rule_list})


@app.route(rule_prefix_url + 'updateRule', methods=['POST'])
def update_rule():

    old_rule_name = request.json['oldRuleName']
    new_rule_name = request.json['newRuleName']
    new_rule_category = request.json['newRuleCategory']
    update_rule_name_and_category(old_rule_name, new_rule_name, new_rule_category)
    rule_from_database = find_rule_by_rule_name(new_rule_name)

    if rule_from_database is not None:
        return jsonify(
            '{"newRuleName":' + rule_from_database.name + ", \"newCategory\": \"" + rule_from_database.category + "\"}")

    return None


@app.route(rule_prefix_url + 'createNewRule', methods=['POST'])
def create_new_rule(new_rule: Rule):
    new_rule_name = new_rule.name
    new_rule_category = new_rule.category
    create_rule(new_rule_category)

    rule_from_database = find_rule_by_rule_name(new_rule_name)
    if rule_from_database is not None:
        return jsonify(
            "{\"ruleName\":\"" + rule_from_database.name + "\", \"category\":\"" + rule_from_database.category + "\"}")

    return None


@app.post(rule_prefix_url + 'createFile')
def create_file():
    # my_request = request.json
    rule_name = request.json['ruleName']
    rule_text = request.json['ruleText']
    rule_text_byte_array = bytearray(rule_text, 'utf-8')

    rule_id = find_id_by_name(rule_name)
    create_rule_file(rule_id, rule_text_byte_array)

    rule_file_from_database = find_rule_text_by_rule_name(rule_name)

    response = jsonify("{}")
    response.headers.add('Access-Control-Allow-Origin', '*')

    if rule_file_from_database is not None:
        return jsonify("{\"ruleText\":\"" + rule_file_from_database.files.decode('utf-8') + "\"}")

    return response


@app.route(rule_prefix_url + 'updateHistory', methods=['POST'])
def update_history():
    inference_engine: InferenceEngine = session.__getattribute__('inferenceEngine')
    working_memory: dict = inference_engine.get_assessment_state().get_working_memory()

    rule_name = request.json['ruleName']
    rule_history: History
    temp_rule = find_rule_by_rule_name(rule_name)

    if temp_rule is not None:
        rule_history = temp_rule.get_the_latest_history()

    parent_temp_history: json = json.loads("{}")

    if rule_history is not None:
        target_history: json = rule_history.history
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

                if len(filtered_dict) > 0:
                    record.set_false_count(int(filtered_dict.get(each_rule_key).get('false')))
                    record.set_true_count(int(filtered_dict.get(each_rule_key).get('true')))
                # if len(filtered_list) > 0:
                #     print(each_rule_key)
                #     record.set_false_count(int(filtered_list[0].get(each_rule_key).get('false')))
                #     record.set_true_count(int(filtered_list[0].get(each_rule_key).get('true')))

                fact_value: FactValue = working_memory[each_rule_key]

                if fact_value.get_value_type() == FactValueType.BOOLEAN:
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
                if str(history_item['type']).lower() != 'boolean':
                    record = HistoryRecord()
                    record.set_name(key)
                    record.set_false_count(int(history_item['false']))
                    record.set_true_count(int(history_item['true']))
                    record.increment_false_count()
                    record_list.append(record)

                else:
                    record = HistoryRecord()
                    record.set_name(key)
                    record.set_false_count(int(history_item['false']))
                    record.set_true_count(int(history_item['true']))
                    record_list.append(record)

        for each_record in record_list:
            temp_history = json.loads("{}")
            temp_history["true"] = str(each_record.get_true_count())
            temp_history["false"] = str(each_record.get_false_count())
            temp_history["type"] = each_record.get_type()

            parent_temp_history[each_record.get_name()] = temp_history
    else:  # case of the rule file has never been used so that there is a no record history.
        for work_item in working_memory.keys():
            fact_value: FactValue = working_memory.get(work_item)
            temp_history: json = json.loads("{}")

            if fact_value.get_value_type() == FactValueType.BOOLEAN:
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

    return json.loads("{\"update\":\"done\"}")


@app.route(inference_prefix_url + 'viewSummary')
def view_summary():
    inference_engine: InferenceEngine = session.__getattribute__('inferenceEngine')
    temp_summary_list = list()
    temp_assessment_state = inference_engine.get_assessment_state()
    temp_working_memory = temp_assessment_state.get_working_memory()
    for summary_item in temp_assessment_state.get_summary_list():
        summary_json = json.loads("{}")
        summary_json['nodeText'] = summary_item
        summary_json['nodeValue'] = str(temp_working_memory.get(summary_item).get_value())
        temp_summary_list.append(summary_json)

    # following lines are to transfer all possible left over value from editing answers process from workingMemory
    # to summary list in GUI

    for each_key in temp_working_memory.keys():
        if each_key not in inference_engine.get_assessment_state().get_summary_list():
            summary_json = json.loads("{}")
            summary_json['nodeText'] = each_key
            if type(temp_working_memory.get(each_key).get_value()) == list:
                fact_list = list()
                for each_fact in temp_working_memory.get(each_key).get_value():
                    fact_list.append(each_fact.get_value())
                summary_json['nodeValue'] = json.dumps(fact_list)
            else:
                summary_json['nodeValue'] = str(temp_working_memory.get(each_key).get_value())

            temp_summary_list.append(summary_json)

    return temp_summary_list


# TODO: this API still needs further work
@app.route(inference_prefix_url + 'editAnswer', methods=['POST'])
def edit_answer(question: json):
    inference_engine: InferenceEngine = session.get('inferenceEngine')
    assessment: Assessment = session.get('assessment')

    question_name = question['question']
    inference_engine.edit_answer(question_name)
    object_node: json = json.loads("{}")
    questions_and_answers: json = json.loads("\"workingMemory\":[]")
    temp_working_memory = inference_engine.get_assessment_state().get_working_memory()
    for each_key in temp_working_memory.keys():
        sub_object_node = json.loads("{}")
        sub_object_node['questionText'] = each_key
        sub_object_node['answer'] = str(temp_working_memory.get(each_key))
        sub_object_node['answerValueType'] = str(temp_working_memory.get(each_key).get_value_type())
        questions_and_answers['workingMemory'].append(sub_object_node)

    if temp_working_memory.get(assessment.get_goal_node().get_node_name()) is None \
            or inference_engine.get_assessment_state().all_mandatory_node_determined() is False:
        object_node['hasMoreQuestion'] = 'true'
    else:
        goal_node_name = assessment.get_goal_node().get_node_name()
        object_node['hasMoreQuestion'] = 'false'
        object_node['goalRuleName'] = goal_node_name
        object_node['goalRuleValue'] = str(temp_working_memory.get(goal_node_name).get_value())
        object_node['goalRuleType'] = \
            str(inference_engine.find_type_of_element_to_be_asked(assessment.get_goal_node()).get(
                goal_node_name)).lower()

    return object_node


@app.route(inference_prefix_url + 'feedAnswer', methods=['POST'])
def feed_answer():
    inference_engine: InferenceEngine = session.__getattribute__('inferenceEngine')
    assessment: Assessment = session.__getattribute__('assessment')

    question_name = request.json['question']
    answer_entry = request.json['answer']

    from project.fact_values import FactValueType
    fact_value_type: FactValueType = FactValueType[str(answer_entry['type']).upper()]

    if assessment.get_node_to_be_asked().get_line_type() == LineType.ITERATE:
        inference_engine.feed_answer_to_node(assessment.get_aux_node_to_be_asked(), question_name,
                                             str(answer_entry['answer']), fact_value_type,
                                             assessment)
    else:
        inference_engine.feed_answer_to_node(assessment.get_node_to_be_asked(), question_name,
                                             str(answer_entry['answer']), fact_value_type,
                                             assessment)

    object_node = json.loads("{}")
    if inference_engine.get_assessment_state().get_working_memory().get(
            assessment.get_goal_node().get_node_name()) is None \
            or inference_engine.get_assessment_state().all_mandatory_node_determined() is not True:
        object_node['hasMoreQuestion'] = 'true'
    else:
        goal_node_name: str = assessment.get_goal_node().get_node_name()
        object_node['hasMoreQuestion'] = 'false'
        object_node['goalRuleName'] = goal_node_name
        object_node['goalRuleValue'] = str(
            inference_engine.get_assessment_state().get_working_memory().get(goal_node_name).get_value())
        object_node['goalRuleType'] = str(
            inference_engine.find_type_of_element_to_be_asked(assessment.get_goal_node()).get(
                goal_node_name).value).lower()

    return object_node


@app.route(inference_prefix_url + 'getNextQuestion')
def get_next_question():
    nadia_rule_name = request.args.get('targetRuleName')
    # nadia_rule_name = request.args.get('ruleName')
    inference_engine: InferenceEngine = session.__getattribute__('inferenceEngine')
    if inference_engine is None or inference_engine.get_node_set().get_node_set_name() != nadia_rule_name:
        set_inference_engine()

    inference_engine: InferenceEngine = session.__getattribute__('inferenceEngine')
    assessment: Assessment = session.__getattribute__('assessment')
    next_question_node = inference_engine.get_next_question(assessment)
    if assessment.get_node_to_be_asked().get_line_type() == LineType.ITERATE:
        assessment.set_aux_node_to_be_asked(next_question_node)

    question_fact_value_type_dict: dict = inference_engine.find_type_of_element_to_be_asked(next_question_node)
    questionnaire: list = inference_engine.get_questions_from_node_to_be_asked(next_question_node)
    questionnaire_list = list()
    for question in questionnaire:
        object_node = json.loads("{}")
        object_node['questionText'] = question
        object_node['questionValueType'] = str(question_fact_value_type_dict.get(question).value).lower()

        questionnaire_list.append(object_node)

    return questionnaire_list


@app.route(inference_prefix_url + 'setInferenceEngine')
def set_inference_engine():
    nadia_rule_name = request.args.get('ruleName')
    rule_text: str = str(find_rule_text_by_rule_name(nadia_rule_name).files, 'utf-8')
    rule_set_reader = RuleSetReader()
    rule_set_parser = RuleSetParser()
    rule_set_reader.set_file_with_text(rule_text)
    rule_set_scanner = RuleSetScanner(rule_set_reader, rule_set_parser)
    rule_set_scanner.scan_rule_set()
    rule_set_scanner.establish_node_set()
    inference_engine = InferenceEngine(rule_set_parser.get_node_set())

    # inference_engine.set_node_set(rule_set_parser.get_node_set())
    inference_engine.get_node_set().set_node_set_name(nadia_rule_name)
    assessment = Assessment(rule_set_parser.get_node_set(),
                            rule_set_parser.get_node_set().get_sorted_node_list()[0].get_node_name())
    inference_engine.set_assessment(assessment)

    session.__setattr__('inferenceEngine', inference_engine)
    session.__setattr__('assessment', assessment)
    object_node = json.loads("{}")
    object_node['InferenceEngine'] = 'created'

    return jsonify(object_node)


@app.route(inference_prefix_url + "setMachineLearningInferenceEngine")
def set_machine_learning_inference_engine():
    nadia_rule_name = request.args.get('ruleName')
    rule_text: str = str(find_rule_text_by_rule_name(nadia_rule_name).files, 'utf-8')
    rule_set_reader = RuleSetReader()
    rule_set_parser = RuleSetParser()

    rule_set_reader.set_file_with_text(rule_text)
    rule_set_scanner = RuleSetScanner(rule_set_reader, rule_set_parser)
    rule_set_scanner.scan_rule_set()

    temp_rule = find_rule_by_rule_name(nadia_rule_name)
    rule_history: History = None
    if temp_rule is not None:
        rule_history = temp_rule.get_the_latest_history()

    history_dict = dict()
    if rule_history is not None:
        history_dict = rule_history.history
    else:
        history_dict = None

    rule_set_scanner.establish_node_set(history_dict)
    inference_engine = InferenceEngine(rule_set_parser.get_node_set())
    inference_engine.get_node_set().set_node_set_name(nadia_rule_name)

    assessment = Assessment(rule_set_parser.get_node_set(),
                            rule_set_parser.get_node_set().get_sorted_node_list()[0].get_node_name())
    inference_engine.set_assessment(assessment)

    session.__setattr__('inferenceEngine', inference_engine)
    session.__setattr__('assessment', assessment)

    object_node = json.loads("{}")
    object_node['InferenceEngine'] = 'created'

    return object_node


if __name__ == '__main__':
    app.run()
