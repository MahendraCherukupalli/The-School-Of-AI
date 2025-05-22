from dataclasses import dataclass, asdict, field
from typing import Any, Literal, Optional
import uuid
import time
import json

@dataclass
class ToolCode:
    tool_name: str
    tool_arguments: dict[str, Any]

    def to_dict(self):
        return {
            "tool_name": self.tool_name,
            "tool_arguments": self.tool_arguments
        }


@dataclass
class PerceptionSnapshot:
    entities: list[str]
    result_requirement: str
    original_goal_achieved: bool
    reasoning: str
    local_goal_achieved: bool
    local_reasoning: str
    last_tooluse_summary: str
    solution_summary: str
    confidence: str

@dataclass
class Step:
    index: int
    description: str
    type: Literal["CODE", "CONCLUDE", "NOOP"]
    code: Optional[ToolCode] = None
    conclusion: Optional[str] = None
    execution_result: Optional[str] = None
    error: Optional[str] = None
    perception: Optional[PerceptionSnapshot] = None
    status: Literal["pending", "completed", "failed", "skipped", "completed_by_human"] = "pending"
    attempts: int = 0
    was_replanned: bool = False
    parent_index: Optional[int] = None

    def to_dict(self):
        return {
            "index": self.index,
            "description": self.description,
            "type": self.type,
            "code": self.code.to_dict() if self.code else None,
            "conclusion": self.conclusion,
            "execution_result": self.execution_result,
            "error": self.error,
            "perception": self.perception.__dict__ if self.perception else None,
            "status": self.status,
            "attempts": self.attempts,
            "was_replanned": self.was_replanned,
            "parent_index": self.parent_index
        }


class AgentSession:
    def __init__(self, session_id: str, original_query: str):
        self.session_id = session_id
        self.original_query = original_query
        self.perception: Optional[PerceptionSnapshot] = None
        self.plan_versions: list[dict[str, Any]] = []
        self.state = {
            "original_goal_achieved": False,
            "final_answer": None,
            "confidence": 0.0,
            "reasoning_note": "",
            "solution_summary": ""
            
        }
        self.replanning_attempts: int = 0
        self.hitl_type_pending: Optional[Literal["tool_failure", "plan_failure"]] = None
        self.last_failed_step_index: Optional[int] = None
        self.hitl_prompt: Optional[str] = None

    def add_perception(self, snapshot: PerceptionSnapshot):
        self.perception = snapshot

    def add_plan_version(self, plan_texts: list[str], steps: list[Step]):
        plan = {
            "plan_text": plan_texts,
            "steps": steps.copy()
        }
        self.plan_versions.append(plan)
        return steps[0] if steps else None

    def get_next_step_index(self) -> int:
        current_max_index = -1
        for pv in self.plan_versions:
            for step in pv["steps"]:
                if step.index > current_max_index:
                    current_max_index = step.index
        return current_max_index + 1


    def to_json(self):
        return {
            "session_id": self.session_id,
            "original_query": self.original_query,
            "perception": asdict(self.perception) if self.perception else None,
            "plan_versions": [
                {
                    "plan_text": p["plan_text"],
                    "steps": [s.to_dict() for s in p["steps"]]
                } for p in self.plan_versions
            ],
            "state_snapshot": self.get_snapshot_summary()
        }

    def get_snapshot_summary(self):
        all_completed_steps = []
        for version in self.plan_versions:
            for s in version["steps"]:
                if s.status in ["completed", "completed_by_human", "skipped"]:
                    all_completed_steps.append(s.to_dict())
        
        final_plan_text = self.plan_versions[-1]["plan_text"] if self.plan_versions else []

        return {
            "session_id": self.session_id,
            "query": self.original_query,
            "final_plan_text": final_plan_text,
            "executed_steps_summary": all_completed_steps,
            "final_answer": self.state["final_answer"],
            "confidence": self.state["confidence"],
            "reasoning_note": self.state["reasoning_note"],
            "solution_summary": self.state["solution_summary"],
            "original_goal_achieved": self.state["original_goal_achieved"]
        }

    def mark_complete(self, perception_snapshot: PerceptionSnapshot, final_answer: Optional[str] = None, fallback_confidence: float = 0.95):
        self.state.update({
            "original_goal_achieved": perception_snapshot.original_goal_achieved,
            "final_answer": final_answer or perception_snapshot.solution_summary,
            "confidence": float(perception_snapshot.confidence) if perception_snapshot.confidence else fallback_confidence,
            "reasoning_note": perception_snapshot.reasoning,
            "solution_summary": perception_snapshot.solution_summary
        })



    def simulate_live(self, delay: float = 1.2):
        print("\n=== LIVE AGENT SESSION TRACE ===")
        print(f"Session ID: {self.session_id}")
        print(f"Query: {self.original_query}")
        time.sleep(delay)

        if self.perception:
            print("\n[Perception 0] Initial Perception Output:")
            print(f"  {asdict(self.perception)}")
            time.sleep(delay)

        for i, version in enumerate(self.plan_versions):
            print(f"\n[Decision Plan Text: V{i+1}]:")
            plan_display = version.get("plan_text", [])
            if not isinstance(plan_display, list): plan_display = [str(plan_display)]

            for j, p_line in enumerate(plan_display):
                print(f"  Line {j}: {p_line}")
            time.sleep(delay)

            for step in version["steps"]:
                print(f"\n[Step {step.index}] {step.description}")
                time.sleep(delay / 1.5)

                print(f"  Type: {step.type}")
                if step.code:
                    print(f"  Tool → {step.code.tool_name} | Args → {step.code.tool_arguments}")
                if step.conclusion:
                    print(f"  Conclusion: {step.conclusion}")
                if step.execution_result:
                    try:
                        exec_res_dict = json.loads(step.execution_result)
                        print(f"  Execution Result: {json.dumps(exec_res_dict, indent=2)}")
                    except (json.JSONDecodeError, TypeError):
                        print(f"  Execution Result: {step.execution_result}")

                if step.error:
                    print(f"  Error: {step.error}")
                if step.perception:
                    print("  Perception of Step Result:")
                    perception_dict = asdict(step.perception) if hasattr(step.perception, '__dict__') or isinstance(step.perception, dict) else {"info": str(step.perception)}
                    for k, v_item in perception_dict.items():
                        print(f"    {k}: {v_item}")
                print(f"  Status: {step.status}")
                if step.was_replanned:
                    print(f"  (Replanned from Step {step.parent_index})")
                if step.attempts > 1:
                    print(f"  Attempts: {step.attempts}")
                time.sleep(delay)

        print("\n[Final Session Snapshot]:")
        print(json.dumps(self.get_snapshot_summary(), indent=2))
