# modules/loop.py

import asyncio
from modules.perception import run_perception
from modules.decision import generate_plan
from modules.action import run_python_sandbox
from modules.model_manager import ModelManager
from core.session import MultiMCP
from core.strategy import select_decision_prompt_path
from core.context import AgentContext
from modules.tools import summarize_tools
import re
import json
import ast # For safe string literal evaluation

try:
    from agent import log
except ImportError:
    import datetime
    def log(stage: str, msg: str):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{now}] [{stage}] {msg}")

# Threshold for deciding whether to embed content directly in the prompt 
# or refer to it via a variable for the sandbox.
MAX_CONTENT_LENGTH_FOR_DIRECT_PROMPT = 20000 # Temporarily increased for testing

class AgentLoop:
    def __init__(self, context: AgentContext):
        self.context = context
        self.mcp = self.context.dispatcher
        self.model = ModelManager()

    async def run(self):
        max_steps = self.context.agent_profile.strategy.max_steps
        original_task_description = self.context.user_input
        self.context.final_answer = None # Ensure it's reset at the start of a run

        for step in range(max_steps):
            print(f"🔁 Step {step+1}/{max_steps} starting...")
            self.context.step = step
            lifelines_left = self.context.agent_profile.strategy.max_lifelines_per_step

            while lifelines_left >= 0:
                user_input_override = getattr(self.context, "user_input_override", None)
                current_input_for_perception_and_plan = user_input_override or original_task_description
                
                perception = await run_perception(context=self.context, user_input=current_input_for_perception_and_plan)
                print(f"[perception] {perception}")

                selected_servers = perception.selected_servers
                selected_tools = self.mcp.get_tools_from_servers(selected_servers)
                
                should_allow_no_tools = False
                if user_input_override and ("Do NOT use any tools" in user_input_override or "Your ONLY task now is to process this `fetched_content`" in user_input_override): 
                    should_allow_no_tools = True
                elif user_input_override and len(getattr(self.context, "full_content_from_last_step", "")) < MAX_CONTENT_LENGTH_FOR_DIRECT_PROMPT and "---BEGIN FETCHED CONTENT---" in user_input_override:
                    should_allow_no_tools = True


                if not selected_tools and not should_allow_no_tools:
                    log("loop", "⚠️ No tools selected by perception and not in a 'no-tool' override state — aborting step.")
                    lifelines_left -= 1
                    log("loop", f"🛠 No tools selected, consuming lifeline. Lifelines left: {lifelines_left}")
                    if lifelines_left < 0:
                        log("loop", "⚠️ No tools selected and no lifelines left. Ending step.")
                        break 
                    continue 

                tool_descriptions = summarize_tools(selected_tools)
                prompt_path = select_decision_prompt_path(
                    planning_mode=self.context.agent_profile.strategy.planning_mode,
                    exploration_mode=self.context.agent_profile.strategy.exploration_mode,
                )

                log("loop", f"DEBUG: Input to generate_plan: {current_input_for_perception_and_plan!r}")
                plan = await generate_plan(
                    user_input=current_input_for_perception_and_plan,
                    perception=perception,
                    memory_items=self.context.memory.get_session_items(),
                    tool_descriptions=tool_descriptions,
                    prompt_path=prompt_path,
                    step_num=step + 1,
                    max_steps=max_steps,
                )
                print(f"[plan] {plan}")

                if re.search(r"^\s*(async\s+)?def\s+solve\s*\(\s*\)", plan, re.MULTILINE):
                    print("[loop] Detected solve() plan — running sandboxed...")
                    self.context.log_subtask(tool_name="solve_sandbox", status="pending")
                    
                    content_for_sandbox = None
                    if "fetched_content" in plan: 
                        if hasattr(self.context, 'full_content_from_last_step') and self.context.full_content_from_last_step is not None:
                            content_for_sandbox = self.context.full_content_from_last_step
                        else:
                            log("loop", "⚠️ Plan mentions 'fetched_content' but self.context.full_content_from_last_step is missing or None. This might lead to an error in sandbox.")
                    
                    result = await run_python_sandbox(plan, dispatcher=self.mcp, fetched_content_for_summary=content_for_sandbox)
                    success = False

                    if isinstance(result, str):
                        result = result.strip()
                        if result.startswith("FINAL_ANSWER:"):
                            success = True
                            self.context.final_answer = result
                        elif result.startswith("FURTHER_PROCESSING_REQUIRED:"):
                            raw_payload_from_tool_execution = result.split("FURTHER_PROCESSING_REQUIRED:", 1)[1].strip()
                            
                            extracted_text = raw_payload_from_tool_execution 
                            try:
                                if "TextContent(type='text', text='{\"markdown\":" in raw_payload_from_tool_execution:
                                    json_str_match = re.search(r"text='({.*?})'", raw_payload_from_tool_execution)
                                    if json_str_match:
                                        json_like_str = json_str_match.group(1)
                                        try:
                                            data = json.loads(json_like_str)
                                            if isinstance(data, dict) and "markdown" in data:
                                                extracted_text = data["markdown"]
                                                log("loop", f"ℹ️ Parsed 'markdown' key from TextContent. Extracted length: {len(extracted_text)}")
                                            else: # Should ideally not happen with this specific pattern
                                                log("loop", f"⚠️ TextContent's inner JSON parsed, but no 'markdown' key. Using inner JSON as string: {json_like_str}")
                                                extracted_text = json_like_str 
                                        except json.JSONDecodeError as je:
                                            md_val_match = re.search(r'\{\s*"markdown"\s*:\s*"(.*?)"\s*\}', json_like_str, re.DOTALL)
                                            if md_val_match:
                                                extracted_text = md_val_match.group(1).encode('utf-8').decode('unicode_escape')
                                                log("loop", f"ℹ️ Regex extracted 'markdown' value from problematic TextContent JSON. Extracted length: {len(extracted_text)}")
                                            else:
                                                log("loop", f"⚠️ JSONDecodeError ({je}) and regex fallback failed for TextContent. Using raw: {raw_payload_from_tool_execution}")
                                                extracted_text = raw_payload_from_tool_execution
                                    else:
                                        log("loop", f"⚠️ TextContent structure detected but failed to extract inner text='...' part. Using raw.")
                                        extracted_text = raw_payload_from_tool_execution
                                elif raw_payload_from_tool_execution.startswith("PythonCodeOutput(result="):
                                     match_py = re.match(r"PythonCodeOutput\(result=(.+)\)$", raw_payload_from_tool_execution, re.DOTALL)
                                     if match_py:
                                        temp_text = match_py.group(1)
                                        try:
                                            extracted_text = ast.literal_eval(temp_text) # ast.literal_eval expects a string literal representation
                                            log("loop", f"ℹ️ Parsed PythonCodeOutput string via ast.literal_eval. Extracted length: {len(extracted_text)}")
                                        except Exception as e_ast:
                                            log("loop", f"⚠️ ast.literal_eval failed for PythonCodeOutput string ({e_ast}). Using direct regex content: {temp_text}")
                                            extracted_text = temp_text # Fallback
                                elif raw_payload_from_tool_execution.startswith("MarkdownOutput(markdown="):
                                     match_md = re.match(r"MarkdownOutput\(markdown=(.+)\)$", raw_payload_from_tool_execution, re.DOTALL)
                                     if match_md:
                                        temp_text = match_md.group(1)
                                        try:
                                            extracted_text = ast.literal_eval(temp_text)
                                            log("loop", f"ℹ️ Parsed MarkdownOutput string via ast.literal_eval. Extracted length: {len(extracted_text)}")
                                        except Exception as e_ast:
                                            log("loop", f"⚠️ ast.literal_eval failed for MarkdownOutput string ({e_ast}). Using direct regex content: {temp_text}")
                                            extracted_text = temp_text # Fallback
                                # else: raw_payload_from_tool_execution is used (default)
                            except Exception as e_parse:
                                log("loop", f"⚠️ Outer error during payload parsing: {e_parse}. Using raw payload: {raw_payload_from_tool_execution}")
                                extracted_text = raw_payload_from_tool_execution
                            
                            content_payload = extracted_text.strip() if isinstance(extracted_text, str) else str(extracted_text).strip()
                            log("loop", f"ℹ️ Final content_payload length after parsing: {len(content_payload)}")
                            self.context.full_content_from_last_step = content_payload 

                            if len(content_payload) < MAX_CONTENT_LENGTH_FOR_DIRECT_PROMPT:
                                self.context.user_input_override = (
                                    f"Original user task: {original_task_description}\n\n"
                                    f"Your last tool call produced this content (length: {len(content_payload)}):\n\n"
                                    f"---BEGIN FETCHED CONTENT---\n"
                                    f"{content_payload}\n"
                                    f"---END FETCHED CONTENT---\n\n"
                                    f"Based on the original user task and the fetched content above, please take the next step.\n"
                                    f"If you can directly answer the original user task using this content, your plan should be to respond with:\n"
                                    f"FINAL_ANSWER: [Your direct answer based on the fetched content]\n\n"
                                    f"Otherwise, if you need to process this fetched content further (e.g., summarize a specific part, call another tool on it), "
                                    f"generate a new plan using FUNCTION_CALL. The fetched content is directly visible to you in this prompt for planning. "
                                    f"If your generated plan code needs to operate on this content, it should use standard Python string operations on the content you see here, "
                                    f"or you can choose to use the 'fetched_content' variable which will also be available in the sandbox holding this same content.\n"
                                    f"Example: async def solve(): return f\"FINAL_ANSWER: Extracted info: {{some_python_code_operating_on_the_content_above}}\"\n"
                                    f"Or, if you need a new unrelated search/action, generate that plan."
                                )
                                log("loop", f"📨 Content (length {len(content_payload)}) is short (<= {MAX_CONTENT_LENGTH_FOR_DIRECT_PROMPT}), embedding directly in next prompt for planner.")
                            else: # Content is long
                                self.context.user_input_override = (
                                    f"Original user task: {original_task_description}\n\n"
                                    f"IMPORTANT INSTRUCTION FOR CURRENT STEP:\n"
                                    f"The complete text content (length: {len(content_payload)}) from a previous tool call has been successfully fetched/retrieved.\n"
                                    f"This content is now available to your generated `solve()` function as a variable named `fetched_content`.\n"
                                    f"Your ONLY task now is to process this `fetched_content` as per the original user task (e.g., summarize it, extract information from it, etc.) and provide the FINAL_ANSWER.\n"
                                    f"Do NOT use any tools to re-fetch or re-search if the content is already in `fetched_content`.\n"
                                    f"Generate the response directly using Python code that operates on the `fetched_content` variable.\n\n"
                                    f"If the task is summarization, your plan should be simple Python to take the first N characters (e.g., 500-1000) as an initial summary, phrasing it naturally. For example: async def solve(): return f\"FINAL_ANSWER: This webpage discusses {{fetched_content[:700]}}...\"\n"
                                    f"Example plan for extraction: async def solve(): relevant_info = '...extracted from {{fetched_content}}...'; return f\"FINAL_ANSWER: {{relevant_info}}\""
                                )
                                log("loop", f"📨 Content (length {len(content_payload)}) is long (> {MAX_CONTENT_LENGTH_FOR_DIRECT_PROMPT}), will refer to it via 'fetched_content' variable in sandbox.")
                            
                            self.context.memory.add_tool_output(
                                tool_name="solve_sandbox_intermediate", 
                                tool_args={"plan": plan}, 
                                tool_result={"result_summary": f"Content of length {len(content_payload)} received for further processing."}, 
                                success=True, 
                                tags=["sandbox", "intermediate_result"],
                            )
                            log("loop", f"🔁 Continuing based on FURTHER_PROCESSING_REQUIRED — Step {step+1} continues (new context prepared)...")
                            break 
                        elif result.startswith("[sandbox error:"):
                            success = False
                            self.context.final_answer = "FINAL_ANSWER: [Execution failed due to sandbox error]"
                        else: 
                            success = True
                            self.context.final_answer = f"FINAL_ANSWER: {result}"
                    else: 
                        success = True
                        self.context.final_answer = f"FINAL_ANSWER: {result}" 

                    if not (isinstance(result, str) and result.startswith("FURTHER_PROCESSING_REQUIRED:")):
                        self.context.update_subtask_status("solve_sandbox", "success" if success else "failure")
                        self.context.memory.add_tool_output(
                            tool_name="solve_sandbox_final_attempt", 
                            tool_args= {"plan": plan}, 
                            tool_result={"result": result}, 
                            success=success,
                            tags=["sandbox", "final_attempt_for_step" if not success else "final_result_for_step"],
                        )

                    if self.context.final_answer and not (isinstance(result, str) and result.startswith("FURTHER_PROCESSING_REQUIRED:")):
                         return {"status": "done", "result": self.context.final_answer}

                    if not success: 
                        lifelines_left -= 1
                        log("loop", f"🛠 Execution not successful. Retrying... Lifelines left: {lifelines_left}")
                        if lifelines_left < 0: break 
                        continue 
                    
                    if not (isinstance(result, str) and result.startswith("FURTHER_PROCESSING_REQUIRED:")):
                        log("loop", "Execution was marked success, but no FINAL_ANSWER and not FURTHER_PROCESSING_REQUIRED. Assuming step failed to produce conclusive output.")
                        lifelines_left -= 1
                        log("loop", f"🛠 Assuming step failure due to inconclusive output. Retrying... Lifelines left: {lifelines_left}")
                        if lifelines_left < 0: break 
                        continue 
                else: 
                    log("loop", f"⚠️ Invalid plan detected (not a solve() function) — retrying... Lifelines left: {lifelines_left-1}") 
                    lifelines_left -= 1
                    if lifelines_left < 0: break 
                    continue 
            
            if lifelines_left < 0 :
                log("loop", f"⚠️ All lifelines exhausted for step {step+1}.")
                if not self.context.final_answer: 
                    self.context.final_answer = "FINAL_ANSWER: [Agent failed to complete the task for this step after multiple retries]"
                return {"status": "done", "result": self.context.final_answer}

        log("loop", "⚠️ Max steps reached.")
        if not self.context.final_answer: 
            self.context.final_answer = "FINAL_ANSWER: [Max steps reached]"
        return {"status": "done", "result": self.context.final_answer}
