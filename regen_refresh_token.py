"""Regenerate the Google Ads OAuth refresh token and patch .google-ads.yaml.

Run:  uv run python regen_refresh_token.py
Opens a browser, you approve, then it writes the new refresh_token into the yaml.
"""

import re
from pathlib import Path

import yaml
from google_auth_oauthlib.flow import InstalledAppFlow

YAML_PATH = Path.home() / ".google-ads.yaml"
SCOPES = ["https://www.googleapis.com/auth/adwords"]

cfg = yaml.safe_load(YAML_PATH.read_text())

client_config = {
    "installed": {
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}

flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
# prompt=consent forces a fresh refresh_token to be returned
creds = flow.run_local_server(prompt="consent", access_type="offline")

new_token = creds.refresh_token
if not new_token:
    raise SystemExit("No refresh_token returned. Re-run and ensure you approve consent.")

text = YAML_PATH.read_text()
text = re.sub(r"^refresh_token:.*$", f"refresh_token: {new_token}", text, flags=re.M)
YAML_PATH.write_text(text)
print(f"\nUpdated refresh_token in {YAML_PATH}")
