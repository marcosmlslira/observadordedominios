"""Free tools API — DNS, WHOIS, SSL, Screenshot, and more."""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_admin
from app.infra.external.s3_storage import S3Storage
from app.infra.db.session import get_db
from app.repositories.tool_execution_repository import ToolExecutionRepository
from app.schemas.tools import (
    HistoryItem,
    HistoryListResponse,
    QuickAnalysisRequest,
    QuickAnalysisResponse,
    QuickAnalysisToolResult,
    ToolRequest,
    ToolResponse,
    ToolType,
    WebsiteCloneRequest,
)
from app.services.use_cases.tools.base import BaseToolService, RateLimitExceeded

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/tools",
    tags=["Tools"],
    dependencies=[Depends(get_current_admin)],
)

public_router = APIRouter(
    prefix="/v1/tools",
    tags=["Tools"],
)

# ── Placeholder org ID (until multi-tenancy) ─────────────

PLACEHOLDER_ORG_ID = uuid.UUID(settings.TOOLS_PLACEHOLDER_ORG_ID)


# ── Tool registry ────────────────────────────────────────

_tool_services: dict[str, BaseToolService] = {}


def register_tool(service: BaseToolService) -> None:
    _tool_services[service.tool_type] = service


def get_tool_service(tool_type: str) -> BaseToolService:
    service = _tool_services.get(tool_type)
    if not service:
        raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_type}")
    return service


# ── Individual tool endpoints ─────────────────────────────

def _run_tool(
    tool_type: str,
    body: ToolRequest,
    db: Session,
    force: bool = False,
) -> ToolResponse:
    service = get_tool_service(tool_type)
    try:
        return service.run(
            db,
            PLACEHOLDER_ORG_ID,
            body.target,
            force=force,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.post("/dns-lookup", response_model=ToolResponse, summary="DNS Lookup")
def dns_lookup(body: ToolRequest, force: bool = Query(False), db: Session = Depends(get_db)):
    result = _run_tool("dns_lookup", body, db, force)
    db.commit()
    return result


@router.post("/whois", response_model=ToolResponse, summary="WHOIS Lookup")
def whois_lookup(body: ToolRequest, force: bool = Query(False), db: Session = Depends(get_db)):
    result = _run_tool("whois", body, db, force)
    db.commit()
    return result


@router.post("/ssl-check", response_model=ToolResponse, summary="SSL Certificate Check")
def ssl_check(body: ToolRequest, force: bool = Query(False), db: Session = Depends(get_db)):
    result = _run_tool("ssl_check", body, db, force)
    db.commit()
    return result


@router.post("/http-headers", response_model=ToolResponse, summary="HTTP Headers Analysis")
def http_headers(body: ToolRequest, force: bool = Query(False), db: Session = Depends(get_db)):
    result = _run_tool("http_headers", body, db, force)
    db.commit()
    return result


@router.post("/screenshot", response_model=ToolResponse, summary="Website Screenshot")
def screenshot(body: ToolRequest, force: bool = Query(False), db: Session = Depends(get_db)):
    result = _run_tool("screenshot", body, db, force)
    db.commit()
    return result


@router.post("/suspicious-page", response_model=ToolResponse, summary="Suspicious Page Detector")
def suspicious_page(body: ToolRequest, force: bool = Query(False), db: Session = Depends(get_db)):
    result = _run_tool("suspicious_page", body, db, force)
    db.commit()
    return result


@router.post("/blacklist-check", response_model=ToolResponse, summary="Blacklist Check")
def blacklist_check(body: ToolRequest, force: bool = Query(False), db: Session = Depends(get_db)):
    result = _run_tool("blacklist_check", body, db, force)
    db.commit()
    return result


@router.post("/email-security", response_model=ToolResponse, summary="Email Security Check")
def email_security(body: ToolRequest, force: bool = Query(False), db: Session = Depends(get_db)):
    result = _run_tool("email_security", body, db, force)
    db.commit()
    return result


@router.post("/reverse-ip", response_model=ToolResponse, summary="Reverse IP Lookup")
def reverse_ip(body: ToolRequest, force: bool = Query(False), db: Session = Depends(get_db)):
    result = _run_tool("reverse_ip", body, db, force)
    db.commit()
    return result


@router.post("/ip-geolocation", response_model=ToolResponse, summary="IP Geolocation")
def ip_geolocation(body: ToolRequest, force: bool = Query(False), db: Session = Depends(get_db)):
    result = _run_tool("ip_geolocation", body, db, force)
    db.commit()
    return result


@router.post("/domain-similarity", response_model=ToolResponse, summary="Domain Similarity Generator")
def domain_similarity(body: ToolRequest, force: bool = Query(False), db: Session = Depends(get_db)):
    result = _run_tool("domain_similarity", body, db, force)
    db.commit()
    return result


@router.post("/website-clone", response_model=ToolResponse, summary="Website Clone Detector")
def website_clone(body: WebsiteCloneRequest, force: bool = Query(False), db: Session = Depends(get_db)):
    try:
        target = body.build_execution_target()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = _run_tool("website_clone", ToolRequest(target=target), db, force)
    db.commit()
    return result


@public_router.get("/screenshots/{object_path:path}", include_in_schema=False)
def get_screenshot(object_path: str):
    object_key = f"tools/screenshots/{object_path.lstrip('/')}"
    storage = S3Storage()
    storage.bucket = settings.TOOLS_S3_BUCKET

    try:
        body, content_type = storage.download_object(object_key)
    except Exception as exc:  # pragma: no cover - exercised in production path
        raise HTTPException(status_code=404, detail="Screenshot not found") from exc

    return Response(
        content=body,
        media_type=content_type or "image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# ── Quick Analysis ────────────────────────────────────────

@router.post("/quick-analysis", response_model=QuickAnalysisResponse, summary="Quick Analysis (multi-tool)")
def quick_analysis(body: QuickAnalysisRequest, db: Session = Depends(get_db)):
    quick_id = uuid.uuid4()
    results: dict[str, QuickAnalysisToolResult] = {}
    start = time.monotonic()

    for tool_type in body.tools:
        service = _tool_services.get(tool_type)
        if not service:
            results[tool_type] = QuickAnalysisToolResult(
                status="failed", error=f"Tool not available: {tool_type}",
            )
            continue

        try:
            resp = service.run(
                db,
                PLACEHOLDER_ORG_ID,
                body.target,
                triggered_by="quick_analysis",
                quick_analysis_id=quick_id,
            )
            results[tool_type] = QuickAnalysisToolResult(
                status=resp.status,
                result=resp.result,
                error=resp.error,
                duration_ms=resp.duration_ms,
            )
        except RateLimitExceeded as exc:
            results[tool_type] = QuickAnalysisToolResult(
                status="failed", error=str(exc),
            )

    db.commit()
    total_ms = int((time.monotonic() - start) * 1000)
    all_ok = all(r.status == "completed" for r in results.values())

    return QuickAnalysisResponse(
        quick_analysis_id=quick_id,
        target=body.target,
        status="completed" if all_ok else "partial",
        total_duration_ms=total_ms,
        results=results,
    )


# ── History ───────────────────────────────────────────────

@router.get("/history", response_model=HistoryListResponse, summary="Tool execution history")
def list_history(
    target: str | None = Query(None),
    tool_type: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    repo = ToolExecutionRepository(db)
    items = repo.list_history(
        PLACEHOLDER_ORG_ID,
        target=target,
        tool_type=tool_type,
        limit=limit,
        offset=offset,
    )
    total = repo.count_history(
        PLACEHOLDER_ORG_ID,
        target=target,
        tool_type=tool_type,
    )
    return HistoryListResponse(
        items=[
            HistoryItem(
                execution_id=item.id,
                tool_type=item.tool_type,
                target=item.target,
                status=item.status,
                duration_ms=item.duration_ms,
                triggered_by=item.triggered_by,
                created_at=item.created_at,
            )
            for item in items
        ],
        total=total,
    )


@router.get("/history/{execution_id}", response_model=ToolResponse, summary="Get execution detail")
def get_execution(execution_id: UUID, db: Session = Depends(get_db)):
    repo = ToolExecutionRepository(db)
    record = repo.get_by_id(execution_id)
    if not record:
        raise HTTPException(status_code=404, detail="Execution not found")
    return ToolResponse(
        execution_id=record.id,
        tool_type=record.tool_type,
        target=record.target,
        status=record.status,
        duration_ms=record.duration_ms,
        cached=False,
        result=record.result_data,
        error=record.error_message,
        executed_at=record.created_at,
    )
