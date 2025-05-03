from typing import Optional
from .perception import PerceptionResult
import logging # Import logging

logger = logging.getLogger(__name__) # Get logger

def decide_next_action(perception_result: PerceptionResult) -> Optional[str]:
    """Decides the next action based on the parsed command's intent."""
    logger.info(f"decide_next_action received perception_result: {perception_result}") # Added log

    if perception_result.intent == "fetch_f1_standings":
        logger.info("Decision: Intent is 'fetch_f1_standings'. Action decided as 'fetch_and_process_f1_standings'") # Changed print to logger.info
        return "fetch_and_process_f1_standings"
    else:
        logger.warning(f"Decision: Unknown or missing intent: {perception_result.intent}. Returning None.") # Changed print to logger.warning
        return None # Return None or an 'unknown_intent' string if intent doesn't match

# Example usage (optional)
# if __name__ == "__main__":
#     # Test case 1: Correct intent
#     command_ok = PerceptionResult(user_input="...", intent="fetch_f1_standings", entities=["email@example.com"])
#     action_ok = decide_next_action(command_ok)
#     print(f"Test OK: Action -> {action_ok}")

#     # Test case 2: No intent
#     command_fail = PerceptionResult(user_input="...", intent=None, entities=[])
#     action_fail = decide_next_action(command_fail)
#     print(f"Test Fail: Action -> {action_fail}")
