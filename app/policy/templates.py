# Policy templates for various enterprise industries

FINANCE_TEMPLATE = {
    "name": "Finance",
    "description": "Strict compliance-focused ruleset with lower block limits and extensive HITL validation.",
    "rules": [
        {
            "id": "fin_block_delete",
            "description": "Block any database deletes exceeding 10 records",
            "tool": "db_delete",
            "condition": "params.get('record_count', 0) > 10",
            "action": "block",
            "risk_score": 98,
            "remediation": "Deletes in finance databases are restricted to 10 records. Batch your actions."
        },
        {
            "id": "fin_hitl_delete",
            "description": "Require approval for all database deletes",
            "tool": "db_delete",
            "condition": "params.get('record_count', 0) <= 10 and params.get('record_count', 0) > 0",
            "action": "require_hitl",
            "risk_score": 60,
            "remediation": "Human validation is required for any database deletion."
        },
        {
            "id": "fin_block_external_email",
            "description": "Block all external emails",
            "tool": "send_email",
            "condition": "params.get('recipient_domain') not in internal_domains",
            "action": "block",
            "risk_score": 95,
            "remediation": "Financial communication is restricted to internal ACME domains only."
        },
        {
            "id": "fin_hitl_write",
            "description": "Require HITL for any financial ledger write",
            "tool": "db_write",
            "condition": "True",
            "action": "require_hitl",
            "risk_score": 50,
            "remediation": "All ledger write requests require compliance officer approval."
        }
    ]
}

HEALTHCARE_TEMPLATE = {
    "name": "Healthcare",
    "description": "HIPAA-aligned policy prioritizing patient data privacy and file read guardrails.",
    "rules": [
        {
            "id": "hc_block_confidential_read",
            "description": "Block read of confidential files for non-admins",
            "tool": "read_file",
            "condition": "'confidential' in params.get('path', '') and role != 'admin'",
            "action": "block",
            "risk_score": 99,
            "remediation": "Access to patient confidential files is restricted to Admin personnel."
        },
        {
            "id": "hc_hitl_confidential_read_admin",
            "description": "Require HITL for admin reads of confidential files",
            "tool": "read_file",
            "condition": "'confidential' in params.get('path', '') and role == 'admin'",
            "action": "require_hitl",
            "risk_score": 65,
            "remediation": "Administrative access to Patient Health Information (PHI) requires approval."
        },
        {
            "id": "hc_hitl_external_email",
            "description": "Require HITL for outgoing communication",
            "tool": "send_email",
            "condition": "params.get('recipient_domain') not in internal_domains",
            "action": "require_hitl",
            "risk_score": 70,
            "remediation": "Sharing patient-related logs externally requires compliance review."
        }
    ]
}

RETAIL_TEMPLATE = {
    "name": "Retail",
    "description": "Operational efficiency ruleset with standard controls and loose limits.",
    "rules": [
        {
            "id": "rt_block_bulk_delete",
            "description": "Block database deletes exceeding 200 records",
            "tool": "db_delete",
            "condition": "params.get('record_count', 0) > 200",
            "action": "block",
            "risk_score": 85,
            "remediation": "Deletes over 200 records are blocked to prevent stock sync failures."
        },
        {
            "id": "rt_hitl_external_email",
            "description": "Require human approval for external customer emails",
            "tool": "send_email",
            "condition": "params.get('recipient_domain') not in internal_domains",
            "action": "require_hitl",
            "risk_score": 40,
            "remediation": "Customer campaign emails must be verified."
        }
    ]
}

TEMPLATES = {
    "finance": FINANCE_TEMPLATE,
    "healthcare": HEALTHCARE_TEMPLATE,
    "retail": RETAIL_TEMPLATE
}
