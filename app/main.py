import os
# Force delete all proxy environment variables to prevent httplib2 from resolving them
for key in ['http_proxy', 'https_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'no_proxy', 'NO_PROXY']:
    os.environ.pop(key, None)

# Monkeypatch urllib.request.getproxies to bypass Windows Registry proxy discovery
import urllib.request
urllib.request.getproxies = lambda: {}

from typing import Optional
from fastapi import FastAPI, Request, HTTPException, Query
from app.config import settings
from app.audit.store import AuditStore
from app.hitl.queue import HitlQueue
from app.utils.rate_limiter import RateLimiter
from app.middleware.evaluator import GuardrailEvaluator
from app.agent.gmail_connector import GmailConnector
from app.agent.execution_gateway import ExecutionGateway
from app.utils.logging import setup_logging

# Configure logging
setup_logging()

# Setup FastAPI App
app = FastAPI(
    title="SentinelAI",
    description="SentinelAI Enterprise AI Runtime Governance Platform",
    version="1.0.0"
)

# Instantiate Core Singletons
audit_store = AuditStore()
hitl_queue = HitlQueue(audit_store)
rate_limiter = RateLimiter()
evaluator = GuardrailEvaluator(
    audit_store=audit_store,
    hitl_queue=hitl_queue,
    rate_limiter=rate_limiter,
    dry_run=settings.dry_run
)
gmail_connector = GmailConnector()
execution_gateway = ExecutionGateway(gmail_connector, audit_store)

# Save singletons in application state to facilitate router sharing
app.state.audit_store = audit_store
app.state.hitl_queue = hitl_queue
app.state.rate_limiter = rate_limiter
app.state.evaluator = evaluator
app.state.gmail_connector = gmail_connector
app.state.execution_gateway = execution_gateway

# Include Routers
from app.auth.routes import router as auth_router
from app.hitl.routes import router as hitl_router
from app.audit.routes import router as audit_router
from app.dashboard.routes import router as dashboard_router

app.include_router(auth_router)
app.include_router(hitl_router)
app.include_router(audit_router)
app.include_router(dashboard_router)

@app.get("/health")
def health():
    """Service health state check."""
    return {
        "status": "ok", 
        "dry_run": evaluator.dry_run, 
        "policy_version": evaluator.policy_engine.active_version,
        "gmail_mode": "LIVE" if gmail_connector.is_live else "MOCK"
    }

@app.get("/gmail/inbox")
def list_inbox(request: Request, label: Optional[str] = Query(None, description="Optional label filter, e.g. INBOX, SENT, TRASH")):
    """Exposes current email database content to support dashboard visualizations."""
    return gmail_connector.list_emails(label_filter=label)

@app.post("/gmail/action")
def run_gmail_action(
    tool: str,
    params: dict,
    role: str = Query("junior_dev", description="Role context for tool authorization"),
    agent_id: str = Query("dashboard-operator", description="Agent key identifying session")
):
    """Evaluates and, if allowed, dispatches Gmail action to Execution Gateway.
    Used by interactive visualizer to showcase policy rules enforcement in real time."""
    params["_role"] = role
    evaluation = evaluator.evaluate_action(agent_id, tool, params)
    
    if evaluation["status"] == "allowed":
        try:
            result = execution_gateway.execute(agent_id, tool, params, role)
            return {"status": "executed", "result": result, "evaluation": evaluation}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    elif evaluation["status"] == "pending":
        return {"status": "pending", "request_id": evaluation.get("request_id"), "evaluation": evaluation}
        
    return {"status": "blocked", "evaluation": evaluation}

@app.post("/evaluate")
def evaluate_raw(
    agent_id: str,
    tool: str,
    params: dict,
    policy_version: Optional[str] = Query(None, description="Temporary version override for testing/playground"),
    role: str = Query("junior_dev", description="Role context for rule evaluation"),
    request: Request = None
):
    """Direct execution endpoint for simulation scripts, testing, or playgrounds.
    Allows evaluating a tool execution request against the guardrail engine."""
    params["_role"] = role
    return evaluator.evaluate_action(
        agent_id=agent_id,
        tool=tool,
        params=params,
        policy_version_override=policy_version
    )

@app.post("/agent/run")
def agent_run(
    agent_id: str,
    instruction: str,
    role: str = Query("junior_dev", description="Role context for tool dispatching authorization"),
    dry_run: bool = Query(False, description="Enable dry-run mode (policies evaluate and violations are reported but not executed)")
):
    """Runs a task instruction using the Gemini AI agent or rule-based parser.
    Dispatches tool execution via the ExecutionGateway when permitted.
    Supports dynamic dry_run override for testing/playground."""
    from app.agent.sample_agent import run_agent_task
    
    orig_dry_run = evaluator.dry_run
    evaluator.dry_run = dry_run
    try:
        results = run_agent_task(
            agent_id=agent_id,
            instruction=instruction,
            evaluator=evaluator,
            execution_gateway=execution_gateway,
            role=role
        )
    finally:
        evaluator.dry_run = orig_dry_run
    return results

@app.post("/agent/clear")
def agent_clear(agent_id: str):
    """Clear chat conversation history context for the given agent session ID."""
    from app.agent.sample_agent import conversation_histories
    if agent_id in conversation_histories:
        conversation_histories[agent_id] = []
    return {"status": "success", "agent_id": agent_id}


# Active policy administration endpoints
@app.get("/policy/config")
def get_policy_config():
    """Retrieve details of currently active policies, templates, and active rules list."""
    return {
        "active_version": evaluator.policy_engine.active_version,
        "active_template": evaluator.policy_engine.active_template,
        "rules": evaluator.policy_engine.rules,
        "rule_count": len(evaluator.policy_engine.rules)
    }

@app.post("/policy/version")
def set_policy_version(version: str):
    """Change the active policy file rules version (e.g. 'v1', 'v2', 'v3')."""
    evaluator.policy_engine.set_version(version)
    return {"status": "success", "active_version": evaluator.policy_engine.active_version}

@app.post("/policy/template")
def set_policy_template(template: str):
    """Load a specific pre-configured industry template ruleset ('finance', 'healthcare', 'retail')."""
    success = evaluator.policy_engine.load_template(template)
    if not success:
        raise HTTPException(status_code=404, detail=f"Policy template '{template}' not found.")
    return {"status": "success", "active_version": evaluator.policy_engine.active_version, "template": template}

@app.get("/connector/status")
def connector_status():
    """Returns the operational status of all registered action connectors.
    Demonstrates SentinelAI's extensible multi-connector architecture.
    Gmail is the first connector; AWS, Slack, GitHub, and Google Drive are next."""
    return {
        "connectors": [
            {
                "id": "gmail",
                "name": "Gmail",
                "type": "email",
                "status": "live" if gmail_connector.is_live else "mock",
                "description": "Google Gmail API connector for email send, read, delete, archive, forward, reply",
                "operations": ["send", "read", "search", "delete", "archive", "restore", "reply", "forward", "manage_labels"],
                "active": True
            },
            {
                "id": "aws",
                "name": "AWS (S3 / Lambda / EC2)",
                "type": "cloud_infrastructure",
                "status": "planned",
                "description": "AWS cloud operations connector — same governance engine, different target",
                "operations": ["s3_upload", "ec2_restart", "lambda_invoke", "iam_modify"],
                "active": False
            },
            {
                "id": "slack",
                "name": "Slack",
                "type": "messaging",
                "status": "planned",
                "description": "Slack workspace messaging and channel management connector",
                "operations": ["send_message", "delete_message", "create_channel", "invite_user"],
                "active": False
            },
            {
                "id": "github",
                "name": "GitHub",
                "type": "code_repository",
                "status": "planned",
                "description": "GitHub repository operations connector",
                "operations": ["create_pr", "merge_pr", "delete_branch", "push_commit"],
                "active": False
            },
            {
                "id": "google_drive",
                "name": "Google Drive",
                "type": "file_storage",
                "status": "planned",
                "description": "Google Drive file management connector",
                "operations": ["upload", "share", "delete", "move"],
                "active": False
            }
        ],
        "governance_engine": "SentinelAI v1.0",
        "note": "All connectors share the same governance engine. Adding a new connector requires only implementing the connector interface — zero changes to policy, risk, HITL, or audit systems."
    }

