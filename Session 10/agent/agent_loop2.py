import uuid
import json
import datetime
from typing import Optional, Union, Literal

from perception.perception import Perception
from decision.decision import Decision
from action.executor import run_user_code
from agent.agentSession import AgentSession, PerceptionSnapshot, Step, ToolCode
from agent.hitl_request import HITLRequest
from memory.session_log import live_update_session
from memory.memory_search import MemorySearch
from mcp_servers.multiMCP import MultiMCP


GLOBAL_PREVIOUS_FAILURE_STEPS = 3
MAX_REPLAN_ATTEMPTS = 2

class AgentLoop:
    def __init__(self, perception_prompt_path: str, decision_prompt_path: str, multi_mcp: MultiMCP, strategy: str = "exploratory"):
        self.perception = Perception(perception_prompt_path)
        self.decision = Decision(decision_prompt_path, multi_mcp)
        self.multi_mcp = multi_mcp
        self.strategy = strategy
        self.current_session: Optional[AgentSession] = None
        self.replanning_attempts = 0
        self.current_steps = 0

    async def run(self, query: str, hitl_input_data: Optional[str] = None, hitl_input_type: Optional[Literal["tool_failure", "plan_failure"]] = None) -> Union[AgentSession, HITLRequest]:
        self.replanning_attempts = 0
        self.current_steps = 0
        session: AgentSession
        step_to_process_next: Optional[Step] = None
        current_session_step_failures_memory = []

        if hitl_input_data and self.current_session and self.current_session.original_query == query:
            session = self.current_session
            print(f"\n🔄 Resuming session {session.session_id} for query '{query}' with human input for {session.hitl_type_pending}.")

            if session.hitl_type_pending == "tool_failure":
                target_step_index = session.last_failed_step_index
                failed_step_obj = None
                if target_step_index is not None and session.plan_versions:
                    for step_in_plan in session.plan_versions[-1]["steps"]:
                        if step_in_plan.index == target_step_index:
                            failed_step_obj = step_in_plan
                            break
                
                if failed_step_obj:
                    print(f"Injecting human input into Step {failed_step_obj.index}: {failed_step_obj.description}")
                    failed_step_obj.execution_result = json.dumps({"status": "success", "result": hitl_input_data, "source": "human_input"})
                    failed_step_obj.status = "completed_by_human"
                    failed_step_obj.error = None
                    
                    perception_input_for_hitl = self.perception.build_perception_input(
                        raw_input=hitl_input_data, 
                        memory=[],
                        current_plan=session.plan_versions[-1]["plan_text"],
                        snapshot_type="step_result_human_provided"
                    )
                    perception_result_after_hitl = self.perception.run(perception_input_for_hitl)
                    failed_step_obj.perception = PerceptionSnapshot(**perception_result_after_hitl)
                    live_update_session(session)
                    
                    session.hitl_type_pending = None
                    session.last_failed_step_index = None
                    session.hitl_prompt = None

                    step_to_process_next = self.evaluate_step(failed_step_obj, session, query)
                else:
                    print(f"⚠️ Error: Could not find failed step (index: {session.last_failed_step_index}) to inject human tool input. Re-planning.")
                    session.hitl_type_pending = None
                    decision_input_fallback = {
                        "plan_mode": "mid_session", "planning_strategy": self.strategy, "original_query": query,
                        "perception": session.perception.__dict__ if session.perception else {},
                        "current_plan_version": len(session.plan_versions),
                        "current_plan": session.plan_versions[-1]["plan_text"] if session.plan_versions else [],
                        "completed_steps": [s.to_dict() for pv in session.plan_versions for s in pv["steps"] if s.status in ["completed", "completed_by_human"]],
                    }
                    decision_output = self.decision.run(decision_input_fallback)
                    step_to_process_next = session.add_plan_version(decision_output["plan_text"], [self.create_step(decision_output)])

            elif session.hitl_type_pending == "plan_failure":
                print(f"Using human suggestion for re-planning: {hitl_input_data}")
                session.replanning_attempts = 0
                
                decision_input_human_guided = {
                    "plan_mode": "mid_session",
                    "planning_strategy": self.strategy,
                    "original_query": query,
                    "perception": session.perception.__dict__ if session.perception else {},
                    "user_plan_suggestion": hitl_input_data,
                    "current_plan_version": len(session.plan_versions),
                    "current_plan": session.plan_versions[-1]["plan_text"] if session.plan_versions else [],
                    "completed_steps": [s.to_dict() for pv in session.plan_versions for s in pv["steps"] if s.status in ["completed", "completed_by_human"]],
                }
                decision_output = self.decision.run(decision_input_human_guided)
                step_to_process_next = session.add_plan_version(decision_output["plan_text"], [self.create_step(decision_output)])
                
                session.hitl_type_pending = None
                session.hitl_prompt = None
                live_update_session(session)
                print(f"\n[Decision Plan Text (Human Guided): V{len(session.plan_versions)}]:")
                for line in session.plan_versions[-1]["plan_text"]:
                    print(f"  {line}")
            else:
                print(f"⚠️ Error: Resuming HITL but unknown type: {session.hitl_type_pending}. Re-initializing session.")
                self.current_session = None

        if not self.current_session or self.current_session.original_query != query or step_to_process_next is None and not hitl_input_data:
            if self.current_session and self.current_session.original_query != query:
                print(f"⚠️ New query '{query}' received. Clearing previous session for '{self.current_session.original_query}'.")
            
            _session_id = str(uuid.uuid4())
            session = AgentSession(session_id=_session_id, original_query=query)
            self.current_session = session
            self.log_session_start(session, query)

            historical_memory_results = self.search_memory(query)
            
            perception_input_initial = self.perception.build_perception_input(
                raw_input=query, 
                memory=historical_memory_results,
                snapshot_type="user_query"
            )
            perception_result = self.perception.run(perception_input_initial)
            session.add_perception(PerceptionSnapshot(**perception_result))

            if perception_result.get("original_goal_achieved"):
                self.handle_perception_completion(session, perception_result)
                self.current_session = None
                return session

            decision_output = self.make_initial_decision(query, perception_result)
            step_to_process_next = session.add_plan_version(decision_output["plan_text"], [self.create_step(decision_output)])
            live_update_session(session)
            print(f"\n[Decision Plan Text: V{len(session.plan_versions)}]:")
            for line in session.plan_versions[-1]["plan_text"]:
                print(f"  {line}")
        
        if not self.current_session:
             print("Critical Error: current_session is None before main loop. Re-initializing.")
             _session_id = str(uuid.uuid4())
             session = AgentSession(session_id=_session_id, original_query=query)
             self.current_session = session
             decision_output = {"step_index":0, "description": "Session error, requesting NOP", "type":"NOP", "code":"", "conclusion":"", "plan_text":["Step 0: Session initialization error."]}
             step_to_process_next = session.add_plan_version(decision_output["plan_text"], [self.create_step(decision_output)])

        session = self.current_session

        active_step = step_to_process_next
        while active_step:
            if session.hitl_type_pending:
                current_session_step_failures_memory.clear()
                return HITLRequest(prompt_to_user=session.hitl_prompt, session_id=session.session_id, type=session.hitl_type_pending)

            executed_step_obj = await self.execute_step(active_step, session, current_session_step_failures_memory)

            if session.hitl_type_pending:
                current_session_step_failures_memory.clear()
                return HITLRequest(prompt_to_user=session.hitl_prompt, session_id=session.session_id, type=session.hitl_type_pending)

            if executed_step_obj is None:
                if session.state.get("original_goal_achieved") or (active_step and active_step.type == "NOP"):
                    final_session_state = self.current_session
                    self.current_session = None
                    return final_session_state
                else:
                    print(f"⚠️ Loop terminated unexpectedly after step type {active_step.type if active_step else 'Unknown'}.")
                    final_session_state = self.current_session
                    if final_session_state and not final_session_state.state.get("reasoning_note"):
                        final_session_state.state["reasoning_note"] = "Agent loop ended without explicit goal achievement or HITL."
                    self.current_session = None
                    return final_session_state

            active_step = self.evaluate_step(executed_step_obj, session, query) 

            if session.hitl_type_pending:
                current_session_step_failures_memory.clear()
                return HITLRequest(prompt_to_user=session.hitl_prompt, session_id=session.session_id, type=session.hitl_type_pending)

            if executed_step_obj.status == "failed":
                self.replanning_attempts += 1
                if self.replanning_attempts >= 5:
                    print(f"🔥 Max retries ({self.replanning_attempts}) reached for query: {query}")
                    return {
                        "status": "error",
                        "error": "Maximum retries reached for this step."
                    }
                continue

            self.replanning_attempts = 0
            self.current_steps += 1
        
        final_session_state = self.current_session
        self.current_session = None
        if final_session_state and not final_session_state.state.get("original_goal_achieved") and not final_session_state.state.get("reasoning_note"):
             final_session_state.state["reasoning_note"] = "Agent completed all planned steps but goal not marked as achieved."
        return final_session_state

    def log_session_start(self, session, query):
        print("\n=== LIVE AGENT SESSION TRACE ===")
        print(f"Session ID: {session.session_id}")
        print(f"Query: {query}")

    def search_memory(self, query):
        # print("Searching Recent Conversation History")
        searcher = MemorySearch()
        results = searcher.search_memory(query)
        # if not results:
        #     print("❌ No matching memory entries found.\n")
        # else:
        #     print("\n🎯 Top Matches:\n")
        #     for i, res in enumerate(results, 1):
        #         print(f"[{i}] File: {res['file']}\nQuery: {res['query']}\nResult Requirement: {res['result_requirement']}\nSummary: {res['solution_summary']}\n")
        return results

    def run_perception(self, query, memory_results, session_step_failures_memory=None, snapshot_type="user_query", current_plan=None):
        combined_memory = (memory_results or []) + (session_step_failures_memory or [])
        perception_input = self.perception.build_perception_input(
            raw_input=query, 
            memory=combined_memory, 
            current_plan=current_plan, 
            snapshot_type=snapshot_type
        )
        perception_result = self.perception.run(perception_input)
        print("\n[Perception Result]:")
        print(json.dumps(perception_result, indent=2, ensure_ascii=False))
        return perception_result

    def handle_perception_completion(self, session, perception_result):
        print("\n✅ Perception fully answered the query.")
        session.state.update({
            "original_goal_achieved": True,
            "final_answer": perception_result.get("solution_summary", "Answer ready."),
            "confidence": perception_result.get("confidence", 0.95),
            "reasoning_note": perception_result.get("reasoning", "Handled by perception."),
            "solution_summary": perception_result.get("solution_summary", "Answer ready.")
        })
        live_update_session(session)

    def make_initial_decision(self, query, perception_result):
        decision_input = {
            "plan_mode": "initial",
            "planning_strategy": self.strategy,
            "original_query": query,
            "perception": perception_result
        }
        decision_output = self.decision.run(decision_input)
        return decision_output

    def create_step(self, decision_output):
        step_type = decision_output.get("type", "NOOP")
        if step_type == "NOP":
             step_type = "NOOP" 
        
        return Step(
            index=decision_output.get("step_index", 0),
            description=decision_output.get("description", "No description."),
            type=step_type,
            code=ToolCode(tool_name="raw_code_block", tool_arguments={"code": decision_output["code"]}) if decision_output.get("type") == "CODE" and decision_output.get("code") else None,
            conclusion=decision_output.get("conclusion"),
        )

    async def execute_step(self, step: Step, session: AgentSession, session_step_failures_memory: list) -> Optional[Step]:
        print(f"\n[Step {step.index}] {step.description}")

        if step.type == "CODE":
            if not step.code or not step.code.tool_arguments.get("code"):
                print(f"🚫 Step {step.index} is CODE type but has no code to execute. Marking as error.")
                step.error = "Missing code for CODE step."
                step.status = "failed"
                session.hitl_type_pending = "tool_failure"
                session.last_failed_step_index = step.index
                session.hitl_prompt = f"Step {step.index} ('{step.description}') is of type CODE but has no actual code. Can you provide the code or expected output?"
                live_update_session(session)
                return step

            code_to_execute = step.code.tool_arguments["code"]
            print("-" * 50, "\n[EXECUTING CODE]\n", code_to_execute)
            executor_response = await run_user_code(code_to_execute, self.multi_mcp)
            
            if executor_response.get("status") == "error":
                error_msg = executor_response.get("error", "Unknown execution error.")
                print(f"🚫 Code execution failed: {error_msg}")
                step.error = str(error_msg)
                step.status = "failed"
                
                failure_details = {"step_index": step.index, "description": step.description, "code": code_to_execute, "error": error_msg}
                session_step_failures_memory.append(failure_details)
                if len(session_step_failures_memory) > GLOBAL_PREVIOUS_FAILURE_STEPS:
                    session_step_failures_memory.pop(0)
                
                session.hitl_type_pending = "tool_failure"
                session.last_failed_step_index = step.index
                session.hitl_prompt = (
                    f"The code execution for Step {step.index} ('{step.description}') failed:\n"
                    f"--- CODE ---\n{code_to_execute}\n--- END CODE ---\n"
                    f"Error: {error_msg}\n\n"
                    f"How should I proceed? You can provide the expected output for this step, "
                    f"or suggest a correction to the code."
                )
                live_update_session(session)
                return step

            step.execution_result = json.dumps(executor_response)
            step.status = "completed"
            
            perception_input_step = self.perception.build_perception_input(
                raw_input=str(executor_response.get('result', 'Execution successful, no specific result output.')),
                memory=session_step_failures_memory,
                current_plan=session.plan_versions[-1]["plan_text"],
                snapshot_type="step_result"
            )
            perception_result = self.perception.run(perception_input_step)
            step.perception = PerceptionSnapshot(**perception_result)
            live_update_session(session)
            return step

        elif step.type == "CONCLUDE":
            print(f"\n💡 Conclusion: {step.conclusion}")
            step.execution_result = step.conclusion
            step.status = "completed"

            perception_input_conclude = self.perception.build_perception_input(
                raw_input=str(step.conclusion),
                memory=session_step_failures_memory,
                current_plan=session.plan_versions[-1]["plan_text"],
                snapshot_type="step_result"
            )
            perception_result = self.perception.run(perception_input_conclude)
            step.perception = PerceptionSnapshot(**perception_result)
            
            session.mark_complete(step.perception, final_answer=step.conclusion)
            live_update_session(session)
            if session.state.get("original_goal_achieved"):
                 return None
            else:
                 print(f"⚠️ Conclusion step {step.index} completed, but perception indicates overall goal not yet achieved.")
                 return step

        elif step.type == "NOP":
            print(f"\n❓ Clarification needed (NOP): {step.description}")
            step.status = "completed"
            step.execution_result = f"NOOP: {step.description}"
            session.state["reasoning_note"] = f"Agent action: NOOP - {step.description}"
            session.state["final_answer"] = "Clarification or further input needed from user."
            session.state["original_goal_achieved"] = False
            live_update_session(session)
            return None

        return step

    def evaluate_step(self, step: Step, session: AgentSession, query: str) -> Optional[Step]:
        if not step.perception:
            print(f"⚠️ Warning: Step {step.index} ('{step.description}') has no perception data. Assuming step was unhelpful.")
            step.perception = PerceptionSnapshot(entities=[], result_requirement="N/A", original_goal_achieved=False, 
                                                 reasoning="Missing perception after step execution.", local_goal_achieved=False, 
                                                 local_reasoning="Assuming unhelpful due to missing perception.", 
                                                 last_tooluse_summary=str(step.execution_result)[:100], solution_summary="N/A", confidence="0.0")
            live_update_session(session)

        if step.perception.original_goal_achieved:
            print("\n✅ Goal achieved.")
            session.mark_complete(step.perception)
            live_update_session(session)
            return None

        elif step.perception.local_goal_achieved:
            current_plan_steps = session.plan_versions[-1]["steps"]
            next_step_index_in_plan = -1
            for i, s_in_plan in enumerate(current_plan_steps):
                if s_in_plan.index == step.index:
                    if i + 1 < len(current_plan_steps):
                        next_step_index_in_plan = i + 1
                        break
            
            if next_step_index_in_plan != -1:
                next_step_obj = current_plan_steps[next_step_index_in_plan]
                print(f"\n➡️ Local goal for Step {step.index} achieved. Proceeding to next step in plan: Step {next_step_obj.index} ('{next_step_obj.description}').")
                return next_step_obj
            else:
                print(f"\n🏁 Local goal for Step {step.index} (last in plan) achieved, but original query '{query}' not fully resolved. Requesting next decision.")
                decision_input_continue = {
                    "plan_mode": "mid_session", "planning_strategy": self.strategy, "original_query": query,
                    "current_plan_version": len(session.plan_versions),
                    "current_plan": session.plan_versions[-1]["plan_text"],
                    "completed_steps": [s.to_dict() for pv in session.plan_versions for s in pv["steps"] if s.status in ["completed", "completed_by_human"]],
                    "current_step": step.to_dict(),
                    "perception": step.perception.__dict__
                }
                decision_output = self.decision.run(decision_input_continue)
                next_step_obj = session.add_plan_version(decision_output["plan_text"], [self.create_step(decision_output)])
                print(f"\n[Decision Plan Text (Continuation): V{len(session.plan_versions)}]:")
                for line in session.plan_versions[-1]["plan_text"]:
                    print(f"  {line}")
                return next_step_obj

        else:
            print(f"\n🔁 Step {step.index} ('{step.description}') unhelpful or perception indicates failure. Replanning.")
            session.replanning_attempts += 1
            live_update_session(session)

            if session.replanning_attempts >= MAX_REPLAN_ATTEMPTS:
                print(f"🔥 Max re-planning attempts ({MAX_REPLAN_ATTEMPTS}) reached for query: {query}")
                last_plan_text_list = session.plan_versions[-1]["plan_text"] if session.plan_versions else ["No plan was available."]
                last_plan_str = "\n".join([f"  - {L}" for L in last_plan_text_list])

                session.hitl_type_pending = "plan_failure"
                session.hitl_prompt = (
                    f"I'm having trouble making progress on your query: '{query}'.\n"
                    f"I've tried {session.replanning_attempts} different approaches based on my current understanding.\n"
                    f"My last attempted plan was:\n{last_plan_str}\n"
                    f"The last step {step.index} ('{step.description}') resulted in: {step.perception.local_reasoning if step.perception else 'Perception N/A'}\n\n"
                    f"Can you suggest a different overall approach, the next specific step, or clarify the goal?"
                )
                return step

            decision_input_replan = {
                "plan_mode": "mid_session", "planning_strategy": self.strategy, "original_query": query,
                "current_plan_version": len(session.plan_versions),
                "current_plan": session.plan_versions[-1]["plan_text"],
                "completed_steps": [s.to_dict() for pv in session.plan_versions for s in pv["steps"] if s.status in ["completed", "completed_by_human"]],
                "current_step": step.to_dict(),
                "perception": step.perception.__dict__
            }
            decision_output = self.decision.run(decision_input_replan)
            next_step_obj = session.add_plan_version(decision_output["plan_text"], [self.create_step(decision_output)])
            print(f"\n[Decision Plan Text (Replanned): V{len(session.plan_versions)}]:")
            for line in session.plan_versions[-1]["plan_text"]:
                print(f"  {line}")
            return next_step_obj