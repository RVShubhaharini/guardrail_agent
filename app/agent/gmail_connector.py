import os
# Force delete all proxy environment variables to prevent httplib2 from resolving them
for key in ['http_proxy', 'https_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'no_proxy', 'NO_PROXY']:
    os.environ.pop(key, None)

# Monkeypatch urllib.request.getproxies to bypass Windows Registry proxy discovery
import urllib.request
urllib.request.getproxies = lambda: {}

# Monkeypatch httplib2 to disable proxy detection (used by googleapiclient)
try:
    import httplib2
    httplib2.proxy_info_from_environment = lambda method='https': None
    httplib2.ProxyInfo = type('ProxyInfo', (), {'__init__': lambda self, *a, **kw: None})
except ImportError:
    pass

import json
import logging
import threading
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Try importing official Google API Client modules
GOOGLE_API_AVAILABLE = False
try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    GOOGLE_API_AVAILABLE = True
except ImportError:
    pass

# SCOPES required for real Gmail operations
SCOPES = ['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/gmail.send']

class GmailConnector:
    """Manages connection to the Gmail API.
    Operates in dual-mode: Real Google API connector if credentials exist,
    otherwise falls back to a stateful Mock Gmail Simulator for safe sandbox validation."""

    def __init__(self):
        self.is_live = False
        self.creds = None
        self._thread_local = threading.local()
        
        # Stateful Mock Inbox Database (Initial Corporate Emails)
        self.mock_db: List[Dict[str, Any]] = [
            {
                "id": "msg_001",
                "from": "secops@acme-corp.com",
                "to": "john@acme-corp.com",
                "subject": "⚠️ Urgent: Access Token Expiry Notice",
                "body": "Your corporate API session is due to expire in 2 hours. Please rotate keys.",
                "labels": ["INBOX", "URGENT"],
                "timestamp": datetime.utcnow().isoformat(),
                "attachments": []
            },
            {
                "id": "msg_002",
                "from": "manager@acme-corp.com",
                "to": "john@acme-corp.com",
                "subject": "Project Roadmap Review & Feedback Request",
                "body": "Hi John, please review the Q3 planning documentation and reply before Friday.",
                "labels": ["INBOX", "IMPORTANT"],
                "timestamp": datetime.utcnow().isoformat(),
                "attachments": [{"filename": "q3_roadmap.pdf", "content_type": "application/pdf"}]
            },
            {
                "id": "msg_003",
                "from": "spam-campaign@external-ads.net",
                "to": "john@acme-corp.com",
                "subject": "🚀 Grow your corporate sales by 10x instantly!",
                "body": "Dear ACME representative, click here to purchase advertising packages.",
                "labels": ["INBOX", "SPAM"],
                "timestamp": datetime.utcnow().isoformat(),
                "attachments": []
            },
            {
                "id": "msg_004",
                "from": "colleague@acme-corp.com",
                "to": "john@acme-corp.com",
                "subject": "Lunch Plans Today?",
                "body": "Hey, going to the local burger joint around 12:30 PM. Let me know if you want to join.",
                "labels": ["INBOX"],
                "timestamp": datetime.utcnow().isoformat(),
                "attachments": []
            }
        ]

        self.quarantine_vault: List[Dict[str, Any]] = self._load_quarantine_vault()
        self.replied_message_ids: set = self._load_replied_message_ids()
        self._initialize_connector()

    def _load_quarantine_vault(self) -> List[Dict[str, Any]]:
        file_path = os.path.join("data", "quarantine_vault.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        return json.loads(content)
            except Exception as e:
                logger.error(f"Error loading quarantine vault from file: {e}")
        return []

    def _save_quarantine_vault(self):
        try:
            os.makedirs("data", exist_ok=True)
            file_path = os.path.join("data", "quarantine_vault.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(self.quarantine_vault, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving quarantine vault to file: {e}")

    def _load_replied_message_ids(self) -> set:
        file_path = os.path.join("data", "replied_emails.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        return set(json.loads(content))
            except Exception as e:
                logger.error(f"Error loading replied emails file: {e}")
        return set()

    def _save_replied_message_ids(self):
        try:
            os.makedirs("data", exist_ok=True)
            file_path = os.path.join("data", "replied_emails.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(list(self.replied_message_ids), f, indent=2)
        except Exception as e:
            logger.error(f"Error saving replied emails file: {e}")

    def _initialize_connector(self):
        """Discovers and establishes connection to the Google API if configured."""
        if not GOOGLE_API_AVAILABLE:
            logger.info("Google API Client packages not available. Defaulting to Mock Simulator.")
            return

        creds = None
        # Check if token JSON is provided via environment variable (ideal for Render/AWS)
        token_env = os.environ.get("GMAIL_TOKEN_JSON") or os.environ.get("GOOGLE_TOKEN_JSON")
        if token_env:
            try:
                token_data = json.loads(token_env)
                creds = Credentials.from_authorized_user_info(token_data, SCOPES)
                logger.info("[Gmail] Credentials loaded successfully from GMAIL_TOKEN_JSON environment variable.")
            except Exception as e:
                logger.error(f"Error loading credentials from GMAIL_TOKEN_JSON env var: {e}")

        # Fall back to local token.json file
        if not creds and os.path.exists('token.json'):
            try:
                creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            except Exception as e:
                logger.error(f"Error loading token.json: {e}")

        # If there are no valid credentials available, let the user log in.
        if creds and not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    # Note: google.auth.transport.requests.Request does not accept a timeout in __init__
                    # The timeout must be passed through an httplib2 or requests session instead
                    import requests as _requests
                    _session = _requests.Session()
                    _session.proxies = {}  # force no proxy for token refresh
                    _session.verify = False # Bypass certificate check for token refresh under proxy
                    import urllib3
                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                    creds.refresh(Request(session=_session))
                    # Refreshed tokens must be written back to token.json!
                    with open('token.json', 'w') as token:
                        token.write(creds.to_json())
                    logger.info("[Gmail] Refreshed expired credentials and saved to token.json.")
                except Exception as e:
                    logger.error(f"Error refreshing credentials: {e}")
                    creds = None
            else:
                creds = None

        self.creds = creds
        self._thread_local = threading.local() # Reset thread-local cache to force rebuild on new creds
        if creds and creds.valid:
            self.is_live = True
            logger.info("[Gmail] Live Google Gmail API Connector credentials loaded successfully.")
        else:
            self.is_live = False
            logger.info("No credentials found or credentials invalid. Defaulting to stateful Mock Gmail Simulator.")

    @property
    def service(self):
        """Thread-safe lazy initializer for the Google API service."""
        if not self.is_live or not self.creds:
            return None
        if not hasattr(self._thread_local, "service"):
            try:
                import httplib2
                import google_auth_httplib2
                http_client = httplib2.Http(disable_ssl_certificate_validation=True)
                authorized_http = google_auth_httplib2.AuthorizedHttp(self.creds, http=http_client)
                self._thread_local.service = build('gmail', 'v1', http=authorized_http)
            except Exception as e:
                logger.error(f"Failed to construct Google Gmail Client Service in thread {threading.current_thread().name}: {e}")
                self._thread_local.service = None
        return self._thread_local.service

    # --- Gmail API Connector Operations ---

    def list_emails(self, label_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """List recent emails."""
        if self.is_live:
            try:
                # Query real Gmail API
                q_args = {"userId": "me", "maxResults": 10}
                if label_filter:
                    q_args["labelIds"] = [label_filter]
                results = self.service.users().messages().list(**q_args).execute()
                messages = results.get('messages', [])
                
                output = []
                for msg in messages:
                    detail = self.service.users().messages().get(userId="me", id=msg["id"]).execute()
                    
                    # Extract headers
                    headers = detail.get("payload", {}).get("headers", [])
                    subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "(No Subject)")
                    sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "Unknown")
                    to = next((h["value"] for h in headers if h["name"].lower() == "to"), "me")
                    
                    labels = detail.get("labelIds", [])
                    if detail["id"] in getattr(self, "replied_message_ids", set()) and "REPLIED" not in labels:
                        labels.append("REPLIED")
                        
                    output.append({
                        "id": detail["id"],
                        "from": sender,
                        "to": to,
                        "subject": subject,
                        "body": detail.get("snippet", ""),
                        "labels": labels,
                        "timestamp": datetime.utcnow().isoformat(), # approximate
                        "attachments": []
                    })
                return output
            except Exception as e:
                logger.error(f"Live Gmail list failed: {e}. Falling back to mock data.")
        
        # Mock mode fallback
        if label_filter:
            return [m for m in self.mock_db if label_filter in m.get("labels", [])]
        return self.mock_db

    def send_email(self, to: str, subject: str, body: str, attachments: List[dict] = None) -> Dict[str, Any]:
        """Send an email."""
        logger.info(f"Gmail Connector: sending email to '{to}' | Subject: '{subject}'")
        
        if self.is_live:
            try:
                import base64
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart
                
                # Get the authenticated sender's email address
                profile = self.service.users().getProfile(userId="me").execute()
                sender_email = profile.get("emailAddress", "me")
                
                if attachments:
                    message = MIMEMultipart()
                    message.attach(MIMEText(body))
                else:
                    message = MIMEText(body)
                
                message['to'] = to
                message['from'] = sender_email
                message['subject'] = subject
                
                raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
                sent_msg = self.service.users().messages().send(userId="me", body={'raw': raw}).execute()
                logger.info(f"[Gmail] Live send successful: message ID={sent_msg['id']} to={to}")
                return {"id": sent_msg["id"], "status": "sent", "to": to, "is_live": True}
            except Exception as e:
                logger.error(f"Live Gmail send failed: {e}.")
                raise e

        # Stateful Mock write
        new_id = f"msg_{len(self.mock_db) + 1:03d}"
        new_email = {
            "id": new_id,
            "from": "me@acme-corp.com",
            "to": to,
            "subject": subject,
            "body": body,
            "labels": ["SENT"],
            "timestamp": datetime.utcnow().isoformat(),
            "attachments": attachments or []
        }
        self.mock_db.insert(0, new_email) # prepend
        return {"id": new_id, "status": "sent", "is_live": False}

    def read_email(self, message_id: str) -> Optional[Dict[str, Any]]:
        """Read a specific email."""
        if self.is_live and not message_id.startswith("msg_"):
            try:
                detail = self.service.users().messages().get(userId="me", id=message_id).execute()
                headers = detail.get("payload", {}).get("headers", [])
                subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "(No Subject)")
                sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "Unknown")
                to = next((h["value"] for h in headers if h["name"].lower() == "to"), "me")
                
                # Check for attachments
                attachments = []
                parts = detail.get("payload", {}).get("parts", [])
                for part in parts:
                    filename = part.get("filename")
                    if filename:
                        attachments.append({"filename": filename, "content_type": part.get("mimeType")})
                        
                return {
                    "id": message_id,
                    "from": sender,
                    "to": to,
                    "subject": subject,
                    "body": detail.get("snippet", ""),
                    "labels": detail.get("labelIds", []),
                    "timestamp": datetime.utcnow().isoformat(),
                    "attachments": attachments
                }
            except Exception as e:
                logger.error(f"Live Gmail read failed: {e}.")

        for msg in self.mock_db:
            if msg["id"] == message_id:
                return msg
        return None

    def search_emails(self, query: str) -> List[Dict[str, Any]]:
        """Search emails using matching terms."""
        if self.is_live:
            try:
                results = self.service.users().messages().list(userId="me", q=query, maxResults=10).execute()
                # Resolve details...
                messages = results.get('messages', [])
                output = []
                for msg in messages:
                    detail = self.service.users().messages().get(userId="me", id=msg["id"]).execute()
                    headers = detail.get("payload", {}).get("headers", [])
                    subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "(No Subject)")
                    output.append({"id": msg["id"], "subject": subject, "snippet": detail.get("snippet", "")})
                return output
            except Exception as e:
                logger.error(f"Live Gmail search failed: {e}")

        # Mock search
        q = query.lower().strip()
        
        # Parse query for prefixes (e.g. from:, subject:, to:)
        filter_from = None
        filter_subject = None
        filter_to = None
        terms = []
        
        for part in q.split():
            if part.startswith("from:"):
                filter_from = part[len("from:"):].strip()
            elif part.startswith("subject:"):
                filter_subject = part[len("subject:"):].strip()
            elif part.startswith("to:"):
                filter_to = part[len("to:"):].strip()
            else:
                terms.append(part)
                
        results = []
        for msg in self.mock_db:
            match = True
            if filter_from and filter_from not in msg["from"].lower():
                match = False
            if filter_to and filter_to not in msg["to"].lower():
                match = False
            if filter_subject and filter_subject not in msg["subject"].lower():
                match = False
            if terms:
                for term in terms:
                    if not (term in msg["subject"].lower() or 
                            term in msg["body"].lower() or 
                            term in msg["from"].lower() or 
                            term in msg["to"].lower()):
                        match = False
                        break
            if match:
                results.append(msg)
        return results

    def delete_email(self, message_id: str) -> bool:
        """Delete an email (moves to TRASH and saves into Quarantine Vault)."""
        # Save full email content into Quarantine Vault before deleting
        try:
            email_info = self.read_email(message_id)
            if email_info and not any(q["id"] == message_id for q in getattr(self, "quarantine_vault", [])):
                quarantine_record = {
                    "id": message_id,
                    "from": email_info.get("from", "Unknown"),
                    "to": email_info.get("to", "me"),
                    "subject": email_info.get("subject", "(No Subject)"),
                    "body": email_info.get("body", ""),
                    "timestamp": email_info.get("timestamp", datetime.utcnow().isoformat()),
                    "quarantined_at": datetime.utcnow().isoformat(),
                    "status": "QUARANTINED_AND_DELETED",
                    "threat_reason": "Email deleted and moved to TRASH vault",
                    "risk_score": 100
                }
                if not hasattr(self, "quarantine_vault"):
                    self.quarantine_vault = []
                self.quarantine_vault.insert(0, quarantine_record)
                self._save_quarantine_vault()
        except Exception as ex:
            logger.error(f"Error preserving email to quarantine vault: {ex}")

        if self.is_live and not message_id.startswith("msg_"):
            try:
                self.service.users().messages().trash(userId="me", id=message_id).execute()
                return True
            except Exception as e:
                logger.error(f"Live Gmail delete failed: {e}")
                raise e

        for msg in self.mock_db:
            if msg["id"] == message_id:
                msg["labels"] = [l for l in msg["labels"] if l != "INBOX"]
                msg["labels"].append("TRASH")
                return True
        return False

    def archive_email(self, message_id: str) -> bool:
        """Archive an email (removes INBOX label)."""
        if self.is_live and not message_id.startswith("msg_"):
            try:
                self.service.users().messages().batchModify(
                    userId="me",
                    body={"ids": [message_id], "removeLabelIds": ["INBOX"]}
                ).execute()
                return True
            except Exception as e:
                logger.error(f"Live Gmail archive failed: {e}")
                raise e

        for msg in self.mock_db:
            if msg["id"] == message_id:
                msg["labels"] = [l for l in msg["labels"] if l != "INBOX"]
                msg["labels"].append("ARCHIVE")
                return True
        return False

    def restore_email(self, message_id: str) -> bool:
        """Restore an email (adds INBOX label, removes TRASH/ARCHIVE)."""
        if self.is_live and not message_id.startswith("msg_"):
            try:
                self.service.users().messages().batchModify(
                    userId="me",
                    body={"ids": [message_id], "addLabelIds": ["INBOX"], "removeLabelIds": ["TRASH"]}
                ).execute()
                return True
            except Exception as e:
                logger.error(f"Live Gmail restore failed: {e}")
                raise e

        for msg in self.mock_db:
            if msg["id"] == message_id:
                msg["labels"] = [l for l in msg["labels"] if l not in ("TRASH", "ARCHIVE")]
                msg["labels"].append("INBOX")
                return True
        return False

    def reply_email(self, message_id: str, body: str) -> Dict[str, Any]:
        """Reply to an email."""
        msg = self.read_email(message_id)
        if not msg:
            raise ValueError(f"Message ID '{message_id}' not found.")
            
        subject = f"Re: {msg.get('subject', 'No Subject')}"
        to = msg.get("from", "unknown@acme-corp.com")
        
        # Mark the original message with REPLIED label persistently
        if not hasattr(self, "replied_message_ids"):
            self.replied_message_ids = set()
        self.replied_message_ids.add(message_id)
        self._save_replied_message_ids()
        
        for item in self.mock_db:
            if item["id"] == message_id:
                if "labels" not in item:
                    item["labels"] = []
                if "REPLIED" not in item["labels"]:
                    item["labels"].append("REPLIED")
                    
        return self.send_email(to=to, subject=subject, body=body)

    def forward_email(self, message_id: str, to: str) -> Dict[str, Any]:
        """Forward an email."""
        msg = self.read_email(message_id)
        if not msg:
            raise ValueError(f"Message ID '{message_id}' not found.")
            
        subject = f"Fwd: {msg['subject']}"
        body = f"---------- Forwarded message ---------\nFrom: {msg['from']}\nDate: {msg.get('timestamp')}\nSubject: {msg['subject']}\nTo: {msg['to']}\n\n{msg['body']}"
        return self.send_email(to=to, subject=subject, body=body, attachments=msg.get("attachments", []))

    def manage_labels(self, message_id: str, add_labels: List[str], remove_labels: List[str]) -> bool:
        """Add or remove labels from an email."""
        if self.is_live and not message_id.startswith("msg_"):
            try:
                self.service.users().messages().batchModify(
                    userId="me",
                    body={"ids": [message_id], "addLabelIds": add_labels, "removeLabelIds": remove_labels}
                ).execute()
                return True
            except Exception as e:
                logger.error(f"Live Gmail manage labels failed: {e}")
                raise e

        for msg in self.mock_db:
            if msg["id"] == message_id:
                current = set(msg["labels"])
                for l in remove_labels:
                    current.discard(l)
                for l in add_labels:
                    current.add(l)
                msg["labels"] = list(current)
                return True
        return False
