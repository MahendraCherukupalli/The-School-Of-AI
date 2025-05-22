import csv
import time
import yaml
import asyncio
import re
import os
import sys
from pathlib import Path
from agent.agent_loop2 import AgentLoop  # Adjust import as needed
from mcp_servers.multiMCP import MultiMCP
from agent.agentSession import AgentSession
from agent.hitl_request import HITLRequest

# Import the global tool_stats from your tool execution module
from action.executor import tool_stats, extract_data_from_chunk

# CONFIG
QUERY_FILE = "queries.csv"
TOOL_LOG_FILE = "tool_performance_log.csv"
QUERY_RESULT_FILE = "query_results.csv"
SUMMARY_FILE = "simulation_summary.csv"
SLEEP_SECONDS = 30  # Safe for Google APIs; adjust as needed
AUTO_HITL = True  # Set to True to handle common failures automatically
MAX_AUTO_HITL_ATTEMPTS = 2  # Maximum number of auto HITL attempts before asking user
MAX_QUERIES = None  # How many queries to run (set to None for all)
START_INDEX = 0  # Where to start in the query list
FORCE_TOOL_USE = True  # Force agent to use tools even for simple queries
SKIP_COMPLETED = False  # Skip queries already successfully processed
RESET_STATS = True  # Reset tool statistics at the beginning of each run
CLEAR_PREVIOUS_RESULTS = True  # Clear previous result files before starting

# List of available tools from mcp_server_config.yaml
AVAILABLE_TOOLS = """
Math Server Tools: add, subtract, multiply, divide, power, cbrt, factorial, remainder, sin, cos, tan
Document Server Tools: search_stored_documents_rag, convert_webpage_url_into_markdown, extract_pdf
Web Search Tools: duckduckgo_search_results, download_raw_html_from_url
"""

# Custom prompt additions to force tool use
FORCE_TOOL_USE_PERCEPTION_SUFFIX = """
### IMPORTANT TESTING INSTRUCTION:
For the purposes of this simulation exercise, set 'original_goal_achieved' to false in your INITIAL perception.
This will force the agent to use at least one tool for every query.

HOWEVER, after a tool has been used and a valid answer has been found, you SHOULD mark 'original_goal_achieved' as true in subsequent perceptions to allow the agent to complete its task.

In other words:
1. First perception: Always set original_goal_achieved = false
2. After tool use with successful result: Set original_goal_achieved = true when the answer is complete
""" if FORCE_TOOL_USE else ""

FORCE_TOOL_USE_DECISION_SUFFIX = """
### IMPORTANT TESTING INSTRUCTION:
For the purposes of this simulation exercise, ALWAYS use at least one tool in your INITIAL plan.
NEVER use a "CONCLUDE" step immediately as your FIRST step, even for simple queries.

Always create at least one "CODE" step that utilizes a tool from this list of available tools:
{available_tools}

- For any math query (like "What is 2+2?"), use the math server tools like add, subtract, multiply
- For document-related queries, use search_stored_documents_rag
- For web-related queries, use duckduckgo_search_results

IMPORTANT SYNTAX RULES:
1. For math tools (add, subtract, multiply, divide):
   ```python
   result = add(2, 2)  # Correct - use integers for math operations, NO await keyword
   ```

2. For web search tools (duckduckgo_search_results):
   ```python
   result = duckduckgo_search_results(query="your query")  # CORRECT - don't use await
   ```
   OR
   ```python
   result = duckduckgo_search_results("your query")  # CORRECT - don't use await
   ```

3. For document search tools:
   ```python
   result = search_stored_documents_rag(query="your query")  # CORRECT - don't use await
   ```
  
Do NOT use tools that aren't listed above. Never use made-up tools that don't exist.
Do NOT use the await keyword - it's not needed and will cause errors.

AFTER using at least one tool, if you have sufficient information to answer the query, you SHOULD use a CONCLUDE step to provide the final answer.
""".format(available_tools=AVAILABLE_TOOLS) if FORCE_TOOL_USE else ""

def load_queries(filename):
    with open(filename, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)

def save_tool_stats(filename, stats):
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Tool Name", "Calls", "Success", "Failure"])
        for tool, data in stats.items():
            writer.writerow([tool, data["calls"], data["success"], data["fail"]])

def save_query_result(filename, query, plan, result):
    # Check if file exists to write header
    try:
        with open(filename, 'x', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Query", "Plan", "Result"])
    except FileExistsError:
        pass # File already exists, no need to write header

    with open(filename, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # Ensure plan is treated as a single string, handling newlines
        writer.writerow([query, plan, result])

def save_simulation_summary(filename, summary_data):
    """
    Save summary statistics about the simulation run
    """
    headers = ["Total Queries", "Successful", "Failed", "HITL Required", 
              "Auto-HITL Used", "User-HITL Used", "Most Common Error", "Avg Time Per Query"]
    
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerow([
            summary_data.get("total_queries", 0),
            summary_data.get("successful", 0),
            summary_data.get("failed", 0),
            summary_data.get("hitl_required", 0),
            summary_data.get("auto_hitl_used", 0),
            summary_data.get("user_hitl_used", 0),
            summary_data.get("most_common_error", "N/A"),
            summary_data.get("avg_time", "N/A")
        ])

def auto_hitl_response(hitl_request, query):
    """
    Automatically generate HITL responses for common issues
    """
    prompt = hitl_request.prompt_to_user
    error_match = re.search(r"Error:(.*?)(?:\n|$)", prompt, re.DOTALL)
    error_message = error_match.group(1).strip() if error_match else ""
    code_match = re.search(r"--- CODE ---\n(.*?)\n--- END CODE ---", prompt, re.DOTALL)
    code = code_match.group(1).strip() if code_match else ""
    
    # Case 0: No tool found or undefined function
    if "is not defined" in error_message or "name" in error_message and "not defined" in error_message:
        # Try to extract the undefined tool name
        tool_match = re.search(r"name '(\w+)' is not defined", error_message)
        if tool_match:
            undefined_tool = tool_match.group(1)
            if undefined_tool in ["add", "subtract", "multiply", "divide"]:
                return f"Use this tool from the math MCP server: {undefined_tool}(a, b)"
            else:
                return f"Use only available tools like: add, subtract, multiply, divide, search_stored_documents_rag, or duckduckgo_search_results. Do not use '{undefined_tool}'."
        return "Use only available tools from the math, documents, or web search servers. Check your tool name is correct."
    
    # Case 1: Type conversion error
    if "can't multiply sequence by non-int" in error_message or "must be " in error_message and " not " in error_message or "expected" in error_message and "got" in error_message:
        # Try to identify type conversion issues
        if "multiply" in code:
            return "Make sure to use integers for multiply, not strings. Change multiply(\"4\", \"5\") to multiply(4, 5)."
        elif "add" in code:
            return "Make sure to use integers for add, not strings. Change add(\"2\", \"2\") to add(2, 2)."
        elif "subtract" in code:
            return "Make sure to use integers for subtract, not strings. Change subtract(\"5\", \"3\") to subtract(5, 3)."
        elif "divide" in code:
            return "Make sure to use integers or floats for divide, not strings. Change divide(\"10\", \"2\") to divide(10, 2)."
        else:
            return "There's a type mismatch in your code. Make sure you're using the correct data types for function arguments (integers for math operations, not strings)."
    
    # Case 2: search_stored_documents with wrong format
    if "search_stored_documents" in code and "input=" in code:
        corrected_code = code.replace("input={", "").replace("}", "")
        return f"Try this: {corrected_code}"
    
    # Case 3: search_stored_documents_rag with wrong format
    if "search_stored_documents_rag" in code and "input=" in code:
        corrected_code = code.replace("input={", "").replace("}", "")
        return f"Try this: {corrected_code}"
    
    # Case 4: Too many functions
    if "Too many functions" in error_message:
        return "Process one URL at a time instead of all at once"
    
    # Case 5: Wrong argument format for any function
    if "validation error" in error_message:
        return "The function requires simple positional arguments, not a dictionary"
    
    # Case 6: Invalid await expression
    if "can't be used in 'await' expression" in error_message or "object str can't be used in 'await'" in error_message:
        # Extract the tool being used with await
        await_match = re.search(r"await\s+([^\(]+)\(", code)
        if await_match:
            tool_name = await_match.group(1).strip()
            # Generate corrected code without await
            corrected_code = code.replace(f"await {tool_name}", tool_name)
            return f"Don't use the await keyword. Try this instead:\n{corrected_code}"
        else:
            return "Remove all await keywords from your code. Just use duckduckgo_search_results directly without await."
    
    # Case 7: Tool not found or module issue
    if "ModuleNotFoundError" in error_message or "ImportError" in error_message:
        return "Use only built-in tools like add, subtract, search_stored_documents_rag, or duckduckgo_search_results. Do not try to import external modules."
    
    # Case 8: Web search related issues
    if ("Find" in query and "news" in query) or ("latest" in query and "news" in query) or ("search" in query.lower()):
        if "duckduckgo_search_results" in code:
            # Remove await if present
            corrected_code = code.replace("await ", "")
            # Fix quotes if needed
            corrected_code = corrected_code.replace('""', '"')
            return f"Try this code without the await keyword:\n{corrected_code}"
        else:
            return "For web search queries, use the duckduckgo_search_results tool without the await keyword. Example: result = duckduckgo_search_results(\"latest AI news\")"
    
    # Case 9: Math operation on simple query
    if any(x in query.lower() for x in ["what is", "calculate", "compute", "how much", "sum of", "product of"]) and any(x in query for x in ["+", "-", "*", "/"]):
        if "+" in query:
            return "Use the add tool for this math operation. For example: result = add(2, 2)"
        elif "-" in query:
            return "Use the subtract tool for this math operation. For example: result = subtract(5, 3)"
        elif "*" in query:
            return "Use the multiply tool for this math operation. For example: result = multiply(4, 5)"
        elif "/" in query:
            return "Use the divide tool for this math operation. For example: result = divide(10, 2)"
        else:
            return "Use one of the math tools (add, subtract, multiply, divide) for this calculation."
    
    # Fallback
    return "Please try a different approach. Use one of these tools: add, subtract, multiply, divide, search_stored_documents_rag, or duckduckgo_search_results. Do NOT use the await keyword."

def get_already_processed_queries():
    """Read the query_results.csv file to get a list of queries that have already been processed"""
    processed_queries = set()
    try:
        if os.path.exists(QUERY_RESULT_FILE):
            with open(QUERY_RESULT_FILE, newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader)  # Skip header
                for row in reader:
                    if row and len(row) > 0:
                        processed_queries.add(row[0])
            print(f"Found {len(processed_queries)} previously processed queries")
    except Exception as e:
        print(f"Error reading existing results: {e}")
    return processed_queries

def reset_tool_statistics():
    """Reset the global tool_stats dictionary"""
    global tool_stats
    # Create a backup of previous stats
    if os.path.exists(TOOL_LOG_FILE):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_file = f"{os.path.splitext(TOOL_LOG_FILE)[0]}_{timestamp}.csv"
        try:
            with open(TOOL_LOG_FILE, 'r') as src, open(backup_file, 'w') as dst:
                dst.write(src.read())
            print(f"Backed up previous tool statistics to {backup_file}")
        except Exception as e:
            print(f"Failed to backup tool statistics: {e}")
    
    # Reset the stats
    tool_stats.clear()
    print("Tool statistics reset")

def clear_previous_results():
    """Clear previous result files before starting a new simulation run"""
    files_to_clear = [QUERY_RESULT_FILE, SUMMARY_FILE]
    
    for file in files_to_clear:
        if os.path.exists(file):
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_file = f"{os.path.splitext(file)[0]}_{timestamp}.csv"
            try:
                # Backup the file
                with open(file, 'r') as src, open(backup_file, 'w') as dst:
                    dst.write(src.read())
                # Delete the original file
                os.remove(file)
                print(f"Backed up and cleared {file}")
            except Exception as e:
                print(f"Error clearing {file}: {e}")

async def run_simulator():
    # Initialize tracking metrics
    summary_data = {
        "total_queries": 0,
        "successful": 0,
        "failed": 0,
        "hitl_required": 0,
        "auto_hitl_used": 0,
        "user_hitl_used": 0,
        "errors": {},
        "start_time": time.time()
    }
    
    # Create results directory if it doesn't exist
    results_dir = "simulation_results"
    os.makedirs(results_dir, exist_ok=True)
    
    # Reset tool statistics if enabled
    if RESET_STATS:
        reset_tool_statistics()
    
    # Clear previous results if enabled
    if CLEAR_PREVIOUS_RESULTS:
        clear_previous_results()

    print(f"Loading queries from {QUERY_FILE}...")
    queries = load_queries(QUERY_FILE)
    print(f"Loaded {len(queries)} queries.")

    # Initialize MCP Servers
    print("Initializing MCP Servers...")
    try:
        with open("config/mcp_server_config.yaml", "r") as f:
            profile = yaml.safe_load(f)
            mcp_servers_list = profile.get("mcp_servers", [])
            configs = list(mcp_servers_list)
    except FileNotFoundError:
        print("🚨 Error: mcp_server_config.yaml not found.")
        return
    except yaml.YAMLError as e:
        print(f"🚨 Error parsing mcp_server_config.yaml: {e}")
        return

    multi_mcp = MultiMCP(server_configs=configs)
    try:
        await multi_mcp.initialize()
        print("✅ MCP servers initialized successfully")
    except Exception as e:
        print(f"🚨 An unexpected error occurred during MultiMCP initialization: {e}")
        return

    # Initialize AgentLoop
    try:
        # Load prompt templates and add suffix if FORCE_TOOL_USE is enabled
        perception_path = "prompts/perception_prompt.txt"
        decision_path = "prompts/decision_prompt.txt"
        
        perception_prompt = None
        decision_prompt = None
        
        if FORCE_TOOL_USE:
            # Read original prompts
            with open(perception_path, 'r', encoding='utf-8') as f:
                perception_prompt = f.read() + FORCE_TOOL_USE_PERCEPTION_SUFFIX
            
            with open(decision_path, 'r', encoding='utf-8') as f:
                decision_prompt = f.read() + FORCE_TOOL_USE_DECISION_SUFFIX
                
            # Create temporary prompt files
            perception_path = "prompts/perception_prompt_sim.txt"
            decision_path = "prompts/decision_prompt_sim.txt"
            
            with open(perception_path, 'w', encoding='utf-8') as f:
                f.write(perception_prompt)
                
            with open(decision_path, 'w', encoding='utf-8') as f:
                f.write(decision_prompt)
            
            print("Created modified prompts to force tool usage")
        
        loop = AgentLoop(
            perception_prompt_path=perception_path,
            decision_prompt_path=decision_path,
            multi_mcp=multi_mcp,
            strategy="exploratory"
        )
    except Exception as e:
        print(f"🚨 An unexpected error occurred during AgentLoop initialization: {e}")
        return

    print("Starting simulation...")

    # Configure which queries to run
    end_index = min(START_INDEX + MAX_QUERIES, len(queries)) if MAX_QUERIES else len(queries)
    queries_to_run = queries[START_INDEX:end_index]
    print(f"Will process {len(queries_to_run)} queries from index {START_INDEX} to {end_index-1}")
    
    # Skip already processed queries if enabled
    already_processed = set()
    if SKIP_COMPLETED:
        already_processed = get_already_processed_queries()
        print(f"Will skip {len(already_processed.intersection([q['Query'] for q in queries_to_run]))} already processed queries")

    for i, query_data in enumerate(queries_to_run):
        query = query_data["Query"]
        
        # Skip if already processed and SKIP_COMPLETED is True
        if SKIP_COMPLETED and query in already_processed:
            print(f"\n--- Skipping Query {i+1}/{len(queries_to_run)}: {query} (already processed) ---")
            continue
            
        query_start_time = time.time()
        print(f"\n--- Running Query {i+1}/{len(queries_to_run)}: {query} ---")
        summary_data["total_queries"] += 1

        current_query_finished = False
        hitl_input_data = None
        hitl_input_type = None
        hitl_interaction_summary = []
        auto_hitl_attempts = 0  # Track number of auto HITL attempts for current query

        while not current_query_finished:
            try:
                # Run the agent loop for the query
                response = await loop.run(
                    query=query,
                    hitl_input_data=hitl_input_data,
                    hitl_input_type=hitl_input_type
                )

                # Reset HITL inputs after potentially using them
                hitl_input_data = None
                hitl_input_type = None
                auto_hitl_attempts = 0  # Reset counter on successful step

                # Check the response type
                if isinstance(response, AgentSession):
                    # Agent completed the task (either directly or after HITL)
                    final_answer = response.state.get("final_answer", "N/A")

                    # --- Construct the detailed plan text for CSV ---
                    plan_details = []
                    if hitl_interaction_summary:
                         plan_details.append("--- Human-In-The-Loop Interaction(s) ---")
                         plan_details.extend(hitl_interaction_summary)
                         plan_details.append("-------------------------------------")
                         plan_details.append("Final Agent Outcome:")

                    if response.plan_versions:
                         # If there's a final plan after all interactions, include it
                         plan_details.append("Final Plan:")
                         plan_details.extend(response.plan_versions[-1]["plan_text"])
                    elif response.state.get("original_goal_achieved") and response.perception:
                         # If the goal was achieved by initial perception and no plan was needed/generated
                         if not hitl_interaction_summary: # Only add if no HITL occurred first
                              plan_details.append("Answered by initial perception/memory")
                         else: # If HITL occurred, but perception somehow finalized it after that
                              plan_details.append("Answer finalized by perception after HITL")
                              plan_details.append(f"Perception Reasoning: {response.perception.reasoning}")
                    elif not hitl_interaction_summary:
                         # Fallback for scenarios with no HITL, no plan, and no perception answer
                         plan_details.append("N/A (No explicit plan or initial perception answer)")

                    final_plan_text = "\n".join(plan_details)
                    # --- End of plan text construction ---

                    save_query_result(QUERY_RESULT_FILE, query, final_plan_text, final_answer)
                    print(f"Query {i+1} completed in {time.time() - query_start_time:.2f} seconds. Result logged.")
                    current_query_finished = True # This query is done
                    summary_data["successful"] += 1

                elif isinstance(response, HITLRequest):
                    # Agent requires Human-In-The-Loop input
                    summary_data["hitl_required"] += 1
                    print(f"Query {i+1} triggered HITL: {response.prompt_to_user}")

                    # Log the agent's request
                    hitl_interaction_summary.append(f"Agent Prompt ({response.type}): {response.prompt_to_user}")

                    # Check if we should use AUTO_HITL or ask user
                    if AUTO_HITL and auto_hitl_attempts < MAX_AUTO_HITL_ATTEMPTS:
                        # Generate automatic response
                        user_hitl_response = auto_hitl_response(response, query)
                        summary_data["auto_hitl_used"] += 1
                        auto_hitl_attempts += 1
                        print(f"🤖 Auto HITL Attempt {auto_hitl_attempts}/{MAX_AUTO_HITL_ATTEMPTS}: {user_hitl_response}")
                    else:
                        # Ask the user for input
                        if AUTO_HITL and auto_hitl_attempts >= MAX_AUTO_HITL_ATTEMPTS:
                            print(f"⚠️ Auto HITL max attempts reached ({auto_hitl_attempts}). Asking for user input.")
                        user_hitl_response = input("🔵 Your Input for HITL: ").strip()
                        summary_data["user_hitl_used"] += 1
                        auto_hitl_attempts = 0  # Reset auto attempts after user input

                    if user_hitl_response.lower() in {"exit", "quit"}:
                        print("👋 Exiting simulation due to user input.")
                        # Log the partial state and exit
                        partial_plan = "\n".join(hitl_interaction_summary) + "\n-- Simulation interrupted --"
                        save_query_result(QUERY_RESULT_FILE, query, partial_plan, "Simulation exited by user during HITL")
                        # Save tool stats before exiting
                        save_tool_stats(TOOL_LOG_FILE, tool_stats)
                        
                        # Calculate final summary stats
                        summary_data["avg_time"] = f"{(time.time() - summary_data['start_time']) / summary_data['total_queries']:.2f} seconds"
                        if summary_data["errors"]:
                            summary_data["most_common_error"] = max(summary_data["errors"].items(), key=lambda x: x[1])[0]
                        save_simulation_summary(SUMMARY_FILE, summary_data)
                        return # Exit the entire simulation

                    # Log the user's response
                    hitl_interaction_summary.append(f"User Input: {user_hitl_response}")

                    # Set the HITL input data and type for the next loop iteration
                    hitl_input_data = user_hitl_response
                    hitl_input_type = response.type

                else:
                    print(f"Query {i+1} returned unexpected response type: {type(response)}")
                    error_msg = f"Unexpected response type: {type(response)}"
                    save_query_result(QUERY_RESULT_FILE, query, "Unexpected Response Type", str(response))
                    current_query_finished = True  # Treat unexpected response as end of query processing
                    summary_data["failed"] += 1
                    if error_msg in summary_data["errors"]:
                        summary_data["errors"][error_msg] += 1
                    else:
                        summary_data["errors"][error_msg] = 1

            except Exception as e:
                print(f"🚨 Error running query {i+1}: {e}")
                error_msg = str(e)
                # Log the error and any preceding HITL summary
                error_plan = "\n".join(hitl_interaction_summary) + f"\n-- Error during execution --\nError: {error_msg}"
                save_query_result(QUERY_RESULT_FILE, query, error_plan, error_msg)
                current_query_finished = True  # Treat error as end of query processing
                summary_data["failed"] += 1
                if error_msg in summary_data["errors"]:
                    summary_data["errors"][error_msg] += 1
                else:
                    summary_data["errors"][error_msg] = 1

        # Save tool stats after each query is fully processed
        save_tool_stats(TOOL_LOG_FILE, tool_stats)

        if i < len(queries_to_run) - 1:
            print(f"Sleeping for {SLEEP_SECONDS} seconds...")
            time.sleep(SLEEP_SECONDS)

    # Calculate final summary stats
    total_time = time.time() - summary_data["start_time"]
    summary_data["avg_time"] = f"{total_time / summary_data['total_queries']:.2f} seconds"
    if summary_data["errors"]:
        summary_data["most_common_error"] = max(summary_data["errors"].items(), key=lambda x: x[1])[0]
    save_simulation_summary(SUMMARY_FILE, summary_data)
    
    # Clean up temporary prompt files if needed
    if FORCE_TOOL_USE:
        if os.path.exists("prompts/perception_prompt_sim.txt"):
            os.remove("prompts/perception_prompt_sim.txt")
        if os.path.exists("prompts/decision_prompt_sim.txt"):
            os.remove("prompts/decision_prompt_sim.txt")
        print("Cleaned up temporary prompt files")

    print("\nSimulation finished.")
    print(f"Tool performance logged to {TOOL_LOG_FILE}")
    print(f"Query results logged to {QUERY_RESULT_FILE}")
    print(f"Simulation summary logged to {SUMMARY_FILE}")
    print(f"\nSummary: {summary_data['successful']}/{summary_data['total_queries']} queries successful, {summary_data['hitl_required']} required HITL assistance")
    print(f"Auto-HITL used {summary_data['auto_hitl_used']} times, User-HITL used {summary_data['user_hitl_used']} times")


if __name__ == "__main__":
    try:
        asyncio.run(run_simulator())
    except KeyboardInterrupt:
        print("\n👋 Simulation interrupted by user.")
    except Exception as e:
         print(f"🚨 An unexpected critical error occurred in simulator: {e}") 