from pydantic import BaseModel
from typing import Optional, List
import re
import logging # Import logging

logger = logging.getLogger(__name__) # Get logger

class PerceptionResult(BaseModel):
    user_input: str
    intent: Optional[str] = None
    entities: List[str] = []
    tool_hint: Optional[str] = None

def parse_command(command: str) -> PerceptionResult:
    logger.info(f"parse_command received command: {command}") # Added log
    match = re.search(
        r'find the current point standings of f1 racers, then put that into a google excel sheet, and then share the link to this sheet with me \((.+?@.+?\..+?)\)',
        command,
        re.IGNORECASE
    )

    if match:
        intent = "fetch_f1_standings"
        email = match.group(1).strip()
        logger.info(f"Perception: Matched intent '{intent}', extracted email '{email}'") # Changed print to logger.info
        return PerceptionResult(
            user_input=command,
            intent=intent,
            entities=[email]
        )
    else:
        logger.warning(f"Perception: Command did not match expected format: '{command}'") # Changed print to logger.warning
        return PerceptionResult(user_input=command, intent=None, entities=[])

if __name__ == "__main__":
    command = "Find the Current Point Standings of F1 Racers, then put that into a Google Excel Sheet, and then share the link to this sheet with me (your-email@gmail.com)"
    parsed = parse_command(command)
    print(parsed)

    command_fail = "Tell me about F1 standings"
    parsed_fail = parse_command(command_fail)
    print(parsed_fail)
