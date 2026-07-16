from fastapi import APIRouter, Request, Query
from typing import Optional

router = APIRouter(prefix="/audit", tags=["Audit Log"])

@router.get("/recent")
def list_recent(request: Request, limit: int = Query(50, ge=1, le=100)):
    """Fetch the most recent evaluation logs."""
    audit_store = request.app.state.audit_store
    return audit_store.recent(limit=limit)

@router.get("/search")
def search_audits(
    request: Request,
    agent_id: Optional[str] = Query(None, description="Filter by Agent ID"),
    tool: Optional[str] = Query(None, description="Filter by Tool Name"),
    action: Optional[str] = Query(None, description="Filter by Evaluated Action (allowed, blocked, pending)"),
    policy_version: Optional[str] = Query(None, description="Filter by Policy version (e.g. v1, v2)"),
    limit: int = Query(50, ge=1, le=100)
):
    """Search and filter the audit records."""
    audit_store = request.app.state.audit_store
    return audit_store.search(
        agent_id=agent_id,
        tool=tool,
        action=action,
        policy_version=policy_version,
        limit=limit
    )
