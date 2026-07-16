# ActionGuard — AI Action-Level Guardrail Platform
### Full Design + Code Structure for PS-3.1 (5-Day Build Plan)

---

## 1. Product Framing

Don't submit "a solution to PS-3.1." Submit **ActionGuard** — a runtime governance layer that sits between any AI agent and the tools it can call, blocking, escalating, or logging every action *before* it executes.

**One-line pitch for your video:** *"Every guardrail platform today filters what an LLM says. ActionGuard governs what it does."*

---

## 2. Architecture Overview

```
                     ┌─────────────────────────┐
                     │   Sample Agent (real     │
                     │   Anthropic API calls)   │
                     └────────────┬─────────────┘
                                  │ wants to call a tool
                                  ▼
                     ┌─────────────────────────┐
                     │   Guardrail Evaluator    │◄──── policy/rules.yaml
                     │  (pre-execution check)   │
                     └────────────┬─────────────┘
                 ┌────────────────┼────────────────┐
                 ▼                ▼                ▼
             BLOCK          REQUIRE_HITL      LOG_AND_ALLOW
                 │                │                │
                 │                ▼                │
                 │      ┌───────────────────┐      │
                 │      │   HITL Queue       │      │
                 │      │ (approve/reject)   │      │
                 │      └─────────┬──────────┘      │
                 │                │ approved         │
                 └────────────────┴──────────────────┘
                                  ▼
                     ┌─────────────────────────┐
                     │      Mock Tool Layer     │
                     │ (db_delete, send_email,  │
                     │  read_file, db_write)    │
                     └────────────┬─────────────┘
                                  ▼
                     ┌─────────────────────────┐
                     │      Audit Logger        │──► DynamoDB (AWS) /
                     │  (every decision logged) │    SQLite (local)
                     └────────────┬─────────────┘
                                  ▼
                     ┌─────────────────────────┐
                     │   FastAPI + Dashboard    │
                     │  (polling, no WebSocket) │
                     └─────────────────────────┘
```

**Why no WebSockets:** a polling dashboard (refresh every 3s via `fetch`) looks 90% as "live" in a demo video but removes the #1 cause of AWS deployment pain (ALB idle timeouts killing persistent connections). This is a deliberate risk-reduction choice — mention it in your write-up as an engineering tradeoff, it shows maturity.

---

## 3. Feature Matrix (Core = required, ★ = bonus add-ons)

| Feature | Source | Why it's worth including |
|---|---|---|
| Pre-execution action evaluator | PS-3.1 core | Required |
| YAML policy rules (block / require_hitl / log_and_allow) | PS-3.1 core | Required |
| Simulation harness (3 outcome types) | PS-3.1 core | Required, also = your test suite |
| Full audit log, queryable | PS-3.1 core | Required |
| ★ Dry-run mode | PS-3.1 official bonus | Cheap to add, high credibility |
| ★ Rate limiting per tool | Borrowed from PS-5.1 | ~20 lines, adds "WAF" flavor |
| ★ Time-of-day / business-hours condition | Borrowed from PS-10.2 | Shows context-aware policy without building a full DSL |
| ★ Real LLM-driven agent (Anthropic API) | Production-readiness brief | Satisfies "connects to a real LLM provider" scoring criterion |
| ★ Human approval via API (not just CLI) | Your own polish | Turns HITL into something demoable in the video |
| Health check + structured logging | Production-readiness brief | Explicitly listed as a scoring factor |
| Docker + one-command AWS deploy | Production-readiness brief | Explicitly listed as a scoring factor |

Keep the ★ list to exactly these five. Do not add more — this is already a full 5-day scope.

---

## 4. Repository Structure

```
action-guard/
├── README.md
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── infra/
│   ├── deploy.sh
│   ├── cloudformation.yaml
│   └── task-definition.json
├── app/
│   ├── main.py
│   ├── config.py
│   ├── models/
│   │   └── schemas.py
│   ├── policy/
│   │   ├── rules.yaml
│   │   └── engine.py
│   ├── guardrail/
│   │   └── evaluator.py
│   ├── hitl/
│   │   ├── queue.py
│   │   └── routes.py
│   ├── audit/
│   │   ├── store.py
│   │   └── routes.py
│   ├── agent/
│   │   ├── tools.py
│   │   └── sample_agent.py
│   ├── dashboard/
│   │   ├── routes.py
│   │   └── templates/index.html
│   └── utils/
│       ├── logging.py
│       └── rate_limiter.py
├── tests/
│   └── test_scenarios.py
├── scripts/
│   └── simulate.py
└── docs/
    └── architecture.md
```

---

## 5. Core Code

### `app/policy/rules.yaml`
```yaml
rules:
  - id: block_bulk_delete
    description: "Block any database delete where record count exceeds 100"
    tool: db_delete
    condition: "params['record_count'] > 100"
    action: block

  - id: allow_small_delete
    description: "Log and allow deletes of 5 or fewer records"
    tool: db_delete
    condition: "params['record_count'] <= 100"
    action: log_and_allow

  - id: hitl_external_email
    description: "Require HITL for any email sent to an external domain"
    tool: send_email
    condition: "params['recipient_domain'] not in internal_domains"
    action: require_hitl

  - id: allow_internal_email
    description: "Log and allow internal emails"
    tool: send_email
    condition: "params['recipient_domain'] in internal_domains"
    action: log_and_allow

  - id: log_confidential_read
    description: "Log and allow reads of paths containing 'confidential'"
    tool: read_file
    condition: "'confidential' in params['path']"
    action: log_and_allow

  # ★ bonus: time-of-day awareness (PS-10.2 flavor)
  - id: after_hours_write_hitl
    description: "Require HITL for data writes outside business hours (6am-9pm)"
    tool: db_write
    condition: "hour_of_day < 6 or hour_of_day > 21"
    action: require_hitl

  # ★ bonus: simple rate limiting (PS-5.1 flavor)
  - id: rate_limit_any_tool
    description: "Block if this agent has made more than 10 calls to this tool in the last 60s"
    tool: "*"
    condition: "calls_last_minute > 10"
    action: block
```

### `app/policy/engine.py`
```python
import yaml
from pathlib import Path
from simpleeval import simple_eval, EvalWithCompoundTypes

RULES_PATH = Path(__file__).parent / "rules.yaml"


class PolicyEngine:
    """Loads YAML rules and evaluates a single tool-call context against them.
    Uses simpleeval instead of raw eval() — never execute untrusted expressions
    with Python's eval(), even in a 5-day project. This is a good talking point
    in your write-up (security-conscious design of the guardrail itself)."""

    ACTION_PRIORITY = {"block": 3, "require_hitl": 2, "log_and_allow": 1}

    def __init__(self, rules_path: Path = RULES_PATH):
        self.rules = self._load(rules_path)

    def _load(self, path: Path):
        with open(path) as f:
            data = yaml.safe_load(f)
        return data["rules"]

    def evaluate(self, tool: str, params: dict, context: dict) -> dict:
        """Returns the MOST RESTRICTIVE matching decision.
        context includes: internal_domains, hour_of_day, calls_last_minute, etc."""
        eval_ctx = {"params": params, **context}
        matched = []

        for rule in self.rules:
            if rule["tool"] not in ("*", tool):
                continue
            try:
                condition_result = simple_eval(
                    rule["condition"],
                    names=eval_ctx,
                    operators=EvalWithCompoundTypes.OPERATORS,
                )
            except Exception:
                continue  # malformed/unmatched condition -> skip, don't crash the evaluator
            if condition_result:
                matched.append(rule)

        if not matched:
            return {"action": "log_and_allow", "rule_id": None, "reason": "no matching rule (default allow)"}

        # most restrictive rule wins: block > require_hitl > log_and_allow
        winner = max(matched, key=lambda r: self.ACTION_PRIORITY[r["action"]])
        return {"action": winner["action"], "rule_id": winner["id"], "reason": winner["description"]}
```

### `app/guardrail/evaluator.py`
```python
import time
from datetime import datetime
from app.policy.engine import PolicyEngine
from app.audit.store import AuditStore
from app.hitl.queue import HitlQueue
from app.utils.rate_limiter import RateLimiter

INTERNAL_DOMAINS = {"acme-corp.com", "internal.acme-corp.com"}


class GuardrailEvaluator:
    def __init__(self, audit: AuditStore, hitl: HitlQueue, dry_run: bool = False):
        self.engine = PolicyEngine()
        self.audit = audit
        self.hitl = hitl
        self.rate_limiter = RateLimiter()
        self.dry_run = dry_run

    def evaluate_action(self, agent_id: str, tool: str, params: dict) -> dict:
        context = {
            "internal_domains": INTERNAL_DOMAINS,
            "hour_of_day": datetime.utcnow().hour,
            "calls_last_minute": self.rate_limiter.record_and_count(agent_id, tool),
        }

        decision = self.engine.evaluate(tool, params, context)
        record = {
            "timestamp": datetime.utcnow().isoformat(),
            "agent_id": agent_id,
            "tool": tool,
            "params": params,
            "action": decision["action"],
            "rule_id": decision["rule_id"],
            "reason": decision["reason"],
            "dry_run": self.dry_run,
        }

        if self.dry_run:
            # evaluate + log what WOULD have happened, but never actually block or pause
            record["simulated_outcome"] = decision["action"]
            record["action"] = "log_and_allow"  # dry run always lets execution continue
            self.audit.write(record)
            return {"status": "allowed", "dry_run": True, "would_have": decision["action"]}

        self.audit.write(record)

        if decision["action"] == "block":
            return {"status": "blocked", "reason": decision["reason"], "rule_id": decision["rule_id"]}

        if decision["action"] == "require_hitl":
            request_id = self.hitl.enqueue(agent_id, tool, params, decision["reason"])
            return {"status": "pending", "request_id": request_id}

        return {"status": "allowed", "rule_id": decision["rule_id"]}
```

### `app/utils/rate_limiter.py`
```python
import time
from collections import defaultdict, deque

class RateLimiter:
    """In-memory sliding window. Fine for a single-container deployment;
    note in your write-up that a production version would back this with Redis."""
    def __init__(self, window_seconds: int = 60):
        self.window = window_seconds
        self.calls = defaultdict(deque)

    def record_and_count(self, agent_id: str, tool: str) -> int:
        key = f"{agent_id}:{tool}"
        now = time.time()
        dq = self.calls[key]
        dq.append(now)
        while dq and dq[0] < now - self.window:
            dq.popleft()
        return len(dq)
```

### `app/hitl/queue.py`
```python
import uuid
from datetime import datetime

class HitlQueue:
    def __init__(self, audit_store):
        self.pending = {}
        self.audit = audit_store

    def enqueue(self, agent_id, tool, params, reason) -> str:
        request_id = str(uuid.uuid4())
        self.pending[request_id] = {
            "request_id": request_id,
            "agent_id": agent_id,
            "tool": tool,
            "params": params,
            "reason": reason,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
        }
        return request_id

    def resolve(self, request_id: str, decision: str, reviewer: str = "demo_reviewer"):
        item = self.pending.get(request_id)
        if not item:
            return None
        item["status"] = decision  # "approved" or "rejected"
        item["reviewer"] = reviewer
        item["resolved_at"] = datetime.utcnow().isoformat()
        self.audit.write({**item, "event": "hitl_resolution"})
        return item

    def get_status(self, request_id: str):
        return self.pending.get(request_id)

    def list_pending(self):
        return [v for v in self.pending.values() if v["status"] == "pending"]
```

### `app/hitl/routes.py`
```python
from fastapi import APIRouter, HTTPException
from app.main import hitl_queue

router = APIRouter(prefix="/hitl", tags=["hitl"])

@router.get("/pending")
def list_pending():
    return hitl_queue.list_pending()

@router.post("/{request_id}/approve")
def approve(request_id: str):
    result = hitl_queue.resolve(request_id, "approved")
    if not result:
        raise HTTPException(404, "request not found")
    return result

@router.post("/{request_id}/reject")
def reject(request_id: str):
    result = hitl_queue.resolve(request_id, "rejected")
    if not result:
        raise HTTPException(404, "request not found")
    return result

@router.get("/{request_id}/status")
def status(request_id: str):
    result = hitl_queue.get_status(request_id)
    if not result:
        raise HTTPException(404, "request not found")
    return result
```

### `app/audit/store.py`
```python
import os, json, sqlite3
from datetime import datetime

USE_DYNAMO = os.getenv("USE_DYNAMODB", "false").lower() == "true"

class AuditStore:
    """Abstracts storage so local dev uses SQLite (zero setup) and AWS uses
    DynamoDB (no VPC/connection-pool headaches — a deliberate choice to avoid
    RDS networking complexity in a 5-day AWS deployment)."""

    def __init__(self):
        if USE_DYNAMO:
            import boto3
            self.table = boto3.resource("dynamodb").Table(os.getenv("AUDIT_TABLE", "action_guard_audit"))
        else:
            self.conn = sqlite3.connect("audit.db", check_same_thread=False)
            self.conn.execute("""CREATE TABLE IF NOT EXISTS audit
                (id TEXT PRIMARY KEY, ts TEXT, payload TEXT)""")
            self.conn.commit()

    def write(self, record: dict):
        record.setdefault("id", f"{datetime.utcnow().timestamp()}")
        if USE_DYNAMO:
            self.table.put_item(Item=json.loads(json.dumps(record, default=str)))
        else:
            self.conn.execute("INSERT INTO audit VALUES (?, ?, ?)",
                (record["id"], record.get("timestamp", ""), json.dumps(record, default=str)))
            self.conn.commit()

    def recent(self, limit: int = 50):
        if USE_DYNAMO:
            resp = self.table.scan(Limit=limit)
            items = resp.get("Items", [])
            return sorted(items, key=lambda r: r.get("timestamp", ""), reverse=True)
        else:
            rows = self.conn.execute(
                "SELECT payload FROM audit ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
            return [json.loads(r[0]) for r in rows]
```

### `app/agent/tools.py`
```python
def db_delete(record_count: int):
    return {"result": f"deleted {record_count} records"}

def db_write(record_id: str, data: dict):
    return {"result": f"wrote record {record_id}"}

def send_email(recipient_domain: str, subject: str):
    return {"result": f"email '{subject}' sent to domain {recipient_domain}"}

def read_file(path: str):
    return {"result": f"read contents of {path}"}

TOOL_REGISTRY = {
    "db_delete": db_delete,
    "db_write": db_write,
    "send_email": send_email,
    "read_file": read_file,
}
```

### `app/agent/sample_agent.py`
```python
"""Minimal real-LLM-driven agent. Every tool call the model wants to make is
routed through GuardrailEvaluator BEFORE execution — this is the actual PS-3.1
requirement. Uses the Anthropic API directly (no heavy framework) to keep the
dependency surface small and deployment low-risk."""

import os, json, anthropic
from app.agent.tools import TOOL_REGISTRY

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

TOOLS_SCHEMA = [
    {"name": "db_delete", "description": "Delete records from the database",
     "input_schema": {"type": "object", "properties": {"record_count": {"type": "integer"}}, "required": ["record_count"]}},
    {"name": "db_write", "description": "Write a record to the database",
     "input_schema": {"type": "object", "properties": {"record_id": {"type": "string"}, "data": {"type": "object"}}, "required": ["record_id"]}},
    {"name": "send_email", "description": "Send an email",
     "input_schema": {"type": "object", "properties": {"recipient_domain": {"type": "string"}, "subject": {"type": "string"}}, "required": ["recipient_domain", "subject"]}},
    {"name": "read_file", "description": "Read a file by path",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
]

def run_agent_task(agent_id: str, instruction: str, evaluator):
    messages = [{"role": "user", "content": instruction}]
    response = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=1024,
        tools=TOOLS_SCHEMA, messages=messages,
    )

    results = []
    for block in response.content:
        if block.type == "tool_use":
            decision = evaluator.evaluate_action(agent_id, block.name, block.input)
            if decision["status"] == "blocked":
                results.append({"tool": block.name, "outcome": "BLOCKED", "reason": decision["reason"]})
                continue
            if decision["status"] == "pending":
                results.append({"tool": block.name, "outcome": "PENDING_HITL", "request_id": decision["request_id"]})
                continue
            tool_result = TOOL_REGISTRY[block.name](**block.input)
            results.append({"tool": block.name, "outcome": "EXECUTED", "result": tool_result})
    return results
```

### `app/main.py`
```python
from fastapi import FastAPI
from app.audit.store import AuditStore
from app.hitl.queue import HitlQueue
from app.guardrail.evaluator import GuardrailEvaluator
from app.utils.logging import setup_logging
import os

setup_logging()
app = FastAPI(title="ActionGuard", version="1.0")

audit_store = AuditStore()
hitl_queue = HitlQueue(audit_store)
evaluator = GuardrailEvaluator(audit_store, hitl_queue, dry_run=os.getenv("DRY_RUN", "false").lower() == "true")

from app.hitl.routes import router as hitl_router
from app.audit.routes import router as audit_router
from app.dashboard.routes import router as dashboard_router
app.include_router(hitl_router)
app.include_router(audit_router)
app.include_router(dashboard_router)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/agent/run")
def agent_run(agent_id: str, instruction: str):
    from app.agent.sample_agent import run_agent_task
    return run_agent_task(agent_id, instruction, evaluator)

@app.post("/evaluate")
def evaluate_raw(agent_id: str, tool: str, params: dict):
    """Direct endpoint for the simulation harness / grading scripts —
    doesn't require a real LLM call, so success criteria tests run fast and free."""
    return evaluator.evaluate_action(agent_id, tool, params)
```

### `app/audit/routes.py`
```python
from fastapi import APIRouter
from app.main import audit_store

router = APIRouter(prefix="/audit", tags=["audit"])

@router.get("/recent")
def recent(limit: int = 50):
    return audit_store.recent(limit)
```

### `app/dashboard/routes.py` + `templates/index.html`
```python
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pathlib import Path

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
def dashboard():
    return Path(__file__).parent.joinpath("templates/index.html").read_text()
```

```html
<!-- app/dashboard/templates/index.html -->
<!DOCTYPE html>
<html>
<head>
  <title>ActionGuard Dashboard</title>
  <style>
    body { font-family: system-ui; background: #0b0f14; color: #e2e8f0; padding: 24px; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; }
    td, th { padding: 8px; border-bottom: 1px solid #1f2937; text-align: left; font-size: 13px; }
    .block { color: #f87171; } .hitl { color: #fbbf24; } .allow { color: #34d399; }
    button { background: #34d399; border: none; padding: 4px 10px; border-radius: 4px; cursor: pointer; margin-right: 4px; }
    button.reject { background: #f87171; }
  </style>
</head>
<body>
  <h2>🛡 ActionGuard — Live Audit Feed</h2>
  <div id="stats"></div>
  <h3>Pending HITL Approvals</h3>
  <table id="hitl"><thead><tr><th>Tool</th><th>Reason</th><th>Action</th></tr></thead><tbody></tbody></table>
  <h3>Recent Decisions</h3>
  <table id="audit"><thead><tr><th>Time</th><th>Agent</th><th>Tool</th><th>Action</th><th>Reason</th></tr></thead><tbody></tbody></table>

  <script>
    async function refresh() {
      const audit = await (await fetch('/audit/recent')).json();
      const pending = await (await fetch('/hitl/pending')).json();

      document.querySelector('#stats').innerText =
        `Blocked: ${audit.filter(a=>a.action==='block').length} | ` +
        `HITL: ${audit.filter(a=>a.action==='require_hitl').length} | ` +
        `Allowed: ${audit.filter(a=>a.action==='log_and_allow').length}`;

      const auditBody = document.querySelector('#audit tbody');
      auditBody.innerHTML = audit.map(a => `<tr>
        <td>${a.timestamp}</td><td>${a.agent_id}</td><td>${a.tool}</td>
        <td class="${a.action==='block'?'block':a.action==='require_hitl'?'hitl':'allow'}">${a.action}</td>
        <td>${a.reason||''}</td></tr>`).join('');

      const hitlBody = document.querySelector('#hitl tbody');
      hitlBody.innerHTML = pending.map(p => `<tr>
        <td>${p.tool}</td><td>${p.reason}</td>
        <td><button onclick="act('${p.request_id}','approve')">Approve</button>
            <button class="reject" onclick="act('${p.request_id}','reject')">Reject</button></td></tr>`).join('');
    }
    async function act(id, action) {
      await fetch(`/hitl/${id}/${action}`, { method: 'POST' });
      refresh();
    }
    setInterval(refresh, 3000);
    refresh();
  </script>
</body>
</html>
```

---

## 6. Simulation Harness (maps 1:1 to the grading success criteria)

### `scripts/simulate.py`
```python
"""Run this to prove every success criterion from the problem statement fires
correctly. Put the output straight into your write-up as evidence."""
import requests

BASE = "http://localhost:8000"

def check(label, agent_id, tool, params, expected):
    r = requests.post(f"{BASE}/evaluate", json={}, params={"agent_id": agent_id, "tool": tool}, json=params)
    status = r.json()["status"]
    print(f"[{'PASS' if status==expected else 'FAIL'}] {label}: expected={expected} got={status}")

if __name__ == "__main__":
    check("Bulk delete (500 records) is BLOCKED", "agent-1", "db_delete", {"record_count": 500}, "blocked")
    check("Small delete (5 records) is ALLOWED", "agent-1", "db_delete", {"record_count": 5}, "allowed")
    check("External email requires HITL", "agent-1", "send_email",
          {"recipient_domain": "gmail.com", "subject": "hi"}, "pending")
    check("Internal email is ALLOWED", "agent-1", "send_email",
          {"recipient_domain": "acme-corp.com", "subject": "hi"}, "allowed")
```

Also write `tests/test_scenarios.py` with the same four cases as real `pytest` assertions — grading a repo with an actual test suite (not just a manual script) is one of the clearest "this person builds real software" signals in a review.

---

## 7. Docker + AWS Deployment

### `Dockerfile`
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD curl -f http://localhost:8000/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### `requirements.txt`
```
fastapi==0.115.0
uvicorn[standard]==0.30.6
pyyaml==6.0.2
simpleeval==1.0.3
anthropic==0.34.2
boto3==1.35.0
pydantic==2.9.0
requests==2.32.3
pytest==8.3.2
```

### `docker-compose.yml` (local dev — no AWS needed to test everything)
```yaml
version: "3.9"
services:
  action-guard:
    build: .
    ports: ["8000:8000"]
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - USE_DYNAMODB=false
      - DRY_RUN=false
```

### AWS deployment path (ECS Fargate — chosen over EC2/Lambda/EKS deliberately)

**Why Fargate:** no servers to patch, no VPC subnet headaches like RDS, scales to zero cost when idle, and — critically for your timeline — `aws ecs` has a small, predictable command surface, unlike EKS or raw EC2 where most "deployment day disasters" happen.

`infra/deploy.sh`:
```bash
#!/bin/bash
set -e
REGION=us-east-1
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REPO=action-guard

aws ecr create-repository --repository-name $REPO --region $REGION || true
aws ecr get-login-password --region $REGION | docker login --username AWS \
  --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com

docker build -t $REPO .
docker tag $REPO:latest $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPO:latest
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPO:latest

aws dynamodb create-table --table-name action_guard_audit \
  --attribute-definitions AttributeName=id,AttributeType=S \
  --key-schema AttributeName=id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST --region $REGION || true

aws cloudformation deploy \
  --template-file infra/cloudformation.yaml \
  --stack-name action-guard-stack \
  --capabilities CAPABILITY_IAM \
  --region $REGION \
  --parameter-overrides ImageUri=$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPO:latest

echo "Deployed. Fetching public URL..."
aws cloudformation describe-stacks --stack-name action-guard-stack \
  --query "Stacks[0].Outputs" --region $REGION
```

Keep `infra/cloudformation.yaml` minimal: one Fargate service, one ALB, one target group, IAM role scoped to DynamoDB read/write + Secrets Manager read for the Anthropic key. This is the single riskiest file in the whole project — **build and test it on day 3, not day 5**, so you have slack if IAM permissions or health-check paths need adjusting.

**Deployment risk-reduction checklist (do these to avoid the exact class of problem you've hit before):**
- Pin every dependency version in `requirements.txt` — never `pip install` without versions in the Dockerfile.
- Test the *exact* Docker image locally (`docker run` the built image, not just `uvicorn` from source) before pushing to ECR — this catches 90% of "works on my machine" issues.
- Put the Anthropic API key in **Secrets Manager**, not plaintext env vars in the task definition.
- Set the ALB health check path to `/health` explicitly — a missing/misconfigured health check is the #1 cause of "deployed but shows unhealthy" on ECS.
- Keep the container **stateless** (already true here since DynamoDB holds all state) so ECS can freely restart/replace tasks without data loss.

---

## 8. 5-Day Execution Plan

| Day | Deliverable |
|---|---|
| **1** | Repo scaffold, policy engine + evaluator working locally, `simulate.py` passing all 4 checks against localhost |
| **2** | HITL queue + approve/reject endpoints, audit store (SQLite locally), dry-run mode, rate limiter, dashboard HTML wired to polling endpoints |
| **3** | Real Anthropic-powered sample agent wired through the evaluator; Dockerfile built and tested locally; **AWS CloudFormation + Fargate deploy attempted today** (leaves 2 days of buffer if it breaks) |
| **4** | Fix any AWS issues, switch storage to DynamoDB, re-run full simulation suite against the deployed URL, write README + architecture doc, add automated deploy script polish |
| **5** | Record 5-8 min video (demo first, architecture second), write the PDF write-up (include the "why Fargate not EKS," "why polling not WebSocket" tradeoff reasoning — reviewers notice deliberate engineering choices), zip and submit with time to spare |

---

## 9. What to Say in the Video/Write-up to Maximize Impact

- Open with the **blocked bulk-delete demo** live against your deployed AWS URL, not localhost — this single moment proves production-readiness in 15 seconds.
- Explicitly name the tradeoffs you made (DynamoDB over RDS, polling over WebSocket, Fargate over EKS) and *why* — this is what separates "finished the assignment" from "engineered a solution."
- Show the dry-run mode catching a violation without blocking real traffic — reviewers explicitly listed this as a bonus, make sure it's visible on screen.
- Close with the market comparison: most commercial guardrail platforms (Lakera, Prompt Security, etc.) filter LLM *text*; ActionGuard governs the *action* — that's your differentiation line for the PDF write-up.
