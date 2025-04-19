import os
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
import asyncio
from google import genai
from concurrent.futures import TimeoutError
from functools import partial

# Load environment variables from .env file
load_dotenv()

# Access your API key and initialize Gemini client correctly
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

# Email configuration
recipient_email = os.getenv("RECIPIENT_EMAIL")
if not recipient_email:
    raise ValueError("RECIPIENT_EMAIL environment variable is not set")

max_iterations = 6
last_response = None
iteration = 0
iteration_response = []

async def generate_with_timeout(client, prompt, timeout=10):
    """Generate content with a timeout"""
    print("Starting LLM generation...")
    try:
        # Convert the synchronous generate_content call to run in a thread
        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(
                None, 
                lambda: client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt
                )
            ),
            timeout=timeout
        )
        print("LLM generation completed")
        return response
    except TimeoutError:
        print("LLM generation timed out!")
        raise
    except Exception as e:
        print(f"Error in LLM generation: {e}")
        raise

def reset_state():
    """Reset all global variables to their initial state"""
    global last_response, iteration, iteration_response
    last_response = None
    iteration = 0
    iteration_response = []

async def main():
    reset_state()  # Reset at the start of main
    print("Starting main execution...")
    try:
        # Create a single MCP server connection
        print("Establishing connection to MCP server...")
        server_params = StdioServerParameters(
            command="python",
            args=["example2-3.py"]
        )

        async with stdio_client(server_params) as (read, write):
            print("Connection established, creating session...")
            async with ClientSession(read, write) as session:
                print("Session created, initializing...")
                await session.initialize()
                
                # Get available tools
                print("Requesting tool list...")
                tools_result = await session.list_tools()
                tools = tools_result.tools
                print(f"Successfully retrieved {len(tools)} tools")

                # Create system prompt with available tools
                print("Creating system prompt...")
                print(f"Number of tools: {len(tools)}")
                
                try:
                    # First, let's inspect what a tool object looks like
                    # if tools:
                    #     print(f"First tool properties: {dir(tools[0])}")
                    #     print(f"First tool example: {tools[0]}")
                    
                    tools_description = []
                    for i, tool in enumerate(tools):
                        try:
                            # Get tool properties
                            params = tool.inputSchema
                            desc = getattr(tool, 'description', 'No description available')
                            name = getattr(tool, 'name', f'tool_{i}')
                            
                            # Format the input schema in a more readable way
                            if 'properties' in params:
                                param_details = []
                                for param_name, param_info in params['properties'].items():
                                    param_type = param_info.get('type', 'unknown')
                                    param_details.append(f"{param_name}: {param_type}")
                                params_str = ', '.join(param_details)
                            else:
                                params_str = 'no parameters'

                            tool_desc = f"{i+1}. {name}({params_str}) - {desc}"
                            tools_description.append(tool_desc)
                            print(f"Added description for tool: {tool_desc}")
                        except Exception as e:
                            print(f"Error processing tool {i}: {e}")
                            tools_description.append(f"{i+1}. Error processing tool")
                    
                    tools_description = "\n".join(tools_description)
                    print("Successfully created tools description")
                except Exception as e:
                    print(f"Error creating tools description: {e}")
                    tools_description = "Error loading tools"
                
                print("Created system prompt...")
                
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

EXAMPLE:

For input: "What is the sum of five and three?"

Parsed values: 5, 3  
Operation: add  
Reasoning steps: ["parsing", "arithmetic", "formatting"]  
Final output:  
`FUNCTION_CALL: add|5|3`

After receiving the result (8), you would:  
`FUNCTION_CALL: send_email|Sum of 5 and 3 is 8.`

Make sure to complete all steps in sequence and stop after sending the email.
"""

                query = """Calculate ASCII values for INDIA, find sum of their exponentials, and send the result via email"""
                print("Starting iteration loop...")
                
                # Use global iteration variables
                global iteration, last_response
                
                while iteration < max_iterations:
                    print(f"\n--- Iteration {iteration + 1} ---")
                    if last_response is None:
                        current_query = query
                    else:
                        current_query = current_query + "\n\n" + " ".join(iteration_response)
                        current_query = current_query + "  What should I do next?"

                    # Get model's response with timeout
                    print("Preparing to generate LLM response...")
                    prompt = f"""{system_prompt}

Available tools:
{tools_description}

Query: {current_query}"""
                    try:
                        response = await generate_with_timeout(client, prompt)
                        response_text = response.text.strip()
                        print(f"LLM Response: {response_text}")
                        
                        # Find the FUNCTION_CALL line in the response
                        for line in response_text.split('\n'):
                            line = line.strip()
                            if line.startswith("FUNCTION_CALL:"):
                                response_text = line
                                break
                        
                    except Exception as e:
                        print(f"Failed to get LLM response: {e}")
                        break


                    if response_text.startswith("FUNCTION_CALL:"):
                        _, function_info = response_text.split(":", 1)
                        parts = [p.strip() for p in function_info.split("|")]
                        func_name, params = parts[0], parts[1:]
                        
                        print(f"\nDEBUG: Raw function info: {function_info}")
                        print(f"DEBUG: Split parts: {parts}")
                        print(f"DEBUG: Function name: {func_name}")
                        print(f"DEBUG: Raw parameters: {params}")

                        # Handle explicit error call from LLM
                        if func_name == "error":
                            error_message = " ".join(params) if params else "Unknown error from LLM"
                            print(f"LLM returned an error: {error_message}")
                            iteration_response.append(f"LLM Error: {error_message}")
                            break # Stop processing
                        
                        try:
                            # Find the matching tool to get its input schema
                            tool = next((t for t in tools if t.name == func_name), None)
                            if not tool:
                                print(f"DEBUG: Available tools: {[t.name for t in tools]}")
                                raise ValueError(f"Unknown tool: {func_name}")

                            print(f"DEBUG: Found tool: {tool.name}")
                            print(f"DEBUG: Tool schema: {tool.inputSchema}")

                            # Prepare arguments according to the tool's input schema
                            arguments = {}
                            schema_properties = tool.inputSchema.get('properties', {})
                            print(f"DEBUG: Schema properties: {schema_properties}")

                            # Use a copy of params for iteration
                            current_params = list(params)

                            # Handle send_gmail specifically to ensure correct parameter mapping
                            if func_name == "send_gmail":
                                num_params = len(current_params)
                                if num_params == 0:
                                     raise ValueError(f"No parameters provided for send_gmail. Expected subject and body details.")
                                
                                # First param is subject
                                arguments['subject'] = str(current_params.pop(0))
                                
                                # If more params exist, join them for the body, otherwise use empty string
                                if current_params: # Check if list is not empty after popping subject
                                    arguments['body'] = "|".join(str(p) for p in current_params)
                                else:
                                    arguments['body'] = "" # Use empty body if only subject was provided
                                    print("WARN: Only one parameter provided for send_gmail. Using it as subject and setting body to empty.")

                                arguments['recipient'] = recipient_email # Set recipient from env var
                                print(f"DEBUG: Special handling for send_gmail. Arguments: {arguments}")
                                current_params = [] # Clear params as they are now used
                            else:
                                # Original logic for other tools
                                for param_name, param_info in schema_properties.items():
                                    if not current_params:  # Check if we have enough parameters
                                        raise ValueError(f"Not enough parameters provided for {func_name}")
                                        
                                    value = current_params.pop(0)  # Get and remove the first parameter
                                    param_type = param_info.get('type', 'string')
                                    
                                    print(f"DEBUG: Converting parameter {param_name} with value {value} to type {param_type}")
                                    
                                    # Convert the value to the correct type based on the schema
                                    if param_type == 'integer':
                                        arguments[param_name] = int(value)
                                    elif param_type == 'number':
                                        arguments[param_name] = float(value)
                                    elif param_type == 'array':
                                        # Handle array input
                                        if isinstance(value, str):
                                            # Simple split logic, might need refinement for complex arrays
                                            value_list = [v.strip() for v in value.strip('[]').split(',')]
                                        else: # Assuming it might already be a list somehow (less likely)
                                            value_list = value
                                        # Attempt conversion based on array item type if specified (optional)
                                        # For now, assume array of integers as per previous logic
                                        try:
                                            arguments[param_name] = [int(x) for x in value_list]
                                        except ValueError:
                                             print(f"WARN: Could not convert all items in array to int for {param_name}. Keeping as strings.")
                                             arguments[param_name] = [str(x) for x in value_list] # Fallback to strings
                                    else:
                                        arguments[param_name] = str(value)
                            
                            # Ensure recipient is set for send_gmail, even if handled above (redundant but safe)
                            if func_name == "send_gmail":
                                arguments['recipient'] = recipient_email
                                
                            # Check if any parameters were unexpectedly remaining
                            if current_params:
                                print(f"WARN: Unused parameters provided by LLM for {func_name}: {current_params}")


                            print(f"DEBUG: Final arguments before call: {arguments}")
                            print(f"DEBUG: Calling tool {func_name}")
                            
                            # Remove the explicit recipient setting here, as it's handled above
                            # arguments['recipient'] = recipient_email 
                            
                            result = await session.call_tool(func_name, arguments=arguments)
                            print(f"DEBUG: Raw result: {result}")
                            
                            # Get the full result content
                            if hasattr(result, 'content'):
                                print(f"DEBUG: Result has content attribute")
                                # Handle multiple content items
                                if isinstance(result.content, list):
                                    # Convert all text results to their appropriate type
                                    iteration_result = []
                                    for item in result.content:
                                        text_value = item.text if hasattr(item, 'text') else str(item)
                                        try:
                                            # Try to convert to int if possible
                                            iteration_result.append(int(text_value))
                                        except ValueError:
                                            iteration_result.append(text_value)
                                else:
                                    iteration_result = str(result.content)
                            else:
                                print(f"DEBUG: Result has no content attribute")
                                iteration_result = str(result)
                                
                            print(f"DEBUG: Final iteration result: {iteration_result}")
                            
                            # Format the response based on result type
                            if isinstance(iteration_result, list):
                                if all(isinstance(x, int) for x in iteration_result):
                                    # Corrected comma placement in join
                                    result_str = f"[{','.join(str(x) for x in iteration_result)}]"
                                else:
                                    # Corrected comma placement in join
                                    result_str = f"[{', '.join(iteration_result)}]"
                            else:
                                result_str = str(iteration_result)

                            # Track the operation generically
                            iteration_response.append(f"Result: {result_str}")
                            if "email sent" in str(result_str).lower():
                                break  # End the loop after email is sent

                            last_response = iteration_result

                        except Exception as e:
                            print(f"DEBUG: Tool call failed for {func_name} with args {arguments}")
                            print(f"DEBUG: Error details: {str(e)}")
                            print(f"DEBUG: Error type: {type(e)}")
                            import traceback
                            traceback.print_exc()
                            # Provide clearer feedback to the LLM about the tool failure
                            error_feedback = f"Tool call failed for '{func_name}' with error: {str(e)}"
                            iteration_response.append(error_feedback)
                            # We still break here, as the current logic doesn't support retries within the Python script.
                            # The LLM is expected to handle retries based on its prompt instructions.
                            break

                    elif response_text.startswith("FINAL_ANSWER:"):
                        print("\n=== Warning: Unexpected FINAL_ANSWER format ===")
                        print("The agent should be using email to send results.")
                        break

                    iteration += 1

    except Exception as e:
        print(f"Error in main execution: {e}")
        import traceback
        traceback.print_exc()
    finally:
        reset_state()  # Reset at the end of main

if __name__ == "__main__":
    asyncio.run(main()) 