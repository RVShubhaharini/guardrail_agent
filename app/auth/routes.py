import os
import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from app.agent.gmail_connector import SCOPES

# Set environment variable to allow insecure HTTP for local dev
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Google OAuth"])

@router.get("/login")
def auth_login(request: Request):
    """Initiates Google OAuth 2.0 Web flow for Gmail access."""
    if not os.path.exists('credentials.json'):
        raise HTTPException(status_code=400, detail="credentials.json file is missing on the server.")
        
    try:
        # Build the auth flow using client credentials
        flow = Flow.from_client_secrets_file(
            'credentials.json',
            scopes=SCOPES,
            redirect_uri='http://localhost:8000/auth/callback'
        )
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            prompt='consent',
            include_granted_scopes='true'
        )
        return RedirectResponse(authorization_url)
    except Exception as e:
        logger.error(f"Failed to generate authorization URL: {e}")
        raise HTTPException(status_code=500, detail=f"OAuth initialization failed: {str(e)}")

@router.get("/callback")
def auth_callback(request: Request):
    """Processes Google OAuth redirect, exchanges code for token, and activates Live Gmail Connector."""
    if not os.path.exists('credentials.json'):
        raise HTTPException(status_code=400, detail="credentials.json file is missing on the server.")
        
    try:
        flow = Flow.from_client_secrets_file(
            'credentials.json',
            scopes=SCOPES,
            redirect_uri='http://localhost:8000/auth/callback'
        )
        
        # Exchange authorization code for token
        flow.fetch_token(authorization_response=str(request.url))
        creds = flow.credentials
        
        # Save token to token.json
        with open('token.json', 'w') as token_file:
            token_file.write(creds.to_json())
            
        # Re-initialize GmailConnector to transition from Mock to Live
        gmail_connector = request.app.state.gmail_connector
        gmail_connector._initialize_connector()
        
        logger.info("[Auth] Gmail OAuth flow completed successfully. Connector switched to LIVE.")
        
        # Redirect back to the dashboard home page
        return RedirectResponse(url="/")
    except Exception as e:
        logger.error(f"Failed to complete OAuth callback: {e}")
        raise HTTPException(status_code=500, detail=f"OAuth callback failed: {str(e)}")

@router.get("/status")
def auth_status(request: Request):
    """Returns current Gmail connection details (mock vs live)."""
    gmail_connector = request.app.state.gmail_connector
    return {
        "is_live": gmail_connector.is_live,
        "mode": "LIVE" if gmail_connector.is_live else "MOCK"
    }

@router.post("/logout")
def auth_logout(request: Request):
    """Deletes token.json and resets Gmail Connector to Mock mode."""
    if os.path.exists('token.json'):
        try:
            os.remove('token.json')
        except Exception as e:
            logger.error(f"Failed to delete token.json: {e}")
            raise HTTPException(status_code=500, detail="Could not clean authentication token.")
            
    # Reset connector
    gmail_connector = request.app.state.gmail_connector
    gmail_connector._initialize_connector()
    
    return {"status": "success", "mode": "MOCK"}
