"""One-time, local authorization helper. Tokens stay in .secrets/ (gitignored)."""

from __future__ import annotations

import argparse
import getpass

from services import DROPBOX_TOKEN, SECRETS, dropbox_client, google_credentials


def connect_google() -> None:
    google_credentials(interactive=True)
    print("Google Workspace and Analytics connected.")


def connect_dropbox() -> None:
    SECRETS.mkdir(parents=True, exist_ok=True)
    print("Create a scoped Dropbox app with files.metadata.read and files.content.read.")
    token = getpass.getpass("Paste its access token (hidden): ").strip()
    if not token:
        raise SystemExit("No token supplied.")
    DROPBOX_TOKEN.write_text(token, encoding="utf-8")
    dropbox_client().users_get_current_account()
    print("Dropbox connected.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("service", choices=["google", "dropbox", "all"])
    args = parser.parse_args()
    if args.service in {"google", "all"}:
        connect_google()
    if args.service in {"dropbox", "all"}:
        connect_dropbox()
