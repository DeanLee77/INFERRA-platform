from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from src.domain.demo import (
    build_decision_receipt,
    build_fixture_manifest,
    build_reasoning_run_review_fixture,
    build_reasoning_run_review_run,
)


rule_router = APIRouter(prefix="/service/rule", tags=["private-demo"])
inference_router = APIRouter(prefix="/service/inference", tags=["private-demo"])


@rule_router.get("/syntheticDecisionReceiptFixture")
async def get_synthetic_decision_receipt_fixture() -> dict:
    return build_fixture_manifest()


@inference_router.get("/syntheticDecisionReceipt", response_model=None)
async def get_synthetic_decision_receipt(
    case_id: str = Query("certify-ready", alias="caseId"),
):
    try:
        return build_decision_receipt(case_id)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


@inference_router.get("/reasoningRunReviewFixture", response_model=None)
async def get_reasoning_run_review_fixture() -> dict:
    return build_reasoning_run_review_fixture()


@inference_router.get("/reasoningRunReviewRun", response_model=None)
async def get_reasoning_run_review_run(
    result_state: str = Query("success", alias="resultState"),
):
    try:
        return build_reasoning_run_review_run(result_state)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


router = APIRouter()
router.include_router(rule_router)
router.include_router(inference_router)
