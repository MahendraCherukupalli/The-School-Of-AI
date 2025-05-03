import requests
import os
from .gmail_handler import send_email
from .models import F1Standings
from .f1_api import get_f1_standings
from .gsheet_handler import create_google_sheet
from typing import Callable, List
from .utils import notify_sse  # Import notify_sse from utils

# SSE_SERVER_URL and notify_sse are now in utils.py
# SSE_SERVER_URL = "http://localhost:5000/notify" # Remove or comment out

class ActionHandler:
    def __init__(self, notify_callback: Callable[[str], None]):
        """
        Initializes the ActionHandler with a callback for notifications.

        Args:
            notify_callback: A function that takes a string message
                             and sends a notification (e.g., to SSE).
        """
        self._notify = notify_callback
        # You could also pass the SSE_SERVER_URL here if it's dynamic
        # self._sse_server_url = sse_server_url

    async def fetch_f1_standings(self) -> List[F1Standings]:
        self._notify("Fetching F1 standings...")
        try:
            data = await get_f1_standings()
            # Parse the data according to Ergast API structure (adjust if necessary)
            standings_list = data.get('MRData', {}).get('StandingsTable', {}).get('StandingsLists', [])
            if not standings_list:
                print("No standings found in API response.")
                self._notify("Error: No standings data found.")
                return []

            driver_standings = standings_list[0].get('DriverStandings', [])
            parsed_standings = []
            for standing in driver_standings:
                driver_info = standing.get('Driver', {})
                points = standing.get('points', 0)
                # Using familyName as 'team' for simplicity as per original model
                # Make sure 'Driver' key exists and has 'familyName'
                driver_family_name = driver_info.get('familyName', 'Unknown Driver')
                # Ensure points are converted to int or float if they come as strings
                try:
                    # Attempt integer conversion first, then float if needed
                    if isinstance(points, str):
                        if '.' in points:
                             points_value = float(points)
                        else:
                            points_value = int(points)
                    else:
                         points_value = points # Assume it's already int or float
                except (ValueError, TypeError) as e:
                    print(f"Could not convert points '{points}' to number: {e}. Setting to 0.")
                    points_value = 0

                parsed_standings.append(F1Standings(team=driver_family_name, points=points_value))

            self._notify(f"Successfully fetched {len(parsed_standings)} F1 standings.")
            return parsed_standings
        except Exception as e:
            print(f"Error fetching or parsing F1 standings: {e}")
            self._notify(f"Error fetching F1 standings: {e}")
            # Decide how to handle errors: return empty list, raise exception, etc.
            return [] # Return empty list on error

    async def create_and_share_sheet(self, standings_data: List[F1Standings]) -> str:
        """Creates Google Sheet and returns the link."""
        self._notify("Creating Google Sheet...")
        try:
            link = await create_google_sheet(standings_data)
            self._notify("Google Sheet created successfully.")
            return link
        except Exception as e:
            print(f"Error creating Google Sheet: {e}")
            self._notify(f"Error creating Google Sheet: {e}")
            raise # Re-raise to indicate failure

    async def send_email_with_link(self, email: str, link: str):
        """Sends an email with the Google Sheet link."""
        self._notify(f"Sending email to {email}...")
        subject = "Your F1 Standings Google Sheet"
        body = f"Here is the link to the Google Sheet with the current F1 standings:\n\n{link}"
        try:
            await send_email(email, subject, body)
            print(f"Email sent to {email} with link: {link}")
            self._notify("Email sent successfully.")
        except Exception as e:
            print(f"Error sending email: {e}")
            self._notify(f"Error sending email: {e}")
            # Decide how to handle email errors
            # Maybe log it but don't stop the whole process?

# Example usage
# if __name__ == "__main__": # REMOVE OR COMMENT OUT THIS BLOCK
#     # This block is for testing the action module in isolation.
#     # If you want to test it, you need to provide mock dependencies or run it within an asyncio loop
#     # and potentially mock the notify_callback and other imported functions.
#     print("Action module standalone test is not configured.")
#     pass
