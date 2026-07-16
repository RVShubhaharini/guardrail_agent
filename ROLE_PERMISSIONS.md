# SentinelAI — Role Permission Matrix (RBAC)

This document maps what operations each operator role can perform when executing tools through SentinelAI.

---

## 1. Role Matrix Overview

| Operation / Tool | Anonymous | Guest | Intern / Support | Junior Developer | Administrator |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Direct Internal Emails** | 🚫 Blocked | 🟢 Allowed | 🟢 Allowed | 🟢 Allowed | 🟢 Allowed |
| **External Emails (Gmail)** | 🚫 Blocked | 🚫 Blocked | 🚫 Blocked | ⚡ Require HITL | ⚡ Require HITL |
| **Database Read** | 🚫 Blocked | 🟢 Allowed | 🟢 Allowed | 🟢 Allowed | 🟢 Allowed |
| **Database Write (Daytime)** | 🚫 Blocked | 🟢 Allowed | 🟢 Allowed | 🟢 Allowed | 🟢 Allowed |
| **Database Write (After-Hours)** | 🚫 Blocked | ⚡ Require HITL | ⚡ Require HITL | ⚡ Require HITL | ⚡ Require HITL |
| **Database Delete (≤ 100)** | 🚫 Blocked | 🚫 Blocked | 🚫 Blocked | 🟢 Allowed | 🟢 Allowed |
| **Database Delete (> 100)** | 🚫 Blocked | 🚫 Blocked | 🚫 Blocked | 🚫 Blocked | 🚫 Blocked |
| **Email Delete (Single)** | 🚫 Blocked | 🚫 Blocked | 🟢 Allowed | 🟢 Allowed | 🟢 Allowed |
| **Email Delete (Bulk)** | 🚫 Blocked | 🚫 Blocked | ⚡ Require HITL | ⚡ Require HITL | ⚡ Require HITL |
| **Read Restricted Files** | 🚫 Blocked | 🚫 Blocked | 🚫 Blocked | 🚫 Blocked | 🟢 Allowed |

* **🟢 Allowed**: Executes immediately.
* **⚡ Require HITL**: Pauses execution. Requires approval from the Review Queue on the dashboard.
* **🚫 Blocked**: Prevented immediately.

---

## 2. Granular Role Descriptions

### 👤 Anonymous / Unauthenticated Session
- **Access Level**: None (Zero Trust)
- **Goal**: Blocks rogue scripts, bots, or unauthenticated agent sessions.
- **Rules Triggered**:
  - `block_unauthenticated_agent` (Risk: 100) on any tool call.

### 👤 Guest / Intern / Support Roles
- **Access Level**: Limited Operational Access
- **Goal**: Restricts low-clearance operators to safe internal lookups only.
- **Restrictions**:
  - Cannot delete database records (`restrict_tool_by_agent_role`, Risk: 95).
  - Guests cannot delete emails (`block_guest_delete_email`, Risk: 95).
  - Interns/Support cannot email external domains (`block_intern_external_send`, Risk: 88).
  - Cannot read files marked as `restricted` classification.

### 👤 Junior Developer / Developer Roles
- **Access Level**: Standard Engineering Access
- **Goal**: Allows software development automation while preventing data leakages or bulk destruction.
- **Restrictions**:
  - Cannot read restricted database/file parameters.
  - Deleting records is capped at **100 records** per command.
  - Sending emails, forwarding files, or deleting bulk threads requires **Human-in-the-Loop approval** before execution.

### 👤 Administrator
- **Access Level**: Full Administrative Access
- **Goal**: Grants high-clearance access for system maintenance.
- **Special Capabilities**:
  - Only role authorized to read files classified as `restricted`.
  - Authorized to delete records up to 100 and write database items (after-hours writes still trigger a temporal HITL warning for audit visibility).
