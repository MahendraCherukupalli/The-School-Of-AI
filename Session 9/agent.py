# agent.py

import asyncio
import yaml
# import re # Only if re is used directly in this file for other purposes
from core.loop import AgentLoop
from core.session import MultiMCP
from core.context import AgentContext
import datetime
import sys
from core.conversation_history import add_conversation, find_conversation_by_question
from core.heuristics import is_valid_agent_output # <<< IMPORTED HERE

def log(stage: str, msg: str):
    """Simple timestamped console logger."""
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] [{stage}] {msg}")

async def main():
    print("🧠 Cortex-R Agent Ready")
    current_session_id = None

    # Initialize conversation history (and FAISS index) at startup if desired
    # This can be done here or ensure_initialized() will be called lazily
    # from core.conversation_history import ensure_initialized
    # ensure_initialized()
    # print("Conversation history and semantic search pre-initialized by agent startup.")


    with open("config/profiles.yaml", "r") as f:
        profile = yaml.safe_load(f)
        mcp_servers_list = profile.get("mcp_servers", [])
        mcp_servers_dict = {server["id"]: server for server in mcp_servers_list}
        
    multi_mcp = MultiMCP(server_configs=mcp_servers_list)
    await multi_mcp.initialize()

    try:
        while True:
            try:
                print(f"DEBUG PRE-INPUT: sys.stdin.closed = {sys.stdin.closed}")
                print(f"DEBUG PRE-INPUT: sys.stdin.isatty() = {sys.stdin.isatty()}")
                sys.stdout.flush()
                
                next_user_query_prompt = "🧑 What do you want to solve today? ('exit' to quit, 'new' for new session) → "
                current_user_query = await asyncio.to_thread(input, next_user_query_prompt)
                current_user_query = current_user_query.strip()

                print(f"DEBUG POST-INPUT: sys.stdin.closed = {sys.stdin.closed}")
                print(f"DEBUG POST-INPUT: sys.stdin.isatty() = {sys.stdin.isatty()}")
                sys.stdout.flush()

            except EOFError:
                print("INFO: EOFError encountered (likely end of input stream). Exiting.")
                break
            except RuntimeError as e:
                if "input(): lost sys.stdin" in str(e) or "set_wakeup_fd only works in main thread" in str(e):
                    print(f"ERROR: Runtime error with input ({e}). Exiting.")
                    break
                raise

            if not current_user_query:
                continue
            if current_user_query.lower() == 'exit':
                print("👋 Exiting agent...")
                break
            if current_user_query.lower() == 'new':
                current_session_id = None
                print("🆕 Starting a new session.")
                continue

            # Check for existing answer before processing
            log("CacheCheck", f"Checking cache for: '{current_user_query}'")
            cached_answer = find_conversation_by_question(current_user_query)
            if cached_answer:
                print(f"\n💡 Cached Answer: {cached_answer}")
                continue

            log("AgentLoop", f"Processing query: '{current_user_query}'")
            effective_input_for_loop = current_user_query 

            while True:
                context = AgentContext(
                    user_input=effective_input_for_loop,
                    session_id=current_session_id,
                    dispatcher=multi_mcp,
                    mcp_server_descriptions=mcp_servers_dict
                )
                agent = AgentLoop(context)
                
                if not current_session_id:
                    current_session_id = context.session_id
                    log("Session", f"Session started/assigned: {current_session_id}")

                result = await agent.run()

                final_answer_text = None
                further_processing_input = None

                if isinstance(result, str):
                    if "FINAL_ANSWER:" in result:
                        final_answer_text = result.split("FINAL_ANSWER:", 1)[1].strip()
                    elif "FURTHER_PROCESSING_REQUIRED:" in result:
                        further_processing_input = result.split("FURTHER_PROCESSING_REQUIRED:", 1)[1].strip()
                    else: # Could be a direct string answer, or a bracketed message
                        final_answer_text = result 
                elif isinstance(result, dict) and "result" in result: 
                    answer_content = result["result"]
                    if "FINAL_ANSWER:" in answer_content:
                        final_answer_text = answer_content.split("FINAL_ANSWER:", 1)[1].strip()
                    elif "FURTHER_PROCESSING_REQUIRED:" in answer_content:
                        further_processing_input = answer_content.split("FURTHER_PROCESSING_REQUIRED:", 1)[1].strip()
                    else: # Could be a direct string answer from dict, or a bracketed message
                        final_answer_text = answer_content
                else:
                    # This will likely be caught by is_successful_final_answer if it's a bracketed message,
                    # or by the prefix check if we add one for this case.
                    final_answer_text = f"Unexpected result format from agent: {result}"

                if final_answer_text is not None:
                    print(f"\n💡 Final Answer: {final_answer_text}")
                    
                    # MODIFIED: Use the imported heuristic function
                    if current_user_query and is_valid_agent_output(final_answer_text): # <<< CALLED HERE
                         log("CacheSave", f"Query processed successfully, and the answer was saved to history.")
                         add_conversation(current_user_query, final_answer_text)
                    else:
                         log("CacheSave", f"Query could not be processed. answer not saved.")
                    break 
                elif further_processing_input is not None:
                    log("AgentLoop", f"Further processing required. New input: '{further_processing_input}'")
                    effective_input_for_loop = further_processing_input
                else: 
                    log("AgentLoop", f"Unknown agent state or empty result. Result: {result}. Breaking to get new user input.")
                    print("\n⚠️ The agent could not determine a final answer or next step.")
                    break 

    except KeyboardInterrupt:
        print("\n👋 Received exit signal (KeyboardInterrupt). Shutting down...")
    except Exception as e: 
        log("FATAL", f"An unexpected error occurred in the main loop: {e}")
        import traceback
        traceback.print_exc() 
    finally:
        log("Shutdown", "Shutting down MCP connections...")
        await multi_mcp.shutdown()
        log("Shutdown", "MCP connections closed. Agent terminated.")

if __name__ == "__main__":
    try:
        # Optional: Pre-initialize conversation history components
        # from core.conversation_history import ensure_initialized
        # ensure_initialized() 
        
        asyncio.run(main())
    except RuntimeError as e:
        if "Event loop is closed" in str(e) and sys.version_info >= (3,9): 
             log("Shutdown", "Event loop was already closed.")
        elif "cannot schedule new futures after shutdown" in str(e):
             log("Shutdown", "Attempted to schedule new futures after shutdown.")
        else:
            # For other RuntimeErrors, it's good to see the error
            log("FATAL", f"RuntimeError during agent execution: {e}")
            raise 
    except Exception as e: 
        log("FATAL", f"An unexpected error occurred at script level: {e}")
        import traceback
        traceback.print_exc()



# Find the ASCII values of characters in INDIA and then return sum of exponentials of those values.
# How much Anmol singh paid for his DLF apartment via Capbridge? 
# What do you know about Don Tapscott and Anthony Williams?
# What is the relationship between Gensol and Go-Auto?
# which course are we teaching on Canvas LMS? "H:\DownloadsH\How to use Canvas LMS.pdf"
# Summarize this page: https://theschoolof.ai/
# What is the log value of the amount that Anmol singh paid for his DLF apartment via Capbridge? 

# What is DLF's stated approach to water conservation?
# Outline the primary recommendations or solutions proposed in the analysis of Tesla's intellectual property and the carbon crisis.
# Summarize this page: https://www.analyticsvidhya.com/blog/2019/08/11-important-model-evaluation-error-metrics/#Confusion_Matrix

# Memory test
# How much Capbridge paid for Anmol sing DLF apartment?