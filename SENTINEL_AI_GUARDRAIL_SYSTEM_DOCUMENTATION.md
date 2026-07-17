# 🛡️ SentinelAI: Autonomous Agentic AI Inbox Guardian & Governance Engine
> **System Architecture, Policy Evaluator Logic, Phishing Rules Engine, and Guardrail Pipeline Documentation**

---

## 📋 1. Executive Summary & Core Purpose

**SentinelAI** is an enterprise-grade **Agentic AI System** designed to act as an **Autonomous Inbox Guardian & Security Governance Engine**. 

Unlike standard reactive AI chatbots that wait passively for user instructions, SentinelAI operates **autonomously and continuously**:
1. **Monitors Environment:** Listens to incoming email events via live Google Gmail API or simulated enterprise inbox feeds.
2. **Autonomous Analysis & Planning:** Uses Groq Llama-3.3-70B and Google Gemini 2.5 Flash to evaluate incoming communications, recognize security threats, and formulate action plans (e.g., reply, archive, delete, forward, or escalate).
3. **Multi-Layered Guardrail Governance:** Intercepts every single tool invocation through a 9-Layer Policy Evaluator Engine before execution.
4. **Governed Execution:** Executes safe actions, quarantees security threats into a disk vault, and pauses risky operations into an interactive **Human-in-the-Loop (HITL)** approval queue.

```text
               +-------------------------------------------------------+
               |             INCOMING EMAIL / INBOX EVENT               |
               +-------------------------------------------------------+
                                           |
                                           v
               +-------------------------------------------------------+
               |        SENTINELAI AUTONOMOUS MONITOR DEAMON LOOP      |
               +-------------------------------------------------------+
                                           |
                                           v
               +-------------------------------------------------------+
               |        6-CATEGORY PHISHING CLASSIFICATION ENGINE       |
               | (Domain, Credential, Financial, Urgency, Link, File)  |
               +-------------------------------------------------------+
                         /                                   \
                        /                                     \
        [THREAT DETECTED]                             [NEEDS PLANNING]
                      /                                         \
                     v                                           v
+------------------------------------------+   +------------------------------------------+
|  INSTANT GUARDIAN AUTO-QUARANTINE        |   |    LLM AUTONOMOUS AGENT PLANNER          |
|  - Move to Trash                         |   |    - Groq Llama-3.3-70B                  |
|  - Store full email in Threat Vault      |   |    - Google Gemini 2.5 Flash              |
|  - Notify Guardian Agent Console         |   |    - Proposes Tool Invocation            |
+------------------------------------------+   +------------------------------------------+
                     \                                           /
                      \                                         /
                       v                                       v
               +-------------------------------------------------------+
               |         EXECUTION GATEWAY INTERCEPTOR LAYER           |
               +-------------------------------------------------------+
                                           |
                                           v
               +-------------------------------------------------------+
               |       9-LAYER POLICY GUARDRAIL EVALUATOR ENGINE       |
               | (RBAC, Policy v1/v2/v3, DLP, Temporal, Rate Limits)   |
               +-------------------------------------------------------+
                   /                       |                       \
                  /                        |                        \
         [ALLOWED]                     [PAUSED]                    [BLOCKED]
            /                              |                            \
           v                               v                             v
+-----------------------+     +------------------------+     +------------------------+
|  EXECUTE ACTION LIVE  |     |  HUMAN-IN-THE-LOOP     |     | REJECT & AUDIT LOG     |
|  - Live Gmail API     |     |  REVIEW QUEUE (HITL)   |     | - Write to audit_store |
|  - Update Inbox UI    |     |  - Operator Approval   |     | - Show UI Block Alert  |
|  - Tag [REPLIED]      |     |  - Operator Rejection  |     | - Counter Increment    |
+-----------------------+     +------------------------+     +------------------------+
```

---

## ⚙️ 2. Technologies, Frameworks & Infrastructure

| Layer / Subsystem | Technology / Library | Usage & Responsibility |
| :--- | :--- | :--- |
| **Backend Core** | Python 3.11+, FastAPI (ASGI) | Asynchronous web API server, state management, router mounting, dependency injection. |
| **Server Process** | Uvicorn | High-performance ASGI server running on port 8000. |
| **LLM Agent Planners** | Groq API (`llama-3.3-70b-versatile`), Google GenAI (`gemini-2.5-flash`) | Autonomous email analysis, action planning, natural language explanation generation. |
| **Email Connector** | Google Gmail API v1 (`google-api-python-client`, OAuth2) | Production live connector for OAuth2 credentials, MIME text/multipart parsing, message fetching, label modification, live sending/replying. |
| **Policy Engine** | Custom Declarative Evaluator Engine (`app/middleware/evaluator.py`, `app/policies/`) | Multi-layered rule evaluation, role parsing, risk scoring, remediation engine. |
| **Frontend Visualizer** | HTML5, Vanilla JavaScript (ES6+), Vanilla CSS | Dark-mode glassmorphism visualizer dashboard, real-time polling, modal overlays, interactive HITL queue. |
| **Persistence Layer** | JSON File Stores (`data/quarantine_vault.json`, `data/replied_emails.json`, `data/audit_store.json`), SQLite (`audit.db`) | Disk-backed storage for threat vaults, audit logs, and replied message tracking. |
| **Testing Suite** | Pytest | 49 automated test suites verifying governance layers, scenario benchmarks, and connector integrations. |

---

## 🎣 3. Enterprise Phishing Classification Engine (6 Categories)

Located in `app/agent/phishing_detector.py`, the Phishing Classification Engine evaluates emails across **6 distinct threat vectors** and calculates a dynamic risk score from 0 to 100:

```python
# Location: app/agent/phishing_detector.py
```

### Threat Categories & Indicator Vectors

```text
1. Spoofed / Fraudulent Sender Domains:
   Triggers: amaz0n, paypa1, micros0ft, apple-support, g00gle, secure-bank, verify-account,
             security-update, admin-support, alert-system, phish, hacker, fake, scam, lottery,
             wire-transfer, crypto-wallet, customer-service-update, noreply-security, bank-verify.

2. Credential Harvesting & Password Traps:
   Triggers: reset password, update password, change your password, password expired,
             verify credentials, login to verify, confirm identity, two-factor, mfa reset,
             account verification, enter pin, security code, password.

3. Financial & Banking Exploitation:
   Triggers: bank account, credit card, debit card, wire transfer, routing number, bank details,
             billing information, payment failure, unauthorized transaction, invoice attached,
             overdue invoice, gift card, bitcoin, crypto transfer, claim prize, lottery winner,
             refund pending, tax refund.

4. High-Pressure Urgency Tactics:
   Triggers: urgent, immediate action required, account suspended, account terminated,
             within 24 hours, within 2 hours, act now, final warning, security breach,
             unauthorized access, suspicious login, unusual activity, action required.

5. Suspicious Call-To-Action Links:
   Triggers: click here, click the link, log in now, update details, verify now,
             download attachment, open link, claim now.

6. High-Risk Executable & Sensitive File Attachments:
   Triggers: password, passwords, credential, salary_sheet, keylog, malware,
             .exe, .scr, .vbs, .bat, .cmd, .js, .xlsm.
```

---

## 🛡️ 4. The 9-Layer Policy Evaluator & Guardrail Pipeline

Every tool execution initiated by an AI Agent, user action, or background thread must pass through the **Execution Gateway** (`app/agent/execution_gateway.py`), which invokes the 9-Layer Policy Evaluator (`app/middleware/evaluator.py`).

```text
                               +----------------------------------+
                               |    TOOL INVOCATION INTERCEPTED   |
                               +----------------------------------+
                                                |
                                                v
 +-----------------------------------------------------------------------------------------------+
 | LAYER 1: Role-Based Access Control (RBAC Check)                                               |
 | LAYER 2: Declarative Policy Rule Matcher (Version v1 / v2 / v3)                               |
 | LAYER 3: Sensitive File & Data Leak Protection (DLP)                                          |
 | LAYER 4: External Recipient Data Exfiltration Interceptor                                     |
 | LAYER 5: Temporal Governance & After-Hours Operation Inspector                                |
 | LAYER 6: Cumulative Rate Limiter & Anomaly Detection (Deletes/Min)                            |
 | LAYER 7: Repeat Violator Escalation Tracker                                                   |
 | LAYER 8: Human-in-the-Loop (HITL) Authoritative Review Queue                                  |
 | LAYER 9: AI Risk Assessor & Explanation Remediation Engine                                    |
 +-----------------------------------------------------------------------------------------------+
                                                |
                                                v
                                  EVALUATION RESULT DECISION
```

### Breakdown of the 9 Guardrail Layers:

1. **Layer 1: Role-Based Access Control (RBAC):**
   * Verifies if the active operator role (`guest`, `junior_dev`, `dev`, `senior_dev`, `admin`, `system_guardian`) is authorized to execute the target tool (`gmail_delete_email`, `gmail_send_email`, `db_delete`, etc.).
2. **Layer 2: Declarative Policy Rules Engine:**
   * Evaluates input conditions against active policy versions (`v1`, `v2`, `v3`). Supports dynamic hot-swapping between policy versions without restarting the application.
3. **Layer 3: Sensitive Data & File Leak Protection (DLP):**
   * Intercepts attempts to delete or transfer sensitive attachments (e.g., `salary_2026.xlsx`, `passwords.xlsx`, `confidential_*.pdf`).
4. **Layer 4: External Recipient Interception:**
   * Detects emails or forwards sent to external domains (`@external.com`, `@external-biz.com`). Enforces mandatory HITL approval.
5. **Layer 5: Temporal & After-Hours Governance:**
   * Evaluates current timestamp against company working hours (8:00 AM – 6:00 PM). Flags after-hours operations for operator authorization.
6. **Layer 6: Cumulative Rate Limiting & Bulk Anomaly Detection:**
   * Tracks cumulative deletions per minute per agent. If deletions exceed 5 operations in 5 minutes, it triggers a bulk-deletion alert and pauses execution.
7. **Layer 7: Repeat Violator Escalation:**
   * Tracks historical policy violations per agent ID. Automatically escalates repeat offenders to mandatory HITL review.
8. **Layer 8: Human-in-the-Loop (HITL) Review Queue:**
   * When an action status is `PENDING`, execution is paused, and a request object is enqueued into `app.state.hitl_queue`. The action cannot execute until an authorized human operator clicks **Approve** or **Reject** in the UI.
9. **Layer 9: AI Security Risk Evaluator & Remediation Engine:**
   * Calculates aggregated risk score (0–100), determines risk classification (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), and generates clear natural language explanations and remediation suggestions.

---

## 📊 5. Policy Evaluator Rules Reference Table

| Rule ID | Policy Version | Trigger Condition | Action / Status | Risk Score | Remediation / Explanation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `RULE_GUEST_DELETE_BLOCKED` | `v1`, `v2`, `v3` | `role == "guest"` AND `tool == "gmail_delete_email"` | **`BLOCKED`** | 90 | Guest role is not permitted to delete email records. |
| `RULE_CONFIDENTIAL_EXTERNAL_BLOCKED` | `v1`, `v2`, `v3` | Attachment contains `"confidential"` OR `"salary"` AND recipient is external | **`BLOCKED`** | 95 | Confidential files cannot be transmitted to external domains. |
| `RULE_UNAUTHENTICATED_AGENT_BLOCKED` | `v1`, `v2`, `v3` | `role == "anonymous"` OR `agent_id == "unknown"` | **`BLOCKED`** | 100 | Unauthenticated agent access is strictly prohibited. |
| `RULE_EXTERNAL_RECIPIENT_HITL` | `v2`, `v3` | Recipient domain is external (e.g. `@external.com`) | **`PENDING` (HITL)** | 50 | Outbound communications to external parties require manager approval. |
| `RULE_BULK_DELETE_HITL` | `v2`, `v3` | `record_count > 3` OR cumulative deletes $> 5$ | **`PENDING` (HITL)** | 75 | Bulk record deletion exceeds automated threshold; operator review required. |
| `RULE_AFTER_HOURS_HITL` | `v3` | Time outside 08:00–18:00 | **`PENDING` (HITL)** | 60 | Operations outside business hours require manual oversight. |
| `RULE_REPEAT_VIOLATOR` | `v3` | Violation count $> 2$ for agent | **`PENDING` (HITL)** | 85 | Agent has multiple policy violations; execution paused for audit. |
| `RULE_RATE_LIMIT_EXCEEDED` | `v1`, `v2`, `v3` | Invocations $> 10$ per minute | **`BLOCKED`** | 80 | Rate limit exceeded. Request throttled. |
| `RULE_PHISHING_AUTO_QUARANTINE` | System | Phishing risk score $\ge 35$ | **`BLOCKED` (Auto-Trash)** | 100 | Phishing threat detected. Automatically deleted and archived in vault. |

---

## 💾 6. Persistence Architecture & Vault Storage

SentinelAI uses a tri-vault persistence strategy to ensure data integrity across application restarts:

```text
                                +----------------------------------+
                                |   PERSISTENCE STORAGE ARCHITECTURE|
                                +----------------------------------+
                                                 |
         +---------------------------------------+---------------------------------------+
         |                                       |                                       |
         v                                       v                                       v
+---------------------------------+    +---------------------------------+    +---------------------------------+
| QUARANTINED THREAT VAULT        |    | AUDIT STORE DISK TRAIL          |    | REPLIED MESSAGES TRACKER        |
| File: data/quarantine_vault.json|    | File: data/audit_store.json     |    | File: data/replied_emails.json  |
| Saves full body, sender, date,  |    | Appends all gateway evaluation  |    | Tracks message IDs that have    |
| risk score 100, and threat logs |    | logs, risk scores, and reasons  |    | been replied to by agent/user   |
+---------------------------------+    +---------------------------------+    +---------------------------------+
```

1. **Quarantined Threat Vault (`data/quarantine_vault.json`):**
   * Preserves every deleted threat email with its full text, sender, date, risk score 100, and threat reason.
2. **Governance Audit Store (`data/audit_store.json` & `audit.db`):**
   * Appends every single evaluation event, policy decision, role, risk score, and timestamp for compliance auditing.
3. **Replied Email Tracker (`data/replied_emails.json`):**
   * Tracks message IDs that have been answered. Prevents duplicate automated replies and renders the green `[REPLIED]` badge and `✓ Replied` button in the UI.

---

## 🖥️ 7. Real-Time Dashboard & User Interface Features

The visualizer dashboard (`app/dashboard/templates/index.html`) provides interactive controls:

```text
+----------------------------------------------------------------------------------------------------+
| SENTINELAI GOVERNANCE DASHBOARD                                                                    |
+----------------------------------------------------------------------------------------------------+
| METRICS TILE: Total Actions: 10  | Allowed: 30%  | HITL Paused: 0  | Blocked: 0% | Risk Score: 16  |
+----------------------------------+-----------------------------------------------------------------+
| SIMULATED INBOX VISUALIZER       | GUARDIAN AGENT CONSOLE & THREAT VAULT                           |
| Buttons:                         | - 🛡️ Guardian Console Alerts                                    |
| [🚨 Phishing Attack]             | - ☣️ Quarantined Threat Vault & Saved Logs                      |
| [💼 Payroll Audit]               | - 🚨 Human-in-the-Loop Review Queue                             |
| [👑 CEO VIP]                     | - 🛡️ Live Policy Interceptor Inspector                           |
| [💳 Expense Claim]               |                                                                 |
| [💬 Ask for Reply]               |                                                                 |
|                                  |                                                                 |
| Email Cards Rendering:           |                                                                 |
| - Badges: [UNREAD] [REPLIED]     |                                                                 |
| - Actions: Archive, Delete,      |                                                                 |
|   [🤖 Ask Agent to Reply]        |                                                                 |
+----------------------------------+-----------------------------------------------------------------+
| GOVERNANCE AUDIT LOGS TABLE                                                                        |
| Timestamp | Agent | Action | Role | Status | Risk Score | Reason / Remediation Summary          |
+----------------------------------------------------------------------------------------------------+
```

---

## 🛠️ 8. Installation, Configuration & Execution Guide

### Prerequisites
* Python 3.11 or higher
* PowerShell / Terminal
* Google Gmail API credentials (`credentials.json` & `token.json` optional for live mode)

### 1. Clone & Environment Setup
```bash
# Clone repository
git clone <repository_url>
cd guardrail_agent

# Create virtual environment
python -m venv venv

# Activate virtual environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables (`.env`)
Create a `.env` file in the project root:
```env
PORT=8000
POLICY_VERSION=v3
DRY_RUN_MODE=false
ENABLE_MONITOR=true
MONITOR_INTERVAL=15
GROQ_API_KEY=your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
```

### 3. Run Automated Unit & Integration Tests
```bash
pytest tests/ -v
```
*Output: `49 passed`*

### 4. Launch Application Server
```bash
python -m uvicorn app.main:app --port 8000
```

### 5. Open Dashboard
Navigate to `http://127.0.0.1:8000` in your web browser. Perform a **Hard Refresh** (`Ctrl + F5`) to load the visualizer dashboard.

---

## 📄 9. Project File Map

```text
guardrail_agent/
├── app/
│   ├── agent/
│   │   ├── execution_gateway.py     # Execution Interceptor Gateway
│   │   ├── gmail_connector.py       # Live & Mock Gmail API Connector
│   │   ├── monitor.py               # Autonomous Background Inbox Monitor
│   │   └── phishing_detector.py     # 6-Category Phishing Classification Engine
│   ├── audit/
│   │   ├── store.py                 # Audit Store Persistence Engine
│   │   └── routes.py                # Audit API Endpoints
│   ├── context/
│   │   └── builder.py               # Context Builder for Policy Evaluation
│   ├── dashboard/
│   │   ├── routes.py                # Dashboard & Simulation Routes
│   │   └── templates/
│   │       └── index.html           # Dark-Themed Dashboard Visualizer UI
│   ├── explanation/
│   │   └── explainer.py             # Remediation & Risk Assessor Engine
│   ├── hitl/
│   │   ├── queue.py                 # Human-in-the-Loop Queue Store
│   │   └── routes.py                # HITL Review API Endpoints
│   ├── middleware/
│   │   └── evaluator.py             # 9-Layer Policy Evaluator Engine
│   ├── policies/
│   │   ├── v1_baseline.yaml         # Baseline Policies
│   │   ├── v2_standard.yaml         # Standard Enterprise Policies
│   │   └── v3_strict.yaml           # Strict Enterprise Guardrail Policies
│   ├── config.py                    # Application Configuration Settings
│   └── main.py                      # FastAPI Application Entry Point
├── data/
│   ├── audit_store.json             # Persistent Audit Log Store
│   ├── quarantine_vault.json        # Persistent Quarantined Threat Vault
│   └── replied_emails.json          # Persistent Replied Email Tracker
├── tests/                           # 49 Automated Pytest Suite
├── SENTINEL_AI_GUARDRAIL_SYSTEM_DOCUMENTATION.md # Complete System Architecture Guide
├── requirements.txt                 # Project Dependencies
└── README.md                        # Primary Project Overview
```

---
*Document Generated for SentinelAI System Architecture & Policy Guardrail Reference.*
