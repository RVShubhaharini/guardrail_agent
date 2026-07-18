from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

class ActionEvaluationRequest(BaseModel):
    agent_id: str = Field(..., description="ID of the AI agent requesting the tool execution")
    tool: str = Field(..., description="Name of the tool being requested")
    params: Dict[str, Any] = Field(default_factory=dict, description="Parameters passed to the tool")
    policy_version: Optional[str] = Field(None, description="Optional policy version override for testing/playground")

class GovernanceTimelineStep(BaseModel):
    step: str = Field(..., description="Step name in the governance process")
    details: str = Field(..., description="Details of the action performed in this step")
    timestamp: str = Field(..., description="Timestamp when the step occurred")

class DecisionExplanation(BaseModel):
    matched_rules: List[Dict[str, Any]] = Field(default_factory=list, description="Rules matched during evaluation")
    risk_score: int = Field(..., description="Aggregated risk score (0-100)")
    suggested_remediation: Optional[str] = Field(None, description="Remediation instructions if blocked or HITL required")

class ActionEvaluationResponse(BaseModel):
    status: str = Field(..., description="Result status: 'allowed', 'blocked', or 'pending'")
    rule_id: Optional[str] = Field(None, description="The ID of the primary rule triggered")
    reason: Optional[str] = Field(None, description="Reason for the guardrail decision")
    risk_score: int = Field(..., description="Aggregated risk score (0-100)")
    explanation: DecisionExplanation = Field(..., description="Detailed explanation of the decision")
    timeline: List[GovernanceTimelineStep] = Field(default_factory=list, description="Governance lifecycle timeline")
    request_id: Optional[str] = Field(None, description="HITL Request ID if status is 'pending'")
    dry_run: bool = Field(default=False, description="Whether dry run mode was active")

class HITLResolutionRequest(BaseModel):
    decision: Optional[str] = Field(None, description="Resolution: 'approved' or 'rejected'")
    reviewer: str = Field("admin_reviewer", description="User or system resolving the request")

class AgentRunRequest(BaseModel):
    agent_id: str = Field(..., description="Agent ID to identify session")
    instruction: str = Field(..., description="Instruction to run the LLM agent against")

