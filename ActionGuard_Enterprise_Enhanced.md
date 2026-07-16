Production Readiness Matters
Solutions will be evaluated on production readiness. A working solution that runs only on localhost will score lower than one that is deployed and governs real AI workloads in a cloud environment. The closer your solution is to something an enterprise could actually adopt, the higher it will be rated.

The following are examples of what production readiness means in practice:
•	A solution deployed on AWS (Lambda, ECS, EKS, or equivalent) that can govern agents also hosted on AWS scores higher than one running on localhost.
•	A solution that handles concurrent requests, persists state, and exposes a usable API scores higher than one that runs as a single script.
•	A solution with logging, error handling, and a basic health check scores higher than one without.
•	A solution that connects to at least one real LLM provider (OpenAI, Anthropic, AWS Bedrock, etc.) scores higher than one using mocked responses only.

Extra points are awarded for deployment quality, integration breadth, and the degree to which the solution could be plugged into a real enterprise AI stack without significant rework.


Problem Statement Format
Each problem statement contains the following sections:
•	Context — the real-world pain this problem addresses and why current tools fail to solve it.
•	The Challenge — one sentence stating exactly what you are building.
•	What to Build — the concrete components and capabilities your solution must include.
•	Success Criteria — the testable conditions your solution must satisfy to be considered complete.
•	Bonus — optional extensions that demonstrate depth and earn extra credit.

Problems are grouped into ten capability units. Each unit represents a distinct layer of the AI governance stack. You may pick any problem from any unit.
 

Submission Guidelines:

1.	Create a zip file and share the zip file URL in the Google Form as a link. Please ensure the URL is publicly accessible. Strictly do not share the code or any output on public platforms such as GitHub, LinkedIn, or any other social media.
2.	In the zip file, include a video recording that explains your technical solution along with a quick demo at the start. Please keep the video between 5–8 minutes, covering how the solution works and demonstrating outcomes in real scenarios.
3.	In the zip file, also include a write-up in PDF format covering your problem statement, technical solution, architecture diagrams, and any other relevant information for the reviewers — including how your solution works, what problem it solves, and how it compares to or differs from other solutions in the market.
4.	In the zip file, also include the code files along with a clear README, well-documented automated deployment scripts, so that our team can independently verify your claims.
5.	You are free to use any AI coding tools, but you are strictly advised not to share your solution with others. Duplicate submissions may be rejected and reported to the placement cell.


Problem Statement - 3.1	The Action Guardrail

Context
Every commercial guardrails platform filters LLM text input and output. None of them govern what an agent does after the LLM produces output. An agent can generate a perfectly clean, non-toxic response that then instructs a tool to delete ten thousand database records.
Current guardrails pass this through without intervention.


The Challenge
Build a guardrail layer that operates on agent actions — not just text — enforcing policy at the moment a tool call is about to execute.


What to Build
•	A pre-execution action evaluator: before any tool call is dispatched, evaluate it against a policy ruleset.
•	Policy rules expressed in a simple declarative format (YAML or JSON), supporting at minimum: block (reject the call), require_hitl (pause for human review), and log_and_allow (execute but create an audit record).
•	Example rules: block any database delete where record count exceeds 100; require HITL for any email sent to an external domain; log and allow any read of a path containing the word confidential.
•	A simulation harness: run a sample agent through a scenario that triggers each of the three outcome types.


Success Criteria
•	All three outcomes fire correctly on matching tool calls.
 

 
•	A bulk delete of 500 records is blocked; a delete of five records is allowed.
•	An email to an external domain pauses for HITL; an internal email goes through.
•	Audit log captures every evaluated action with outcome and matched rule.


Bonus
•	Add a dry run mode: the agent runs normally but all actions are simulated and policy violations are reported without executing.


# ActionGuard++ --- Enterprise AI Runtime Governance Platform

**Tagline:** Every guardrail platform filters what an LLM says.
ActionGuard governs what it does.

## Enterprise Enhancements

-   Policy Versioning
-   Context Builder
-   Decision Explanation Engine
-   Risk Scoring
-   Searchable Audit Logs
-   Governance Timeline
-   Metrics Dashboard
-   Policy Playground
-   Policy Templates
-   Rule Priority Engine

## Architecture

``` text
User -> AI Agent -> Action Middleware -> Context Builder ->
Policy Engine -> Decision Engine -> (Block/HITL/Allow) ->
Tool Layer -> Audit Store -> Dashboard
```

## Core Modules

1.  Action Middleware
2.  Context Builder (time, role, agent, previous violations, data class,
    policy version)
3.  Policy Engine (YAML)
4.  Decision Engine
5.  HITL Queue
6.  Audit Store
7.  Dashboard
8.  Metrics
9.  Timeline
10. Search

## Enterprise Features

### Policy Versioning

Store rules as: - rules/v1.yaml - rules/v2.yaml - rules/v3.yaml

Log policy version with every decision.

### Rule Priority

Block \> HITL \> Allow.

### Decision Explanation

Return: - matched rule - reason - suggested remediation

### Risk Score

0--30 Allow 31--70 HITL 71--100 Block

### Governance Timeline

Requested -\> Context -\> Rule Match -\> Decision -\> Execution/Block
-\> Audit

### Searchable Audit

Filter by: - agent - tool - date - policy version - decision

### Dashboard

-   Allowed %
-   Blocked %
-   HITL %
-   Top violated rule
-   Top risky tool
-   Avg risk score

### Policy Playground

Test policies without executing actions.

### Policy Templates

Finance, Healthcare, Retail, Enterprise.

## Bonus

-   Dry Run
-   Rate Limiting
-   Context-aware Rules
-   Docker
-   AWS
-   Health Endpoint
-   Structured Logging

## Folder Structure

``` text
actionguard/
 app/
 policy/
 middleware/
 context/
 explanation/
 audit/
 hitl/
 metrics/
 timeline/
 dashboard/
 tests/
 docs/
 infra/
```

## AWS

FastAPI + Docker + ECS Fargate/EC2 + DynamoDB + CloudWatch + Secrets
Manager.

## 5-Day Plan

Day1: Middleware + Policy Engine + Context Builder Day2: HITL + Audit +
Dashboard Day3: Docker + AWS + Metrics Day4: Explanation + Risk +
Search + Templates Day5: Tests + Docs + Demo

## Positioning

Present the project as an **Enterprise AI Runtime Governance Platform**,
not just a PS-3.1 solution.
