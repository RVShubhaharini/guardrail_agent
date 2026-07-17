import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Enterprise Phishing Classification Rules Engine

THREAT_SENDERS = [
    "amaz0n", "paypa1", "micros0ft", "apple-support", "g00gle", "secure-bank",
    "verify-account", "security-update", "admin-support", "service-notice",
    "alert-system", "phish", "hacker", "fake", "scam", "lottery", "wire-transfer",
    "crypto-wallet", "customer-service-update", "noreply-security", "bank-verify"
]

CREDENTIAL_KEYWORDS = [
    "reset password", "update password", "change your password", "password expired",
    "verify credentials", "login to verify", "confirm identity", "two-factor",
    "mfa reset", "account verification", "enter pin", "security code", "password"
]

FINANCIAL_KEYWORDS = [
    "bank account", "credit card", "debit card", "wire transfer", "routing number",
    "bank details", "billing information", "payment failure", "unauthorized transaction",
    "invoice attached", "overdue invoice", "gift card", "bitcoin", "crypto transfer",
    "claim prize", "lottery winner", "refund pending", "tax refund"
]

URGENCY_KEYWORDS = [
    "urgent", "immediate action required", "account suspended", "account terminated",
    "within 24 hours", "within 2 hours", "act now", "final warning", "security breach",
    "unauthorized access", "suspicious login", "unusual activity", "action required"
]

CALL_TO_ACTION_KEYWORDS = [
    "click here", "click the link", "log in now", "update details", "verify now",
    "download attachment", "open link", "claim now"
]

HIGH_RISK_EXTENSIONS = [
    "password", "passwords", "credential", "salary_sheet", "keylog", "malware",
    ".exe", ".scr", ".vbs", ".bat", ".cmd", ".js", ".xlsm"
]

def analyze_phishing_risk(email: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyzes an email against 6 comprehensive phishing risk categories.
    Returns a detailed risk assessment object containing:
    - is_phishing: boolean
    - risk_score: int (0 to 100)
    - categories: list of matched threat categories
    - matched_terms: list of specific words/domains matched
    - summary: descriptive text
    """
    sender = str(email.get("from", "")).lower()
    subject = str(email.get("subject", "")).lower()
    body = str(email.get("body", "")).lower()
    attachments = email.get("attachments", []) or []

    triggers = []
    matched_words = []
    risk_score = 0

    # 1. Typosquatting / Spoofed Sender Check
    matched_senders = [s for s in THREAT_SENDERS if s in sender]
    if matched_senders:
        triggers.append("Spoofed / Fraudulent Sender Domain")
        matched_words.extend(matched_senders)
        risk_score += 40

    # 2. Credential Harvesting Check
    matched_creds = [k for k in CREDENTIAL_KEYWORDS if k in subject or k in body]
    if matched_creds:
        triggers.append("Credential Harvesting / Password Trap")
        matched_words.extend(matched_creds)
        risk_score += 35

    # 3. Financial / Banking Scam Check
    matched_fin = [k for k in FINANCIAL_KEYWORDS if k in subject or k in body]
    if matched_fin:
        triggers.append("Financial / Banking Exploitation")
        matched_words.extend(matched_fin)
        risk_score += 35

    # 4. Urgency & Psychological Pressure Check
    matched_urgency = [k for k in URGENCY_KEYWORDS if k in subject or k in body]
    if matched_urgency:
        triggers.append("High-Pressure Urgency Tactics")
        matched_words.extend(matched_urgency)
        risk_score += 25

    # 5. Phishing Link Call-To-Action Check
    matched_cta = [k for k in CALL_TO_ACTION_KEYWORDS if k in subject or k in body]
    if matched_cta:
        triggers.append("Suspicious Call-to-Action Link")
        matched_words.extend(matched_cta)
        risk_score += 20

    # 6. High-Risk Attachment Check
    matched_att = []
    for att in attachments:
        fname = str(att.get("filename", "")).lower()
        if any(ext in fname for ext in HIGH_RISK_EXTENSIONS):
            matched_att.append(fname)

    if matched_att:
        triggers.append("High-Risk File Attachment")
        matched_words.extend(matched_att)
        risk_score += 45

    # Cap risk score at 100
    risk_score = min(100, risk_score)
    is_phishing = risk_score >= 35 or len(triggers) >= 1

    return {
        "is_phishing": is_phishing,
        "risk_score": risk_score if is_phishing else 0,
        "categories": triggers,
        "matched_terms": list(set(matched_words)),
        "summary": f"Phishing Risk Assessment: {risk_score}/100. Triggers: {', '.join(triggers)}" if is_phishing else "Clean Email"
    }

def is_phishing_or_threat_email(email: Dict[str, Any]) -> bool:
    """Convenience boolean check for background monitor loop."""
    result = analyze_phishing_risk(email)
    return result["is_phishing"]
