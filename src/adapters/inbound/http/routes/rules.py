import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.adapters.inbound.http.dependencies import get_db_session
from src.adapters.inbound.http.schemas.rules import (
    CreateRuleFileRequest,
    CreateRuleRequest,
    LatestRuleFileResponse,
    LatestRuleHistoryResponse,
    RuleCreatedResponse,
    RuleSummaryResponse,
    RuleTextResponse,
    RuleTreeDataResponse,
    SaveConvertedRuleRequest,
    UpdateRuleRequest,
    UpdateRuleResponse,
)
from src.adapters.outbound.persistence.rule_repository import RuleRepositoryImpl
from src.services.rule_service import RuleService


router = APIRouter(prefix="/service/rule", tags=["rules"])
logger = logging.getLogger("inferra.fastapi.rules")


def _service(db: Session) -> RuleService:
    return RuleService(RuleRepositoryImpl(db))


@router.get("/searchRuleByName", response_model=RuleSummaryResponse)
async def search_rule_by_name(
    rule_name: str = Query(..., alias="ruleName"),
    db: Session = Depends(get_db_session),
) -> RuleSummaryResponse:
    rule = _service(db).get_rule_by_name(rule_name)
    return RuleSummaryResponse.model_validate(rule.__dict__)


@router.get("/findRuleTreeDataByName", response_model=RuleTreeDataResponse)
async def find_rule_tree_data_by_name(
    rule_name: str = Query(..., alias="ruleName"),
    db: Session = Depends(get_db_session),
) -> RuleTreeDataResponse:
    logger.info("Fetching rule tree data for %s", rule_name)
    return RuleTreeDataResponse(ruleTreeData=_service(db).get_rule_tree_data(rule_name))


@router.get("/findRuleTextByName", response_model=RuleTextResponse)
async def find_rule_text_by_name(
    rule_name: str = Query(..., alias="ruleName"),
    db: Session = Depends(get_db_session),
) -> RuleTextResponse:
    logger.info("Fetching rule text for %s", rule_name)
    return RuleTextResponse(ruleText=_service(db).get_rule_text(rule_name))


@router.get("/findTheLatestRuleFileByName", response_model=LatestRuleFileResponse)
async def find_the_latest_rule_file_by_name(
    rule_name: str = Query(..., alias="ruleName"),
    db: Session = Depends(get_db_session),
) -> LatestRuleFileResponse:
    service = _service(db)
    rule_file = service.get_latest_rule_file(rule_name)
    return LatestRuleFileResponse(
        fileId=rule_file.file_id,
        ruleId=rule_file.rule_id,
        ruleText=service.decode_rule_file(rule_file),
    )


@router.get("/findTheLatestRuleHistoryByName", response_model=LatestRuleHistoryResponse)
async def find_the_latest_rule_history_by_name(
    rule_name: str = Query(..., alias="ruleName"),
    db: Session = Depends(get_db_session),
) -> LatestRuleHistoryResponse:
    result = _service(db).get_latest_rule_history(rule_name)
    history = result["history"]
    rule = result["rule"]
    return LatestRuleHistoryResponse(
        ruleId=rule.rule_id,
        ruleName=rule.name,
        history=history,
    )


@router.get("/findAllRules", response_model=list[RuleSummaryResponse])
async def find_all_rules(db: Session = Depends(get_db_session)) -> list[RuleSummaryResponse]:
    return [RuleSummaryResponse.model_validate(rule) for rule in _service(db).list_rules()]


@router.post("/updateRule", response_model=UpdateRuleResponse)
async def update_rule(payload: UpdateRuleRequest, db: Session = Depends(get_db_session)) -> UpdateRuleResponse:
    rule = _service(db).update_rule(
        payload.oldRuleName,
        payload.newRuleName,
        payload.newRuleCategory,
    )
    return UpdateRuleResponse(newRuleName=rule.name, newCategory=rule.category)


@router.post("/createNewRule", response_model=RuleCreatedResponse)
async def create_new_rule(payload: CreateRuleRequest, db: Session = Depends(get_db_session)) -> RuleCreatedResponse:
    rule = _service(db).create_rule(payload.name, payload.category, payload.description)
    return RuleCreatedResponse(
        ruleName=rule.name,
        category=rule.category,
        description=rule.description,
    )


@router.post("/saveConvertedRule", response_model=RuleCreatedResponse)
async def save_converted_rule(
    payload: SaveConvertedRuleRequest,
    db: Session = Depends(get_db_session),
) -> RuleCreatedResponse:
    rule = _service(db).save_converted_rule(
        payload.name,
        payload.category,
        payload.description,
        payload.ruleText,
    )
    return RuleCreatedResponse(
        ruleName=rule.name,
        category=rule.category,
        description=rule.description,
    )


@router.post("/createFile", response_model=RuleTextResponse)
async def create_file(payload: CreateRuleFileRequest, db: Session = Depends(get_db_session)) -> RuleTextResponse:
    return RuleTextResponse(ruleText=_service(db).create_rule_file(payload.ruleName, payload.ruleText))


@router.get("/targetNodeNameList", response_model=list[str])
async def target_node_name_list(
    rule_name: str = Query(..., alias="ruleName"),
    db: Session = Depends(get_db_session),
) -> list[str]:
    return _service(db).get_target_node_names(rule_name)
