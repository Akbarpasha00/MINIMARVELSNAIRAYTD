"""Run locally: python tools/authorize_youtube.py client_secret.json.
Writes credentials locally; never print or commit refresh tokens.
"""
import json
import os
from pathlib import Path
import sys
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/youtube.upload',
          'https://www.googleapis.com/auth/youtube.readonly']
flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], SCOPES)
credentials = flow.run_local_server(port=0, access_type='offline', prompt='consent')
if not credentials.refresh_token:
    raise RuntimeError('No refresh token returned; authorize again with consent.')
path = Path('token.json')
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as handle:
    json.dump({'YOUTUBE_CLIENT_ID': credentials.client_id,
               'YOUTUBE_CLIENT_SECRET': credentials.client_secret,
               'YOUTUBE_REFRESH_TOKEN': credentials.refresh_token}, handle, indent=2)
print('Saved token.json locally. Copy its values into GitHub Actions secrets, then delete it.')
