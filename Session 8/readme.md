# F1 Standings Bot

This project is a Python application that leverages a Telegram bot to fetch current F1 driver standings, store them in a Google Sheet, and send the link to the sheet via email to a specified recipient. It also includes a simple Server-Sent Events (SSE) server for broadcasting status updates.

## Features

*   **Telegram Bot Interface:** Interact with the application using commands sent via Telegram.
*   **F1 Standings:** Fetches the latest driver standings from the Ergast API.
*   **Google Sheets Integration:** Creates a new Google Sheet and populates it with the F1 standings.
*   **Google Drive Integration:** Shares the generated Google Sheet with public read access.
*   **Gmail Integration:** Sends an email containing the link to the Google Sheet to a specified email address.
*   **Server-Sent Events (SSE):** Provides real-time status updates on the application's progress.
*   **Modular Design:** Organized into different modules for perception, decision, action, API handling, and service integration.

## Project Structure

├── Task/
│ ├── action.py # Handles execution of specific actions (fetching data, GSheets, Gmail)
│ ├── client_secret.json # Google API client credentials (DO NOT commit)
│ ├── config.py # Shared configuration (Google API scopes)
│ ├── decision.py # Decides the action based on parsed command
│ ├── f1_api.py # Fetches F1 standings from Ergast API
│ ├── gmail_handler.py # Interacts with Gmail API
│ ├── gsheet_handler.py # Interacts with Google Sheets and Drive APIs
│ ├── init.py # Makes the directory a Python package
│ ├── main.py # Main entry point, starts servers, orchestrates flow
│ ├── models.py # Data models (e.g., F1Standings)
│ ├── perception.py # Parses incoming commands
│ ├── requirements.txt # Project dependencies
│ ├── sse_server.py # Simple SSE server for notifications
│ ├── telegram_bot.py # Telegram bot interface
│ ├── token.pickle # Stores Google API tokens (DO NOT commit)
│ └── utils.py # Utility functions (e.g., notify_sse)
└── .gitignore # Specifies intentionally untracked files (should include secrets)

### Prerequisites

*   Python 3.7+
*   Git

### 1. Clone the Repository

```bash
git clone <your-repository-url>
cd <your-repository-name>/Task # Navigate to the Task directory
```

### 2. Install Dependencies

Install the required Python packages:

```bash
pip install -r requirements.txt
```

### 3. Set up Telegram Bot Token

Obtain a bot token from the BotFather on Telegram. Create a `.env` file in the **project root directory** (one level above the `Task` folder, where `.gitignore` is located) with the following content:

```env
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
```

Replace `YOUR_TELEGRAM_BOT_TOKEN` with your actual token. Ensure `.env` is listed in your `.gitignore` file.

### 4. Set up Google API Credentials

This application requires access to Google Sheets and Gmail APIs.

*   Go to the Google Cloud Console ([https://console.cloud.google.com/](https://console.cloud.google.com/)).
*   Create a new project or select an existing one.
*   Enable the **Google Sheets API**, **Google Drive API**, and **Gmail API** for your project.
*   Configure the OAuth consent screen.
*   Create **OAuth 2.0 Client IDs** credentials for a "Desktop app".
*   Download the `client_secret.json` file and place it inside the `Task/` directory. **Rename it to `client_secret.json` if it has a different name.**

**IMPORTANT:** `client_secret.json` contains sensitive information. **Do not commit this file to your repository.** Ensure it is listed in your `.gitignore`.

### 5. Handle `token.pickle`

The first time you run the Google Sheets or Gmail integration, a browser window will open asking you to authorize the application. After successful authorization, a `token.pickle` file will be created in the `Task/` directory. This file stores your refresh and access tokens.

**IMPORTANT:** `token.pickle` contains highly sensitive tokens that grant access to your Google account data. **Do not commit this file to your repository.** Ensure it is listed in your `.gitignore`.

## Running the Application

The `main.py` script starts the necessary servers (Telegram bot and SSE server) as subprocesses.

Navigate to the **project root directory** (one level above the `Task` folder) in your terminal and run:

```bash
python -m Task.main
```

This will start the SSE server on `http://localhost:5000` and the Telegram bot will begin polling for updates. You should see output in your console indicating that the servers have started.

Press `Ctrl+C` in the terminal to stop all running servers.

## Interacting with the Bot

Once the application is running, find your Telegram bot and send the following command format:

```
Find the Current Point Standings of F1 Racers, then put that into a Google Excel Sheet, and then share the link to this sheet with me (your-email@gmail.com)
```

Replace `your-email@gmail.com` with the email address you want the Google Sheet link sent to.

The bot will process your request, fetch standings, create and share the sheet, send the email, and reply to you with a confirmation message (or an error).

## SSE Notifications

The SSE server runs on `http://localhost:5000`. You can connect to `http://localhost:5000/events` from a web browser or a client application to receive real-time status updates as the bot processes requests.

## Contributing

(Optional section: Add details on how others can contribute to your project)

## License

(Optional section: Add license information, e.g., MIT License)
