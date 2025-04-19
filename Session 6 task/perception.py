from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import asyncio
from concurrent.futures import TimeoutError

# Pydantic model for the raw parsed function call from LLM
class ParsedFunctionCall(BaseModel):
    func_name: str
    raw_params: List[str]

# Pydantic model for the structured parameters ready for MCP call
class StructuredParams(BaseModel):
    arguments: Dict[str, Any]

# Pydantic model for the output of the perception step (after LLM call)
class PerceptionOutput(BaseModel):
    llm_raw_response: str
    parsed_call: Optional[ParsedFunctionCall] = None
    is_final_answer: bool = False
    error: Optional[str] = None

def parse_llm_response(llm_response_text: str) -> PerceptionOutput:
    """Parses the raw LLM response text to find FUNCTION_CALL or FINAL_ANSWER."""
    parsed_call = None
    is_final = False
    error_msg = None
    function_call_line = None

    lines = llm_response_text.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith("FUNCTION_CALL:"):
            function_call_line = line
            break # Assume only one function call per response
        # Add handling for FINAL_ANSWER if needed based on future prompts
        # elif line.startswith("FINAL_ANSWER:"):
        #     is_final = True
        #     break

    if function_call_line:
        try:
            _, function_info = function_call_line.split(":", 1)
            parts = [p.strip() for p in function_info.split("|")]
            if not parts:
                 raise ValueError("Empty function call info")
            func_name = parts[0]
            raw_params = parts[1:]
            parsed_call = ParsedFunctionCall(func_name=func_name, raw_params=raw_params)
            print(f"DEBUG (Perception): Parsed FUNCTION_CALL: {func_name} with params: {raw_params}")
        except Exception as e:
            error_msg = f"Failed to parse FUNCTION_CALL line '{function_call_line}': {e}"
            print(f"ERROR (Perception): {error_msg}")
    # elif is_final:
    #     print("DEBUG (Perception): Detected FINAL_ANSWER.")
    else:
        # If no FUNCTION_CALL (or FINAL_ANSWER) is found, treat as an error or unexpected response
        error_msg = "LLM response did not contain a valid FUNCTION_CALL line."
        print(f"WARN (Perception): {error_msg} Response: {llm_response_text}")

    return PerceptionOutput(
        llm_raw_response=llm_response_text,
        parsed_call=parsed_call,
        is_final_answer=is_final,
        error=error_msg
    )

def structure_tool_parameters(
    parsed_call: ParsedFunctionCall,
    tool_schema: Dict[str, Any],
    recipient_email: str # Needed specifically for send_gmail
) -> StructuredParams:
    """Converts raw string parameters to a typed dictionary based on the tool schema."""
    arguments: Dict[str, Any] = {}
    schema_properties = tool_schema.get('properties', {})
    current_params = list(parsed_call.raw_params) # Operate on a copy
    func_name = parsed_call.func_name

    print(f"DEBUG (Perception): Structuring params for {func_name}. Schema props: {schema_properties}. Raw params: {current_params}")

    try:
        # Special handling for send_gmail
        if func_name == "send_gmail":
            if len(current_params) == 0:
                 raise ValueError(f"No parameters provided for send_gmail. Expected subject and body details.")
            arguments['subject'] = str(current_params.pop(0))
            if current_params:
                arguments['body'] = "|".join(str(p) for p in current_params)
            else:
                arguments['body'] = ""
                print("WARN (Perception): Only one parameter provided for send_gmail. Using it as subject and setting body to empty.")
            arguments['recipient'] = recipient_email # Set recipient from env var/state
            current_params = [] # Mark params as consumed
            print(f"DEBUG (Perception): Special handling for send_gmail. Arguments: {arguments}")
        else:
            # Generic handling for other tools based on schema properties
            for param_name, param_info in schema_properties.items():
                if not current_params:
                    # Check if parameter is required (usually implied if listed)
                    if param_info.get('required', True): # Assume required if not specified
                         raise ValueError(f"Missing required parameter '{param_name}' for tool '{func_name}'")
                    else:
                        # Handle optional parameters if needed (not typical in this setup)
                        continue

                value_str = current_params.pop(0)
                param_type = param_info.get('type', 'string')
                print(f"DEBUG (Perception): Processing param '{param_name}'. Raw value: '{value_str}', Target type: {param_type}")

                if param_type == 'integer':
                    arguments[param_name] = int(value_str)
                elif param_type == 'number':
                    arguments[param_name] = float(value_str)
                elif param_type == 'array':
                    # Expecting comma-separated values, optionally within brackets
                    cleaned_value = value_str.strip('[] ')
                    if cleaned_value:
                        value_list = [v.strip() for v in cleaned_value.split(',')] 
                    else:
                        value_list = []
                    
                    # Determine item type (simplistic: assume int if 'integer' in schema, else string)
                    items_info = param_info.get('items', {})
                    items_type = items_info.get('type', 'string') 
                    
                    try:
                        if items_type == 'integer':
                             arguments[param_name] = [int(x) for x in value_list]
                        elif items_type == 'number':
                             arguments[param_name] = [float(x) for x in value_list]
                        else: # Default to string items
                             arguments[param_name] = [str(x) for x in value_list]
                    except ValueError as e:
                        print(f"WARN (Perception): Could not convert all array items for '{param_name}' to {items_type}. Error: {e}. Keeping as strings.")
                        arguments[param_name] = [str(x) for x in value_list] # Fallback
                elif param_type == 'string':
                     arguments[param_name] = str(value_str)
                else:
                    print(f"WARN (Perception): Unknown parameter type '{param_type}' for {param_name}. Treating as string.")
                    arguments[param_name] = str(value_str)
        
        # Ensure recipient is set for send_gmail again (redundant but safe)
        if func_name == "send_gmail":
            arguments['recipient'] = recipient_email

        # Check for unused parameters provided by LLM
        if current_params:
            print(f"WARN (Perception): Unused parameters provided by LLM for {func_name}: {current_params}")

        print(f"DEBUG (Perception): Final structured arguments for {func_name}: {arguments}")
        return StructuredParams(arguments=arguments)

    except ValueError as e:
        print(f"ERROR (Perception): Parameter mismatch/conversion error for {func_name}: {e}")
        raise # Re-raise to be caught by the main loop
    except Exception as e:
        print(f"ERROR (Perception): Unexpected error structuring parameters for {func_name}: {e}")
        raise # Re-raise

def format_tool_result(mcp_result: Any) -> str:
    """Formats the result from MCP tool call into a string for memory/LLM context."""
    print(f"DEBUG (Perception): Formatting MCP result: {mcp_result} (Type: {type(mcp_result)})")
    result_str = "Error: Result object structure not recognized."
    try:
        if hasattr(mcp_result, 'content'):
            content = mcp_result.content
            print(f"DEBUG (Perception): Result has 'content' attribute: {content}")
            if isinstance(content, list):
                # Handle list of content items (like TextContent)
                processed_items = []
                for item in content:
                    if hasattr(item, 'text'):
                         processed_items.append(str(item.text))
                    elif isinstance(item, (str, int, float)): # Handle primitive types directly in list
                        processed_items.append(str(item))
                    else:
                         processed_items.append(str(item)) # Fallback
                # Format based on content type
                if all(item.isdigit() or (item.startswith('-') and item[1:].isdigit()) for item in processed_items):
                    # Looks like a list of integers
                    result_str = f"[{','.join(processed_items)}]"
                else:
                     # General list formatting
                    result_str = f"[{', '.join(processed_items)}]"
            elif hasattr(content, 'text'): # Single content item with text
                result_str = str(content.text)
            elif isinstance(content, (str, int, float)): # Primitive content
                result_str = str(content)
            else: # Fallback for other content types
                 result_str = str(content)
        # Handle cases where the result is directly a primitive or a simple dict/list
        elif isinstance(mcp_result, (str, int, float)):
            result_str = str(mcp_result)
        elif isinstance(mcp_result, list):
             # Similar list processing as above
             processed_items = [str(item) for item in mcp_result]
             if all(item.isdigit() or (item.startswith('-') and item[1:].isdigit()) for item in processed_items):
                 result_str = f"[{','.join(processed_items)}]"
             else:
                 result_str = f"[{', '.join(processed_items)}]"
        elif isinstance(mcp_result, dict):
            # Basic dictionary representation
            result_str = str(mcp_result)
        else:
            # Fallback for unexpected result types
             result_str = str(mcp_result)
             print(f"WARN (Perception): Formatting fallback for result type {type(mcp_result)}")

    except Exception as e:
        print(f"ERROR (Perception): Failed to format tool result: {e}. Raw result: {mcp_result}")
        result_str = f"Error formatting result: {e}"

    print(f"DEBUG (Perception): Formatted result string: {result_str}")
    return result_str
