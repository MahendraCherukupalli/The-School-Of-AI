import asyncio
import yaml
from mcp_servers.multiMCP import MultiMCP
from typing import Optional, Literal

from dotenv import load_dotenv
# from agent.agent_loop import AgentLoop
from agent.agent_loop2 import AgentLoop
from agent.agentSession import AgentSession
from agent.hitl_request import HITLRequest
from pprint import pprint

BANNER = """
──────────────────────────────────────────────────────
🔸  Agentic Query Assistant  🔸
Type your question and press Enter.
Type 'exit' or 'quit' to leave.
──────────────────────────────────────────────────────
"""


async def interactive() -> None:
    print(BANNER)
    print("Loading MCP Servers...")
    try:
        with open("config/mcp_server_config.yaml", "r") as f:
            profile = yaml.safe_load(f)
            mcp_servers_list = profile.get("mcp_servers", [])
            configs = list(mcp_servers_list)
    except FileNotFoundError:
        print("🚨 Error: mcp_server_config.yaml not found. Please ensure the configuration file exists.")
        return
    except yaml.YAMLError as e:
        print(f"🚨 Error parsing mcp_server_config.yaml: {e}")
        return
    except Exception as e:
        print(f"🚨 An unexpected error occurred during MCP config loading: {e}")
        return

    # Initialize MCP + Dispatcher
    multi_mcp = MultiMCP(server_configs=configs)
    try:
        await multi_mcp.initialize()
    except Exception as e:
        print(f"🚨 An unexpected error occurred during MultiMCP initialization: {e}")
        return

    try:
        loop = AgentLoop(
            perception_prompt_path="prompts/perception_prompt.txt",
            decision_prompt_path="prompts/decision_prompt.txt",
            multi_mcp=multi_mcp,
            strategy="exploratory"
        )
    except Exception as e:
        print(f"🚨 An unexpected error occurred during AgentLoop initialization: {e}")
        return

    active_query: Optional[str] = None
    hitl_input_data: Optional[str] = None
    hitl_input_type: Optional[Literal["tool_failure", "plan_failure"]] = None

    while True:
        current_input_query: Optional[str] = None
        if not hitl_input_data:
            user_input = input("🟢 You: ").strip()
            if user_input.lower() in {"exit", "quit"}:
                print("👋 Goodbye!")
                break
            active_query = user_input
            current_input_query = active_query
        else:
            current_input_query = active_query


        if active_query is None :
            print("Logic error: active_query is None. Please restart.")
            break

        print("Processing...")
        response = await loop.run(
            query=active_query,
            hitl_input_data=hitl_input_data,
            hitl_input_type=hitl_input_type
        )

        hitl_input_data = None
        hitl_input_type = None

        if isinstance(response, HITLRequest):
            print(f"ℹ️ Agent requires assistance (Session ID: {response.session_id}, Type: {response.type})")
            print(f"❓ Agent: {response.prompt_to_user}")
            user_hitl_response = input("🔵 Your Input: ").strip()
            
            if user_hitl_response.lower() in {"exit", "quit"}:
                print("👋 Goodbye! (Exited during HITL)")
                loop.current_session = None
                active_query = None
                continue


            hitl_input_data = user_hitl_response
            hitl_input_type = response.type
            continue 
        
        elif isinstance(response, AgentSession):
            print("\n🌟 Agent Task Concluded 🌟")
            if response.state.get("current_step_summary"):
                print(f"▶️ Last Action: {response.state['current_step_summary']}")
            if response.state.get("final_answer"):
                print(f"✅ Final Answer: {response.state['final_answer']}")
            if response.state.get("reasoning_note"):
                print(f"🤔 Reasoning: {response.state['reasoning_note']}")
            # if response.state.get("solution_summary"):
            #      print(f"📄 Summary: {response.state['solution_summary']}")
            else:
                pprint(response.to_json())

            active_query = None
            print("\n──────────────────────────────────────────────────────\n")


        else:
            print(f"🚨 Unexpected response type from AgentLoop: {type(response)}. Please check agent_loop2.py.")
            active_query = None
            print("\n──────────────────────────────────────────────────────\n")

if __name__ == "__main__":
    try:
        asyncio.run(interactive())
    except KeyboardInterrupt:
        print("\n👋 Exiting due to user interruption.")
    except Exception as e:
        print(f"🚨 An unexpected critical error occurred in main: {e}")

