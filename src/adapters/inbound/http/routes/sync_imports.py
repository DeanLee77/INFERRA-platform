"""
Sync & Import API Router.

Phase 2 endpoints for async pipeline observability and modular
import resolution:
- GET /api/v1/sync/status — Celery task status for a rule
- GET /api/v1/rules/{rule_name}/imports — Import tree for a rule
- GET /api/v1/rules/{rule_name}/validate — Import-aware rule validation
"""

import hashlib
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import structlog

from src.domain.imports.import_matchers import extract_imports
from src.domain.imports.import_resolver import (
    CircularImportError,
    ImportDepthExceededError,
    RuleSetImportResolver,
)
from src.domain.state.feature_flags import FeatureFlags
from src.services.rule_validation_service import RuleValidationService
from src.tasks.rule_sync import _inflight_tasks

router = APIRouter(prefix="/api/v1", tags=["sync", "imports"])
log = structlog.get_logger("inferra.fastapi.sync_imports")


class SyncStatusResponse(BaseModel):
    rule_name: str
    status: str = Field(description="pending | completed | failed | unknown")
    source_hash: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


class ImportEntry(BaseModel):
    name: str
    content_hash: str
    node_count: int
    depth: int
    direct_imports: List[str] = Field(default_factory=list)


class ImportTreeResponse(BaseModel):
    rule_name: str
    imports: List[ImportEntry]
    has_cycles: bool
    total_count: int
    offset: int
    limit: int


class ValidationDetail(BaseModel):
    code: str
    message: str
    location: Optional[str] = None


class RuleValidateWithImportsResponse(BaseModel):
    valid: bool
    errors: List[ValidationDetail]
    warnings: List[ValidationDetail]


def _get_rule_text(rule_name: str) -> str:
    from src.services.rule_service import RuleService
    from src.adapters.outbound.persistence.rule_repository import RuleRepositoryImpl
    from src.adapters.inbound.http.dependencies import get_db_session

    db = next(get_db_session(), None)
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        service = RuleService(RuleRepositoryImpl(db))
        return service.get_rule_text(rule_name)
    except LookupError:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_name}' does not exist")
    finally:
        db.close()


def _count_source_nodes(rule_text: str) -> int:
    count = 0
    ignored_prefixes = ("#", "//", "IMPORT:", "RULE SET:")
    for raw_line in rule_text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith(ignored_prefixes):
            continue
        count += 1
    return count


def _count_rule_text_nodes(rule_name: str, rule_text: str) -> int:
    try:
        from src.domain.rule_parser.rule_set_parser import RuleSetParser
        from src.domain.rule_parser.rule_set_reader import RuleSetReader
        from src.domain.rule_parser.rule_set_scanner import RuleSetScanner

        reader = RuleSetReader()
        reader.create()
        parser = RuleSetParser()
        parser.create()
        parser.set_source_name(rule_name)
        reader.set_file_with_text(rule_text)
        scanner = RuleSetScanner(reader, parser)
        scanner.scan_rule_set()
        scanner.establish_node_set()
        node_set = parser.get_node_set()

        node_dictionary = getattr(node_set, "get_node_dictionary", lambda: {})()
        if hasattr(node_dictionary, "__len__") and len(node_dictionary) > 0:
            return len(node_dictionary)

        sorted_nodes = getattr(node_set, "get_sorted_node_list", lambda: [])()
        if hasattr(sorted_nodes, "__len__") and len(sorted_nodes) > 0:
            return len(sorted_nodes)
    except Exception as exc:
        log.debug("import_node_count_parse_failed", rule_name=rule_name, error=str(exc))

    return _count_source_nodes(rule_text)


def _build_import_entry(module_name: str, origin) -> ImportEntry:
    module_text = _get_rule_text(module_name)
    return ImportEntry(
        name=module_name,
        content_hash=hashlib.sha256(module_text.encode()).hexdigest()[:16],
        node_count=_count_rule_text_nodes(module_name, module_text),
        depth=origin.depth,
        direct_imports=extract_imports(module_text),
    )


@router.get("/sync/status", response_model=SyncStatusResponse)
async def get_sync_status(rule_name: str = Query(..., description="Rule name to check")) -> SyncStatusResponse:
    if not FeatureFlags().async_sync_enabled:
        return SyncStatusResponse(rule_name=rule_name, status="disabled")

    try:
        from celery.result import AsyncResult
    except ImportError:
        return SyncStatusResponse(rule_name=rule_name, status="unknown")

    matching = {sh: tid for sh, tid in _inflight_tasks.items()}
    task_id = None
    for source_hash, tid in matching.items():
        try:
            result = AsyncResult(tid)
            if result.status in ("PENDING", "STARTED", "RETRY"):
                task_id = tid
                break
        except Exception:
            continue

    if task_id is None:
        try:
            rule_text = _get_rule_text(rule_name)
            source_hash = hashlib.sha256(rule_text.encode()).hexdigest()
            if source_hash in _inflight_tasks:
                task_id = _inflight_tasks[source_hash]
        except Exception as exc:
            log.debug("sync_status_rule_lookup_skipped", rule_name=rule_name, error=str(exc))
            pass

    if task_id is None:
        return SyncStatusResponse(rule_name=rule_name, status="unknown")

    try:
        result = AsyncResult(task_id)
        status_map = {
            "PENDING": "pending",
            "STARTED": "pending",
            "RETRY": "pending",
            "SUCCESS": "completed",
            "FAILURE": "failed",
        }
        mapped = status_map.get(result.status, "unknown")
        response = SyncStatusResponse(
            rule_name=rule_name,
            status=mapped,
            source_hash=None,
        )
        if mapped == "completed" and result.result:
            data = result.result if isinstance(result.result, dict) else {}
            response.source_hash = data.get("hash")
        elif mapped == "failed" and result.result:
            response.error = str(result.result)
        return response
    except Exception as exc:
        log.warning("sync_status_check_failed", rule_name=rule_name, error=str(exc))
        return SyncStatusResponse(rule_name=rule_name, status="unknown")


@router.get("/rules/{rule_name}/imports", response_model=ImportTreeResponse)
async def get_rule_imports(
    rule_name: str,
    depth: Optional[int] = Query(None, description="Max import depth to traverse"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> ImportTreeResponse:
    try:
        rule_text = _get_rule_text(rule_name)
    except HTTPException:
        raise

    # Import preview is a read-only analysis path and must match the
    # import-aware save/execution path even when MODULAR_IMPORTS is not set
    # in the container environment.
    flags = FeatureFlags(modular_imports=True)
    if not flags.modular_imports:
        return ImportTreeResponse(
            rule_name=rule_name,
            imports=[],
            has_cycles=False,
            total_count=0,
            offset=offset,
            limit=limit,
        )

    resolver = RuleSetImportResolver(
        rule_loader=_get_rule_text,
        feature_flags=flags,
    )

    has_cycles = False
    resolved: dict = {}
    try:
        resolved = resolver.resolve(rule_name)
    except CircularImportError as e:
        has_cycles = True
        log.warning("circular_import_detected", rule_name=rule_name, chain=e.import_chain)
    except ImportDepthExceededError:
        raise HTTPException(
            status_code=422,
            detail=f"Import depth exceeded for rule '{rule_name}'",
        )

    entries: List[ImportEntry] = []
    for mod_name, origin in resolved.items():
        if mod_name == rule_name:
            continue
        entries.append(_build_import_entry(mod_name, origin))

    if depth is not None:
        entries = [e for e in entries if e.depth <= depth]

    total_count = len(entries)
    paged = entries[offset : offset + limit]

    return ImportTreeResponse(
        rule_name=rule_name,
        imports=paged,
        has_cycles=has_cycles,
        total_count=total_count,
        offset=offset,
        limit=limit,
    )


@router.get("/rules/{rule_name}/validate", response_model=RuleValidateWithImportsResponse)
async def validate_rule_with_imports(rule_name: str) -> RuleValidateWithImportsResponse:
    try:
        rule_text = _get_rule_text(rule_name)
    except HTTPException:
        raise

    service = RuleValidationService()
    result = service.validate(rule_text=rule_text, rule_name=rule_name)

    errors = [
        ValidationDetail(code=e.code, message=e.message, location=f"line {e.line}" if e.line else None)
        for e in result.errors
    ]
    warnings = [
        ValidationDetail(code=w.code, message=w.message, location=f"line {w.line}" if w.line else None)
        for w in result.warnings
    ]

    flags = FeatureFlags(modular_imports=True)
    if flags.modular_imports:
        resolver = RuleSetImportResolver(
            rule_loader=_get_rule_text,
            feature_flags=flags,
        )
        try:
            resolver.resolve(rule_name)
        except CircularImportError as e:
            chain_str = " → ".join(e.import_chain)
            errors.append(
                ValidationDetail(
                    code="CIRCULAR_IMPORT",
                    message=f"Cycle detected: {chain_str}",
                )
            )
        except ImportDepthExceededError as e:
            errors.append(
                ValidationDetail(
                    code="IMPORT_DEPTH_EXCEEDED",
                    message=str(e),
                )
            )

    return RuleValidateWithImportsResponse(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )
