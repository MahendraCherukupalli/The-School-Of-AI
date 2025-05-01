from models import PerceptionResult
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def extract_perception(user_input: str) -> PerceptionResult:
    """
    Extracts perception from the user input.

    In this simplified version, it just packages the raw input.
    Future enhancements could involve LLM calls for intent/entity extraction.
    """
    if not user_input:
        logging.warning("extract_perception called with empty input.")
        # Return a default or handle as appropriate, here returning with empty string
        return PerceptionResult(user_input="")

    logging.info(f"Extracting perception for input: '{user_input[:50]}...'")
    result = PerceptionResult(user_input=user_input)
    logging.info("Perception extraction complete (simplified).")
    return result
