import uuid
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.audit.store import AuditStore
from app.config import settings

logger = logging.getLogger(__name__)


class HitlQueue:
    """Manages the Human-in-the-Loop review queue.
    Stores pending authorization requests and handles approved/rejected resolutions.

    Persistence strategy:
    - Local development: in-memory dict (fast, no dependencies)
    - AWS production (USE_DYNAMODB=true): DynamoDB table with pk=HITL#<request_id>
      This ensures HITL requests survive ECS container restarts / redeployments.
    """

    HITL_PREFIX = "HITL#"

    def __init__(self, audit_store: AuditStore):
        # In-memory fallback store (always used for local dev)
        self.pending: Dict[str, Dict[str, Any]] = {}
        self.audit = audit_store
        self.use_dynamo = settings.use_dynamodb

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enqueue(
        self,
        agent_id: str,
        tool: str,
        params: dict,
        reason: str,
        risk_score: int,
        policy_version: str
    ) -> str:
        """Create a new pending HITL authorization request.

        Returns the request_id string for later resolution.
        """
        request_id = str(uuid.uuid4())
        item = {
            "request_id": request_id,
            "agent_id": agent_id,
            "tool": tool,
            "params": params,
            "reason": reason,
            "risk_score": risk_score,
            "policy_version": policy_version,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
        }

        # Always keep in-memory copy for fast lookups within the same process
        self.pending[request_id] = item

        # Persist to DynamoDB for cross-restart durability
        if self.use_dynamo:
            self._dynamo_put(request_id, item)

        logger.info(f"[HITL] Enqueued request_id={request_id} for tool={tool} agent={agent_id}")
        return request_id

    def resolve(
        self,
        request_id: str,
        decision: str,
        reviewer: str = "admin_reviewer"
    ) -> Optional[dict]:
        """Approve or reject a pending HITL request.

        Args:
            request_id: UUID of the HITL request.
            decision: Either 'approved' or 'rejected'.
            reviewer: Human operator identifier.

        Returns:
            The resolved item dict, or None if not found.
        """
        # Try in-memory first, then fall back to DynamoDB query
        item = self.pending.get(request_id)
        if not item and self.use_dynamo:
            item = self._dynamo_get(request_id)

        if not item:
            logger.warning(f"[HITL] resolve called for unknown request_id={request_id}")
            return None

        item["status"] = decision  # "approved" or "rejected"
        item["reviewer"] = reviewer
        item["resolved_at"] = datetime.utcnow().isoformat()

        # Write resolution into the central audit log
        resolution_record = {
            **item,
            "event": "hitl_resolution",
            "action": f"hitl_{decision}"
        }
        self.audit.write(resolution_record)

        # Remove from active pending stores
        self.pending.pop(request_id, None)
        if self.use_dynamo:
            self._dynamo_delete(request_id)

        logger.info(f"[HITL] Resolved request_id={request_id} as '{decision}' by reviewer='{reviewer}'")
        return item

    def get_status(self, request_id: str) -> Optional[dict]:
        """Return the current state of a HITL request (pending only)."""
        item = self.pending.get(request_id)
        if not item and self.use_dynamo:
            item = self._dynamo_get(request_id)
        return item

    def list_pending(self) -> List[dict]:
        """Return all currently pending HITL authorization requests."""
        if self.use_dynamo:
            # Rebuild in-memory from DynamoDB (handles multi-replica ECS cases)
            dynamo_pending = self._dynamo_list_pending()
            # Merge with in-memory (in-memory is authoritative for same-process requests)
            merged = {item["request_id"]: item for item in dynamo_pending}
            merged.update(self.pending)
            return list(merged.values())
        return list(self.pending.values())

    # ------------------------------------------------------------------
    # DynamoDB Helpers (only active when USE_DYNAMODB=true)
    # ------------------------------------------------------------------

    def _dynamo_put(self, request_id: str, item: dict):
        """Persist a HITL request to DynamoDB."""
        try:
            table = self.audit.table
            dynamo_item = {
                # Use composite key: id=HITL#<uuid>, timestamp=created_at
                "id": f"{self.HITL_PREFIX}{request_id}",
                "timestamp": item["created_at"],
                **{k: v for k, v in item.items() if v is not None},
                # Serialize nested dicts to JSON strings for DynamoDB compatibility
                "params": json.dumps(item.get("params", {}), default=str),
            }
            table.put_item(Item=dynamo_item)
        except Exception as e:
            logger.error(f"[HITL] DynamoDB put failed for request_id={request_id}: {e}")

    def _dynamo_get(self, request_id: str) -> Optional[dict]:
        """Retrieve a single HITL request from DynamoDB by request_id."""
        try:
            table = self.audit.table
            # Scan for matching HITL item (acceptable — HITL queue is always small)
            response = table.scan(
                FilterExpression="begins_with(#id, :prefix) AND request_id = :rid",
                ExpressionAttributeNames={"#id": "id"},
                ExpressionAttributeValues={
                    ":prefix": self.HITL_PREFIX,
                    ":rid": request_id
                },
                Limit=1
            )
            items = response.get("Items", [])
            if items:
                item = items[0]
                # Deserialize params back from JSON string
                if isinstance(item.get("params"), str):
                    item["params"] = json.loads(item["params"])
                return item
        except Exception as e:
            logger.error(f"[HITL] DynamoDB get failed for request_id={request_id}: {e}")
        return None

    def _dynamo_delete(self, request_id: str):
        """Remove a resolved HITL request from the DynamoDB pending store."""
        try:
            table = self.audit.table
            # We need to find the timestamp to build the composite key
            items_response = table.scan(
                FilterExpression="begins_with(#id, :prefix) AND request_id = :rid",
                ExpressionAttributeNames={"#id": "id"},
                ExpressionAttributeValues={
                    ":prefix": self.HITL_PREFIX,
                    ":rid": request_id
                },
                Limit=1
            )
            items = items_response.get("Items", [])
            for item in items:
                table.delete_item(
                    Key={"id": item["id"], "timestamp": item["timestamp"]}
                )
        except Exception as e:
            logger.error(f"[HITL] DynamoDB delete failed for request_id={request_id}: {e}")

    def _dynamo_list_pending(self) -> List[dict]:
        """List all pending HITL requests from DynamoDB."""
        try:
            table = self.audit.table
            response = table.scan(
                FilterExpression="begins_with(#id, :prefix) AND #status = :pending",
                ExpressionAttributeNames={"#id": "id", "#status": "status"},
                ExpressionAttributeValues={
                    ":prefix": self.HITL_PREFIX,
                    ":pending": "pending"
                }
            )
            items = response.get("Items", [])
            # Deserialize params
            for item in items:
                if isinstance(item.get("params"), str):
                    try:
                        item["params"] = json.loads(item["params"])
                    except Exception:
                        pass
            return sorted(items, key=lambda x: x.get("created_at", ""), reverse=True)
        except Exception as e:
            logger.error(f"[HITL] DynamoDB list_pending failed: {e}")
            return []
