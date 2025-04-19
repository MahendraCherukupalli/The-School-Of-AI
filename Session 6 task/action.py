from pydantic import BaseModel
from typing import Dict, Any, Optional

# Import necessary components from other modules
from memory import AppState
from perception import PerceptionOutput, structure_tool_parameters, format_tool_result

class ActionResult(BaseModel):
    success: bool
    result_str: Optional[str] = None
    error: Optional[str] = None

async def execute_action(state: AppState, decision: PerceptionOutput) -> ActionResult:
    """Executes the action determined by the decision module (LLM response)."""
    print(f"--- Iteration {state.current_iteration + 1} (Action) ---")

    # Check if the decision step itself resulted in an error
    if decision.error:
        print(f"ERROR (Action): Decision step failed: {decision.error}")
        return ActionResult(success=False, error=f"Decision step failed: {decision.error}")

    # Check if the decision was to call a function
    if not decision.parsed_call:
        # This case might occur if the LLM response was unexpected or indicates completion (e.g., FINAL_ANSWER)
        # For now, we treat lack of a function call after a successful decision step as an unexpected state.
        # If FINAL_ANSWER logic is added, handle it here.
        print("WARN (Action): No function call parsed from LLM response. Raw response:", decision.llm_raw_response)
        # If final answer is needed, check decision.is_final_answer
        # return ActionResult(success=True, result_str="Final answer reached or no action needed.") 
        return ActionResult(success=False, error="No function call found in the LLM decision.")

    parsed_call = decision.parsed_call
    func_name = parsed_call.func_name

    print(f"DEBUG (Action): Attempting to execute action: {func_name}")

    # Handle explicit error call from LLM
    if func_name == "error":
        error_message = " ".join(parsed_call.raw_params) if parsed_call.raw_params else "Unknown error specified by LLM"
        print(f"ERROR (Action): LLM returned an explicit error call: {error_message}")
        return ActionResult(success=False, error=f"LLM Error: {error_message}")

    # Find the tool definition in the state
    tool = next((t for t in state.mcp_tools if hasattr(t, 'name') and t.name == func_name), None)
    if not tool:
        print(f"ERROR (Action): Tool '{func_name}' not found in available tools: {[t.name for t in state.mcp_tools if hasattr(t, 'name')]}")
        return ActionResult(success=False, error=f"Unknown tool: {func_name}")

    try:
        # Get the tool's input schema
        tool_schema = tool.inputSchema if hasattr(tool, 'inputSchema') else {}
        print(f"DEBUG (Action): Found tool '{func_name}'. Schema: {tool_schema}")

        # Structure the parameters based on the schema
        structured_params_result = structure_tool_parameters(
            parsed_call=parsed_call,
            tool_schema=tool_schema,
            recipient_email=state.recipient_email # Pass recipient email for send_gmail
        )
        arguments = structured_params_result.arguments
        print(f"DEBUG (Action): Structured parameters for '{func_name}': {arguments}")

        # Execute the tool call via MCP session
        print(f"DEBUG (Action): Calling MCP tool '{func_name}'...")
        mcp_result = await state.mcp_session.call_tool(func_name, arguments=arguments)
        print(f"DEBUG (Action): Raw MCP result for '{func_name}': {mcp_result}")

        # Format the result into a string
        result_str = format_tool_result(mcp_result)
        print(f"DEBUG (Action): Formatted result string for '{func_name}': {result_str}")

        return ActionResult(success=True, result_str=result_str)

    except ValueError as e:
        # Errors during parameter structuring or conversion
        error_msg = f"Parameter error for tool '{func_name}': {e}"
        print(f"ERROR (Action): {error_msg}")
        # import traceback
        # traceback.print_exc()
        return ActionResult(success=False, error=error_msg)
    except Exception as e:
        # Errors during the actual MCP tool call
        error_msg = f"Tool call execution failed for '{func_name}': {e}"
        print(f"ERROR (Action): {error_msg}")
        # import traceback
        # traceback.print_exc()
        return ActionResult(success=False, error=error_msg)

# --- Removed old code ---
# from pydantic import BaseModel
# from typing import Dict, Any
# import os

# recipient_email = os.getenv("RECIPIENT_EMAIL")

# class ActionInput(BaseModel):
#     action: str
#     args: Dict[str, Any]
#     tools: Any
#     session: Any  # MCP session

# class ActionOutput(BaseModel):
#     result: str
#     success: bool

# async def act(input_data: ActionInput) -> ActionOutput:
#     func_name = input_data.action
#     args = input_data.args
#     tool = next((t for t in input_data.tools if t.name == func_name), None)
#     if not tool:
#         return ActionOutput(result=f"Tool {func_name} not found", success=False)

#     try:
#         if func_name == "send_gmail":
#             args['recipient'] = recipient_email

#         result = await input_data.session.call_tool(func_name, arguments=args)

#         result_text = str(result.content) if hasattr(result, 'content') else str(result)
#         return ActionOutput(result=result_text, success=True)

#     except Exception as e:
#         return ActionOutput(result=str(e), success=False)
