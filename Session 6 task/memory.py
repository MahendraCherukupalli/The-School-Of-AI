from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict

# Pydantic model for storing details of one iteration
class IterationRecord(BaseModel):
    iteration: int
    prompt_context: str  # What was sent to the LLM
    llm_raw_response: str # Raw response from LLM
    parsed_action: Optional[str] = None # e.g., "FUNCTION_CALL: add|1|2" or "FINAL_ANSWER: ..."
    action_result: Optional[str] = None # Result from executing the action/tool
    error: Optional[str] = None # Any error that occurred during the iteration

# Pydantic model for holding the complete application state
class AppState(BaseModel):
    initial_query: str
    system_prompt: str
    tools_description: str
    iteration_history: List[IterationRecord] = Field(default_factory=list)
    max_iterations: int = 6
    current_iteration: int = 0
    mcp_session: Any # MCP ClientSession object
    mcp_tools: List[Any] # List of tool objects from MCP
    gemini_client: Any # Gemini Client object
    recipient_email: str
    last_tool_result_str: Optional[str] = None # Store the string representation of the last result
    user_preferences: Optional[Dict[str, Optional[str]]] = None 

    class Config:
        arbitrary_types_allowed = True # Allow complex types like ClientSession

def initialize_state(
    initial_query: str,
    system_prompt: str,
    tools_description: str,
    mcp_session: Any,
    mcp_tools: List[Any],
    gemini_client: Any,
    recipient_email: str,
    max_iterations: int = 6,
    user_preferences: Optional[Dict[str, Optional[str]]] = None
) -> AppState:
    """Initializes the application state, including user preferences."""
    return AppState(
        initial_query=initial_query,
        system_prompt=system_prompt,
        tools_description=tools_description,
        mcp_session=mcp_session,
        mcp_tools=mcp_tools,
        gemini_client=gemini_client,
        recipient_email=recipient_email,
        max_iterations=max_iterations,
        user_preferences=user_preferences
    )

def update_state_after_iteration(
    state: AppState,
    prompt_context: str,
    llm_raw_response: str,
    parsed_action: Optional[str] = None,
    action_result: Optional[str] = None,
    error: Optional[str] = None
) -> AppState:
    """Adds the record of the completed iteration to the state and increments iteration count."""
    record = IterationRecord(
        iteration=state.current_iteration + 1,
        prompt_context=prompt_context, # Storing the context used for this iteration
        llm_raw_response=llm_raw_response,
        parsed_action=parsed_action,
        action_result=action_result,
        error=error
    )
    state.iteration_history.append(record)
    state.current_iteration += 1
    if action_result is not None:
         state.last_tool_result_str = action_result # Update last result if action was successful
    if error:
        # Optionally clear last result on error, or keep it for context? Let's keep it for now.
        pass
    return state

def get_full_prompt_context(state: AppState) -> str:
    """Builds the context string for the LLM based on history and preferences."""
    preference_lines = []
    if state.user_preferences:
        preference_lines.append("--- User Preferences ---")
        user_name = state.user_preferences.get('user_name')
        preferred_subject = state.user_preferences.get('preferred_subject')
        if user_name:
            preference_lines.append(f"User Name for Greeting: {user_name}")
        if preferred_subject:
            preference_lines.append(f"Preferred Email Subject: {preferred_subject}")
        preference_lines.append("------------------------")
    preferences_str = "\n".join(preference_lines) + "\n\n" if preference_lines else ""

    history_parts = []
    if state.iteration_history:
        # Include results from previous iterations for context
        last_record = state.iteration_history[-1]
        history_parts.append(f"Previous Action: {last_record.parsed_action or 'N/A'}")
        if last_record.action_result:
            history_parts.append(f"Previous Result: {last_record.action_result}")
        if last_record.error:
             history_parts.append(f"Previous Error: {last_record.error}")

    full_context = f"{preferences_str}{state.system_prompt}\n\nAvailable tools:\n{state.tools_description}\n\nInitial Query: {state.initial_query}"

    if history_parts:
        full_context += "\n\n--- History ---"
        full_context += "\n" + "\n".join(history_parts)
        full_context += "\n\nWhat should I do next based on the previous result/error and user preferences?"
    else:
         full_context += "\n\nWhat is the first step to address the query, considering user preferences?"

    # Limit context length if necessary (simple example)
    # max_context_length = 4000 # Example limit
    # if len(full_context) > max_context_length:
    #     full_context = full_context[-max_context_length:] # Keep the most recent part

    return full_context
