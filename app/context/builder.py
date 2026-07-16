from datetime import datetime
from typing import Dict, Any, List, Optional
from app.utils.rate_limiter import RateLimiter

# Internal corporate domains for recipient domain classification
INTERNAL_DOMAINS = {"acme-corp.com", "internal.acme-corp.com"}

# Attachment keywords that classify an email as containing confidential material
CONFIDENTIAL_KEYWORDS = [
    "confidential", "salary", "salaries", "payroll", "secrets",
    "tax", "passport", "contract", "ssn", "pii", "classified",
    "restricted", "private", "credential", "password"
]

# Data path keywords that trigger restricted classification
RESTRICTED_PATH_KEYWORDS = ["confidential", "restricted", "secrets", "private", "classified"]


class ContextBuilder:
    """Enriches agent action requests with multi-dimensional security context.

    The context object is the input to the PolicyEngine's rule evaluation.
    Each field maps directly to conditions used in the YAML rule sets.

    Context Layers:
      1. Temporal  — hour_of_day, business_hours flag
      2. Rate      — calls_last_minute per agent+tool
      3. Identity  — role (from params._role)
      4. Recipient — recipient_domain vs internal_domains
      5. Attachment — has_confidential_attachment (filename classification)
      6. Data      — data_classification (general / sensitive / restricted)
      7. Violations — previous_violations from audit history
      8. Cumulative — cumulative_deletes_5m, cumulative_email_deletes_5m
      9. Geo Stub  — geo_context (extensibility placeholder)
    """

    def __init__(self, rate_limiter: RateLimiter):
        self.rate_limiter = rate_limiter

    def build_context(
        self,
        agent_id: str,
        tool: str,
        params: Dict[str, Any],
        audit_store=None
    ) -> Dict[str, Any]:
        """Build and return the full security context dictionary for rule evaluation."""

        # ── Layer 1: Temporal context ─────────────────────────────────
        now = datetime.utcnow()
        hour_of_day = now.hour
        # Business hours: 6 AM – 9 PM UTC
        business_hours = 6 <= hour_of_day <= 21

        # ── Layer 2: Rate limiting counts ─────────────────────────────
        calls_last_minute = self.rate_limiter.record_and_count(agent_id, tool)

        # ── Layer 3: Role resolution ──────────────────────────────────
        role = params.get("_role", "junior_dev")

        # ── Layer 4: Recipient domain classification ──────────────────
        recipient_domain = self._resolve_recipient_domain(params)
        is_internal_recipient = recipient_domain in INTERNAL_DOMAINS if recipient_domain else True

        # ── Layer 5: Attachment content classification ─────────────────
        has_confidential_attachment = self._has_confidential_attachment(params)

        # ── Layer 6: Data classification ──────────────────────────────
        data_classification = self._classify_data(tool, params, has_confidential_attachment)

        # ── Layer 7: Historical violations ────────────────────────────
        previous_violations = self._count_previous_violations(agent_id, audit_store)

        # ── Layer 8: Cumulative metric tracking ───────────────────────
        cumulative_deletes_5m = self._track_db_deletes(agent_id, tool, params)
        cumulative_email_deletes_5m = self._track_email_deletes(agent_id, tool)

        # ── Layer 9: Geo context stub (extensibility) ─────────────────
        # In production, this would resolve from IP geolocation or VPN header
        geo_context = "domestic"

        return {
            # Identity
            "agent_id": agent_id,
            "role": role,

            # Temporal
            "hour_of_day": hour_of_day,
            "business_hours": business_hours,
            "timestamp": now.isoformat(),

            # Rate limiting
            "calls_last_minute": calls_last_minute,

            # Recipient / domain
            "recipient_domain": recipient_domain,
            "internal_domains": INTERNAL_DOMAINS,
            "is_internal_recipient": is_internal_recipient,

            # Attachment classification
            "has_confidential_attachment": has_confidential_attachment,

            # Data classification
            "data_classification": data_classification,

            # History
            "previous_violations": previous_violations,

            # Cumulative tracking
            "cumulative_deletes_5m": cumulative_deletes_5m,
            "cumulative_email_deletes_5m": cumulative_email_deletes_5m,

            # Geo
            "geo_context": geo_context,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_recipient_domain(self, params: Dict[str, Any]) -> str:
        """Extract the email domain from the 'to' parameter."""
        to_field = params.get("to", "")
        if isinstance(to_field, str) and "@" in to_field:
            return to_field.split("@")[-1].strip().lower()
        elif isinstance(to_field, list) and len(to_field) > 0:
            first = to_field[0]
            if isinstance(first, str) and "@" in first:
                return first.split("@")[-1].strip().lower()
        return ""

    def _has_confidential_attachment(self, params: Dict[str, Any]) -> bool:
        """Returns True if any attachment filename contains a confidential keyword."""
        # Explicit simulation override (for playground/testing)
        if params.get("_has_confidential_attachment") is True:
            return True

        attachments = params.get("attachments", [])
        if isinstance(attachments, list):
            for attach in attachments:
                if isinstance(attach, dict):
                    filename = attach.get("filename", "").lower()
                    if any(kw in filename for kw in CONFIDENTIAL_KEYWORDS):
                        return True
        return False

    def _classify_data(
        self,
        tool: str,
        params: Dict[str, Any],
        has_confidential_attachment: bool
    ) -> str:
        """Infer data classification level from tool and parameters."""
        path = params.get("path", "")
        if isinstance(path, str) and any(k in path.lower() for k in RESTRICTED_PATH_KEYWORDS):
            return "restricted"
        if has_confidential_attachment:
            return "restricted"
        if tool == "db_delete" and params.get("record_count", 0) > 50:
            return "sensitive"
        return "general"

    def _count_previous_violations(self, agent_id: str, audit_store) -> int:
        """Count how many times this agent has been blocked in recent audit history."""
        if audit_store is None:
            return 0
        try:
            recent_logs = audit_store.recent(limit=100)
            return sum(
                1 for log in recent_logs
                if log.get("agent_id") == agent_id and log.get("action") == "block"
            )
        except Exception as e:
            print(f"[ContextBuilder] Error counting previous violations: {e}")
            return 0

    def _track_db_deletes(self, agent_id: str, tool: str, params: Dict[str, Any]) -> float:
        """Track cumulative database delete volume in the last 5 minutes."""
        if tool == "db_delete":
            deleted_count = params.get("record_count", 0)
            return self.rate_limiter.record_and_sum_metric(
                agent_id=agent_id,
                metric_name="cumulative_deletes_5m",
                value=float(deleted_count)
            )
        return 0

    def _track_email_deletes(self, agent_id: str, tool: str) -> float:
        """Track cumulative email delete/archive operations in the last 5 minutes."""
        if tool in ("gmail_delete_email", "gmail_archive_email"):
            return self.rate_limiter.record_and_sum_metric(
                agent_id=agent_id,
                metric_name="cumulative_email_deletes_5m",
                value=1.0
            )
        return 0
