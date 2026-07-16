"""
test_governance_pipeline.py
===========================
Integration tests for the full SentinelAI governance pipeline.

Each test creates a GuardrailEvaluator with real components (PolicyEngine, ContextBuilder, etc.)
and verifies end-to-end that the correct decision is made for each scenario.

Run with:
    pytest tests/test_governance_pipeline.py -v
"""
import pytest
import sys
import os
import tempfile

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.middleware.evaluator import GuardrailEvaluator
from app.audit.store import AuditStore
from app.hitl.queue import HitlQueue
from app.utils.rate_limiter import RateLimiter


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

def make_evaluator():
    """Create a fresh GuardrailEvaluator with a temp SQLite DB for isolation."""
    # Use a unique temp file per evaluator to prevent cross-test audit pollution
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()

    # Patch the db_path for this test's AuditStore
    audit = AuditStore.__new__(AuditStore)
    audit.use_dynamo = False
    audit.db_path = tmp.name
    audit._init_sqlite()

    hitl = HitlQueue(audit)
    limiter = RateLimiter()

    ev = GuardrailEvaluator(
        audit_store=audit,
        hitl_queue=hitl,
        rate_limiter=limiter,
        dry_run=False
    )
    # Force v3 for all tests
    ev.policy_engine.set_version("v3")
    return ev


@pytest.fixture
def evaluator():
    """Fresh evaluator with isolated SQLite DB per test."""
    return make_evaluator()


AGENT_ID = "test-agent-pipeline"


# ─────────────────────────────────────────────
# Test Suite
# ─────────────────────────────────────────────

class TestLayerOneAuthentication:
    """Layer 1: Authentication & Identity Verification"""

    def test_anonymous_agent_is_blocked(self, evaluator):
        """Anonymous agents must never be allowed to execute tools."""
        result = evaluator.evaluate_action(
            agent_id=AGENT_ID,
            tool="gmail_send_email",
            params={"to": "anyone@example.com", "_role": "anonymous"}
        )
        assert result["status"] == "blocked", (
            f"Expected 'blocked' for anonymous role, got '{result['status']}'"
        )
        assert result["risk_score"] >= 90, "Anonymous agent must carry maximum risk score"

    def test_empty_agent_id_is_blocked(self, evaluator):
        """Empty agent ID is equivalent to unauthenticated — must be blocked."""
        result = evaluator.evaluate_action(
            agent_id="",
            tool="gmail_send_email",
            params={"to": "anyone@example.com", "_role": "junior_dev"}
        )
        assert result["status"] == "blocked"


class TestLayerThreeRBAC:
    """Layer 3: Role-Based Access Control"""

    def test_guest_delete_email_is_blocked(self, evaluator):
        """Guest role must not be able to delete corporate emails."""
        result = evaluator.evaluate_action(
            agent_id=AGENT_ID,
            tool="gmail_delete_email",
            params={"message_id": "msg_001", "_role": "guest"}
        )
        assert result["status"] == "blocked", (
            f"Expected 'blocked' for guest delete, got '{result['status']}'"
        )
        assert result["rule_id"] == "block_guest_delete_email"

    def test_admin_delete_email_is_allowed(self, evaluator):
        """Admin role must be able to delete emails without restriction."""
        result = evaluator.evaluate_action(
            agent_id="admin-agent",
            tool="gmail_delete_email",
            params={"message_id": "msg_001", "_role": "admin"}
        )
        assert result["status"] == "allowed", (
            f"Expected 'allowed' for admin delete, got '{result['status']}'"
        )

    def test_intern_external_send_is_blocked(self, evaluator):
        """Interns must not be able to send emails to external domains."""
        result = evaluator.evaluate_action(
            agent_id=AGENT_ID,
            tool="gmail_send_email",
            params={"to": "partner@external-company.com", "subject": "Hi", "body": "Hello", "_role": "intern"}
        )
        assert result["status"] == "blocked", (
            f"Expected 'blocked' for intern external send, got '{result['status']}'"
        )


class TestLayerFiveAttachmentClassification:
    """Layer 5: Sensitive Records & Attachment Classification"""

    def test_confidential_attachment_to_external_is_blocked(self, evaluator):
        """Sending salary/confidential attachments to external recipients must be blocked."""
        result = evaluator.evaluate_action(
            agent_id=AGENT_ID,
            tool="gmail_send_email",
            params={
                "to": "hacker@gmail.com",
                "subject": "Salary Report",
                "body": "See attached.",
                "attachments": [{"filename": "salary_q2_2025.pdf", "content_type": "application/pdf"}],
                "_role": "junior_dev"
            }
        )
        assert result["status"] == "blocked", (
            f"Expected 'blocked' for confidential external attachment, got '{result['status']}'"
        )
        assert result["risk_score"] >= 95, "Confidential attachment must carry very high risk score"
        assert result["rule_id"] == "block_confidential_attachment_external"

    def test_confidential_forward_to_external_is_blocked(self, evaluator):
        """Forwarding confidential emails to external domain must be blocked."""
        result = evaluator.evaluate_action(
            agent_id=AGENT_ID,
            tool="gmail_forward_email",
            params={
                "message_id": "msg_002",
                "to": "competitor@rival.com",
                "_role": "junior_dev",
                "_has_confidential_attachment": True
            }
        )
        assert result["status"] == "blocked"

    def test_internal_email_with_attachment_is_allowed(self, evaluator):
        """Sending confidential attachment to internal domain must be allowed."""
        # Use a unique agent ID to prevent violation history from other tests bleeding in
        result = evaluator.evaluate_action(
            agent_id="fresh-internal-agent",
            tool="gmail_send_email",
            params={
                "to": "colleague@acme-corp.com",
                "subject": "Salary Update",
                "body": "Here is the report.",
                "attachments": [{"filename": "salary_q2.pdf"}],
                "_role": "junior_dev"
            }
        )
        assert result["status"] == "allowed", (
            f"Expected 'allowed' for internal confidential, got '{result['status']}' "
            f"(rule: {result.get('rule_id')}, risk: {result.get('risk_score')})"
        )


class TestLayerNineHITL:
    """Layer 9: Human-in-the-Loop Rules"""

    def test_external_email_requires_hitl(self, evaluator):
        """Any email sent to an external domain must pause for human approval."""
        result = evaluator.evaluate_action(
            agent_id="fresh-hitl-agent",
            tool="gmail_send_email",
            params={
                "to": "partner@gmail.com",
                "subject": "Meeting Notes",
                "body": "Please find notes from our sync.",
                "_role": "junior_dev"
            }
        )
        assert result["status"] == "pending", (
            f"Expected 'pending' for external email, got '{result['status']}'"
        )
        assert "request_id" in result, "HITL response must include a request_id"
        # The rule_id may be 'hitl_external_email' or 'hitl_repeat_violator'
        # depending on shared audit history — either is a correct HITL rule
        assert result["rule_id"] in (
            "hitl_external_email",
            "hitl_repeat_violator",
            "hitl_after_hours_send",
        ), f"Unexpected rule_id: {result['rule_id']}"

    def test_external_forward_requires_hitl(self, evaluator):
        """Forwarding a message to an external domain must require HITL."""
        result = evaluator.evaluate_action(
            agent_id=AGENT_ID,
            tool="gmail_forward_email",
            params={
                "message_id": "msg_003",
                "to": "partner@gmail.com",
                "_role": "junior_dev"
            }
        )
        assert result["status"] == "pending"

    def test_internal_email_is_allowed_without_hitl(self, evaluator):
        """Internal emails must go through without HITL."""
        result = evaluator.evaluate_action(
            agent_id="clean-internal-agent",
            tool="gmail_send_email",
            params={
                "to": "manager@acme-corp.com",
                "subject": "Weekly Report",
                "body": "Here is the weekly update.",
                "_role": "junior_dev"
            }
        )
        assert result["status"] == "allowed", (
            f"Expected 'allowed' for internal email, got '{result['status']}' "
            f"(rule: {result.get('rule_id')}, risk: {result.get('risk_score')})"
        )


class TestLayerSixCumulativeDetection:
    """Layer 6: Cumulative Policy Evaluation (Batch Bypass Prevention)"""

    def test_bulk_email_deletions_trigger_hitl(self, evaluator):
        """After 3 email deletions within 5 minutes, the 4th must require HITL."""
        agent_id = "bulk-delete-agent"

        # Perform 3 deletes first
        for i in range(3):
            evaluator.evaluate_action(
                agent_id=agent_id,
                tool="gmail_delete_email",
                params={"message_id": f"msg_00{i+1}", "_role": "junior_dev"}
            )

        # 4th delete should trigger HITL
        result = evaluator.evaluate_action(
            agent_id=agent_id,
            tool="gmail_delete_email",
            params={"message_id": "msg_004", "_role": "junior_dev"}
        )
        assert result["status"] == "pending", (
            f"Expected 'pending' after 4th consecutive delete, got '{result['status']}'"
        )
        assert result["rule_id"] == "hitl_bulk_email_delete"


class TestLayerSevenRateLimiting:
    """Layer 7: Rate Limiting & Network Safety"""

    def test_rate_limit_blocks_after_10_calls(self, evaluator):
        """An agent calling the same tool more than 10 times/minute must be blocked."""
        agent_id = "rate-limit-agent"

        # Make 10 calls to exhaust the limit
        for i in range(10):
            evaluator.evaluate_action(
                agent_id=agent_id,
                tool="gmail_read_email",
                params={"message_id": "msg_001", "_role": "junior_dev"}
            )

        # 11th call must be blocked
        result = evaluator.evaluate_action(
            agent_id=agent_id,
            tool="gmail_read_email",
            params={"message_id": "msg_001", "_role": "junior_dev"}
        )
        assert result["status"] == "blocked", (
            f"Expected 'blocked' after rate limit exceeded, got '{result['status']}'"
        )
        assert result["rule_id"] == "rate_limit_any_tool"


class TestHITLResolution:
    """HITL Queue — Enqueue, Approve, and verify resolution."""

    def test_hitl_approve_executes_action(self, evaluator):
        """Approving a HITL request should resolve it with 'approved' status."""
        # Create a HITL request via external email
        result = evaluator.evaluate_action(
            agent_id=AGENT_ID,
            tool="gmail_send_email",
            params={
                "to": "partner@gmail.com",
                "subject": "Approval Test",
                "body": "Test body.",
                "_role": "junior_dev"
            }
        )
        assert result["status"] == "pending"
        request_id = result["request_id"]

        # Approve the request
        resolved = evaluator.hitl_queue.resolve(
            request_id=request_id,
            decision="approved",
            reviewer="test_admin"
        )
        assert resolved is not None
        assert resolved["status"] == "approved"
        assert resolved["reviewer"] == "test_admin"

    def test_hitl_reject_removes_from_queue(self, evaluator):
        """Rejecting a HITL request should remove it from the pending queue."""
        result = evaluator.evaluate_action(
            agent_id=AGENT_ID,
            tool="gmail_send_email",
            params={
                "to": "rejected@gmail.com",
                "subject": "Reject Test",
                "body": "Test.",
                "_role": "junior_dev"
            }
        )
        assert result["status"] == "pending"
        request_id = result["request_id"]

        # Reject
        evaluator.hitl_queue.resolve(request_id, "rejected", reviewer="test_admin")

        # Should no longer be in pending queue
        pending = evaluator.hitl_queue.list_pending()
        assert not any(r["request_id"] == request_id for r in pending)


class TestDryRunMode:
    """Dry Run Mode — policy evaluates but never blocks."""

    def test_dry_run_allows_blocked_action(self):
        """In dry run mode, even normally-blocked actions must be allowed through."""
        audit = AuditStore()
        hitl = HitlQueue(audit)
        limiter = RateLimiter()
        ev_dry = GuardrailEvaluator(
            audit_store=audit,
            hitl_queue=hitl,
            rate_limiter=limiter,
            dry_run=True  # dry run ON
        )
        ev_dry.policy_engine.set_version("v3")

        result = ev_dry.evaluate_action(
            agent_id="dry-run-agent",
            tool="gmail_send_email",
            params={
                "to": "hacker@evil.com",
                "subject": "Salary Data",
                "body": "Here it is.",
                "attachments": [{"filename": "salary.pdf"}],
                "_role": "guest"
            }
        )
        assert result["status"] == "allowed", (
            f"Dry run mode must always return 'allowed', got '{result['status']}'"
        )
        assert result["dry_run"] is True
        assert result["would_have"] in ("block", "require_hitl")
