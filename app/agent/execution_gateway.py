import logging
from typing import Dict, Any, Optional
from datetime import datetime
from app.agent.gmail_connector import GmailConnector
from app.audit.store import AuditStore

logger = logging.getLogger(__name__)

class ExecutionGateway:
    """Enterprise Execution Gateway.
    The ONLY system component authorized to invoke the GmailConnector.
    Handles final verification, executes tool logic, and logs output results."""

    def __init__(self, gmail_connector: GmailConnector, audit_store: AuditStore):
        self.connector = gmail_connector
        self.audit = audit_store

    def execute(self, agent_id: str, tool_name: str, params: dict, role: str) -> Dict[str, Any]:
        logger.info(f"ExecutionGateway intercepting invocation: {tool_name} for Agent '{agent_id}' (Role: {role})")

        # 1. Final Security Gateway Validations (Layer 1 & Layer 3 redundant checks)
        if not agent_id or role == "anonymous":
            raise PermissionError("Execution Gateway Block: Request is unauthenticated.")
            
        if tool_name == "gmail_delete_email" and role in ("guest", "intern", "support"):
            raise PermissionError(f"Execution Gateway Block: Role '{role}' is not authorized to delete corporate emails.")

        # 2. Resolve target tool execution
        now_str = datetime.utcnow().isoformat()
        status = "success"
        result = {}

        try:
            if tool_name == "gmail_send_email":
                result = self.connector.send_email(
                    to=params.get("to"),
                    subject=params.get("subject"),
                    body=params.get("body"),
                    attachments=params.get("attachments")
                )
            elif tool_name == "gmail_read_email":
                result = self.connector.read_email(message_id=params.get("message_id"))
            elif tool_name == "gmail_search_emails":
                result = self.connector.search_emails(query=params.get("query"))
            elif tool_name == "gmail_delete_email":
                success = self.connector.delete_email(message_id=params.get("message_id"))
                if not success:
                    raise ValueError(f"Failed to delete email message '{params.get('message_id')}'. Message ID not found.")
                result = {"status": "deleted"}
            elif tool_name == "gmail_archive_email":
                success = self.connector.archive_email(message_id=params.get("message_id"))
                if not success:
                    raise ValueError(f"Failed to archive email message '{params.get('message_id')}'. Message ID not found.")
                result = {"status": "archived"}
            elif tool_name == "gmail_restore_email":
                success = self.connector.restore_email(message_id=params.get("message_id"))
                if not success:
                    raise ValueError(f"Failed to restore email message '{params.get('message_id')}'. Message ID not found.")
                result = {"status": "restored"}
            elif tool_name == "gmail_reply_email":
                result = self.connector.reply_email(
                    message_id=params.get("message_id"),
                    body=params.get("body")
                )
            elif tool_name == "gmail_forward_email":
                result = self.connector.forward_email(
                    message_id=params.get("message_id"),
                    to=params.get("to")
                )
            elif tool_name == "gmail_manage_labels":
                success = self.connector.manage_labels(
                    message_id=params.get("message_id"),
                    add_labels=params.get("add_labels", []),
                    remove_labels=params.get("remove_labels", [])
                )
                if not success:
                    raise ValueError(f"Failed to update labels for email message '{params.get('message_id')}'. Message ID not found.")
                result = {"status": "updated"}
            elif tool_name == "db_delete":
                # Maps database records to the Gmail inbox folder as requested!
                count = params.get("record_count", 0)
                deleted_ids = []
                try:
                    # List recent inbox items
                    emails = self.connector.list_emails(label_filter="INBOX")
                    # Take first N emails
                    to_delete = emails[:count] if count > 0 else []
                    for email in to_delete:
                        msg_id = email.get("id")
                        if msg_id:
                            self.connector.delete_email(message_id=msg_id)
                            deleted_ids.append(msg_id)
                    result = {
                        "status": "success",
                        "message": f"Successfully deleted {len(deleted_ids)} inbox records (emails) from the Gmail INBOX folder.",
                        "deleted_record_ids": deleted_ids,
                        "target_count": count
                    }
                except Exception as ex:
                    logger.error(f"Error executing db_delete on inbox: {ex}")
                    result = {"status": "failed", "error": str(ex)}
            elif tool_name == "send_email":
                result = self.connector.send_email(
                    to=params.get("to"),
                    subject=params.get("subject"),
                    body=params.get("body"),
                    attachments=params.get("attachments")
                )
            elif tool_name == "read_file":
                # Simulated file reading
                result = {"status": "success", "path": params.get("path"), "content": "Sample file contents for preview."}
            elif tool_name == "db_write":
                # Simulated database write
                result = {"status": "success", "record_id": params.get("record_id"), "message": "Record written successfully."}
            else:
                raise ValueError(f"Unknown operations target: {tool_name}")

        except Exception as e:
            status = "failed"
            result = {"error": str(e)}
            logger.error(f"Execution Gateway error running '{tool_name}': {e}")
            raise e

        finally:
            # 3. Log execution event in central audits store
            execution_record = {
                "timestamp": now_str,
                "event": "execution_gateway_dispatch",
                "agent_id": agent_id,
                "tool": tool_name,
                "params": params,
                "role": role,
                "status": status,
                "result": result
            }
            self.audit.write(execution_record)

        return result
