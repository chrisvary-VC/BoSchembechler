"""Read-only clients for the user's Google workspace, GA4, and Dropbox."""

from __future__ import annotations

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

ROOT = Path(__file__).resolve().parent.parent
SECRETS = Path(os.getenv("AIOS_SECRETS_DIR", ROOT / ".secrets"))
GOOGLE_CLIENT = SECRETS / "google-oauth-client.json"
GOOGLE_TOKEN = SECRETS / "google-token.json"
DROPBOX_TOKEN = SECRETS / "dropbox-token.txt"

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/tasks",
]


def google_credentials(interactive: bool = False) -> Credentials:
    creds = None
    if GOOGLE_TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN), GOOGLE_SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    missing_scopes = bool(creds and not creds.has_scopes(GOOGLE_SCOPES))
    if (not creds or not creds.valid or missing_scopes) and interactive:
        if not GOOGLE_CLIENT.exists():
            raise FileNotFoundError(
                f"Place the Google Desktop OAuth JSON at {GOOGLE_CLIENT}"
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(GOOGLE_CLIENT), GOOGLE_SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True)
    if not creds or not creds.valid or not creds.has_scopes(GOOGLE_SCOPES):
        raise RuntimeError("Google is not connected. Run: python agent/connect_services.py google")
    SECRETS.mkdir(parents=True, exist_ok=True)
    GOOGLE_TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


def google_service(api: str, version: str):
    from googleapiclient.discovery import build
    return build(api, version, credentials=google_credentials(), cache_discovery=False)


def dropbox_client():
    import dropbox
    token = os.getenv("DROPBOX_ACCESS_TOKEN")
    if not token and DROPBOX_TOKEN.exists():
        token = DROPBOX_TOKEN.read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError("Dropbox is not connected. Run: python agent/connect_services.py dropbox")
    return dropbox.Dropbox(token)
