from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

flow = InstalledAppFlow.from_client_secrets_file(
    "federated-social-network-40159d36f50e.json", SCOPES
)

creds = flow.run_local_server(port=8080)

print("REFRESH TOKEN:", creds.refresh_token)
