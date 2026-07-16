# SentinelAI — Technical Architecture Guide

## Overview

SentinelAI is an **Enterprise Runtime AI Governance Platform**. It acts as a mandatory middleware layer between an AI Agent and any real-world system (Gmail, AWS, Slack, GitHub, etc.), ensuring every proposed action is evaluated, risk-scored, and either allowed, held for human approval, or blocked — **before a single API call is made to the target system**.

---

## System Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                      SentinelAI Platform                       │
│                                                                │
│  Input Layer                                                   │
│  ─────────────────────────────────────────────────────────    │
│  ┌───────────────┐   ┌───────────────┐   ┌────────────────┐  │
│  │  Gemini 2.5   │   │  REST API     │   │  Dashboard     │  │
│  │  AI Agent     │   │  /evaluate    │   │  Operator UI   │  │
│  └───────┬───────┘   └───────┬───────┘   └───────┬────────┘  │
│          │                   │                    │            │
│          └─────────────┬─────┘────────────────────┘           │
│                        │                                       │
│                        ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │              GuardrailEvaluator (Core)                  │  │
│  │                                                         │  │
│  │  Step 1: ContextBuilder                                 │  │
│  │          └─ Role, time, domain, attachment,             │  │
│  │             rate limits, violations, geo                │  │
│  │                                                         │  │
│  │  Step 2: PolicyEngine                                   │  │
│  │          └─ Load v1/v2/v3 YAML rules                   │  │
│  │          └─ simpleeval condition matching               │  │
│  │          └─ Return list of matched rules                │  │
│  │                                                         │  │
│  │  Step 3: DecisionExplainer                             │  │
│  │          └─ Aggregate risk score (0-100)               │  │
│  │          └─ Map to: block / require_hitl / allow       │  │
│  │          └─ Build 5-step governance timeline           │  │
│  │                                                         │  │
│  │  Step 4: Branch                                        │  │
│  │          ├─ block       → AuditStore.write()           │  │
│  │          ├─ require_hitl → HitlQueue.enqueue()         │  │
│  │          └─ allow       → AuditStore.write()           │  │
│  └─────────────────────────────────────────────────────────┘  │
│                        │                                       │
│                        ▼ (allowed only)                        │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │              ExecutionGateway                           │  │
│  │  - Final redundant security check                       │  │
│  │  - Route to correct connector method                    │  │
│  │  - Write execution result to AuditStore                 │  │
│  └─────────────────────────────────────────────────────────┘  │
│                        │                                       │
│          ┌─────────────┼───────────────┐                      │
│          ▼             ▼               ▼                      │
│    GmailConnector   [AWSConnector]  [SlackConnector]          │
│    (Live + Mock)    (Planned)       (Planned)                  │
│                                                                │
│  Storage Layer                                                 │
│  ────────────                                                  │
│  AuditStore: SQLite (dev) / DynamoDB (AWS production)          │
│  HitlQueue:  In-memory (dev) / DynamoDB (AWS production)       │
└────────────────────────────────────────────────────────────────┘
```

---

## Component Deep-Dive

### GuardrailEvaluator (`app/middleware/evaluator.py`)

The central interceptor. Every single tool call must pass through here.

```python
def evaluate_action(agent_id, tool, params, policy_version_override=None):
    context = context_builder.build_context(...)  # 9-layer context
    matched_rules = policy_engine.evaluate(tool, params, context)
    outcome = explainer.explain_decision(...)     # risk score + decision
    # → block, require_hitl, or allow
```

**Key Design**: The evaluator is **stateless per request** — all state lives in `AuditStore` and `HitlQueue`. This makes it safe to run in multiple ECS replicas.

---

### ContextBuilder (`app/context/builder.py`)

Enriches each action request with 9 layers of contextual metadata:

| # | Context Field | Description |
|---|---|---|
| 1 | `role` | From `params._role` — injected by agent or API caller |
| 2 | `hour_of_day` | UTC hour — used for after-hours rules |
| 3 | `business_hours` | Boolean: 6 AM–9 PM UTC |
| 4 | `recipient_domain` | Extracted from `params.to` email address |
| 5 | `has_confidential_attachment` | Filename keyword scanning |
| 6 | `data_classification` | general / sensitive / restricted |
| 7 | `previous_violations` | Blocked count from audit history |
| 8 | `cumulative_*` | Rolling 5-min delete/archive counts |
| 9 | `geo_context` | Stub (domestic) — extensibility placeholder |

---

### PolicyEngine (`app/policy/engine.py`)

Loads YAML rule sets and evaluates conditions using `simpleeval` (sandboxed Python expression evaluator).

**Rule Structure (YAML):**
```yaml
- id: block_confidential_attachment_external
  description: "Block confidential attachments to external domains"
  tool: gmail_send_email
  condition: "has_confidential_attachment and recipient_domain not in internal_domains"
  action: block
  risk_score: 98
  remediation: "Sending confidential attachments to external domains is prohibited."
```

**Policy Versions:**

| Version | Rules | Use Case |
|---|---|---|
| `v1` | 2 rules | Basic (rate limit + bulk delete) |
| `v2` | 5 rules | Intermediate (+ RBAC + HITL) |
| `v3` | 16 rules | Full 9-layer enterprise protection |

**Industry Templates**: Finance, Healthcare, Retail — pre-configured rule sets that can be applied at runtime via `POST /policy/template`.

---

### DecisionExplainer (`app/explanation/explainer.py`)

Computes the final decision and builds a human-readable audit trail:

**Risk Score Logic:**
```
Base risk: 10
+ 25 if data_classification == 'restricted'
+ 10 * previous_violations (capped at 100)
→ Max with all matched rule risk_scores
→ If matched rule has explicit action, override decision
```

**Decision Mapping:**
```
0–30:  log_and_allow
31–70: require_hitl
71–100: block
```

**Governance Timeline (5 steps):**
1. `Requested` — agent + tool logged
2. `Context` — role, classification, rate, violations
3. `Rule Match` — matched rule IDs + policy version
4. `Decision` — risk score + resolution action
5. `Execution/Block` — final outcome

---

### HitlQueue (`app/hitl/queue.py`)

Manages pending human approval requests.

**Local Dev**: In-memory Python dict (fast, no dependencies)  
**AWS Production**: DynamoDB-backed with `HITL#<uuid>` key prefix

```
POST /hitl/{id}/approve
  → HitlQueue.resolve(id, "approved")
  → ExecutionGateway.execute(...)
  → AuditStore.write(execution_record)
```

**Why DynamoDB on AWS**: ECS Fargate containers restart during deployments, scaling events, or health check failures. In-memory queue would lose all pending approvals. DynamoDB persistence ensures no approval is ever lost.

---

### AuditStore (`app/audit/store.py`)

Dual-mode audit logging:

| Mode | Storage | When |
|---|---|---|
| Local dev | `audit.db` (SQLite) | `USE_DYNAMODB=false` |
| AWS prod | DynamoDB `action_guard_audit` | `USE_DYNAMODB=true` |

**Schema (both modes):**
```
id          → unique record ID (timestamp-based)
timestamp   → UTC ISO string
agent_id    → agent session identifier
tool        → tool name (e.g., gmail_send_email)
action      → block / allowed / require_hitl
policy_version → v1 / v2 / v3 / template:finance
risk_score  → 0-100
payload     → full JSON of the event
```

---

### ExecutionGateway (`app/agent/execution_gateway.py`)

The **only** component authorized to call `GmailConnector`. Acts as a final security checkpoint:

1. Verify `agent_id` is not empty
2. Verify `role != anonymous`
3. Block guest/intern/support from delete operations
4. Route to correct connector method
5. Log execution result to AuditStore

This redundant check ensures that even if the evaluator were bypassed (e.g., direct `/gmail/action` call), the gateway enforces minimum security.

---

### GmailConnector (`app/agent/gmail_connector.py`)

**Dual-mode connector**:

- **Live Mode**: Connects to real Gmail API using OAuth2 credentials (`token.json`)
- **Mock Mode**: Stateful in-memory inbox simulator with 4 pre-loaded corporate emails

Auto-detects: if `token.json` is valid → Live Mode. Otherwise → Mock Mode (safe for demos and testing).

---

## Multi-Connector Extensibility

This is the most important architectural property. The governance engine is completely decoupled from the connector:

```
              SentinelAI Governance Engine
                          │
     ┌────────────────────┼────────────────────┐
     ▼                    ▼                    ▼
GmailConnector        AWSConnector        SlackConnector
(implemented)         (planned)           (planned)
```

To add a new connector, you only need to:
1. Create `app/agent/aws_connector.py` implementing `send()`, `delete()`, etc.
2. Register its tools in `ExecutionGateway.execute()` (add `elif tool_name == "aws_*":`)
3. Add YAML rules in `v3.yaml` targeting the new tool names

**Zero changes** to: PolicyEngine, ContextBuilder, DecisionExplainer, HitlQueue, AuditStore, Dashboard.

---

## AWS Production Architecture

```
Internet
    │
    ▼
Application Load Balancer (HTTP :80)
    │
    ▼
ECS Fargate Task (sentinelai:latest)
    │  Uses:
    ├─ DynamoDB (audit_guard_audit) ← persistent audit + HITL
    ├─ Secrets Manager (GEMINI_API_KEY) ← never in plaintext
    └─ CloudWatch Logs (/ecs/sentinelai) ← 30-day retention

IAM Roles:
  ECSExecutionRole → AmazonECSTaskExecutionRolePolicy + SecretsManager:GetSecretValue
  ECSTaskRole      → DynamoDB full access on audit table + CloudWatch:PutLogEvents
```

**CloudFormation Stack** (`infra/cloudformation.yaml`) provisions all of the above in one command:
```bash
bash infra/deploy.sh
```

---

## Data Flow — Complete Request Lifecycle

```
1. User types: "Send salary.pdf to competitor@gmail.com"
2. Gemini 2.5 Flash generates: gmail_send_email(to=..., attachments=[salary.pdf])
3. sample_agent.py intercepts the function call BEFORE executing it
4. GuardrailEvaluator.evaluate_action() called
5. ContextBuilder: role=junior_dev, has_confidential_attachment=True, recipient_domain=gmail.com
6. PolicyEngine: condition matches "block_confidential_attachment_external"
7. DecisionExplainer: risk_score=98, decision=block, timeline=[5 steps]
8. AuditStore.write({action: "block", risk_score: 98, ...})
9. Return {status: "blocked", risk_score: 98, rule_id: "block_confidential_attachment_external"}
10. Gemini receives error feedback in conversation history
11. Dashboard shows new blocked event in real-time

→ Gmail API is NEVER called. The attachment never leaves the system.
```

---

## Security Layers Summary

| Layer | Name | Implementation |
|---|---|---|
| 1 | Authentication | `role == 'anonymous'` → immediate block |
| 2 | Session Integrity | `not agent_id` → immediate block |
| 3 | RBAC | Guest/intern/support tool restrictions |
| 4 | Temporal Context | After-hours sends → HITL |
| 5 | Data Classification | Confidential attachment keywords |
| 6 | Cumulative Detection | 5-min rolling delete/archive window |
| 7 | Rate Limiting | 10 calls/min per agent+tool |
| 8 | Escalating Enforcement | ≥3 violations → all actions HITL |
| 9 | HITL Standard Rules | External email/forward → Human approval |
