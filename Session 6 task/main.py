import os
import asyncio
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from google import genai
import traceback # For detailed error logging

# Import refactored components
from memory import AppState, initialize_state, update_state_after_iteration, get_full_prompt_context
from decision import decide_next_action
from action import execute_action
# Perception functions might be used implicitly by decision/action, but explicit import isn't needed here

# --- Configuration ---
load_dotenv()

# Gemini API Key
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable is not set")

# Email Configuration (Recipient)
recipient_email = os.getenv("RECIPIENT_EMAIL")
if not recipient_email:
    raise ValueError("RECIPIENT_EMAIL environment variable is not set")

# Agent Configuration
max_iterations = 6
system_prompt = """You are a calculator assistant that performs mathematical operations using structured reasoning and tool calls. You must strictly follow the multi-step process below and produce only structured outputs.

TASK FLOW:

1.Parse Text to Numbers
   - Extract numeric values from the input text.
   - Annotate the reasoning type as "parsing".

2.Determine and Perform the Correct Operation
   - Identify the correct mathematical operation (e.g., add, subtract, multiply, divide).
   - Tag the reasoning as "arithmetic".
   - Call the appropriate tool function using the parsed numbers.

3.Format the Result for Email
   - Prepare the email content including:
     a. Original text input
     b. Parsed values
     c. Operation performed
     d. Final result
   - Tag this reasoning as "formatting".

4.Send Email
   - Call the email-sending function with the formatted message.

INSTRUCTIONS:

- Think step-by-step and tag each step with its reasoning type.
- After each reasoning step, perform a brief internal self-check (e.g., "Are values parsed correctly?", "Does the operation match the question?").
- If uncertain or if tool input is missing/invalid, return:
  `FUNCTION_CALL: error|Invalid or incomplete input`
- If a tool call fails, retry once. If it fails again, return an error message in the same format.

OUTPUT FORMAT:

- You must respond with EXACTLY ONE line in this format:
  `FUNCTION_CALL: function_name|param1|param2|...`
- No additional text or explanation is allowed.
- You may only use functions that appear in the available tool list. Always use the correct syntax and parameters.

*** Applying User Preferences for Email ***
- When you decide to send the final calculation result via email, check the 'User Preferences' provided in the context.
- The action to send an email expects parameters in the format: `function_name|subject|body`.
- If a 'Preferred Email Subject' is available in preferences, use it exactly as the `subject` parameter for the email action. Otherwise, create a relevant subject.
- If a 'User Name for Greeting' is available, start the `body` parameter with "Hello [User Name]," followed by the results. Otherwise, just include the results in the `body`.

EXAMPLE:

For input: "What is the sum of five and three?"

Parsed values: 5, 3
Operation: add
Reasoning steps: ["parsing", "arithmetic", "formatting"]
Final output:
`FUNCTION_CALL: add|5|3`

After receiving the result (8), and assuming User Preferences were:
User Name for Greeting: Mahendra
Preferred Email Subject: Calculation Result
And the email tool is named 'send_email', you would output:
`FUNCTION_CALL: send_email|Calculation Result|Hello Mahendra, The sum is 8.`

If Preferred Email Subject was empty, you might output:
`FUNCTION_CALL: send_email|Sum Calculation Result|Hello Mahendra, The sum is 8.`

Make sure to complete all steps in sequence and stop after sending the email.
"""
initial_query = "Calculate ASCII values for INDIA, find sum of their exponentials, and send the result via email"
# --- End Configuration ---

# --- Helper Functions ---

def collect_user_preferences() -> dict:
    """Asks the user for preferences before starting the main flow."""
    print("\n--- Gathering Preferences ---")
    user_name = input("Your name for the email greeting? ")
    preferred_subject = input("Preferred email subject? (Optional, press Enter to skip): ")
    print("---------------------------")
    return {
        "user_name": user_name.strip() if user_name else None,
        "preferred_subject": preferred_subject.strip() if preferred_subject else None
    }

def format_tools_description(tools) -> str:
    """Creates a formatted string describing available tools for the LLM prompt."""
    tools_description_list = []
    print(f"DEBUG (Main): Formatting {len(tools)} tools...")
    for i, tool in enumerate(tools):
        try:
            params = getattr(tool, 'inputSchema', {})
            desc = getattr(tool, 'description', 'No description available')
            name = getattr(tool, 'name', f'tool_{i}')

            param_details = []
            # Updated check: properties can be None or empty dict
            if isinstance(params, dict) and 'properties' in params and params['properties']:
                for param_name, param_info in params['properties'].items():
                     # Ensure param_info is a dict before accessing keys
                    if isinstance(param_info, dict):
                        param_type = param_info.get('type', 'unknown')
                        param_desc = param_info.get('description', '') # Optional description
                        detail = f"{param_name}: {param_type}"
                        if param_desc:
                             detail += f" ({param_desc})"
                        param_details.append(detail)
                    else:
                        print(f"WARN (Main): Unexpected format for param_info '{param_info}' in tool '{name}'")
                        param_details.append(f"{param_name}: unknown_format")
                params_str = ', '.join(param_details)
            else:
                params_str = 'no parameters'
                # print(f"DEBUG (Main): Tool '{name}' has no parameters or schema not found/invalid.")

            tool_desc = f"{i+1}. {name}({params_str}) - {desc}"
            tools_description_list.append(tool_desc)
            # print(f"DEBUG (Main): Added description for tool: {tool_desc}")
        except Exception as e:
            tool_name_fallback = getattr(tool, 'name', f'tool_{i}')
            print(f"ERROR (Main): Error processing tool description for '{tool_name_fallback}': {e}")
            traceback.print_exc()
            tools_description_list.append(f"{i+1}. Error processing tool '{tool_name_fallback}'")

    return "\n".join(tools_description_list)

async def main():
    state = None # Initialize state to None for finally block
    print("--- Starting Agent Execution ---")
    try:
        # <<< Add preference collection here >>>
        preferences = collect_user_preferences()

        print("Initializing Gemini client...")
        # Adjust client initialization if needed based on genai library specifics
        # e.g., genai.configure(api_key=api_key)
        # client = genai.GenerativeModel('gemini-pro') # Example for a specific model
        client = genai.Client(api_key=api_key)
        print("Gemini client initialized.")

        print("Establishing connection to MCP server (example2-4.py)...")
        server_params = StdioServerParameters(
            command="python",
            # *** IMPORTANT: Update to the correct tool server script ***
            args=["example2-4.py"] 
        )

        async with stdio_client(server_params) as (read, write):
            print("MCP Connection established. Creating session...")
            async with ClientSession(read, write) as session:
                print("MCP Session created. Initializing...")
                await session.initialize()
                print("MCP Session initialized.")

                print("Requesting tool list from MCP server...")
                tools_result = await session.list_tools()
                tools = tools_result.tools
                print(f"Successfully retrieved {len(tools)} tools.")

                # Format tools description
                tools_description = format_tools_description(tools)
                print("--- Available Tools ---")
                print(tools_description)
                print("-----------------------")

                # Initialize agent state, now including preferences
                state = initialize_state(
                    initial_query=initial_query,
                    system_prompt=system_prompt,
                    tools_description=tools_description,
                    mcp_session=session,
                    mcp_tools=tools,
                    gemini_client=client, # Pass the initialized client
                    recipient_email=recipient_email,
                    max_iterations=max_iterations,
                    # <<< Pass collected preferences >>>
                    user_preferences=preferences 
                )
                print("Agent state initialized (including preferences).")

                # --- Main Execution Loop ---
                while state.current_iteration < state.max_iterations:
                    # 1. Decide next action
                    decision_output = await decide_next_action(state)

                    # Capture prompt context used for this iteration before potential modification
                    prompt_context_for_memory = get_full_prompt_context(state)

                    # 2. Execute the action
                    action_result = await execute_action(state, decision_output)

                    # 3. Update State
                    state = update_state_after_iteration(
                        state=state,
                        prompt_context=prompt_context_for_memory,
                        llm_raw_response=decision_output.llm_raw_response,
                        # Use the parsed action string if available, otherwise indicate error/no action
                        parsed_action=str(decision_output.parsed_call) if decision_output.parsed_call else decision_output.error or "No Action Parsed",
                        action_result=action_result.result_str, # Store the string result
                        error=action_result.error # Store any error from execution
                    )

                    # 4. Log and Check Stop Conditions
                    if action_result.success:
                        print(f"✅ Iteration {state.current_iteration} Result: {action_result.result_str}")
                        # Check for specific success condition (e.g., email sent)
                        if action_result.result_str and "email sent successfully" in action_result.result_str.lower():
                            print("--- Email sent. Task completed successfully. ---")
                            break
                    else:
                        print(f"❌ Iteration {state.current_iteration} Error: {action_result.error}")
                        # Decide if we should stop on error
                        print("--- Agent loop stopped due to error. ---")
                        break 
                    
                    # Optional: Add a small delay between iterations if needed
                    # await asyncio.sleep(1)

                else: # Loop finished without break (max iterations reached)
                    print(f"--- Max iterations ({state.max_iterations}) reached. Stopping agent. ---")
                # --- End Main Execution Loop ---

    except Exception as e:
        print(f"\n💥💥💥 An unexpected error occurred in the main execution: {e} 💥💥💥")
        print("--- Error Details ---")
        traceback.print_exc()
        print("---------------------")
    finally:
        print("--- Agent Execution Finished ---")
        if state:
            print("--- Final State ---")
            # Avoid printing potentially large/complex objects directly
            print(f"Initial Query: {state.initial_query}")
            print(f"Iterations Completed: {state.current_iteration}")
            print(f"Last Tool Result: {state.last_tool_result_str}")
            print("Iteration History:")
            for record in state.iteration_history:
                print(f"  Iter {record.iteration}: Action={record.parsed_action}, Result={record.action_result}, Error={record.error}")
            print("-------------------")
        else:
             print("(No state information available due to early failure)")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n--- Agent execution interrupted by user. ---")
    except Exception as e:
        # Catch any other unexpected errors during asyncio.run or final cleanup
        print(f"\n💥💥💥 Critical error during script execution: {e} 💥💥💥")
        traceback.print_exc()

# --- Removed old code ---
# def collect_user_preferences() -> str:
#     name = input("What's your name? ")
#     location = input("Where are you located? (optional) ")
#     topic = input("What's your favorite topic or interest? ")
#     taste = input("Do you have a taste preference (e.g. spicy, sweet)? ")

#     pref = f"User {name} from {location or 'unknown location'} likes {topic} and prefers {taste or 'no specific taste'}."
#     return pref

# ... (rest of old main logic)
