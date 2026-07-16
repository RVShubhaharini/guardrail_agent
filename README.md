# SentinelAI — Enterprise Runtime AI Governance Platform

> **This is not an email client. This is the security layer that sits between an AI Agent and the real world.**

[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com)
[![Gemini 2.5](https://img.shields.io/badge/Gemini-2.5--Flash-orange.svg)](https://ai.google.dev)
[![AWS ECS](https://img.shields.io/badge/AWS-ECS%20Fargate-FF9900.svg)](https://aws.amazon.com/ecs/)
[![DynamoDB](https://img.shields.io/badge/AWS-DynamoDB-FF9900.svg)](https://aws.amazon.com/dynamodb/)

---

## What Is SentinelAI?

SentinelAI is an **Enterprise Runtime AI Governance Platform** — a production-grade middleware layer that intercepts, evaluates, and controls every tool call an AI Agent wants to execute **before it reaches the real world**.

```
           Gemini 2.5 Agent
                  │
     "Send payroll.xlsx to competitor@gmail.com"
                  │
                  ▼
       ┌──────────────────────┐
       │   SentinelAI Engine  │
       │                      │
       │  ① Auth Verification │
       │  ② RBAC Check        │
       │  ③ Policy Engine     │
       │  ④ Risk Scoring      │
       │  ⑤ Context Analysis  │
       │  ⑥ HITL Queue        │
       │  ⑦ Audit Logging     │
       └──────────────────────┘
                  │
          BLOCKED — Risk: 98
          Rule: block_confidential_attachment_external
```

Gmail is the **first connector** in a multi-connector architecture. The same governance engine protects AWS, Slack, GitHub, and Google Drive — with zero changes to the policy, HITL, or audit systems.

---

## Why This Matters

AI Agents are becoming powerful enough to execute real-world actions:

| Action | Without Governance | With SentinelAI |
|---|---|---|
| `Delete 500 emails` | Executes immediately | Requires HITL approval |
| `Send salary.pdf to external` | Executes immediately | **BLOCKED** (Risk: 98) |
| `Forward confidential to rival` | Executes immediately | **BLOCKED** (Risk: 99) |
| `11th API call in 60 seconds` | Executes | **BLOCKED** (Rate limit) |
| `Anonymous agent requesting tool` | Executes | **BLOCKED** (Risk: 100) |

This is the problem that Microsoft Copilot, Google Gemini Enterprise, and OpenAI Agents all need to solve. **SentinelAI is that solution.**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     SentinelAI Platform                     │
│                                                             │
│  ┌─────────┐    ┌──────────────────────────────────────┐   │
│  │ Gemini  │───▶│         GuardrailEvaluator           │   │
│  │  Agent  │    │                                      │   │
│  └─────────┘    │  PolicyEngine  ──▶  YAML Rule Sets   │   │
│                 │  ContextBuilder──▶  9-Layer Context  │   │
│  ┌─────────┐    │  RiskScorer    ──▶  0-100 Score      │   │
│  │  REST   │───▶│  DecisionExplainer ▶ Timeline        │   │
│  │   API   │    │  HitlQueue     ──▶  Approval Flow    │   │
│  └─────────┘    │  AuditStore    ──▶  SQLite/DynamoDB  │   │
│                 └──────────────────────────────────────┘   │
│                              │                              │
│                     ExecutionGateway                        │
│                    (Only authorized                         │
│                   component to execute)                     │
│                              │                              │
│           ┌──────────────────┼──────────────────┐          │
│           ▼                  ▼                  ▼          │
│      Gmail API          [AWS Next]        [Slack Next]     │
│      Connector          Connector         Connector        │
└─────────────────────────────────────────────────────────────┘
```

---

## 9-Layer Governance Engine (v3 Policy)

| Layer | Rule | What It Catches |
|---|---|---|
| **1** | Authentication | Anonymous / unauthenticated agents |
| **2** | Session Integrity | Invalid agent IDs, session hijacking |
| **3** | RBAC | Guest/intern/support unauthorized tool access |
| **4** | Temporal Context | After-hours sends requiring HITL |
| **5** | Data Classification | Confidential attachments to external domains |
| **6** | Cumulative Detection | Bulk delete bypass (>3 emails in 5 min → HITL) |
| **7** | Rate Limiting | >10 calls/minute → Block |
| **8** | Repeat Violators | ≥3 violations → Escalating enforcement |
| **9** | HITL Standard | Any external email → Human approval |

---

## Key Features

### ✅ Real Gemini 2.5 Flash AI Agent
- Accepts natural language instructions (`"Send salary.pdf to partner@gmail.com"`)
- Generates structured tool calls using Google GenAI function calling
- Tool calls intercepted **before execution** by the governance engine

### ✅ Multi-Version Policy Engine
- YAML-based rule sets (`v1`, `v2`, `v3`)
- Switch policy version at runtime via API: `POST /policy/version?version=v3`
- Industry templates: `finance`, `healthcare`, `retail`
- Hot-swap without restarting the server

### ✅ Human-in-the-Loop (HITL) Queue
- High-risk actions automatically paused for human approval
- `GET /hitl/pending` — see what's waiting
- `POST /hitl/{id}/approve` — approve and execute
- `POST /hitl/{id}/reject` — reject and notify agent
- DynamoDB-backed on AWS — **survives container restarts**

### ✅ Complete Audit Trail
- Every action (allowed, blocked, pending) written to audit store
- SQLite in local dev, DynamoDB in AWS production
- Searchable: `GET /audit?agent_id=X&action=blocked`

### ✅ Enterprise Dashboard
- Real-time governance metrics
- Live approval queue
- Policy version switcher
- Gemini AI chat interface with governance overlay
- Risk score visualizations

### ✅ Multi-Connector Architecture
- Gmail is **Connector #1** — used to demonstrate governance
- Same engine, zero code changes to plug in AWS, Slack, GitHub, Drive
- `GET /connector/status` shows all registered connectors

---

## Quick Start — Local Development

```bash
# 1. Clone and create virtual environment
cd d:/now_new
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate    # Linux/Mac

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
copy .env.example .env
# Edit .env: add your GEMINI_API_KEY

# 4. Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 5. Open the dashboard
# http://localhost:8000/

# 6. View API documentation
# http://localhost:8000/docs

# 7. Run governance simulation (all 9 layers)
python scripts/simulate.py

# 8. Run automated tests
pytest tests/ -v
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Governance Dashboard UI |
| `GET` | `/health` | System health + policy version |
| `POST` | `/agent/run` | Run Gemini AI agent with governance |
| `POST` | `/evaluate` | Evaluate any tool call against policy |
| `POST` | `/gmail/action` | Execute Gmail action through governance |
| `GET` | `/gmail/inbox` | List emails (real or mock) |
| `GET` | `/hitl/pending` | List pending HITL approvals |
| `POST` | `/hitl/{id}/approve` | Approve a HITL request |
| `POST` | `/hitl/{id}/reject` | Reject a HITL request |
| `GET` | `/audit` | Query audit log |
| `GET` | `/policy/config` | Get active rules + version |
| `POST` | `/policy/version` | Switch policy version |
| `POST` | `/policy/template` | Load industry template |
| `GET` | `/connector/status` | View all connector statuses |
| `GET` | `/docs` | FastAPI Swagger UI |

---

## Enterprise Network & Reliability Engineering

SentinelAI includes robust design considerations for enterprise local development and security environments:
- **SSL Interception / Zscaler Bypass**: Automatically bypasses common `[SSL: WRONG_VERSION_NUMBER]` errors in proxy-monitored corporate networks by configuring custom `httplib2` and `requests` sessions with certificate validation disabled for Google API and OAuth token refresh endpoints.
- **Hybrid Mailbox Handling**: Intelligently routes mock message IDs (prefixed with `msg_`) to the simulated state database and real message IDs to the Gmail API. This allows developers to seamlessly test governance rules on both actual and mock emails in Live mode without triggering 404/not found exceptions.

---

## AWS Deployment

SentinelAI is production-ready for AWS deployment:

```bash
# Prerequisites: Docker, AWS CLI configured

# Set your Gemini API key
export GEMINI_API_KEY="your-key-here"

# Deploy to AWS (ECS Fargate + ALB + DynamoDB)
bash infra/deploy.sh
```

The CloudFormation stack provisions:
- **ECS Fargate** — containerized, auto-scaling
- **Application Load Balancer** — public HTTPS endpoint
- **DynamoDB** — persistent audit log (pay-per-request)
- **Secrets Manager** — Gemini API key (never in plaintext)
- **CloudWatch** — container logging (30-day retention)
- **IAM Roles** — least-privilege task execution

---

## Demo Scenarios (For Recruiters & Interviews)

### Scenario 1: AI tries to exfiltrate data
> *"Send salary.xlsx to competitor@gmail.com"*

SentinelAI detects confidential attachment + external domain → **BLOCKED instantly** (Risk: 98)

### Scenario 2: Bulk delete attempt
> *"Delete all emails from this week"*

First 3 deletions allowed → 4th triggers bulk detection → **HITL approval required**

### Scenario 3: Anonymous agent
> Any tool call with `role=anonymous`

Immediately **BLOCKED** with Risk Score 100, even before reaching the Gmail API

### Scenario 4: Human approves a flagged action
> Admin reviews `/hitl/pending`, clicks Approve

Action executes through ExecutionGateway, audit log updated, agent notified

### Scenario 5: Policy version switch
> Switch from `v1` (2 rules) to `v3` (16 rules) live via dashboard

Zero downtime, instant enforcement of new rules on the next tool call

---

## Project Structure

```
sentinelai/
├── app/
│   ├── agent/
│   │   ├── sample_agent.py      # Gemini 2.5 Flash agent + mock fallback
│   │   ├── gmail_connector.py   # Gmail API (live + mock dual-mode)
│   │   └── execution_gateway.py # Only authorized executor
│   ├── middleware/
│   │   └── evaluator.py         # GuardrailEvaluator (the core interceptor)
│   ├── policy/
│   │   ├── engine.py            # YAML rule loader + simpleeval evaluator
│   │   ├── templates.py         # Industry template rulesets
│   │   └── rules/
│   │       ├── v1.yaml          # Basic rules (2 rules)
│   │       ├── v2.yaml          # Intermediate (5 rules)
│   │       └── v3.yaml          # Full 9-layer enterprise (16 rules)
│   ├── context/
│   │   └── builder.py           # 9-layer security context builder
│   ├── explanation/
│   │   └── explainer.py         # Risk scoring + governance timeline
│   ├── hitl/
│   │   ├── queue.py             # HITL queue (DynamoDB-persistent on AWS)
│   │   └── routes.py            # Approve/reject endpoints
│   ├── audit/
│   │   ├── store.py             # SQLite (dev) + DynamoDB (AWS) dual-mode
│   │   └── routes.py            # Audit search endpoints
│   ├── dashboard/
│   │   └── templates/index.html # Enterprise governance dashboard
│   └── main.py                  # FastAPI app + all route registration
├── infra/
│   ├── cloudformation.yaml      # Complete AWS production stack
│   └── deploy.sh                # One-command AWS deployment
├── scripts/
│   └── simulate.py              # 9-layer governance demonstration
├── tests/
│   ├── test_governance_pipeline.py  # Integration tests
│   ├── test_policy_engine.py        # Policy engine unit tests
│   └── test_scenarios.py            # Scenario-based tests
├── Dockerfile                   # Production container
├── docker-compose.yml           # Local multi-service compose
├── requirements.txt
└── .env.example
```

---

## Tech Stack

| Component | Technology |
|---|---|
| AI Agent | Google Gemini 2.5 Flash (function calling) |
| Backend | FastAPI + Python 3.11 |
| Policy Engine | YAML + simpleeval (sandboxed expression evaluation) |
| Audit Store | SQLite (dev) / AWS DynamoDB (production) |
| Container | Docker + AWS ECS Fargate |
| Load Balancer | AWS Application Load Balancer |
| Secrets | AWS Secrets Manager |
| Logs | AWS CloudWatch |
| Gmail | Google Gmail API v1 (OAuth2 + stateful mock) |

---

*SentinelAI — Governance before execution. Safety at the edge.*
