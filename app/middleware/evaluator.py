from datetime import datetime
from typing import Dict, Any, Optional
from app.policy.engine import PolicyEngine
from app.context.builder import ContextBuilder
from app.explanation.explainer import DecisionExplainer
from app.audit.store import AuditStore
from app.hitl.queue import HitlQueue
from app.utils.rate_limiter import RateLimiter

class GuardrailEvaluator:
    """Enterprise middleware that intercepts and evaluates agent tool-call execution requests
    against security policy files, computing dynamic context, risk scores, and generating timelines."""

    def __init__(
        self,
        audit_store: AuditStore,
        hitl_queue: HitlQueue,
        rate_limiter: RateLimiter,
        dry_run: bool = False
    ):
        self.audit_store = audit_store
        self.hitl_queue = hitl_queue
        self.rate_limiter = rate_limiter
        self.policy_engine = PolicyEngine()
        self.context_builder = ContextBuilder(rate_limiter)
        self.explainer = DecisionExplainer()
        self.dry_run = dry_run

    def evaluate_action(
        self,
        agent_id: str,
        tool: str,
        params: dict,
        policy_version_override: Optional[str] = None
    ) -> dict:
        
        # 1. Select the policy ruleset version (with support for overrides in playground simulations)
        current_version = policy_version_override or self.policy_engine.active_version
        if policy_version_override:
            # Temporarily configure version
            original_version = self.policy_engine.active_version
            self.policy_engine.set_version(policy_version_override)

        try:
            # 2. Compile dynamic context
            context = self.context_builder.build_context(
                agent_id=agent_id,
                tool=tool,
                params=params,
                audit_store=self.audit_store
            )

            # 3. Match rules
            matched_rules = self.policy_engine.evaluate(tool, params, context)

            # 4. Generate decision and explanation
            outcome = self.explainer.explain_decision(
                agent_id=agent_id,
                tool=tool,
                params=params,
                context=context,
                matched_rules=matched_rules,
                policy_version=current_version
            )
        finally:
            if policy_version_override:
                # Restore previous configuration
                self.policy_engine.set_version(original_version)

        decision = outcome["decision"]
        risk_score = outcome["risk_score"]
        explanation = outcome["explanation"]
        timeline = outcome["timeline"]

        # 5. Handle execution logic based on Dry Run configuration
        record = {
            "timestamp": datetime.utcnow().isoformat(),
            "agent_id": agent_id,
            "tool": tool,
            "params": params,
            "action": decision,
            "risk_score": risk_score,
            "rule_id": outcome["rule_id"],
            "reason": outcome["reason"],
            "explanation": explanation.model_dump(),
            "timeline": [step.model_dump() for step in timeline],
            "policy_version": current_version,
            "dry_run": self.dry_run
        }

        if self.dry_run:
            # Log what WOULD have happened, but let execution continue
            record["simulated_outcome"] = decision
            record["action"] = "allowed"  # Allow the action
            self.audit_store.write(record)
            
            # Update the last timeline step to reflect dry run allow
            timeline[-1].details = f"Dry Run Mode: Execution allowed. Simulated action was: {decision.upper()}."
            
            return {
                "status": "allowed",
                "rule_id": outcome["rule_id"],
                "reason": f"Dry Run: {outcome['reason']}",
                "risk_score": risk_score,
                "explanation": explanation,
                "timeline": timeline,
                "dry_run": True,
                "would_have": decision
            }

        # 6. Branch on live decisions
        if decision == "block":
            self.audit_store.write(record)
            return {
                "status": "blocked",
                "rule_id": outcome["rule_id"],
                "reason": outcome["reason"],
                "risk_score": risk_score,
                "explanation": explanation,
                "timeline": timeline,
                "dry_run": False
            }

        if decision == "require_hitl":
            request_id = self.hitl_queue.enqueue(
                agent_id=agent_id,
                tool=tool,
                params=params,
                reason=outcome["reason"],
                risk_score=risk_score,
                policy_version=current_version
            )
            record["request_id"] = request_id
            self.audit_store.write(record)
            
            return {
                "status": "pending",
                "request_id": request_id,
                "rule_id": outcome["rule_id"],
                "reason": outcome["reason"],
                "risk_score": risk_score,
                "explanation": explanation,
                "timeline": timeline,
                "dry_run": False
            }

        # Else: allowed
        self.audit_store.write(record)
        return {
            "status": "allowed",
            "rule_id": outcome["rule_id"],
            "reason": outcome["reason"],
            "risk_score": risk_score,
            "explanation": explanation,
            "timeline": timeline,
            "dry_run": False
        }
