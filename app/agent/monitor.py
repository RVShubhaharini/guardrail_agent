import threading
import time
import logging
import json
import re
from typing import Dict, Any, List, Optional
from fastapi import FastAPI
from app.config import settings

logger = logging.getLogger(__name__)

# In-memory cache of processed email IDs
processed_email_ids = set()

def start_inbox_monitor(app: FastAPI):
    """Starts the background thread to monitor the inbox for new emails autonomously."""
    if not settings.enable_monitor:
        logger.info("Inbox monitor is disabled by configuration (ENABLE_MONITOR=false).")
        return
        
    thread = threading.Thread(
        target=_monitor_loop,
        args=(app,),
        name="SentinelAI-InboxMonitor",
        daemon=True
    )
    thread.start()
    logger.info(f"Inbox monitor thread started successfully (polling every {settings.monitor_interval}s).")

def _monitor_loop(app: FastAPI):
    """Infinite background loop polling the inbox for new entries."""
    gmail_connector = app.state.gmail_connector
    
    # 1. Warm up the cache with existing emails so we only process *new* arrivals
    try:
        startup_emails = gmail_connector.list_emails()
        for email in startup_emails:
            processed_email_ids.add(email["id"])
        logger.info(f"[Monitor] Initialized with {len(processed_email_ids)} existing startup emails.")
    except Exception as e:
        logger.error(f"[Monitor] Error during initialization: {e}")

    # 2. Start polling
    while True:
        try:
            # Polling delay
            time.sleep(settings.monitor_interval)
            
            # Fetch latest inbox messages
            emails = gmail_connector.list_emails()
            for email in emails:
                email_id = email["id"]
                if email_id not in processed_email_ids:
                    logger.info(f"[Monitor] New email detected! ID={email_id}, Subject='{email.get('subject')}'")
                    _process_new_email(app, email)
                    processed_email_ids.add(email_id)
        except Exception as e:
            logger.error(f"[Monitor] Error in background monitoring loop: {e}")

def _plan_action_for_email(email: dict) -> dict:
    """Uses LLM (Gemini or Groq) to plan an autonomous action for the email.
    Falls back to a deterministic rule-based heuristic if API keys are missing or calls fail.
    """
    subject = email.get("subject", "")
    body = email.get("body", "")
    sender = email.get("from", "")
    attachments = email.get("attachments", [])
    
    groq_api_key = settings.groq_api_key
    gemini_api_key = settings.gemini_api_key
    
    prompt = (
        "You are an Autonomous AI Agent Inbox Monitor for SentinelAI.\n"
        "Your task is to analyze the following incoming email and propose an action if necessary:\n\n"
        f"Sender: {sender}\n"
        f"Subject: {subject}\n"
        f"Body: {body}\n"
        f"Attachments: {json.dumps(attachments)}\n\n"
        "Determine if any security, operational, or automation action is required.\n"
        "Available actions:\n"
        "- gmail_delete_email (params: {'message_id': string})\n"
        "- gmail_archive_email (params: {'message_id': string})\n"
        "- gmail_send_email (params: {'to': string, 'subject': string, 'body': string, 'attachments': list})\n"
        "- gmail_forward_email (params: {'message_id': string, 'to': string})\n"
        "- gmail_reply_email (params: {'message_id': string, 'body': string})\n"
        "- gmail_manage_labels (params: {'message_id': string, 'add_labels': list, 'remove_labels': list})\n"
        "- db_delete (params: {'record_count': int})\n"
        "- db_write (params: {'record_id': string, 'data': string})\n"
        "- read_file (params: {'path': string})\n\n"
        "Return a JSON response matching the following schema:\n"
        "{\n"
        '  "action_required": boolean,\n'
        '  "tool": string (the action name, or null),\n'
        '  "params": object (parameters for the tool, or null),\n'
        '  "reason": "Concise natural language explanation of why you proposed this action"\n'
        "}\n"
        "Do not include markdown formatting or thinking blocks. Output only raw JSON."
    )
    
    # 1. Try Groq Llama Planner
    if groq_api_key:
        try:
            import requests
            headers = {
                "Authorization": f"Bearer {groq_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "temperature": 0.0
            }
            res = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=5.0
            )
            if res.status_code == 200:
                result = json.loads(res.json()["choices"][0]["message"]["content"].strip())
                if result.get("action_required") and result.get("params"):
                    if "message_id" in result["params"] or result["tool"] in ("gmail_delete_email", "gmail_archive_email", "gmail_forward_email", "gmail_reply_email", "gmail_manage_labels"):
                        result["params"]["message_id"] = email["id"]
                return result
        except Exception as e:
            logger.error(f"[Monitor Planner - Groq] Failed: {e}")
            
    # 2. Try Gemini
    if gemini_api_key:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=gemini_api_key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            if response and response.text:
                result = json.loads(response.text.strip())
                if result.get("action_required") and result.get("params"):
                    if "message_id" in result["params"] or result["tool"] in ("gmail_delete_email", "gmail_archive_email", "gmail_forward_email", "gmail_reply_email", "gmail_manage_labels"):
                        result["params"]["message_id"] = email["id"]
                return result
        except Exception as e:
            logger.error(f"[Monitor Planner - Gemini] Failed: {e}")

    # 3. Fallback Heuristics Planner (Deterministic Rules)
    logger.info("[Monitor Planner] Running fallback rule-based planner heuristics.")
    sub_lower = subject.lower()
    body_lower = body.lower()
    from_lower = sender.lower()
    
    # Use Case 1: Phishing Protection (Reset password / suspicious domains)
    if "amaz0n" in from_lower or ("reset password" in sub_lower and "urgent" in sub_lower):
        return {
            "action_required": True,
            "tool": "gmail_delete_email",
            "params": {"message_id": email["id"]},
            "reason": "Security Alert: Detected suspicious phishing domain (amaz0n) or urgent password reset request."
        }
        
    # Use Case 8: Sensitive Data Leak Detection (e.g. passwords.xlsx attachment)
    has_passwords_attach = any("passwords" in att.get("filename", "").lower() for att in attachments)
    if has_passwords_attach:
        return {
            "action_required": True,
            "tool": "gmail_delete_email",
            "params": {"message_id": email["id"]},
            "reason": "Security Threat: Detected email containing sensitive passwords file."
        }
        
    # Use Case 2: Payroll Protection (salary_2026.xlsx)
    has_salary_attach = any("salary" in att.get("filename", "").lower() for att in attachments)
    if has_salary_attach:
        return {
            "action_required": True,
            "tool": "gmail_forward_email",
            "params": {"message_id": email["id"], "to": "hr-approvals@acme-corp.com"},
            "reason": "Compliance Check: Payroll salary spreadsheet detected. Forwarding to HR approvals for audit compliance."
        }
        
    # Use Case 6: Expense Approval (Uber ₹350 vs ₹25,000)
    if "expense" in sub_lower or "uber" in body_lower or "invoice" in sub_lower:
        numbers = re.findall(r'\d+', body)
        amount = int(numbers[0]) if numbers else 0
        if amount > 500:
            return {
                "action_required": True,
                "tool": "db_write",
                "params": {"record_id": f"exp_{email['id']}", "data": f"Expense claim high: {amount}"},
                "reason": f"Audit Check: Large expense claim of {amount} requires approval."
            }
        else:
            return {
                "action_required": True,
                "tool": "db_write",
                "params": {"record_id": f"exp_{email['id']}", "data": f"Expense claim auto-approved: {amount}"},
                "reason": f"Automation Check: Low-value expense claim of {amount} auto-logged."
            }
            
    # Use Case 11: Priority Inbox (CEO emails)
    if "ceo@acme-corp.com" in from_lower:
        return {
            "action_required": True,
            "tool": "gmail_manage_labels",
            "params": {"message_id": email["id"], "add_labels": ["IMPORTANT", "PRIORITY"], "remove_labels": []},
            "reason": "Operational Alert: Incoming communication from CEO marked high priority."
        }

    # Use Case 10: Duplicate Email / Spam
    if "grow your sales" in sub_lower or "advertising" in body_lower:
        return {
            "action_required": True,
            "tool": "gmail_delete_email",
            "params": {"message_id": email["id"]},
            "reason": "Operational Check: Detected spam newsletter advertising campaign."
        }
        
    return {
        "action_required": False,
        "tool": None,
        "params": None,
        "reason": "No policy action required for this communication thread."
    }

def _process_new_email(app: FastAPI, email: dict):
    """Processes a new email: Plans action -> Evaluates against Guardrails -> Executes if allowed."""
    evaluator = app.state.evaluator
    execution_gateway = app.state.execution_gateway
    
    agent_id = "autonomous-monitor-agent"
    
    # 1. Plan action
    plan = _plan_action_for_email(email)
    
    if not plan.get("action_required"):
        logger.info(f"[Monitor] No action planned for email {email['id']}: {plan.get('reason')}")
        return
        
    tool_name = plan["tool"]
    tool_params = plan["params"] or {}
    reason = plan["reason"]
    
    logger.info(f"[Monitor] Planned action: Calling '{tool_name}' with parameters {tool_params}. Reason: {reason}")
    
    # Inject default role context required for policy matching
    if "_role" not in tool_params:
        tool_params["_role"] = "junior_dev"
        
    # 2. Evaluate proposed action against Guardrail Engine
    evaluation = evaluator.evaluate_action(
        agent_id=agent_id,
        tool=tool_name,
        params=tool_params
    )
    
    status = evaluation["status"]
    logger.info(f"[Monitor Guardrail] Evaluated action. Decision: {status.upper()} (Rule: {evaluation.get('rule_id')}, Risk: {evaluation.get('risk_score')})")
    
    # 3. Handle live decisions
    if status == "allowed":
        try:
            result = execution_gateway.execute(
                agent_id=agent_id,
                tool_name=tool_name,
                params=tool_params,
                role=tool_params["_role"]
            )
            logger.info(f"[Monitor Executor] Successfully executed action: {result}")
        except Exception as e:
            logger.error(f"[Monitor Executor] Failed executing action: {e}")
    elif status == "pending":
        logger.info(f"[Monitor Queue] Action enqueued into Human-in-the-Loop review queue. Request ID: {evaluation.get('request_id')}")
    else:
        logger.info(f"[Monitor Blocked] Action was BLOCKED by policies.")
