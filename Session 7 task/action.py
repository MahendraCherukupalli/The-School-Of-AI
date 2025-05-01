import google.generativeai as genai
import os
import logging
from decision import NO_CONTEXT_RESPONSE # Import the predefined response

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- LLM Setup ---
# Consider moving API key management to a more secure location (e.g., env variables, secrets manager)
# For now, hardcoding as it was in the original script, but add a check.
API_KEY = "AIzaSyASRi_AbdLiLyc02JCYBcltPu-kLUfUWNQ" # Replace with your actual key or load from env
if not API_KEY:
    logging.error("GEMINI_API_KEY is not set. Please configure the API key.")
    # Depending on the application, you might want to raise an exception or exit here.
    # For now, we'll proceed, but API calls will fail.
else:
    try:
        genai.configure(api_key=API_KEY)
        # Initialize the model once, potentially reuse if thread-safe or manage instances
        # For simplicity here, we re-initialize per call, but consider optimization.
        # model = genai.GenerativeModel("gemini-1.5-flash")
        logging.info("Gemini API configured successfully.")
    except Exception as e:
        logging.error(f"Failed to configure Gemini API: {e}")
        # Handle configuration error appropriately

def execute_action(plan: str | None) -> str:
    """
    Executes the generated plan.

    If the plan is a prompt string, it calls the Gemini API for RAG.
    If the plan is None, it returns a predefined 'no context' message.

    Args:
        plan: The RAG prompt string, or None if no context was found.

    Returns:
        The final answer string from the LLM or a predefined message.
    """
    if plan is None:
        logging.info("No plan (context) provided. Returning predefined no-context response.")
        return NO_CONTEXT_RESPONSE

    logging.info("Executing RAG action with Gemini.")
    try:
        # Initialize the model here for simplicity, consider optimizing model instance management
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(plan) # 'plan' is the formatted prompt

        # Basic check if the response has text
        if hasattr(response, 'text'):
            logging.info("Successfully received response from Gemini.")
            return response.text
        else:
            # Handle cases where the response might not be as expected
            logging.error(f"Received unexpected response format from Gemini: {response}")
            return "Error: Received an unexpected response format from the AI."

    except Exception as e:
        logging.error(f"Error generating response from Gemini: {e}")
        # Provide a user-friendly error message
        return f"Error generating response: Failed to communicate with the AI service."
