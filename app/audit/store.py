import os
import json
import sqlite3
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.config import settings

class AuditStore:
    """Handles audit logging using SQLite for local development and DynamoDB for AWS deployments."""

    def __init__(self):
        self.use_dynamo = settings.use_dynamodb
        if self.use_dynamo:
            import boto3
            self.dynamodb = boto3.resource("dynamodb", region_name=settings.aws_default_region)
            self.table = self.dynamodb.Table(settings.audit_table)
        else:
            self.db_path = "audit.db"
            self._init_sqlite()

    def _init_sqlite(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    agent_id TEXT,
                    tool TEXT,
                    action TEXT,
                    policy_version TEXT,
                    risk_score INTEGER,
                    payload TEXT
                )
            """)
        conn.close()

    def write(self, record: dict):
        record.setdefault("id", f"{datetime.utcnow().timestamp()}")
        record.setdefault("timestamp", datetime.utcnow().isoformat())
        
        # Serialize payloads nicely
        # Remove nested structures or use json.dumps for sub-objects
        serialized_payload = json.dumps(record, default=str)

        if self.use_dynamo:
            # DynamoDB put
            item = json.loads(serialized_payload)
            # DynamoDB does not support empty strings or floats cleanly sometimes, 
            # but standard json dumps/loads will create correct DynamoDB types.
            self.table.put_item(Item=item)
        else:
            # SQLite insert
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            with conn:
                conn.execute(
                    "INSERT INTO audit (id, timestamp, agent_id, tool, action, policy_version, risk_score, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        record["id"],
                        record.get("timestamp"),
                        record.get("agent_id"),
                        record.get("tool"),
                        record.get("action"),
                        record.get("policy_version", "v1"),
                        record.get("risk_score", 0),
                        serialized_payload
                    )
                )
            conn.close()

    def search(
        self,
        agent_id: Optional[str] = None,
        tool: Optional[str] = None,
        action: Optional[str] = None,
        policy_version: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        
        if self.use_dynamo:
            # Build DynamoDB scan filter expressions
            filter_expression = None
            expression_attribute_values = {}
            expression_attribute_names = {}
            
            filters = []
            if agent_id:
                filters.append("agent_id = :agent_id")
                expression_attribute_values[":agent_id"] = agent_id
            if tool:
                filters.append("tool = :tool")
                expression_attribute_values[":tool"] = tool
            if action:
                filters.append("#act = :action") # action is a reserved keyword in DynamoDB
                expression_attribute_values[":action"] = action
                expression_attribute_names["#act"] = "action"
            if policy_version:
                filters.append("policy_version = :policy_version")
                expression_attribute_values[":policy_version"] = policy_version

            scan_args = {"Limit": limit}
            if filters:
                scan_args["FilterExpression"] = " AND ".join(filters)
                scan_args["ExpressionAttributeValues"] = expression_attribute_values
                if expression_attribute_names:
                    scan_args["ExpressionAttributeNames"] = expression_attribute_names

            try:
                resp = self.table.scan(**scan_args)
                items = resp.get("Items", [])
                # DynamoDB scans are unordered, sort by timestamp descending
                return sorted(items, key=lambda r: r.get("timestamp", ""), reverse=True)
            except Exception as e:
                print(f"DynamoDB scan error: {e}")
                return []
        else:
            # SQLite query with dynamic conditions
            query = "SELECT payload FROM audit WHERE 1=1"
            params = []
            if agent_id:
                query += " AND agent_id = ?"
                params.append(agent_id)
            if tool:
                query += " AND tool = ?"
                params.append(tool)
            if action:
                query += " AND action = ?"
                params.append(action)
            if policy_version:
                query += " AND policy_version = ?"
                params.append(policy_version)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            rows = conn.execute(query, tuple(params)).fetchall()
            conn.close()
            return [json.loads(r[0]) for r in rows]

    def recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.search(limit=limit)
