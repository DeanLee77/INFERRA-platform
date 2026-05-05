from typing import Any

from pydantic import BaseModel


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


class RuleCreatedResponse(BaseModel):
    ruleName: str | None = None
    category: str | None = None
    description: str | None = None


class CreateRuleFileRequest(BaseModel):
    ruleName: str
    ruleText: str


class LatestRuleFileResponse(BaseModel):
    fileId: int | None = None
    ruleId: int | None = None
    ruleText: str


class LatestRuleHistoryResponse(BaseModel):
    ruleId: int | None = None
    ruleName: str | None = None
    history: dict[str, Any]
