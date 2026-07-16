# SentinelAI — Project Summary & Problem Statement

This document explains what this project does and the problem statement it solves in simple, clear English.

---

## 1. The Problem Statement

**The Security Risk of Autonomous AI Agents:**
As Artificial Intelligence (AI) advances, AI Agents are transitioninig from simply answering questions (like ChatGPT) to taking actions in the real world (e.g., sending emails, deleting database records, running code, and managing files). 

However, giving AI Agents direct access to real-world tools creates massive security risks:
- What if an AI Agent accidentally deletes 10,000 corporate emails?
- What if an external attacker tricks the AI Agent into emailing a confidential spreadsheet (like payroll) to a competitor?
- What if a guest or intern uses the AI Agent to perform actions they are not authorized to do?
- What if the AI Agent goes into an infinite loop and runs thousands of API calls, costing the company thousands of dollars?

**The Core Challenge:**
There must be a security barrier—a guardrail—that intercepts every action an AI Agent wants to make, inspects it against company policies, scores its risk, asks for human approval if needed, and logs everything, **before** the action is actually executed.

---

## 2. What SentinelAI Does

**SentinelAI** is an **Enterprise Runtime AI Governance Platform**. It acts as a safety firewall between the AI Agent and the real world (like the Gmail API or corporate databases).

Here is how it works step-by-step when an agent tries to run a command:

```
[ AI Agent ] ────(wants to call tool)────► [ SentinelAI Guardrail ] ────(checks policy)────► [ Execution Gateway ] ────► [ Gmail / Real World ]
                                                  │
                                                  ├─► RISK < 30: ALLOWED immediately
                                                  ├─► RISK 31-70: PAUSED (Requires Human-in-the-Loop Approval)
                                                  └─► RISK > 70: BLOCKED immediately
```

1. **Interception**: When the AI Agent decides to call a tool (e.g., `gmail_send_email` or `db_delete`), the call is intercepted by SentinelAI's **Execution Gateway**.
2. **Context Building**: SentinelAI gathers details about the request:
   - Who is running it? (Role: Admin, Developer, Junior Developer, Guest, Anonymous)
   - When is it happening? (Business hours vs. after-hours)
   - What data is involved? (Confidential vs. public)
   - How frequent are the actions? (Rate limits, cumulative checks)
3. **Policy Evaluation**: The Guardrail evaluates the request against security rules defined in a YAML configuration file. It uses a **9-Layer Governance Engine**:
   - *Layer 1 (Authentication)*: Blocks anonymous requests.
   - *Layer 3 (RBAC)*: Restricts tool access by role (e.g., guest cannot delete database records).
   - *Layer 5 (Data Classification)*: Blocks sending confidential files to external domains.
   - *Layer 6 (Cumulative Detection)*: Pauses bulk operations (e.g., deleting multiple emails in a short window).
   - *Layer 7 (Rate Limiting)*: Blocks high-frequency spam actions.
4. **Risk Scoring (0 to 100)**: SentinelAI aggregates the metrics and assigns a Risk Score.
5. **Enforcement Decisions**:
   - **Allowed**: Runs the tool immediately and logs the action.
   - **Paused (Human-in-the-Loop / HITL)**: The request is held in a queue. A human reviewer must click "Approve" on the dashboard before it executes.
   - **Blocked**: The action is stopped, and a remediation advice is returned.
6. **Audit Logging**: Every single decision is logged permanently for compliance checks.

---

## 3. Key Components & Environment Adaptations

- **Visual Dashboard**: A clean web control center where administrators can monitor actions in real time, view audit histories, and review the **Human-in-the-Loop** queue to approve or reject paused operations.
- **Gmail Connector (Hybrid Dual-Mode)**:
  - **Live Mode**: When authorized via OAuth, the connector sends and deletes actual emails in your Gmail inbox.
  - **Mock Mode**: If no credentials exist, it falls back to a simulated inbox in memory so you can test attacks and policies safely without polluting a real mailbox.
  - **Zscaler/Proxy Bypass**: Configured with strict custom certificate bypasses to ensure live API calls and OAuth renewals succeed behind corporate proxy/Zscaler interceptors.
  - **Thread-Safety**: Utilizes thread-local storage (`threading.local()`) so FastAPI handles multiple concurrent dashboard polls and agent runs without network socket conflicts.
