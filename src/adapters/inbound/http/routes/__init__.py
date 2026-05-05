from fastapi import APIRouter

from src.adapters.inbound.http.routes.files import router as files_router
from src.adapters.inbound.http.routes.inference import router as inference_router
from src.adapters.inbound.http.routes.metrics import router as metrics_router
from src.adapters.inbound.http.routes.reasoning import router as reasoning_router
from src.adapters.inbound.http.routes.rules import router as rules_router
from src.adapters.inbound.http.routes.sync_imports import router as sync_imports_router
from src.adapters.inbound.http.routes.system import router as system_router
from src.adapters.inbound.http.routes.validation import router as validation_router


api_router = APIRouter()
api_router.include_router(system_router)
api_router.include_router(rules_router)
api_router.include_router(validation_router)
api_router.include_router(inference_router)
api_router.include_router(files_router)
api_router.include_router(metrics_router)
api_router.include_router(sync_imports_router)
api_router.include_router(reasoning_router)

__all__ = ["api_router"]
