import sys
import os
import asyncio # Keep import for async handlers
import logging
import requests # Import requests for sync API call

print("telegram_bot.py: Script starting...")

# Set up basic logging to see output from python-telegram-bot library
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# Get a logger for our script
logger = logging.getLogger(__name__)
logger.info("Logger initialized.")


# Add the parent directory (project root) to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(script_dir, os.pardir) # Go up one directory from Task/
# Insert at position 0 to prioritize project modules
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    logger.info(f"Added {project_root} to sys.path")
else:
     logger.info(f"{project_root} already in sys.path")


from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, BaseHandler # Import BaseHandler for checking handlers
# Import the main async function using absolute path
try:
    from Task.main import main_flow
    logger.info("Successfully imported main_flow from Task.main")
except ImportError as e:
    logger.error(f"Error importing main_flow from Task.main: {e}", exc_info=True) # Log exception info
    sys.exit(1)


# Change relative imports to absolute imports
try:
    # from .action import ActionHandler # Original relative import
    # from .utils import notify_sse # Original relative import
    from Task.action import ActionHandler # Changed to absolute import
    from Task.utils import notify_sse # Changed to absolute import
    logger.info("Successfully imported ActionHandler and notify_sse using absolute paths")
except ImportError as e:
    logger.error(f"Error importing ActionHandler or notify_sse using absolute paths: {e}", exc_info=True) # Log exception info
    sys.exit(1)


# Load environment variables (for bot token)
logger.info("Loading environment variables...")
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_TOKEN:
    logger.error("Error: TELEGRAM_BOT_TOKEN environment variable not set.")
    sys.exit("Telegram bot requires TELEGRAM_BOT_TOKEN environment variable.")
else:
    logger.info(f"Telegram Token loaded. Length: {len(TELEGRAM_TOKEN)}. Starts with: {TELEGRAM_TOKEN[:10]}...") # Log token info


# Global variable to hold the ActionHandler instance
action_handler_instance = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    if update.message:
        logger.info(f"'/start' command received from chat ID {update.message.chat_id}.")
        await update.message.reply_text('Hello! Send me the F1 standings command.')
    else:
        logger.warning("Received update with no message for /start command.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles non-command messages."""
    # Add more robust check for message and text
    if not update or not update.message or not update.message.text:
         logger.info("Received update with no valid message or text content, ignoring.")
         return # Ignore updates without text messages

    logger.info("handle_message triggered!")
    global action_handler_instance

    command_text = update.message.text
    chat_id = update.message.chat_id
    logger.info(f"Received message from chat ID {chat_id}: {command_text}")

    if action_handler_instance is None:
        logger.error("ActionHandler not initialized in Telegram bot.")
        await context.bot.send_message(chat_id=chat_id, text="Bot is starting up, please wait a moment and try again.")
        return

    try:
        await context.bot.send_message(chat_id=chat_id, text="Processing your request...")
        notify_sse(f"Processing Telegram message from chat ID {chat_id}: {command_text[:50]}...")

        logger.info(f"Calling main_flow from handle_message...")
        response = await main_flow(command_text, action_handler_instance)
        logger.info(f"main_flow returned to handle_message. Response: {response[:50]}...")

        await context.bot.send_message(chat_id=chat_id, text=response)
        logger.info("Sent response to Telegram.")

    except Exception as e:
        logger.error(f"Error in handle_message for chat ID {chat_id}: {e}", exc_info=True)
        notify_sse(f"Error in handle_message for chat ID {chat_id}: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"An error occurred: {e}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    # You might want to send a message to yourself here for critical errors
    # if update and hasattr(update, 'effective_chat') and update.effective_chat:
    #     await context.bot.send_message(chat_id=update.effective_chat.id, text="An internal error occurred.")

def clear_pending_updates_sync(token: str):
    """Synchronously clears pending updates using requests."""
    logger.info("Attempting to clear pending Telegram updates synchronously...")
    if not token:
        logger.warning("Telegram token is not available, cannot clear pending updates.")
        return

    api_url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {'offset': -1, 'limit': 1} # offset=-1 clears all updates

    try:
        response = requests.get(api_url, params=params, timeout=10)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        result = response.json()
        if result.get('ok'):
            # If 'result' is an empty list, it means there were updates to clear
            # We can't easily tell *how many* were cleared with offset=-1 directly,
            # but the successful call with offset=-1 acknowledges them.
            logger.info("Synchronously called getUpdates with offset=-1 to clear pending updates.")
        else:
            logger.warning(f"Synchronous update clearing failed. API response: {result}")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Synchronous update clearing failed due to network or API error: {e}", exc_info=True)
    except Exception as e:
        logger.warning(f"An unexpected error occurred during synchronous update clearing: {e}", exc_info=True)


def run_bot(): # run_bot is now synchronous again
    """Starts the Telegram bot."""
    global action_handler_instance
    logger.info("Starting Telegram bot setup...")

    try:
        # ActionHandler can be instantiated here
        action_handler_instance = ActionHandler(notify_callback=notify_sse)
        logger.info("ActionHandler instantiated in Telegram bot.")
    except Exception as e:
        logger.error(f"Error instantiating ActionHandler: {e}", exc_info=True)
        sys.exit(1)

    try:
        # Application builder and build are synchronous
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        logger.info("Telegram Application built.")
    except Exception as e:
        logger.error(f"Error building Telegram Application: {e}", exc_info=True)
        sys.exit(1)

    try:
        # Handlers are added synchronously
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_error_handler(error_handler)
        logger.info("Telegram bot handlers and error handler added.")

        # --- Add Handler Check ---
        if application.handlers:
            logger.info(f"Application has {len(application.handlers)} handler groups.")
            for group_id, group_handlers in application.handlers.items():
                logger.info(f"  Handler Group {group_id}: {len(group_handlers)} handlers")
                for handler in group_handlers:
                    logger.info(f"    - {type(handler).__name__}")
        else:
            logger.warning("Application has no registered handlers!")
        # --- End Handler Check ---

    except Exception as e:
        logger.error(f"Error adding Telegram handlers: {e}", exc_info=True)
        sys.exit(1)

    # --- Clear Pending Updates (Synchronous Call) ---
    # Call the synchronous clearing function BEFORE starting the polling loop
    clear_pending_updates_sync(TELEGRAM_TOKEN)
    # --- End Clear Pending Updates ---


    logger.info("Telegram bot starting polling loop...")
    try:
        logger.info("Attempting to run polling loop...")
        # run_polling is synchronous and blocking, managing its own internal event loop for async handlers
        application.run_polling(
            poll_interval=3.0,
            timeout=20.0, # These timeouts might still be deprecated depending on exact v20 sub-version
            read_timeout=20.0, # but are less likely to cause a TypeError like stop_signal_handler
            connect_timeout=20.0,
            # Removed stop_signal_handler as it's not supported
        )
        logger.info("Telegram bot polling stopped gracefully.")
    except Exception as e:
        # Log the error and exit the subprocess
        logger.error(f"An error occurred during Telegram bot polling: {e}", exc_info=True)
        sys.exit(f"Telegram bot polling failed: {e}")


logger.info("Script defining functions complete.")

if __name__ == '__main__':
    logger.info("Running __main__ block.")
    if TELEGRAM_TOKEN:
        # Call the synchronous run_bot function directly
        # The event loop for async handlers is managed internally by run_polling
        try:
            run_bot() # Call the synchronous function directly
        except SystemExit:
             # Catch SystemExit from sys.exit() calls within run_bot
             pass
        except Exception as e:
             # Catch any unexpected errors from run_bot itself
             logger.error(f"An unexpected error occurred in __main__ after calling run_bot: {e}", exc_info=True)
             sys.exit(1)
    else:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Bot will not start.")

logger.info("Script finished execution (this should only be seen on exit).")
