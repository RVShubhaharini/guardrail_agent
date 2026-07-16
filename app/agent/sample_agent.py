import os
import json
import logging
from typing import Dict, Any, List, Optional
from app.config import settings
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# --- Gemini Tool Declarations for Gmail Operations ---

def gmail_send_email(to: str, subject: str, body: str, attachments: Optional[List[dict]] = None) -> dict:
    """Send a new email message to a recipient, optionally including metadata for attachments.
    
    Args:
        to: Recipient email address (e.g., recipient@domain.com).
        subject: The subject text of the email message.
        body: The text body contents of the email message.
        attachments: Optional list of attachment structures, e.g. [{"filename": "invoice.pdf", "content_type": "application/pdf"}]
    """
    return {"to": to, "subject": subject, "body": body, "attachments": attachments}

def gmail_read_email(message_id: str) -> dict:
    """Read and retrieve full contents of a specific email message by its ID.
    
    Args:
        message_id: The unique message key identifier.
    """
    return {"message_id": message_id}

def gmail_search_emails(query: str) -> dict:
    """Search inbox for email messages matching query criteria.
    
    Args:
        query: Search keywords or filters, e.g., 'invoice' or 'from:secops'.
    """
    return {"query": query}

def gmail_delete_email(message_id: str) -> dict:
    """Delete a specific email message, moving it to Trash.
    
    Args:
        message_id: Unique message identifier.
    """
    return {"message_id": message_id}

def gmail_archive_email(message_id: str) -> dict:
    """Archive an email message, removing it from the Inbox label.
    
    Args:
        message_id: Unique message identifier.
    """
    return {"message_id": message_id}

def gmail_restore_email(message_id: str) -> dict:
    """Restore an archived or deleted email message back to the Inbox.
    
    Args:
        message_id: Unique message identifier.
    """
    return {"message_id": message_id}

def gmail_reply_email(message_id: str, body: str) -> dict:
    """Send a reply to an existing email message thread.
    
    Args:
        message_id: The message identifier to reply to.
        body: The text body of the reply message.
    """
    return {"message_id": message_id, "body": body}

def gmail_forward_email(message_id: str, to: str) -> dict:
    """Forward an existing email message to another recipient address.
    
    Args:
        message_id: Unique identifier of the message to forward.
        to: Target recipient email address.
    """
    return {"message_id": message_id, "to": to}

def gmail_manage_labels(message_id: str, add_labels: Optional[List[str]] = None, remove_labels: Optional[List[str]] = None) -> dict:
    """Add or remove labels on a specific email message.
    
    Args:
        message_id: Unique message identifier.
        add_labels: List of labels to apply to the message.
        remove_labels: List of labels to strip from the message.
    """
    return {"message_id": message_id, "add_labels": add_labels, "remove_labels": remove_labels}

# --- Core PS-3.1 Problem Statement Tool Declarations ---

def db_delete(record_count: int) -> dict:
    """Delete a specified number of records from the database.
    
    Args:
        record_count: The number of database records to delete.
    """
    return {"record_count": record_count}

def send_email(to: str, recipient_domain: Optional[str] = None, subject: str = "", body: str = "") -> dict:
    """Send an email message to a recipient.
    
    Args:
        to: The recipient email address.
        recipient_domain: The domain of the recipient (e.g., gmail.com).
        subject: The subject of the email.
        body: The body content of the email.
    """
    return {"to": to, "recipient_domain": recipient_domain or (to.split("@")[-1] if "@" in to else ""), "subject": subject, "body": body}

def read_file(path: str) -> dict:
    """Read the contents of a file at the specified path.
    
    Args:
        path: The absolute or relative path to the file.
    """
    return {"path": path}

def db_write(record_id: str, data: str) -> dict:
    """Write data to a database record.
    
    Args:
        record_id: The identifier of the database record.
        data: The content to write to the database.
    """
    return {"record_id": record_id, "data": data}

# Core registry listings
GMAIL_TOOLS = [
    gmail_send_email,
    gmail_read_email,
    gmail_search_emails,
    gmail_delete_email,
    gmail_archive_email,
    gmail_restore_email,
    gmail_reply_email,
    gmail_forward_email,
    gmail_manage_labels
]

ALL_TOOLS = GMAIL_TOOLS + [
    db_delete,
    send_email,
    read_file,
    db_write
]

# In-memory store for active agent chat histories: agent_id -> list of genai.types.Content
conversation_histories = {}

def run_agent_task(
    agent_id: str,
    instruction: str,
    evaluator,
    execution_gateway = None,
    role: str = "junior_dev"
) -> List[Dict[str, Any]]:
    """Runs a natural language task instruction through the Gemini-2.5-flash agent.
    Intercepts proposed tool calls and evaluates them against SentinelAI rules.
    If allowed, dispatches execution via the ExecutionGateway."""

    api_key = settings.gemini_api_key
    tool_calls = []

    # Ensure conversation history is initialized for this agent session
    if agent_id not in conversation_histories:
        conversation_histories[agent_id] = []
    history = conversation_histories[agent_id]

    # Append new user message to history
    history.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=instruction)]
        )
    )

    if api_key:
        try:
            logger.info(f"Initializing real Gemini AI agent for SentinelAI (History length: {len(history)})...")
            client = genai.Client(api_key=api_key)
            
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=history,
                config=types.GenerateContentConfig(
                    tools=ALL_TOOLS,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True
                    ),
                    system_instruction=(
                        "You are an active agent for SentinelAI email and database automation. "
                        "You must always use the available tools to perform actions like sending emails (gmail_send_email or send_email), "
                        "reading files (read_file), database deletions (db_delete), and database writes (db_write) when requested by the user. "
                        "Do not simply describe or pretend that you have performed the action without making the function call. "
                        "If you need clarification or missing arguments (like recipient 'to', 'subject', or 'body'), ask the user first. "
                        "Once the user provides the missing details, immediately call the appropriate tool."
                    )
                )
            )

            # Extract generated function calls
            if response.function_calls:
                # Store the model's turn containing the tool calls
                history.append(response.candidates[0].content)
                for call in response.function_calls:
                    args_dict = dict(call.args) if call.args else {}
                    tool_calls.append({
                        "name": call.name,
                        "input": args_dict
                    })
            else:
                # Text response - store the model's response in history
                history.append(response.candidates[0].content)
                # .text can be None in thinking mode — extract from parts as fallback
                response_text = response.text
                if not response_text and response.candidates:
                    parts = response.candidates[0].content.parts or []
                    text_parts = [p.text for p in parts if getattr(p, "text", None)]
                    response_text = " ".join(text_parts).strip() or "I'm ready to help. What would you like me to do with your emails?"
                logger.info(f"Gemini text response (no tool calls generated): {response_text}")
                return [{
                    "tool": "conversational_response",
                    "input": {},
                    "outcome": "TEXT_RESPONSE",
                    "text": response_text,
                    "risk_score": 0,
                    "reason": "Conversational response (no action requested)",
                    "explanation": None,
                    "timeline": []
                }]
        except Exception as e:
            logger.error(f"Gemini API execution failed: {e}. Falling back to local rule-based mock parser.")
            tool_calls = _parse_mock_instruction(instruction, history)
    else:
        logger.info("No GEMINI_API_KEY found. Running rule-based mock parser.")
        tool_calls = _parse_mock_instruction(instruction, history)

    # Process and evaluate tool calls
    results = []
    tool_response_parts = []

    for call in tool_calls:
        tool_name = call["name"]
        tool_input = call["input"]
        
        # Inject simulated role context
        tool_input["_role"] = role

        logger.info(f"Agent '{agent_id}' wants to call tool '{tool_name}' with parameters {tool_input}")
        
        # Route through Guardrail Evaluator BEFORE execution
        evaluation = evaluator.evaluate_action(agent_id, tool_name, tool_input)
        
        status = evaluation["status"]
        if status == "blocked":
            results.append({
                "tool": tool_name,
                "input": tool_input,
                "outcome": "BLOCKED",
                "reason": evaluation.get("reason"),
                "risk_score": evaluation.get("risk_score"),
                "explanation": evaluation.get("explanation").model_dump() if evaluation.get("explanation") else None,
                "timeline": [step.model_dump() for step in evaluation.get("timeline", [])]
            })
            # Feed block error back to conversation history
            tool_response_parts.append(
                types.Part.from_function_response(
                    name=tool_name,
                    response={"error": f"Execution Blocked by SentinelAI rules: {evaluation.get('reason')}"}
                )
            )
        elif status == "pending":
            results.append({
                "tool": tool_name,
                "input": tool_input,
                "outcome": "PENDING_HITL",
                "request_id": evaluation.get("request_id"),
                "reason": evaluation.get("reason"),
                "risk_score": evaluation.get("risk_score"),
                "explanation": evaluation.get("explanation").model_dump() if evaluation.get("explanation") else None,
                "timeline": [step.model_dump() for step in evaluation.get("timeline", [])]
            })
            # Action paused for HITL. We will feed the execution response back when approved/executed.
        else: # status == "allowed"
            # Route execution ONLY through ExecutionGateway if present
            if execution_gateway:
                try:
                    tool_result = execution_gateway.execute(agent_id, tool_name, tool_input, role)
                    results.append({
                        "tool": tool_name,
                        "input": tool_input,
                        "outcome": "EXECUTED",
                        "result": tool_result,
                        "risk_score": evaluation.get("risk_score"),
                        "explanation": evaluation.get("explanation").model_dump() if evaluation.get("explanation") else None,
                        "timeline": [step.model_dump() for step in evaluation.get("timeline", [])]
                    })
                    # Google GenAI SDK requires a dictionary for the function response.
                    resp_dict = tool_result if isinstance(tool_result, dict) else {"result": tool_result}
                    tool_response_parts.append(
                        types.Part.from_function_response(
                            name=tool_name,
                            response=resp_dict
                        )
                    )
                    
                    # Auto-chain: if this search was triggered by a delete intent, auto-dispatch deletes
                    if tool_name == "gmail_search_emails" and call.get("delete_after_search"):
                        found_emails = tool_result if isinstance(tool_result, list) else tool_result.get("result", [])
                        for email in found_emails:
                            msg_id = email.get("id") if isinstance(email, dict) else None
                            if msg_id:
                                logger.info(f"Auto-chaining gmail_delete_email for message_id='{msg_id}' (delete_after_search)")
                                # Remove _role from tool_input first as we'll inject it fresh
                                delete_params = {"message_id": msg_id, "_role": role}
                                delete_eval = evaluator.evaluate_action(agent_id, "gmail_delete_email", delete_params)
                                delete_status = delete_eval["status"]
                                if delete_status == "allowed" and execution_gateway:
                                    try:
                                        delete_result = execution_gateway.execute(agent_id, "gmail_delete_email", delete_params, role)
                                        results.append({
                                            "tool": "gmail_delete_email",
                                            "input": delete_params,
                                            "outcome": "EXECUTED",
                                            "result": delete_result,
                                            "risk_score": delete_eval.get("risk_score"),
                                            "explanation": delete_eval.get("explanation").model_dump() if delete_eval.get("explanation") else None,
                                            "timeline": [step.model_dump() for step in delete_eval.get("timeline", [])]
                                        })
                                        tool_response_parts.append(
                                            types.Part.from_function_response(
                                                name="gmail_delete_email",
                                                response=delete_result if isinstance(delete_result, dict) else {"result": delete_result}
                                            )
                                        )
                                        tool_calls.append({"name": "gmail_delete_email", "input": delete_params})
                                    except Exception as de:
                                        results.append({
                                            "tool": "gmail_delete_email",
                                            "input": delete_params,
                                            "outcome": "EXECUTION_ERROR",
                                            "error": str(de)
                                        })
                                elif delete_status == "blocked":
                                    results.append({
                                        "tool": "gmail_delete_email",
                                        "input": delete_params,
                                        "outcome": "BLOCKED",
                                        "reason": delete_eval.get("reason"),
                                        "risk_score": delete_eval.get("risk_score")
                                    })
                except Exception as e:
                    results.append({
                        "tool": tool_name,
                        "input": tool_input,
                        "outcome": "EXECUTION_ERROR",
                        "error": str(e)
                    })
                    tool_response_parts.append(
                        types.Part.from_function_response(
                            name=tool_name,
                            response={"error": str(e)}
                        )
                    )
            else:
                # No execution gateway present (fallback / mock dry run)
                results.append({
                    "tool": tool_name,
                    "input": tool_input,
                    "outcome": "ALLOWED_NO_GATEWAY",
                    "risk_score": evaluation.get("risk_score")
                })
                tool_response_parts.append(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"status": "Allowed (Dry-run mode, no execution gateway)"}
                    )
                )

    def _generate_mock_response(calls, run_results):
        mock_text = ""
        results_by_tool = {r["tool"]: r for r in run_results if "tool" in r}
        for call in calls:
            t_name = call["name"]
            t_input = call["input"]
            exec_res = results_by_tool.get(t_name)
            if t_name == "gmail_search_emails":
                if exec_res and exec_res.get("outcome") == "EXECUTED":
                    emails = exec_res.get("result", [])
                    if isinstance(emails, dict) and "result" in emails:
                        emails = emails["result"]
                    if emails:
                        mock_text = f"I searched for emails matching query '{t_input.get('query')}' and found {len(emails)} matching emails: "
                        mock_text += ", ".join([f"'{e.get('subject') or '(No Subject)'}' (ID: {e.get('id')})" for e in emails])
                    else:
                        mock_text = f"I searched for emails matching query '{t_input.get('query')}' and found 0 matching emails in your inbox."
                else:
                    mock_text = f"I searched for emails matching query '{t_input.get('query')}' and found 0 matching emails in your inbox."
            elif t_name == "gmail_delete_email":
                if exec_res and exec_res.get("outcome") == "EXECUTED":
                    mock_text = f"I have successfully deleted email message '{t_input.get('message_id')}' from your inbox."
                else:
                    mock_text = f"I have dispatched a delete request for email message '{t_input.get('message_id')}'."
            elif t_name == "gmail_send_email":
                if exec_res and exec_res.get("outcome") == "EXECUTED":
                    mock_text = f"I have successfully sent the email to '{t_input.get('to')}'."
                else:
                    mock_text = f"I have dispatched a send email request to '{t_input.get('to')}'."
            elif t_name == "db_delete":
                if exec_res and exec_res.get("outcome") == "EXECUTED":
                    mock_text = f"Database operation successful: Deleted {t_input.get('record_count')} records."
                else:
                    mock_text = f"A database delete request of {t_input.get('record_count')} records was parsed."
            elif t_name == "send_email":
                if exec_res and exec_res.get("outcome") == "EXECUTED":
                    mock_text = f"Successfully sent email to '{t_input.get('to')}'."
                else:
                    mock_text = f"An email send request to '{t_input.get('to')}' was parsed."
            elif t_name == "read_file":
                if exec_res and exec_res.get("outcome") == "EXECUTED":
                    mock_text = f"Successfully read file content from '{t_input.get('path')}': [File data matches criteria]."
                else:
                    mock_text = f"A file read request for path '{t_input.get('path')}' was parsed."
            elif t_name == "db_write":
                if exec_res and exec_res.get("outcome") == "EXECUTED":
                    mock_text = f"Successfully wrote database record '{t_input.get('record_id')}'."
                else:
                    mock_text = f"A database write request for record '{t_input.get('record_id')}' was parsed."
        if mock_text:
            return {
                "tool": "conversational_response",
                "input": {},
                "outcome": "TEXT_RESPONSE",
                "text": mock_text,
                "risk_score": 0,
                "reason": "Mock conversational response after execution",
                "explanation": None,
                "timeline": []
            }
        return None

    # Sync successfully run tool responses to the conversation history
    # Only call final turn if there were no blocks or pending HITL actions
    any_blocked_or_pending = any(r.get("outcome") in ("BLOCKED", "PENDING_HITL") for r in results)
    
    if tool_response_parts and not any_blocked_or_pending:
        if api_key:
            history.append(
                types.Content(
                    role="user",
                    parts=tool_response_parts
                )
            )
            
            # Call Gemini again to let the model interpret execution outcomes and respond
            try:
                logger.info("Calling Gemini API again for final conversational turn with tool results...")
                client = genai.Client(api_key=api_key)
                final_response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=history,
                    config=types.GenerateContentConfig(
                        tools=ALL_TOOLS,
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(
                            disable=True
                        ),
                        system_instruction=(
                            "You are an active agent for SentinelAI email and database automation. "
                            "You must always use the available tools to perform actions like sending emails (gmail_send_email or send_email), "
                            "reading files (read_file), database deletions (db_delete), and database writes (db_write) when requested by the user. "
                            "Do not simply describe or pretend that you have performed the action without making the function call. "
                            "If you need clarification or missing arguments (like recipient 'to', 'subject', or 'body'), ask the user first. "
                            "Once the user provides the missing details, immediately call the appropriate tool."
                        )
                    )
                )
                
                # Store final model response in history
                if final_response.candidates:
                    history.append(final_response.candidates[0].content)
                
                if final_response.text:
                    results.append({
                        "tool": "conversational_response",
                        "input": {},
                        "outcome": "TEXT_RESPONSE",
                        "text": final_response.text,
                        "risk_score": 0,
                        "reason": "Final conversational response after tool execution",
                        "explanation": None,
                        "timeline": []
                    })
                elif final_response.candidates:
                    # .text can be None in thinking mode — extract from parts
                    parts = final_response.candidates[0].content.parts or []
                    text_parts = [p.text for p in parts if getattr(p, "text", None)]
                    fallback_text = " ".join(text_parts).strip()
                    if fallback_text:
                        results.append({
                            "tool": "conversational_response",
                            "input": {},
                            "outcome": "TEXT_RESPONSE",
                            "text": fallback_text,
                            "risk_score": 0,
                            "reason": "Final conversational response after tool execution",
                            "explanation": None,
                            "timeline": []
                        })
            except Exception as e:
                logger.error(f"Gemini API final response generation failed: {e}. Falling back to mock text.")
                mock_res = _generate_mock_response(tool_calls, results)
                if mock_res:
                    results.append(mock_res)
        else:
            # Fallback mock mode conversational response
            mock_res = _generate_mock_response(tool_calls, results)
            if mock_res:
                results.append(mock_res)

    return results

def _parse_mock_instruction(instruction: str, history: List[Any] = None) -> List[Dict[str, Any]]:
    """Fallback natural language instruction parser to generate structured tool calls without calling API.
    Correctly maps PS-3.1 requirements (database delete, send email, read file) to respective tools."""
    inst_lower = instruction.lower()
    calls = []
    
    # Compile combined history context for extracting parameters
    combined_history = instruction
    if history:
        combined_history = " ".join([
            part.text for msg in history if msg.role == "user" for part in msg.parts if getattr(part, "text", None)
        ])
    comb_lower = combined_history.lower()

    # 1. Database Delete Checks (PS-3.1 Success Criteria)
    if "delete" in inst_lower and ("record" in inst_lower or "db" in inst_lower or "database" in inst_lower or "count" in inst_lower):
        # Extract number (e.g., delete 500 records -> 500, delete 5 records -> 5)
        count = 100
        for word in instruction.split():
            if word.isdigit():
                count = int(word)
                break
        calls.append({
            "name": "db_delete",
            "input": {"record_count": count}
        })

    # 2. Read File Checks (PS-3.1 Success Criteria)
    elif "read" in inst_lower and ("path" in inst_lower or "file" in inst_lower or "confidential" in inst_lower or ".txt" in inst_lower):
        path = "/system/keys.txt"
        for word in instruction.split():
            if "/" in word or "\\" in word or "." in word:
                path = word.strip(".,;:()<>\"'")
                break
        if "confidential" in inst_lower and "confidential" not in path.lower():
            path = "/system/confidential_data.txt"
        calls.append({
            "name": "read_file",
            "input": {"path": path}
        })

    # 3. Database Write Checks
    elif "write" in inst_lower and ("record" in inst_lower or "db" in inst_lower or "database" in inst_lower):
        record_id = "rec_001"
        for word in instruction.split():
            if "_" in word or "-" in word:
                record_id = word.strip(".,;:()<>\"'")
                break
        calls.append({
            "name": "db_write",
            "input": {"record_id": record_id, "data": "Updated record details."}
        })

    # 4. Delete Email Checks
    elif "delete" in inst_lower or "remove" in inst_lower:
        sender = None
        for word in instruction.split():
            if "@" in word:
                sender = word.strip(".,;:()<>\"'")
                break
        
        if sender:
            calls.append({
                "name": "gmail_search_emails",
                "input": {"query": f"from:{sender}"},
                "delete_after_search": True
            })
        else:
            message_id = "msg_001"
            for word in instruction.split():
                clean_word = word.strip(".,;:()<>\"'")
                if clean_word.startswith("msg_") or "msg-" in clean_word or (len(clean_word) == 16 and all(c in "0123456789abcdefABCDEF" for c in clean_word)):
                    message_id = clean_word
                    break
            calls.append({
                "name": "gmail_delete_email",
                "input": {"message_id": message_id}
            })

    # 5. Email Send Checks (both send_email and gmail_send_email)
    elif "send" in inst_lower or "write" in inst_lower or ("email" in inst_lower and "to" in inst_lower):
        to = None
        for word in instruction.split():
            if "@" in word:
                to = word.strip(".,;:()<>\"'")
                break
        if not to:
            to = "recipient@acme-corp.com"
            for word in combined_history.split():
                if "@" in word:
                    to = word.strip(".,;:()<>\"'")
                    break
            
        subject = "SentinelAI Security Broadcast"
        if "subject is" in comb_lower:
            parts = combined_history.split("subject is", 1)
            if len(parts) > 1:
                subject = parts[1].split("with the body", 1)[0].split("body", 1)[0].strip("\"' ")
        elif "subject:" in comb_lower:
            parts = combined_history.split("subject:", 1)
            if len(parts) > 1:
                subject = parts[1].split("with the body", 1)[0].split("body", 1)[0].strip("\"' ")
        elif "roadmap review" in comb_lower:
            subject = "roadmap review"
            
        body = "Hi, please find attached the requested files."
        if "body as like this -" in comb_lower:
            parts = combined_history.split("body as like this -", 1)
            if len(parts) > 1:
                body = parts[1].split("subject", 1)[0].strip("\"' ")
        elif "body:" in comb_lower:
            parts = combined_history.split("body:", 1)
            if len(parts) > 1:
                body = parts[1].split("subject", 1)[0].strip("\"' ")
        elif "body" in comb_lower:
            parts = combined_history.split("body", 1)
            if len(parts) > 1:
                body_candidate = parts[1].strip()
                if body_candidate.startswith("as"):
                    body_candidate = body_candidate[2:].strip()
                    if body_candidate.startswith("like this"):
                        body_candidate = body_candidate[9:].strip()
                body = body_candidate.split("subject", 1)[0].strip("- \"' ")
            
        attachments = []
        if "attachment" in comb_lower or "salary" in comb_lower or "pdf" in comb_lower:
            attachments = [{"filename": "salary_sheet_q2.pdf", "content_type": "application/pdf"}]

        # Check if we should use raw PS-3.1 send_email or gmail_send_email
        tool_name = "send_email" if "send_email" in inst_lower or "send email" in inst_lower else "gmail_send_email"
        calls.append({
            "name": tool_name,
            "input": {
                "to": to,
                "recipient_domain": to.split("@")[-1] if "@" in to else "acme-corp.com",
                "subject": subject,
                "body": body,
                "attachments": attachments
            }
        })

    # 6. Read Email Checks
    elif "read" in inst_lower or "view" in inst_lower:
        message_id = "msg_002"
        for word in instruction.split():
            if word.startswith("msg_") or "msg-" in word:
                message_id = word.strip(".,;:()<>\"'")
                break
        calls.append({
            "name": "gmail_read_email",
            "input": {"message_id": message_id}
        })

    # Default fallback
    if not calls:
        calls.append({
            "name": "gmail_search_emails",
            "input": {"query": "inbox"}
        })

    return calls

