import os
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
import asyncio
from google import genai
import traceback

# Load environment variables
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY not found in environment variables")
client = genai.Client(api_key=api_key)

# Global state
max_iterations = 10
last_response = None
iteration = 0
iteration_response = []

async def generate_with_timeout(client, prompt, timeout=30):
    """Generate content with a timeout"""
    try:
        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(None, 
                lambda: client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt
                )
            ),
            timeout=timeout
        )
        return response
    except Exception as e:
        print(f"Error in LLM generation: {str(e)}")
        traceback.print_exc()
        raise

def reset_state():
    """Reset global state"""
    global last_response, iteration, iteration_response
    last_response = None
    iteration = 0
    iteration_response = []

async def execute_tool(session, command, arguments):
    """Execute a tool with proper error handling"""
    try:
        print(f"Executing: {command} with {arguments}")
        result = await session.call_tool(command, arguments=arguments)
        return result
    except Exception as e:
        print(f"Error executing {command}: {str(e)}")
        traceback.print_exc()
        raise

async def main():
    global iteration, last_response, iteration_response
    reset_state()
    
    try:
        # Connect to MCP server
        server_params = StdioServerParameters(
            command="python",
            args=["example2-3.py"]
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # Get tools description
                tools_result = await session.list_tools()
                tools = tools_result.tools
                tools_description = []
                tool_map = {}  # Map tool names to their definitions
                for tool in tools:
                    params = tool.inputSchema.get('properties', {})
                    param_str = ', '.join(f"{k}: {v.get('type', 'any')}" for k, v in params.items())
                    desc = f"{tool.name}({param_str}) - {tool.description}"
                    tools_description.append(desc)
                    tool_map[tool.name] = tool
                tools_description = "\n".join(tools_description)

                system_prompt = f"""You are a math agent solving problems in iterations. You have access to various mathematical tools.

Available tools:
{tools_description}

You must respond with EXACTLY ONE line in one of these formats (no additional text):
1. For function calls:
   FUNCTION_CALL: function_name|param1|param2|...

2. For final answers:
   FINAL_ANSWER: [number]

Follow these steps in order:
1. Convert the input string to ASCII values
2. Calculate the exponential sum:
   - For each ASCII value x, calculate e^x
   - Sum all the exponential values
   - Format exactly as: FINAL_ANSWER: [sum]
3. Create a visual display of the result:
   - First prepare a graphics environment
   - Next draw a rectangular frame (coordinates should be 1000,400,1600,800)
   - Finally display the complete FINAL_ANSWER: [sum] format in the frame

Important:
- Each step must complete before starting the next
- The frame must be drawn before adding text
- When displaying text, use the complete FINAL_ANSWER: [sum] format
- Use appropriate tools from the available list

Example:
For ASCII values [65, 66]:
Calculate e^65 + e^66 = 1.234e+28
Respond: FINAL_ANSWER: [1.234e+28]

DO NOT include any explanations or additional text.
Your response should be exactly ONE line."""

                query = "Calculate ASCII values of INDIA, find sum of their exponentials, and create a visual display of the result."
                calculation_state = {
                    "ascii_values": None,
                    "final_answer": None,
                    "visualization_steps": []
                }
                steps_done = []

                while iteration < max_iterations:
                    # Determine next required action
                    next_action = None
                    if calculation_state["ascii_values"] is None:
                        next_action = "Calculate ASCII values for 'INDIA'"
                    elif calculation_state["final_answer"] is None and calculation_state["ascii_values"]:
                        values = calculation_state["ascii_values"]
                        exp_terms = " + ".join(f"e^{x}" for x in values)
                        next_action = f"Calculate sum of exponentials: {exp_terms} and provide as FINAL_ANSWER: [sum]"
                    elif calculation_state["final_answer"] and len(calculation_state["visualization_steps"]) < 3:
                        next_action = "Continue with next visualization step"

                    # Prepare current query with state and next action
                    current_query = f"{query}\n\nCompleted steps:\n" + "\n".join(steps_done)
                    if next_action:
                        current_query += f"\n\nNext required action: {next_action}"

                    # Get agent's response
                    print(f"\n--- Iteration {iteration + 1} ---")
                    print("Preparing to generate LLM response...")
                    response = await generate_with_timeout(client, f"{system_prompt}\n\nQuery: {current_query}")
                    response_text = response.text.strip().split('\n')[0]
                    print(f"LLM Response: {response_text}")

                    if response_text.startswith("FUNCTION_CALL:"):
                        _, function_info = response_text.split(":", 1)
                        command, *params = [p.strip() for p in function_info.split("|")]
                        
                        print(f"\nDEBUG: Raw function info: {function_info}")
                        print(f"DEBUG: Split parts: {[command] + params}")
                        print(f"DEBUG: Function name: {command}")
                        print(f"DEBUG: Raw parameters: {params}")
                        
                        # Validate tool exists
                        if command not in tool_map:
                            print(f"DEBUG: Available tools: {[t.name for t in tools]}")
                            print(f"Unknown tool: {command}")
                            continue
                            
                        tool = tool_map[command]
                        print(f"DEBUG: Found tool: {tool.name}")
                        print(f"DEBUG: Tool schema: {tool.inputSchema}")
                        
                        # Skip if step already done
                        step_key = f"FUNCTION_CALL: {command}"
                        if any(step.startswith(step_key) for step in steps_done):
                            print(f"Skipping already completed step: {command}")
                            continue

                        try:
                            # Prepare arguments using correct tool schema
                            arguments = {}
                            if params:
                                schema_props = tool.inputSchema.get('properties', {})
                                print(f"DEBUG: Schema properties: {schema_props}")
                                
                                for (param_name, param_info), param_value in zip(schema_props.items(), params):
                                    param_type = param_info.get('type', 'string')
                                    print(f"DEBUG: Converting parameter {param_name} with value {param_value} to type {param_type}")
                                    
                                    if param_type == 'integer':
                                        arguments[param_name] = int(param_value)
                                    elif param_type == 'number':
                                        arguments[param_name] = float(param_value)
                                    else:
                                        arguments[param_name] = str(param_value)

                            print(f"DEBUG: Final arguments: {arguments}")
                            print(f"DEBUG: Calling tool {command}")
                            
                            # Execute the tool
                            result = await execute_tool(session, command, arguments)
                            print(f"DEBUG: Raw result: {result}")
                            
                            # Process result based on current state
                            if calculation_state["ascii_values"] is None and "string" in arguments:
                                print("DEBUG: Processing ASCII calculation result")
                                result_text = result.content[0].text if hasattr(result, 'content') else str(result)
                                print(f"DEBUG: Result text: {result_text}")
                                ascii_values = [int(x) for x in result_text.strip('[]').split(',')]
                                calculation_state["ascii_values"] = ascii_values
                                steps_done.append(f"ASCII values calculated: {ascii_values}")
                                print(f"ASCII calculation complete: {ascii_values}")
                            else:
                                # Handle visualization steps
                                print(f"DEBUG: Processing step {len(calculation_state['visualization_steps']) + 1}")
                                
                                # If this is the text step, ensure we use the full FINAL_ANSWER format
                                if len(calculation_state["visualization_steps"]) == 2:
                                    # Modify params to include full FINAL_ANSWER format if it's not already there
                                    if params and not params[0].startswith("FINAL_ANSWER:"):
                                        params = [calculation_state["final_answer"]]
                                        print(f"DEBUG: Using full answer format for text: {params[0]}")
                                
                                calculation_state["visualization_steps"].append(command)
                                steps_done.append(f"Step completed: {command}|{('|'.join(params) if params else '')}")
                                print(f"Step complete: {command}")
                                
                                # Check if all steps are done
                                if len(calculation_state["visualization_steps"]) == 3:
                                    print("=== All steps completed successfully ===")
                                    return

                            await asyncio.sleep(2)  # Wait between steps

                        except Exception as e:
                            print(f"Error in execution: {str(e)}")
                            print(f"DEBUG: Full error traceback:")
                            traceback.print_exc()
                            steps_done.append(f"Error: {str(e)}")
                            break

                    elif response_text.startswith("FINAL_ANSWER:"):
                        print("\nDEBUG: Processing FINAL_ANSWER")
                        if calculation_state["ascii_values"] is None:
                            print("Skipping final answer - ASCII values not calculated yet")
                            continue
                            
                        if calculation_state["final_answer"]:
                            print("Skipping final answer - already provided")
                            continue
                            
                        calculation_state["final_answer"] = response_text
                        steps_done.append(f"Final answer: {response_text}")
                        print(f"Final answer recorded: {response_text}")
                        print(f"DEBUG: State after final answer: {calculation_state}")

                    iteration += 1
                    
                if iteration >= max_iterations:
                    print("=== Maximum iterations reached without completing all steps ===")
                    print("Current state:")
                    print(f"ASCII values: {calculation_state['ascii_values']}")
                    print(f"Final answer: {calculation_state['final_answer']}")
                    print(f"Visualization steps completed: {len(calculation_state['visualization_steps'])}/3")

    except Exception as e:
        print(f"Error in main: {str(e)}")
        traceback.print_exc()
    finally:
        reset_state()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        traceback.print_exc()
    
    
