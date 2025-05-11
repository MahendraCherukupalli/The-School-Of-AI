# core/context.py

from typing import List, Optional, Dict, Any
from modules.memory import MemoryManager, MemoryItem
from core.session import MultiMCP  # For dispatcher typing
from pathlib import Path
import yaml
import time
import uuid
from datetime import datetime
from pydantic import BaseModel

class StrategyProfile(BaseModel):
    planning_mode: str
    exploration_mode: Optional[str] = None
    memory_fallback_enabled: bool
    max_steps: int
    max_lifelines_per_step: int


class AgentProfile:
    def __init__(self):
        with open("config/profiles.yaml", "r") as f:
            config = yaml.safe_load(f)

        self.name = config["agent"]["name"]
        self.id = config["agent"]["id"]
        self.description = config["agent"]["description"]

        self.strategy = StrategyProfile(**config["strategy"])
        self.memory_config = config["memory"]
        self.llm_config = config["llm"]
        self.persona = config["persona"]


    def __repr__(self):
        return f"<AgentProfile {self.name} ({self.strategy})>"

class AgentContext:
    """Holds all session state, user input, memory, and strategies."""

    def __init__(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        dispatcher: Optional[MultiMCP] = None,
        mcp_server_descriptions: Optional[List[Any]] = None,
    ):
        if session_id is None:
            today = datetime.now()
            ts = int(time.time())
            uid = uuid.uuid4().hex[:6]
            session_id = f"{today.year}/{today.month:02}/{today.day:02}/session-{ts}-{uid}"

        self.user_input = user_input
        self.agent_profile = AgentProfile()
        self.memory = MemoryManager(session_id=session_id)
        self.session_id = self.memory.session_id
        self.dispatcher = dispatcher  # 🆕 Added formally
        self.mcp_server_descriptions = mcp_server_descriptions  # 🆕 Added formally
        self.step = 0
        self.task_progress = []  # 🆕 Will track tool executions
        self.final_answer = None
        

        # Log session start
        self.add_memory(MemoryItem(
            timestamp=time.time(),
            text=f"Started new session with input: {user_input} at {datetime.utcnow().isoformat()}",
            type="run_metadata",
            session_id=self.session_id,
            tags=["run_start"],
            user_query=user_input,
            metadata={
                "start_time": datetime.now().isoformat(),
                "step": self.step
            }
        ))

    def add_memory(self, item: MemoryItem):
        """Add item to memory"""
        self.memory.add(item)

    def format_history_for_llm(self) -> str:
        if not self.tool_calls:
            return "No previous actions"
            
        history = []
        for i, trace in enumerate(self.history, 1):
            result_str = str(trace.result)
            
            # New truncation logic for ALL steps, including the last one,
            # with a more generous limit.
            max_len = 1500  # Max length for the result string in the context
            if len(result_str) > max_len:
                result_str = result_str[:max_len] + f"... (truncated, original length: {len(result_str)})"
            
            history.append(f"{i}. Used {trace.tool_name} with {trace.arguments}\nResult: {result_str}")
        
        return "\n\n".join(history)

    def log_subtask(self, tool_name: str, status: str = "pending"):
        """Log the start of a new subtask."""
        self.task_progress.append({
            "step": self.step,
            "tool": tool_name,
            "status": status,
        })

    def update_subtask_status(self, tool_name: str, status: str):
        """Update the status of an existing subtask."""
        for item in reversed(self.task_progress):
            if item["tool"] == tool_name and item["step"] == self.step:
                item["status"] = status
                break

    def __repr__(self):
        return f"<AgentContext step={self.step}, session_id={self.session_id}>"
