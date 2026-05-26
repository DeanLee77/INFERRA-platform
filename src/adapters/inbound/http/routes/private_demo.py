from fastapi import APIRouter, HTTPException, Query

from src.domain.demo import build_decision_receipt, build_fixture_manifest


router = APIRouter(tags=["private-demo"])


@router.get("/service/rule/syntheticDecisionReceiptFixture")
async def get_synthetic_decision_receipt_fixture() -> dict:
    return build_fixture_manifest()


@router.get("/service/inference/syntheticDecisionReceipt")
async def get_synthetic_decision_receipt(
    case_id: str = Query("certify-ready", alias="caseId"),
) -> dict:
    try:
        return build_decision_receipt(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
