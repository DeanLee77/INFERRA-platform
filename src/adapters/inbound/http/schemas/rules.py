from typing import Any, Optional

from pydantic import BaseModel, Field


class RuleSummaryResponse(BaseModel):
    rule_id: int | None = None
    name: str | None = None
    category: str | None = None
    description: str | None = None


class RuleTextResponse(BaseModel):
    ruleText: str


class RuleTreeDataResponse(BaseModel):
    ruleTreeData: str


class UpdateRuleRequest(BaseModel):
    oldRuleName: str
    newRuleName: str
    newRuleCategory: str


class UpdateRuleResponse(BaseModel):
    newRuleName: str | None = None
    newCategory: str | None = None


class CreateRuleRequest(BaseModel):
    name: str
    category: str
    description: str


class SaveConvertedRuleRequest(CreateRuleRequest):
    ruleText: str
    waived_error_ids: Optional[list[str]] = None


class RuleCreatedResponse(BaseModel):
    ruleName: str | None = None
    category: str | None = None
    description: str | None = None


class CreateRuleFileRequest(BaseModel):
    ruleName: str
    ruleText: str
    waived_error_ids: Optional[list[str]] = None


class LatestRuleFileResponse(BaseModel):
    fileId: int | None = None
    ruleId: int | None = None
    ruleText: str


class LatestRuleHistoryResponse(BaseModel):
    ruleId: int | None = None
    ruleName: str | None = None
    history: dict[str, Any]


class RuleSetCreateRequest(BaseModel):
    rule_name: str = Field(..., min_length=1, max_length=255)
    category: str = Field("", max_length=255)
    description: str = Field("", max_length=2000)
    rule_text: str = Field(..., min_length=1, max_length=1_000_000)
    waived_error_ids: Optional[list[str]] = None


class RuleSetVersionCreateRequest(BaseModel):
    rule_text: str = Field(..., min_length=1, max_length=1_000_000)
    waived_error_ids: Optional[list[str]] = None


class RuleSetSummaryResponse(BaseModel):
    rule_id: int | None = None
    rule_name: str
    category: str | None = None
    description: str | None = None


class RuleSetDetailResponse(RuleSetSummaryResponse):
    rule_text: str
    latest_file_id: int | None = None


class RuleSetVersionResponse(BaseModel):
    rule_name: str
    rule_text: str
    latest_file_id: int | None = None
