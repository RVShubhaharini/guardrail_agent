from fastapi import APIRouter, HTTPException, Request
from typing import List
from app.models.schemas import HITLResolutionRequest

router = APIRouter(prefix="/hitl", tags=["HITL Queue"])

@router.get("/pending")
def list_pending(request: Request):
    """Retrieve all action requests currently paused and awaiting approval."""
    hitl_queue = request.app.state.hitl_queue
    return hitl_queue.list_pending()

@router.post("/{request_id}/approve")
def approve_request(request_id: str, request: Request, body: HITLResolutionRequest = None):
    """Approve a paused action, allowing the agent to proceed with execution."""
    hitl_queue = request.app.state.hitl_queue
    reviewer = body.reviewer if body else "admin_reviewer"
    result = hitl_queue.resolve(request_id, "approved", reviewer=reviewer)
    if not result:
        raise HTTPException(status_code=404, detail="HITL Request not found or already resolved.")
        
    # Trigger execution of the approved action
    execution_gateway = request.app.state.execution_gateway
    tool_name = result["tool"]
    params = result["params"]
    agent_id = result["agent_id"]
    role = params.get("_role", "junior_dev")
    
    try:
        execution_result = execution_gateway.execute(
            agent_id=agent_id,
            tool_name=tool_name,
            params=params,
            role=role
        )
        result["execution_result"] = execution_result
        result["execution_status"] = "success"

        # Sync tool response to conversation history
        from app.agent.sample_agent import conversation_histories
        if agent_id in conversation_histories:
            from google.genai import types
            history = conversation_histories[agent_id]
            history.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_function_response(
                        name=tool_name,
                        response=execution_result
                    )]
                )
            )
    except Exception as e:
        result["execution_error"] = str(e)
        result["execution_status"] = "failed"
        
        # Sync error response to conversation history
        from app.agent.sample_agent import conversation_histories
        if agent_id in conversation_histories:
            from google.genai import types
            history = conversation_histories[agent_id]
            history.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_function_response(
                        name=tool_name,
                        response={"error": f"Execution failed: {str(e)}"}
                    )]
                )
            )
        raise HTTPException(status_code=500, detail=f"Action approved but execution failed: {str(e)}")
        
    return result

@router.post("/{request_id}/reject")
def reject_request(request_id: str, request: Request, body: HITLResolutionRequest = None):
    """Reject a paused action, preventing execution and notifying the agent."""
    hitl_queue = request.app.state.hitl_queue
    reviewer = body.reviewer if body else "admin_reviewer"
    result = hitl_queue.resolve(request_id, "rejected", reviewer=reviewer)
    if not result:
        raise HTTPException(status_code=404, detail="HITL Request not found or already resolved.")
    return result

@router.get("/{request_id}/status")
def get_status(request_id: str, request: Request):
    """Check the status of a specific HITL authorization request."""
    hitl_queue = request.app.state.hitl_queue
    result = hitl_queue.get_status(request_id)
    if not result:
        # Check if it was already resolved and moved to audits
        audit_store = request.app.state.audit_store
        records = audit_store.search(limit=100)
        for r in records:
            if r.get("request_id") == request_id:
                return r
        raise HTTPException(status_code=404, detail="HITL Request not found.")
    return result
