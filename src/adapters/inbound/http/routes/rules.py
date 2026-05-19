from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from src.adapters.inbound.http.dependencies import get_db_session
from src.adapters.inbound.http.schemas.rules import (
    CreateRuleFileRequest,
    CreateRuleRequest,
    LatestRuleFileResponse,
    LatestRuleHistoryResponse,
    RuleCreatedResponse,
    RuleSetCreateRequest,
    RuleSetDetailResponse,
    RuleSetSummaryResponse,
    RuleSetVersionCreateRequest,
    RuleSetVersionResponse,
    RuleSummaryResponse,
    RuleTextResponse,
    RuleTreeDataResponse,
    SaveConvertedRuleRequest,
    UpdateRuleRequest,
    UpdateRuleResponse,
)
from src.adapters.outbound.persistence.rule_repository import RuleRepositoryImpl
from src.infrastructure.logging_config import get_logger
from src.services.rule_service import RuleService


legacy_router = APIRouter(prefix="/service/rule", tags=["rules"])
modern_router = APIRouter(prefix="/api/v1/rules", tags=["rules"])
logger = get_logger("inferra.fastapi.rules")


def _service(db: Session) -> RuleService:
    return RuleService(RuleRepositoryImpl(db))


def _to_modern_summary(rule) -> RuleSetSummaryResponse:
    if isinstance(rule, dict):
        return RuleSetSummaryResponse(
            rule_id=rule.get("rule_id"),
            rule_name=rule.get("name") or "",
            category=rule.get("category"),
            description=rule.get("description"),
        )
    return RuleSetSummaryResponse(
        rule_id=rule.rule_id,
        rule_name=rule.name or "",
        category=rule.category,
        description=rule.description,
    )


def _to_modern_detail(service: RuleService, rule_name: str) -> RuleSetDetailResponse:
    rule = service.get_rule_by_name(rule_name)
    latest_file = service.get_latest_rule_file(rule_name)
    return RuleSetDetailResponse(
        rule_id=rule.rule_id,
        rule_name=rule.name or "",
        category=rule.category,
        description=rule.description,
        rule_text=service.decode_rule_file(latest_file),
        latest_file_id=latest_file.file_id,
    )


@modern_router.get("", response_model=list[RuleSetSummaryResponse])
async def list_rule_sets(db: Session = Depends(get_db_session)) -> list[RuleSetSummaryResponse]:
    return [_to_modern_summary(rule) for rule in _service(db).list_rules()]


@modern_router.post(
    "",
    response_model=RuleSetDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_rule_set(
    payload: RuleSetCreateRequest,
    db: Session = Depends(get_db_session),
) -> RuleSetDetailResponse:
    service = _service(db)
    service.save_converted_rule(
        payload.rule_name,
        payload.category,
        payload.description,
        payload.rule_text,
        waived_error_ids=payload.waived_error_ids,
    )
    return _to_modern_detail(service, payload.rule_name)


@modern_router.get("/{rule_name}", response_model=RuleSetDetailResponse)
async def get_rule_set(
    rule_name: str,
    db: Session = Depends(get_db_session),
) -> RuleSetDetailResponse:
    return _to_modern_detail(_service(db), rule_name)


@modern_router.post(
    "/{rule_name}/versions",
    response_model=RuleSetVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_rule_set_version(
    rule_name: str,
    payload: RuleSetVersionCreateRequest,
    db: Session = Depends(get_db_session),
) -> RuleSetVersionResponse:
    service = _service(db)
    rule_text = service.create_rule_file(
        rule_name,
        payload.rule_text,
        waived_error_ids=payload.waived_error_ids,
    )
    latest_file = service.get_latest_rule_file(rule_name)
    return RuleSetVersionResponse(
        rule_name=rule_name,
        rule_text=rule_text,
        latest_file_id=latest_file.file_id,
    )


@modern_router.get("/{rule_name}/targets", response_model=list[str])
async def list_rule_set_targets(
    rule_name: str,
    db: Session = Depends(get_db_session),
) -> list[str]:
    return _service(db).get_target_node_names(rule_name)


@legacy_router.get("/searchRuleByName", response_model=RuleSummaryResponse)
async def search_rule_by_name(
    rule_name: str = Query(..., alias="ruleName"),
    db: Session = Depends(get_db_session),
) -> RuleSummaryResponse:
    rule = _service(db).get_rule_by_name(rule_name)
    return RuleSummaryResponse.model_validate(rule.__dict__)


@legacy_router.get("/findRuleTreeDataByName", response_model=RuleTreeDataResponse)
async def find_rule_tree_data_by_name(
    rule_name: str = Query(..., alias="ruleName"),
    db: Session = Depends(get_db_session),
) -> RuleTreeDataResponse:
    logger.info("fetching_rule_tree_data", rule_name=rule_name)
    return RuleTreeDataResponse(ruleTreeData=_service(db).get_rule_tree_data(rule_name))


@legacy_router.get("/findRuleTextByName", response_model=RuleTextResponse)
async def find_rule_text_by_name(
    rule_name: str = Query(..., alias="ruleName"),
    db: Session = Depends(get_db_session),
) -> RuleTextResponse:
    logger.info("fetching_rule_text", rule_name=rule_name)
    return RuleTextResponse(ruleText=_service(db).get_rule_text(rule_name))


@legacy_router.get("/findTheLatestRuleFileByName", response_model=LatestRuleFileResponse)
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


@legacy_router.get("/findTheLatestRuleHistoryByName", response_model=LatestRuleHistoryResponse)
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


@legacy_router.get("/findAllRules", response_model=list[RuleSummaryResponse])
async def find_all_rules(db: Session = Depends(get_db_session)) -> list[RuleSummaryResponse]:
    return [RuleSummaryResponse.model_validate(rule) for rule in _service(db).list_rules()]


@legacy_router.post("/updateRule", response_model=UpdateRuleResponse)
async def update_rule(payload: UpdateRuleRequest, db: Session = Depends(get_db_session)) -> UpdateRuleResponse:
    rule = _service(db).update_rule(
        payload.oldRuleName,
        payload.newRuleName,
        payload.newRuleCategory,
    )
    return UpdateRuleResponse(newRuleName=rule.name, newCategory=rule.category)


@legacy_router.post("/createNewRule", response_model=RuleCreatedResponse)
async def create_new_rule(payload: CreateRuleRequest, db: Session = Depends(get_db_session)) -> RuleCreatedResponse:
    rule = _service(db).create_rule(payload.name, payload.category, payload.description)
    return RuleCreatedResponse(
        ruleName=rule.name,
        category=rule.category,
        description=rule.description,
    )


@legacy_router.post("/saveConvertedRule", response_model=RuleCreatedResponse)
async def save_converted_rule(
    payload: SaveConvertedRuleRequest,
    db: Session = Depends(get_db_session),
) -> RuleCreatedResponse:
    rule = _service(db).save_converted_rule(
        payload.name,
        payload.category,
        payload.description,
        payload.ruleText,
        waived_error_ids=payload.waived_error_ids,
    )
    return RuleCreatedResponse(
        ruleName=rule.name,
        category=rule.category,
        description=rule.description,
    )


@legacy_router.post("/createFile", response_model=RuleTextResponse)
async def create_file(payload: CreateRuleFileRequest, db: Session = Depends(get_db_session)) -> RuleTextResponse:
    return RuleTextResponse(
        ruleText=_service(db).create_rule_file(
            payload.ruleName,
            payload.ruleText,
            waived_error_ids=payload.waived_error_ids,
        )
    )


@legacy_router.get("/targetNodeNameList", response_model=list[str])
async def target_node_name_list(
    rule_name: str = Query(..., alias="ruleName"),
    db: Session = Depends(get_db_session),
) -> list[str]:
    return _service(db).get_target_node_names(rule_name)


router = APIRouter()
router.include_router(modern_router)
router.include_router(legacy_router)
