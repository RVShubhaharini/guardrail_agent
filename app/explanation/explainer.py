from datetime import datetime
from typing import Dict, Any, List
from app.models.schemas import DecisionExplanation, GovernanceTimelineStep

class DecisionExplainer:
    """Explains guardrail decisions by calculating risk scores, compiling remediation paths,
    and building step-by-step governance timelines."""

    def explain_decision(
        self,
        agent_id: str,
        tool: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
        matched_rules: List[Dict[str, Any]],
        policy_version: str
    ) -> Dict[str, Any]:
        
        # 1. Base Risk Score calculation based on Context
        risk_score = 10  # Baseline
        if context.get("data_classification") == "restricted":
            risk_score = max(risk_score, 25)
        if context.get("previous_violations", 0) > 0:
            # Scale risk up based on prior violations
            risk_score = min(100, risk_score + (context["previous_violations"] * 10))

        # 2. Risk Score aggregation from matching rules
        if matched_rules:
            rule_risks = [rule.get("risk_score", 10) for rule in matched_rules]
            risk_score = max(risk_score, *rule_risks)

        # 3. Decision mapping based on Risk Score
        # 0-30: log_and_allow
        # 31-70: require_hitl
        # 71-100: block
        if risk_score >= 71:
            decision = "block"
        elif risk_score >= 31:
            decision = "require_hitl"
        else:
            decision = "log_and_allow"

        # 4. Extract primary matched rule (highest risk)
        primary_rule = None
        remediation = None
        if matched_rules:
            primary_rule = max(matched_rules, key=lambda r: r.get("risk_score", 0))
            remediation = primary_rule.get("remediation")
            # Override decision to match rule's explicit action if configured
            explicit_action = primary_rule.get("action")
            if explicit_action:
                decision = explicit_action
                # Keep score aligned with action
                if decision == "block" and risk_score < 71:
                    risk_score = 75
                elif decision == "require_hitl" and (risk_score < 31 or risk_score > 70):
                    risk_score = 55
                elif decision == "log_and_allow" and risk_score > 30:
                    risk_score = 15

        # If no explicit remediation is found for blocked or HITL decisions, provide default
        if not remediation:
            if decision == "block":
                remediation = "Action blocked by security policy. Contact system administrator."
            elif decision == "require_hitl":
                remediation = "Action paused. Awaiting human operator approval."

        # 5. Build Governance Timeline
        timeline = []
        now_str = datetime.utcnow().isoformat()

        # Step 1: Requested
        timeline.append(GovernanceTimelineStep(
            step="Requested",
            details=f"Agent '{agent_id}' requested tool execution for '{tool}'.",
            timestamp=now_str
        ))

        # Step 2: Context Compiled
        ctx_details = (
            f"Context compiled. Role: {context.get('role')}, "
            f"Classification: {context.get('data_classification')}, "
            f"Rate count: {context.get('calls_last_minute')}, "
            f"Prior violations: {context.get('previous_violations')}."
        )
        timeline.append(GovernanceTimelineStep(
            step="Context",
            details=ctx_details,
            timestamp=now_str
        ))

        # Step 3: Rule Match
        if matched_rules:
            matched_ids = ", ".join([r.get("id") for r in matched_rules])
            match_details = f"Matched rules: [{matched_ids}] under policy version '{policy_version}'."
        else:
            match_details = "No rules triggered. Evaluated against default policy settings."
        timeline.append(GovernanceTimelineStep(
            step="Rule Match",
            details=match_details,
            timestamp=now_str
        ))

        # Step 4: Decision
        decision_details = f"Aggregated risk score: {risk_score}/100. Resolution action set to: {decision.upper()}."
        timeline.append(GovernanceTimelineStep(
            step="Decision",
            details=decision_details,
            timestamp=now_str
        ))

        # Step 5: Execution Outcome
        execution_msg = {
            "block": "Execution BLOCKED. Remediation advice generated.",
            "require_hitl": "Execution PAUSED. Action enqueued into Human-in-the-Loop review portal.",
            "log_and_allow": "Execution ALLOWED. Event dispatched to Audit logger."
        }
        timeline.append(GovernanceTimelineStep(
            step="Execution/Block",
            details=execution_msg.get(decision, "Execution processed."),
            timestamp=now_str
        ))

        explanation = DecisionExplanation(
            matched_rules=[
                {
                    "id": r.get("id"),
                    "description": r.get("description"),
                    "action": r.get("action"),
                    "risk_score": r.get("risk_score")
                } for r in matched_rules
            ],
            risk_score=risk_score,
            suggested_remediation=remediation
        )

        return {
            "decision": decision,
            "risk_score": risk_score,
            "explanation": explanation,
            "timeline": timeline,
            "rule_id": primary_rule.get("id") if primary_rule else None,
            "reason": primary_rule.get("description") if primary_rule else "default allow"
        }

