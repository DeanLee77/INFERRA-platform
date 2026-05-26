from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from src.domain.demo import build_decision_receipt, build_fixture_manifest


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


router = APIRouter()
router.include_router(rule_router)
router.include_router(inference_router)
