from dataclasses import dataclass
from typing import Literal

@dataclass
class HITLRequest:
    prompt_to_user: str
    session_id: str
    type: Literal["tool_failure", "plan_failure"] 