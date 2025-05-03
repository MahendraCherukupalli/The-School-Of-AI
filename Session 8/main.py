import asyncio
import subprocess
import sys # To check arguments if needed
import time
from .perception import parse_command, PerceptionResult
from .decision import decide_next_action
from .action import ActionHandler # Only import the ActionHandler class
import os
from dotenv import load_dotenv
from .config import ALL_GOOGLE_SCOPES  # Ensure this is imported correctly
from .utils import notify_sse  # Import notify_sse from utils
import logging # Import logging

# Import ALL_GOOGLE_SCOPES from the new config module
from .config import ALL_GOOGLE_SCOPES

# Load environment variables
load_dotenv()

# SSE_SERVER_URL is now in utils.py
# notify_sse function is now in utils.py and imported

# --- Server Start Functions ---
# Store subprocess handles to potentially manage them later (e.g., terminate)
server_processes = {}

def start_server(name, script_path):
    """Starts a server script using the same Python executable,
       allowing its output to go to the console."""
    try:
        command = [sys.executable, script_path]
        print(f"main.py: Starting {name} server process with command: {' '.join(command)}") # Added print for clarity

        # Do NOT redirect stdout/stderr to pipes, let them go to the console
        process = subprocess.Popen(command) # Removed stdout=..., stderr=..., text=True
        server_processes[name] = process
        print(f"main.py: Started {name} server (PID: {process.pid})...")

        # Give the process a moment to start
        time.sleep(2) # Increased sleep slightly

        # Check if the process terminated immediately (e.g., due to an error)
        returncode = process.poll()
        if returncode is not None:
            print(f"main.py: [{name} Server] Process terminated unexpectedly with return code {returncode}", file=sys.stderr)
            # We can't read output from pipes here as we didn't redirect them.
            # The error output should have appeared directly on the console.
        else:
            print(f"main.py: [{name} Server] Process (PID: {process.pid}) is running.")

    except FileNotFoundError:
        print(f"main.py: Error: Could not find Python executable at {sys.executable} to run {name}. Make sure the Python environment is correctly configured.", file=sys.stderr)
        # Do not exit immediately, allow other servers to potentially start
    except Exception as e:
        print(f"main.py: Error starting {name} server: {e}", file=sys.stderr)
        # Do not exit immediately

def start_all_servers():
    print("main.py: Attempting to start servers...")
    start_server("SSE", "Task/sse_server.py")
    start_server("TelegramBot", "Task/telegram_bot.py")
    print("main.py: Servers starting... check for their output above.")
    # No need for a long sleep here, the subprocesses will print their own status
    # time.sleep(5) # Removed long sleep
    print("main.py: Servers started. Main script is now waiting for input from bots...")
    print("main.py: Press Ctrl+C to stop the main script and servers.")

# --- Main Application Logic ---
logger = logging.getLogger(__name__) # Get logger

async def process_f1_request(perception: PerceptionResult, action_handler: ActionHandler):
    """Handles the specific F1 standings request flow."""
    logger.info(f"process_f1_request called with perception: {perception}") # Added log

    if not perception.entities:
        logger.warning("No email address found in perception entities. Exiting process_f1_request.") # Added log
        notify_sse("Error: Email address not found in the command.")
        return "Could not find an email address in your request."

    email = perception.entities[0]
    logger.info(f"Extracted email: {email}") # Added log

    try:
        notify_sse("Starting F1 request process...")

        logger.info("Calling action_handler.fetch_f1_standings()...") # Added log
        standings = await action_handler.fetch_f1_standings()
        logger.info(f"fetch_f1_standings returned {len(standings)} standings.") # Added log
        if not standings:
            logger.warning("fetch_f1_standings returned no data.") # Added log
            return "Could not retrieve F1 standings."

        logger.info("Calling action_handler.create_and_share_sheet()...") # Added log
        sheet_link = await action_handler.create_and_share_sheet(standings)
        logger.info(f"create_and_share_sheet returned link: {sheet_link}") # Added log
        notify_sse(f"Sheet created: {sheet_link}")

        logger.info(f"Calling action_handler.send_email_with_link() to {email}...") # Added log
        await action_handler.send_email_with_link(email, sheet_link)
        logger.info("send_email_with_link completed.") # Added log

        final_message = f"OK! I've fetched the F1 standings, put them in a Google Sheet, and sent the link to {email}."
        notify_sse("Process completed successfully.")
        logger.info("process_f1_request finished successfully.") # Added log
        return final_message

    except FileNotFoundError as e:
         logger.error(f"Configuration Error in process_f1_request: {e}", exc_info=True) # Log error
         notify_sse(f"Configuration Error: {e}")
         return f"Configuration Error: {e}. Please ensure client_secret.json and token.pickle are in the Task folder."
    except Exception as e:
        logger.error(f"An error occurred during processing in process_f1_request: {e}", exc_info=True) # Log error
        notify_sse(f"An unexpected error occurred during processing: {e}")
        return f"Sorry, an error occurred while processing your request: {e}"


async def main_flow(command: str, action_handler: ActionHandler):
    """Main orchestration flow, to be called by servers (like Telegram bot)."""
    logger.info(f"main_flow received command: {command[:50]}...") # Added log

    # 1. Perception
    logger.info("Calling parse_command...") # Added log
    parsed_command = parse_command(command)
    logger.info(f"parse_command returned: {parsed_command}") # Added log

    if not parsed_command.intent:
         logger.warning("Parsed command has no intent. Exiting main_flow.") # Added log
         notify_sse("Could not understand the command.")
         return "Sorry, I didn't understand that command format."

    # 2. Decision (Simple routing based on intent)
    logger.info("Calling decide_next_action...") # Added log
    action_to_take = decide_next_action(parsed_command)
    logger.info(f"decide_next_action returned action: {action_to_take}") # Added log


    # 3. Action
    if action_to_take == "fetch_and_process_f1_standings":
        logger.info("Action is 'fetch_and_process_f1_standings'. Calling process_f1_request...") # Added log
        return await process_f1_request(parsed_command, action_handler)
    else:
        logger.warning(f"Command intent '{parsed_command.intent}' not recognized for action. Exiting main_flow.") # Added log
        notify_sse("Command intent not recognized for action.")
        return "Sorry, I don't know how to handle that request."

# --- Entry Point ---
if __name__ == "__main__":
    # Start dependent servers
    start_all_servers()

    print("Servers started. Main script is now waiting for input from bots...")
    print("Press Ctrl+C to stop the main script and servers.")

    try:
        # Keep the main script alive so the subprocesses continue running
        # A simple way is to just sleep or run a loop, though a more
        # sophisticated approach might involve monitoring subprocesses.
        while True:
            time.sleep(1)
            # Optional: Check subprocess status periodically if needed
            # For simplicity, we rely on Ctrl+C to terminate
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received. Stopping servers...")
    finally:
        # Terminate started servers on exit
        for name, proc in server_processes.items():
           if proc.poll() is None: # Only try to terminate if the process is still running
               print(f"Terminating {name} server (PID: {proc.pid})...")
               try:
                   proc.terminate()
                   # Optional: Add a timeout for termination and then kill()
                   proc.wait(timeout=5)
               except subprocess.TimeoutExpired:
                   print(f"Process {name} did not terminate, killing...")
                   proc.kill()
               except Exception as e:
                   print(f"Error terminating {name} server: {e}")

# Ensure logging is set up at the top level of main.py as well
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
