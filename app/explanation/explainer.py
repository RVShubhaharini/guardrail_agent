from datetime import datetime
import os
from typing import Dict, Any, List, Optional
from app.models.schemas import DecisionExplanation, GovernanceTimelineStep
from app.config import settings

class DecisionExplainer:
    """Explains guardrail decisions by calculating risk scores, compiling remediation paths,
    and building step-by-step governance timelines."""

    def _get_ai_risk_assessment(
        self,
        agent_id: str,
        tool: str,
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        import sys
        if "pytest" in sys.modules or "_pytest" in sys.modules or os.getenv("TESTING") == "true":
            return None

        groq_api_key = settings.groq_api_key
        gemini_api_key = settings.gemini_api_key

        # Prepare context summary
        import json
        context_summary = {
            "agent_id": agent_id,
            "role": context.get("role"),
            "tool": tool,
            "recipient_domain": context.get("recipient_domain"),
            "has_confidential_attachment": context.get("has_confidential_attachment"),
            "data_classification": context.get("data_classification"),
            "previous_violations": context.get("previous_violations"),
            "calls_last_minute": context.get("calls_last_minute"),
            "cumulative_deletes_5m": context.get("cumulative_deletes_5m"),
            "cumulative_email_deletes_5m": context.get("cumulative_email_deletes_5m"),
            "parameters_passed": {k: v for k, v in params.items() if not k.startswith("_")}
        }

        prompt = (
            "You are an AI Security and Governance Risk Assessment Agent.\n"
            "Evaluate the safety and security risk of the following tool invocation based on the context:\n\n"
            f"{json.dumps(context_summary, indent=2)}\n\n"
            "Return a JSON response matching the following schema:\n"
            "{\n"
            '  "risk": integer between 0 and 100 representing the threat level,\n'
            '  "decision": "ALLOW" or "HITL" or "BLOCK",\n'
            '  "reason": "Clear, concise natural language explanation of the reasoning and potential security risks"\n'
            "}\n"
        )

        # 1. Try Groq (Llama-3.3-70b-versatile) first if configured
        if groq_api_key:
            try:
                import requests
                headers = {
                    "Authorization": f"Bearer {groq_api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.0
                }

                res = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=5.0
                )

                if res.status_code == 200:
                    chat_res = res.json()
                    content = chat_res["choices"][0]["message"]["content"]
                    result = json.loads(content.strip())

                    raw_decision = result.get("decision", "ALLOW").upper()
                    mapped_decision = "require_hitl" if raw_decision == "HITL" else raw_decision.lower()

                    print(f"[AI Risk Agent - Groq] Llama-3.3-70b-versatile evaluation successful.")
                    return {
                        "risk_score": int(result.get("risk", 10)),
                        "decision": mapped_decision,
                        "reason": result.get("reason", "Analyzed by Groq Llama-3.3 Risk Assessment Agent.")
                    }
                else:
                    print(f"[AI Risk Agent - Groq] API error: {res.status_code} - {res.text}")
            except Exception as e:
                print(f"[AI Risk Agent - Groq] Failed: {e}. Falling back to Gemini.")

        # 2. Try Gemini
        if gemini_api_key:
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=gemini_api_key)

                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )

                if response and response.text:
                    result = json.loads(response.text.strip())
                    raw_decision = result.get("decision", "ALLOW").upper()
                    mapped_decision = "require_hitl" if raw_decision == "HITL" else raw_decision.lower()

                    print(f"[AI Risk Agent - Gemini] Gemini-2.5-flash evaluation successful.")
                    return {
                        "risk_score": int(result.get("risk", 10)),
                        "decision": mapped_decision,
                        "reason": result.get("reason", "Analyzed by Gemini Risk Assessment Agent.")
                    }
            except Exception as e:
                print(f"[AI Risk Agent - Gemini] Failed: {e}")

        return None

    def explain_decision(
        self,
        agent_id: str,
        tool: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
        matched_rules: List[Dict[str, Any]],
        policy_version: str
    ) -> Dict[str, Any]:
        
        # 1. Base Risk Score calculation based on Context (Baseline)
        risk_score = 10  # Baseline
        if context.get("data_classification") == "restricted":
            risk_score = max(risk_score, 25)
        if context.get("previous_violations", 0) > 0:
            risk_score = min(100, risk_score + (context["previous_violations"] * 10))

        decision = "log_and_allow"
        if risk_score >= 71:
            decision = "block"
        elif risk_score >= 31:
            decision = "require_hitl"

        # 2. Integrate Gemini AI Risk Assessment Agent
        ai_assessment = self._get_ai_risk_assessment(agent_id, tool, params, context)
        ai_reason = None
        if ai_assessment:
            risk_score = ai_assessment["risk_score"]
            decision = ai_assessment["decision"]
            ai_reason = ai_assessment["reason"]
            print(f"[AI Risk Agent] Assessment complete. Score: {risk_score}, Decision: {decision}, Reason: {ai_reason}")

        # 3. Rule constraints verification (Policy Engine overrides AI)
        primary_rule = None
        remediation = None
        if matched_rules:
            # Rule engine aggregates the highest configured risk score
            rule_risks = [rule.get("risk_score", 10) for rule in matched_rules]
            risk_score = max(risk_score, *rule_risks)

            primary_rule = max(matched_rules, key=lambda r: r.get("risk_score", 0))
            remediation = primary_rule.get("remediation")
            
            explicit_action = primary_rule.get("action")
            if explicit_action:
                decision = explicit_action
                print(f"[Policy Override] Policy rule '{primary_rule.get('id')}' overrides decision to {decision.upper()}")

        # Align score boundaries with final override decisions
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

        # 4. Build Governance Timeline
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
        if ai_assessment:
            decision_details += " (AI Assessed)"
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
            "reason": ai_reason or (primary_rule.get("description") if primary_rule else "default allow")
        }

