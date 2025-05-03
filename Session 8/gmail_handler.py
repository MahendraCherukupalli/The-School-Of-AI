import base64
import os.path
from email.mime.text import MIMEText
# from google.oauth2.service_account import Credentials # Comment out or remove later
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Import necessary libraries for OAuth flow
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle # To store and load the refresh token

# Import the combined scopes from the new config module
from .config import ALL_GOOGLE_SCOPES

# Define scopes required
# SCOPES = ['https://www.googleapis.com/auth/gmail.send'] # Remove or comment out

# SERVICE_ACCOUNT_FILE = \'credentials.json\' # Comment out or remove

# Define the path for the OAuth 2.0 client secret file and token file
CLIENT_SECRET_FILE = 'Task/client_secret.json'
TOKEN_FILE = 'Task/token.pickle'

async def send_email(recipient: str, subject: str, body: str):
    """Creates and sends an email message."""
    creds = None

    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Ensure the client_secret.json file exists
            if not os.path.exists(CLIENT_SECRET_FILE):
                 raise FileNotFoundError(f"OAuth 2.0 client secret file not found at {CLIENT_SECRET_FILE}")

            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE, ALL_GOOGLE_SCOPES) # Use ALL_GOOGLE_SCOPES
            # Run the flow in a local server mode
            creds = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)

    try:
        # Build the service using the obtained credentials
        service = build('gmail', 'v1', credentials=creds)

        message = MIMEText(body)
        message['to'] = recipient
        # When using OAuth 2.0 with a standard account, the 'from' address
        # is automatically the authenticated user's email. You don't need
        # to set it explicitly here unless you want to specify a 'Send mail as' address
        # configured in your Gmail settings. For simplicity, we will omit it.
        # message['from'] = 'your_gmail_address@gmail.com' # Optional

        message['subject'] = subject

        # Encode the message
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        create_message = {
            'raw': encoded_message
        }
        # pylint: disable=E1101
        # userId='me' correctly refers to the authenticated user when using OAuth 2.0
        send_message = (service.users().messages().send
                        (userId='me', body=create_message)).execute()
        print(F'Sent message Id: {send_message["id"]}')

    except HttpError as error:
        print(F'An API error occurred: {error}')
        # Consider raising the error or returning a failure status
        raise
    except FileNotFoundError as e:
         print(f"Credential file error: {e}")
         raise
    except Exception as e:
        print(f"An unexpected error occurred in gmail_handler: {e}")
        raise

# Example usage (optional)
# import asyncio
# if __name__ == '__main__':
#     async def test_email():
#         try:
#             # Replace with a real recipient email for testing
#             await send_email("test_recipient@example.com", "Test Subject", "Test Body with link: http://example.com")
#             print("Email send attempt complete.")
#         except Exception as e:
#             print(f"Email send failed: {e}")
#     asyncio.run(test_email())
