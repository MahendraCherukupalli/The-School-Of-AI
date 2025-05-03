# Task/config.py

# Define all necessary Google API scopes here
# This list should include all scopes needed by any part of the application
ALL_GOOGLE_SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',       # For sending emails
    'https://www.googleapis.com/auth/spreadsheets',     # For creating/writing sheets
    'https://www.googleapis.com/auth/drive'             # For sharing sheets
]

# You could also move SSE_SERVER_URL here if desired
# SSE_SERVER_URL = "http://localhost:5000/notify"
