# SentinelAI -- Enterprise AI Runtime Governance Platform

## Vision

SentinelAI is an enterprise AI Runtime Governance Platform. Gmail is the
first production connector. The governance engine is reusable for future
connectors.

## Core Flow

User -\> Gemini -\> Structured Tool Call -\> ActionGuard Engine -\>
Identity -\> Authorization -\> Context Builder -\> Risk Engine -\>
Policy Engine -\> Decision Engine -\> Execution Gateway -\> Gmail API
-\> Audit -\> Dashboard

## Modules

-   Gemini: Understand intent, produce tool calls, classify attachments.
-   Identity: Verify user.
-   Authorization: RBAC.
-   Context Builder: Time, recipient, attachment, history.
-   Risk Engine: Compute risk score.
-   Policy Engine: YAML-based policies.
-   Decision Engine: ALLOW / BLOCK / HITL.
-   Execution Gateway: Only component allowed to invoke Gmail.
-   Gmail Connector: Send, Read, Search, Delete, Archive, Restore,
    Reply, Forward, Labels.
-   Audit Engine: Persist all decisions.
-   Dashboard: Metrics, logs, approvals.

## Policies

Examples: - External confidential email -\> HITL - Blacklisted domain
-\> BLOCK - Delete inbox -\> HITL - Intern delete -\> BLOCK - Unknown
user -\> BLOCK

## Gmail Flow

1.  User requests action.
2.  Gemini creates JSON tool call.
3.  Governance validates.
4.  If allowed, Execution Gateway calls Gmail API.
5.  Store audit log.
6.  Update dashboard.

## Advanced Features

-   Decision Cards
-   Policy Playground
-   Governance Replay
-   Policy Versioning
-   Attachment Classification
-   Business Hour Policies
-   Rate Limiting
-   Cumulative Action Detection
-   Searchable Audit Logs

## AWS

Docker -\> FastAPI -\> EC2 -\> Gmail API -\> Gemini API. Future: RDS,
Secrets Manager, CloudWatch.

## Goal

Build a production-oriented MVP emphasizing modularity, extensibility,
documentation, and end-to-end functionality.
