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

from fastapi.middleware.cors import CORSMiddleware

# Setup FastAPI App
app = FastAPI(
    title="SentinelAI",
    description="SentinelAI Enterprise AI Runtime Governance Platform",
    version="1.0.0"
)

# Enable CORS for cloud deployment & frontend clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware to support HEAD requests (used by UptimeRobot & cloud health checkers)
@app.middleware("http")
async def handle_head_requests(request: Request, call_next):
    if request.method == "HEAD":
        request.scope["method"] = "GET"
        response = await call_next(request)
        return response
    return await call_next(request)

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
app.state.guardian_alerts = []
app.state.quarantine_vault = []

# Include Routers
from app.auth.routes import router as auth_router
from app.hitl.routes import router as hitl_router
from app.audit.routes import router as audit_router
from app.dashboard.routes import router as dashboard_router

app.include_router(auth_router)
app.include_router(hitl_router)
app.include_router(audit_router)
app.include_router(dashboard_router)


@app.on_event("startup")
def on_startup():
    from app.agent.monitor import start_inbox_monitor
    start_inbox_monitor(app)

@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    """Service health state check."""
    return {
        "status": "ok", 
        "dry_run": evaluator.dry_run, 
        "policy_version": evaluator.policy_engine.active_version,
        "gmail_mode": "LIVE" if gmail_connector.is_live else "MOCK",
        "monitor_active": settings.enable_monitor
    }

@app.post("/gmail/simulate_receive")
def simulate_receive(
    request: Request,
    sender: str = Query("support@amaz0n-security.com", description="Sender email address"),
    subject: str = Query("URGENT: Reset Password", description="Email subject line"),
    body: str = Query("Please click here to reset your password.", description="Email text body"),
    attachment_filename: Optional[str] = Query(None, description="Optional filename for simulated attachment")
):
    """Simulates receiving a new email in Mock Mode to trigger the background monitor."""
    from datetime import datetime
    gmail_connector = request.app.state.gmail_connector
    new_id = f"msg_{len(gmail_connector.mock_db) + 1:03d}"
    attachments = []
    if attachment_filename:
        attachments.append({"filename": attachment_filename, "content_type": "application/octet-stream"})
        
    new_email = {
        "id": new_id,
        "from": sender,
        "to": "john@acme-corp.com",
        "subject": subject,
        "body": body,
        "labels": ["INBOX"],
        "timestamp": datetime.utcnow().isoformat(),
        "attachments": attachments
    }
    gmail_connector.mock_db.insert(0, new_email)
    return {"status": "success", "simulated_email": new_email}

@app.get("/guardian/alerts")
def get_guardian_alerts(request: Request):
    """Returns active guardian security alerts and interactive reply requests."""
    return getattr(request.app.state, "guardian_alerts", [])

@app.get("/guardian/quarantine_vault")
def get_quarantine_vault(request: Request):
    """Returns stored logs and full email contents of all deleted/quarantined threat emails."""
    gmail_connector = request.app.state.gmail_connector
    return getattr(gmail_connector, "quarantine_vault", [])

@app.post("/guardian/clear_alert/{alert_id}")
def clear_guardian_alert(request: Request, alert_id: str):
    """Dismisses a guardian security alert, marking it as acknowledged in state history."""
    alerts = getattr(request.app.state, "guardian_alerts", [])
    for a in alerts:
        if a["id"] == alert_id:
            a["dismissed"] = True
    return {"status": "success"}

@app.post("/guardian/reply")
def submit_guardian_reply(
    request: Request,
    message_id: str = Query(...),
    reply_body: str = Query(...)
):
    """Submits a user-guided reply to an email thread, running it through guardrails."""
    evaluator = request.app.state.evaluator
    execution_gateway = request.app.state.execution_gateway
    alerts = getattr(request.app.state, "guardian_alerts", [])
    
    alert = next((a for a in alerts if a["id"] == message_id), None)
    if not alert:
        return {"status": "error", "message": "Alert not found or already processed."}
        
    tool_params = {
        "message_id": message_id,
        "body": reply_body,
        "_role": "junior_dev"
    }
    
    evaluation = evaluator.evaluate_action(
        agent_id="autonomous-monitor-agent",
        tool="gmail_reply_email",
        params=tool_params
    )
    
    status = evaluation["status"]
    if status == "allowed":
        try:
            result = execution_gateway.execute(
                agent_id="autonomous-monitor-agent",
                tool_name="gmail_reply_email",
                params=tool_params,
                role="junior_dev"
            )
            # Remove from alerts
            request.app.state.guardian_alerts = [a for a in alerts if a["id"] != message_id]
            return {"status": "executed", "result": result, "evaluation": evaluation}
        except Exception as e:
            return {"status": "error", "message": f"Execution failed: {e}"}
    elif status == "pending":
        alert["status"] = "pending_hitl_approval"
        return {"status": "pending", "evaluation": evaluation}
    else:
        return {"status": "blocked", "evaluation": evaluation}

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

