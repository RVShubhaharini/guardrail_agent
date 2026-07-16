"""
test_policy_engine.py
=====================
Unit tests for the SentinelAI PolicyEngine in isolation.

Tests rule loading, version switching, condition evaluation,
and template loading — independent of the full evaluator stack.

Run with:
    pytest tests/test_policy_engine.py -v
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.policy.engine import PolicyEngine


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def engine_v1():
    return PolicyEngine(default_version="v1")

@pytest.fixture
def engine_v2():
    return PolicyEngine(default_version="v2")

@pytest.fixture
def engine_v3():
    return PolicyEngine(default_version="v3")


# ─────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────

class TestRuleLoading:

    def test_v1_loads_rules(self, engine_v1):
        assert isinstance(engine_v1.rules, list)
        assert len(engine_v1.rules) > 0, "v1 must have at least 1 rule"

    def test_v2_loads_more_rules_than_v1(self, engine_v1, engine_v2):
        assert len(engine_v2.rules) >= len(engine_v1.rules), \
            "v2 should have at least as many rules as v1"

    def test_v3_loads_most_rules(self, engine_v2, engine_v3):
        assert len(engine_v3.rules) >= len(engine_v2.rules), \
            "v3 should have at least as many rules as v2"

    def test_v3_has_critical_rule_ids(self, engine_v3):
        """Verify that all critical rule IDs are present in v3."""
        rule_ids = {r["id"] for r in engine_v3.rules}
        required = {
            "block_unauthenticated_agent",
            "block_guest_delete_email",
            "block_confidential_attachment_external",
            "hitl_bulk_email_delete",
            "rate_limit_any_tool",
            "hitl_external_email",
            "hitl_external_forward",
            "hitl_repeat_violator",
            "block_intern_external_send",
            "block_confidential_forward_external",
        }
        missing = required - rule_ids
        assert not missing, f"Missing critical rules in v3: {missing}"

    def test_fallback_to_v1_for_unknown_version(self):
        """If an unknown version is requested, engine must fall back to v1."""
        engine = PolicyEngine(default_version="v999_nonexistent")
        assert engine.active_version == "v1"
        assert len(engine.rules) > 0


class TestVersionSwitching:

    def test_set_version_updates_rules(self, engine_v1):
        v1_count = len(engine_v1.rules)
        engine_v1.set_version("v3")
        v3_count = len(engine_v1.rules)
        assert v3_count >= v1_count
        assert engine_v1.active_version == "v3"

    def test_set_version_back_to_v1(self, engine_v3):
        engine_v3.set_version("v1")
        assert engine_v3.active_version == "v1"


class TestConditionEvaluation:

    def build_ctx(self, **kwargs):
        """Build a minimal context dict for rule evaluation."""
        defaults = {
            "role": "junior_dev",
            "agent_id": "test-agent",
            "hour_of_day": 10,
            "calls_last_minute": 1,
            "recipient_domain": "acme-corp.com",
            "internal_domains": {"acme-corp.com", "internal.acme-corp.com"},
            "has_confidential_attachment": False,
            "data_classification": "general",
            "previous_violations": 0,
            "cumulative_deletes_5m": 0,
            "cumulative_email_deletes_5m": 0,
            "business_hours": True,
            "is_internal_recipient": True,
            "geo_context": "domestic",
        }
        defaults.update(kwargs)
        return defaults

    def test_anonymous_role_triggers_block(self, engine_v3):
        ctx = self.build_ctx(role="anonymous")
        matched = engine_v3.evaluate("gmail_send_email", {}, ctx)
        rule_ids = [r["id"] for r in matched]
        assert "block_unauthenticated_agent" in rule_ids

    def test_guest_delete_triggers_block_rule(self, engine_v3):
        ctx = self.build_ctx(role="guest")
        matched = engine_v3.evaluate("gmail_delete_email", {}, ctx)
        rule_ids = [r["id"] for r in matched]
        assert "block_guest_delete_email" in rule_ids

    def test_external_email_triggers_hitl_rule(self, engine_v3):
        ctx = self.build_ctx(
            recipient_domain="gmail.com",
            is_internal_recipient=False
        )
        matched = engine_v3.evaluate(
            "gmail_send_email",
            {"to": "anyone@gmail.com"},
            ctx
        )
        rule_ids = [r["id"] for r in matched]
        assert "hitl_external_email" in rule_ids

    def test_confidential_attachment_external_triggers_block(self, engine_v3):
        ctx = self.build_ctx(
            has_confidential_attachment=True,
            recipient_domain="external.com",
            is_internal_recipient=False
        )
        matched = engine_v3.evaluate(
            "gmail_send_email",
            {"attachments": [{"filename": "salary.pdf"}]},
            ctx
        )
        rule_ids = [r["id"] for r in matched]
        assert "block_confidential_attachment_external" in rule_ids

    def test_rate_limit_exceeded_triggers_block(self, engine_v3):
        ctx = self.build_ctx(calls_last_minute=15)
        matched = engine_v3.evaluate("gmail_read_email", {}, ctx)
        rule_ids = [r["id"] for r in matched]
        assert "rate_limit_any_tool" in rule_ids

    def test_bulk_deletes_trigger_hitl(self, engine_v3):
        ctx = self.build_ctx(cumulative_email_deletes_5m=5)
        matched = engine_v3.evaluate("gmail_delete_email", {}, ctx)
        rule_ids = [r["id"] for r in matched]
        assert "hitl_bulk_email_delete" in rule_ids

    def test_repeat_violator_triggers_hitl(self, engine_v3):
        ctx = self.build_ctx(previous_violations=3)
        matched = engine_v3.evaluate("gmail_read_email", {}, ctx)
        rule_ids = [r["id"] for r in matched]
        assert "hitl_repeat_violator" in rule_ids

    def test_clean_internal_email_matches_no_rules(self, engine_v3):
        """A safe internal email from an authorized role must match zero rules."""
        ctx = self.build_ctx(
            role="junior_dev",
            recipient_domain="acme-corp.com",
            is_internal_recipient=True,
            has_confidential_attachment=False,
            calls_last_minute=1,
            previous_violations=0,
            cumulative_email_deletes_5m=0,
        )
        matched = engine_v3.evaluate(
            "gmail_send_email",
            {"to": "colleague@acme-corp.com"},
            ctx
        )
        assert len(matched) == 0, (
            f"Expected 0 matched rules for safe internal email, got: {[r['id'] for r in matched]}"
        )


class TestTemplateLoading:

    def test_load_finance_template(self, engine_v3):
        success = engine_v3.load_template("finance")
        assert success, "Finance template must load successfully"
        assert engine_v3.active_template == "finance"
        assert len(engine_v3.rules) > 0

    def test_load_healthcare_template(self, engine_v3):
        success = engine_v3.load_template("healthcare")
        assert success, "Healthcare template must load successfully"

    def test_unknown_template_returns_false(self, engine_v3):
        success = engine_v3.load_template("nonexistent_industry")
        assert success is False, "Unknown template must return False"

    def test_template_version_label(self, engine_v3):
        engine_v3.load_template("finance")
        assert engine_v3.active_version.startswith("template:")
