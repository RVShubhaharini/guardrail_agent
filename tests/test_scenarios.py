import pytest
from app.audit.store import AuditStore
from app.hitl.queue import HitlQueue
from app.utils.rate_limiter import RateLimiter
from app.middleware.evaluator import GuardrailEvaluator
from app.policy.engine import PolicyEngine

@pytest.fixture
def evaluator():
    import os
    import sqlite3
    # Reset local SQLite database to prevent violation tracking from bleeding across test cases
    if os.path.exists("audit.db"):
        try:
            conn = sqlite3.connect("audit.db")
            conn.execute("DELETE FROM audit")
            conn.commit()
            conn.close()
        except Exception:
            pass

    # Set up clean instances for testing
    store = AuditStore()
    queue = HitlQueue(store)
    limiter = RateLimiter()
    # Force dry_run = False for unit tests
    eval = GuardrailEvaluator(
        audit_store=store,
        hitl_queue=queue,
        rate_limiter=limiter,
        dry_run=False
    )
    # Ensure policy version is v2 to test all rules
    eval.policy_engine.set_version("v2")
    return eval

def test_bulk_delete_blocked(evaluator):
    res = evaluator.evaluate_action(
        agent_id="test-agent",
        tool="db_delete",
        params={"record_count": 500}
    )
    assert res["status"] == "blocked"
    assert res["rule_id"] == "block_bulk_delete"
    assert "exceeds 100" in res["reason"]
    assert res["risk_score"] == 95

def test_small_delete_allowed(evaluator):
    res = evaluator.evaluate_action(
        agent_id="test-agent",
        tool="db_delete",
        params={"record_count": 5}
    )
    assert res["status"] == "allowed"
    assert res["rule_id"] == "allow_small_delete"
    assert res["risk_score"] == 10

def test_external_email_requires_hitl(evaluator):
    res = evaluator.evaluate_action(
        agent_id="test-agent",
        tool="send_email",
        params={"recipient_domain": "gmail.com", "subject": "Hello Test"}
    )
    assert res["status"] == "pending"
    assert res["request_id"] is not None
    assert res["rule_id"] == "hitl_external_email"
    assert res["risk_score"] == 60

def test_internal_email_allowed(evaluator):
    res = evaluator.evaluate_action(
        agent_id="test-agent",
        tool="send_email",
        params={"recipient_domain": "acme-corp.com", "subject": "Hello Internal"}
    )
    assert res["status"] == "allowed"
    assert res["rule_id"] == "allow_internal_email"
    assert res["risk_score"] == 10

def test_dry_run_mode(evaluator):
    # Enable dry run
    evaluator.dry_run = True
    res = evaluator.evaluate_action(
        agent_id="test-agent",
        tool="db_delete",
        params={"record_count": 500}
    )
    # Under dry run, action evaluates but is allowed
    assert res["status"] == "allowed"
    assert res["dry_run"] is True
    assert res["would_have"] == "block"

def test_rate_limiting(evaluator):
    agent_id = "spam-agent"
    tool = "read_file"
    params = {"path": "normal.txt"}

    # Call it 10 times -> should be allowed
    for _ in range(10):
        res = evaluator.evaluate_action(agent_id, tool, params)
        assert res["status"] == "allowed"

    # 11th call should trigger rate limit block
    res = evaluator.evaluate_action(agent_id, tool, params)
    assert res["status"] == "blocked"
    assert res["rule_id"] == "rate_limit_any_tool"
    assert res["risk_score"] == 85

def test_after_hours_hitl(evaluator):
    # Set hour of day to midnight in evaluation context
    evaluator.policy_engine.set_version("v2")
    
    # We can override builder context or evaluate directly
    ctx = {
        "internal_domains": {"acme-corp.com"},
        "hour_of_day": 2, # 2 AM (outside business hours 6am-9pm)
        "calls_last_minute": 1,
        "role": "junior_dev",
        "data_classification": "general",
        "previous_violations": 0
    }
    
    matched = evaluator.policy_engine.evaluate("db_write", {"record_id": "1"}, ctx)
    rule_ids = [r["id"] for r in matched]
    assert "after_hours_write_hitl" in rule_ids

def test_cumulative_delete_bypass(evaluator):
    # Set policy version to v3
    evaluator.policy_engine.set_version("v3")
    
    agent_id = "malicious-agent-1"
    tool = "db_delete"
    
    # 1. Ask to delete 100 records 5 times.
    # Total deletes requested = 500. All should be allowed.
    for _ in range(5):
        res = evaluator.evaluate_action(agent_id, tool, {"record_count": 100})
        assert res["status"] == "allowed"

    # 2. Ask to delete 10 more records.
    # Cumulative deletes requested = 510 > 500. Should trigger cumulative block!
    res = evaluator.evaluate_action(agent_id, tool, {"record_count": 10})
    assert res["status"] == "blocked"
    assert res["rule_id"] == "block_cumulative_delete_bypass"
    assert res["risk_score"] == 98
    assert "cumulative" in res["reason"]

def test_unauthenticated_agent_blocked(evaluator):
    # Set policy version to v3
    evaluator.policy_engine.set_version("v3")
    
    # Agent with anonymous role
    res = evaluator.evaluate_action(
        agent_id="unknown-agent",
        tool="read_file",
        params={"path": "normal.txt", "_role": "anonymous"}
    )
    assert res["status"] == "blocked"
    assert res["rule_id"] == "block_unauthenticated_agent"
    assert res["risk_score"] == 100

def test_role_tool_permissions(evaluator):
    # Set policy version to v3
    evaluator.policy_engine.set_version("v3")
    
    # Guest role trying to delete
    res = evaluator.evaluate_action(
        agent_id="guest-agent",
        tool="db_delete",
        params={"record_count": 5, "_role": "guest"}
    )
    assert res["status"] == "blocked"
    assert res["rule_id"] == "restrict_tool_by_agent_role"
    assert res["risk_score"] == 95

def test_sentinel_confidential_attachment_external_blocked(evaluator):
    # Set policy version to v3
    evaluator.policy_engine.set_version("v3")
    
    # Sending email to external recipient with confidential attachment -> blocked
    res = evaluator.evaluate_action(
        agent_id="test-agent",
        tool="gmail_send_email",
        params={
            "to": "spammer@gmail.com",
            "subject": "Salary Sheet Details",
            "attachments": [{"filename": "salary_report.pdf"}],
            "_role": "junior_dev"
        }
    )
    assert res["status"] == "blocked"
    assert res["rule_id"] == "block_confidential_attachment_external"
    assert res["risk_score"] == 98

def test_sentinel_guest_email_delete_blocked(evaluator):
    # Set policy version to v3
    evaluator.policy_engine.set_version("v3")
    
    # Guest role trying to delete email -> blocked
    res = evaluator.evaluate_action(
        agent_id="test-agent",
        tool="gmail_delete_email",
        params={"message_id": "msg_001", "_role": "guest"}
    )
    assert res["status"] == "blocked"
    assert res["rule_id"] == "block_guest_delete_email"
    assert res["risk_score"] == 95

def test_sentinel_bulk_email_delete_hitl(evaluator):
    # Set policy version to v3
    evaluator.policy_engine.set_version("v3")
    
    # Delete 3 emails -> should be allowed (under the limit of 3)
    for i in range(3):
        res = evaluator.evaluate_action(
            agent_id="delete-agent",
            tool="gmail_delete_email",
            params={"message_id": f"msg_{i}", "_role": "junior_dev"}
        )
        assert res["status"] == "allowed"
        
    # 4th deletion -> cumulative count is 4 > 3 -> requires HITL!
    res = evaluator.evaluate_action(
        agent_id="delete-agent",
        tool="gmail_delete_email",
        params={"message_id": "msg_4", "_role": "junior_dev"}
    )
    assert res["status"] == "pending"
    assert res["rule_id"] == "hitl_bulk_email_delete"
    assert res["risk_score"] == 65

def test_gmail_mock_search_from_sender():
    from app.agent.gmail_connector import GmailConnector
    conn = GmailConnector()
    conn.is_live = False
    
    # Search for emails from 'secops@acme-corp.com'
    res = conn.search_emails("from:secops@acme-corp.com")
    assert len(res) == 1
    assert res[0]["id"] == "msg_001"
    
    # Search for emails from 'external-ads.net'
    res2 = conn.search_emails("from:spam-campaign@external-ads.net")
    assert len(res2) == 1
    assert res2[0]["id"] == "msg_003"

    # Search for general term
    res3 = conn.search_emails("Urgent")
    assert len(res3) == 1
    assert res3[0]["id"] == "msg_001"
