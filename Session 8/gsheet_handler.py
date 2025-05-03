import os.path
# from google.oauth2.service_account import Credentials # Comment out or remove
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing import List
from .models import F1Standings # Import the model

# Import necessary libraries for OAuth flow
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle # To store and load the refresh token

# Import the combined scopes from the new config module
from .config import ALL_GOOGLE_SCOPES

# Define scopes required
# SCOPES = ['https://www.googleapis.com/auth/spreadsheets', # Remove or comment out
#           'https://www.googleapis.com/auth/drive'] # Remove or comment out


# SERVICE_ACCOUNT_FILE = \'credentials.json\' # Comment out or remove

# Define the path for the OAuth 2.0 client secret file and token file
CLIENT_SECRET_FILE = 'Task/client_secret.json' # <-- Add Task/ prefix
TOKEN_FILE = 'Task/token.pickle'             # <-- Also add Task/ prefix for consistency


async def create_google_sheet(standings_data: List[F1Standings]) -> str: # We might need to pass recipient email here later, but let's start with public read
    """Creates a Google Sheet with F1 standings and returns its URL."""
    creds = None

    # Load or get credentials using the OAuth flow
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRET_FILE):
                 raise FileNotFoundError(f"OAuth 2.0 client secret file not found at {CLIENT_SECRET_FILE}")

            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE, ALL_GOOGLE_SCOPES) # Use ALL_GOOGLE_SCOPES
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)


    try:
        # Build the Sheets service
        sheets_service = build('sheets', 'v4', credentials=creds)

        # Build the Drive service for managing permissions
        drive_service = build('drive', 'v3', credentials=creds) # Build Drive service


        # Create the spreadsheet
        spreadsheet = {
            'properties': {
                'title': 'F1 Driver Standings'
            }
        }
        spreadsheet = sheets_service.spreadsheets().create(body=spreadsheet, fields='spreadsheetId,spreadsheetUrl').execute() # Use sheets_service
        spreadsheet_id = spreadsheet.get('spreadsheetId')
        spreadsheet_url = spreadsheet.get('spreadsheetUrl')
        print(f"Created spreadsheet with ID: {spreadsheet_id}")

        # Prepare data: Header + Rows
        values = [
            ["Driver Last Name", "Points"] # Header row
        ]
        for item in standings_data:
             # Ensure points are converted to string or number as Sheets API expects
             points_value = int(item.points) if isinstance(item.points, str) else item.points
             values.append([item.team, points_value])


        body = {
            'values': values
        }
        # Write data to the sheet
        # Adjust the range size based on the number of drivers + header
        range_name = f'Sheet1!A1:B{len(values)}'
        result = sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=range_name,
            valueInputOption='USER_ENTERED', # Interprets values as if typed by user
            body=body).execute() # Use sheets_service
        print(f"{result.get('updatedCells')} cells updated.")

        # Add sharing permissions: Make it readable by anyone with the link
        # This requires the Drive API scope ('https://www.googleapis.com/auth/drive')
        permission = {
            'type': 'anyone',
            'role': 'reader'
        }
        # Use drive_service to create the permission
        drive_service.permissions().create(fileId=spreadsheet_id, body=permission).execute()
        print("Sheet made publicly readable by anyone with the link.")


        return spreadsheet_url

    except HttpError as err:
        print(f"An API error occurred in gsheet_handler: {err}")
        raise # Re-raise for handling in main flow
    except FileNotFoundError as e:
        print(f"Credential file error in gsheet_handler: {e}")
        raise
    except Exception as e:
        print(f"An unexpected error occurred in gsheet_handler: {e}")
        raise # Re-raise

# Example usage (optional)
# import asyncio
# # Assuming F1Standings model is defined elsewhere or in models.py
# # from models import F1Standings # Make sure this import is correct

# if __name__ == '__main__':
#     async def test_sheet():
#         # Sample data matching F1Standings model
#         sample_standings = [
#             F1Standings(team="Verstappen", points=300),
#             F1Standings(team="Perez", points=200),
#             F1Standings(team="Leclerc", points=180)
#         ]
#         try:
#             print("Attempting to create and share sheet...")
#             link = await create_google_sheet(sample_standings)
#             print(f"Sheet created and shared: {link}")
#         except Exception as e:
#             print(f"Sheet creation failed: {e}")

#     # Ensure you have a client_secret.json and potentially token.pickle in the same directory
#     asyncio.run(test_sheet())
