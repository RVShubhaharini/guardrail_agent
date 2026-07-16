def db_delete(record_count: int, **kwargs):
    return {"result": f"Successfully deleted {record_count} records from database."}

def db_write(record_id: str, data: dict, **kwargs):
    return {"result": f"Successfully wrote record '{record_id}' to database."}

def send_email(recipient_domain: str, subject: str, **kwargs):
    return {"result": f"Email with subject '{subject}' sent to domain '{recipient_domain}'."}

def read_file(path: str, **kwargs):
    return {"result": f"File content of '{path}' read successfully."}

TOOL_REGISTRY = {
    "db_delete": db_delete,
    "db_write": db_write,
    "send_email": send_email,
    "read_file": read_file,
}
