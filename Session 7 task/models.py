from pydantic import BaseModel
from typing import Optional, List

class PerceptionResult(BaseModel):
    """Stores the result of the perception phase."""
    user_input: str
    # We can add intent, entities later if needed

# Add other models here as needed, e.g., MemoryItem, ActionResult
