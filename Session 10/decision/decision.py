import os
import json
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai.errors import ServerError
import re
from mcp_servers.multiMCP import MultiMCP
import ast


load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

class Decision:
    def __init__(self, decision_prompt_path: str, multi_mcp: MultiMCP, api_key: str | None = None, model: str = "gemini-2.0-flash"):
        load_dotenv()
        self.decision_prompt_path = decision_prompt_path
        self.multi_mcp = multi_mcp
        self.model = model

        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment or explicitly provided.")
        self.client = genai.Client(api_key=self.api_key)
        

    def run(self, decision_input: dict) -> dict:
        prompt_template = Path(self.decision_prompt_path).read_text(encoding="utf-8")
        function_list_text = self.multi_mcp.tool_description_wrapper()
        tool_descriptions = "\n".join(f"- `{desc.strip()}`" for desc in function_list_text)
        tool_descriptions_segment = "\n\n### The ONLY Available Tools\n\n---\n\n" + tool_descriptions
        
        user_suggestion_prompt_segment = ""
        if "user_plan_suggestion" in decision_input and decision_input["user_plan_suggestion"]:
            user_suggestion = decision_input["user_plan_suggestion"]
            user_suggestion_prompt_segment = (
                "\n\n### Human User Suggestion for Next Plan/Action\n"
                "A human user has provided the following suggestion due to previous difficulties. "
                "You MUST heavily consider this suggestion when formulating your plan. "
                "If it's a specific action, try to make it the next step. If it's a general approach, adapt your plan accordingly.\n"
                f"User's Suggestion: \"\"\"{user_suggestion}\"\"\"\n---"
            )

        decision_input_for_json = {k: v for k, v in decision_input.items() if k != "user_plan_suggestion"}
        main_prompt_body_json = f"\n\n```json\n{json.dumps(decision_input_for_json, indent=2)}\n```"

        full_prompt = f"{prompt_template.strip()}{user_suggestion_prompt_segment}{tool_descriptions_segment}{main_prompt_body_json}"

        # For debugging:
        # print("--- Decision Prompt to LLM ---")
        # print(full_prompt)
        # print("-----------------------------")

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=full_prompt
            )
        except ServerError as e:
            print(f"🚫 Decision LLM ServerError: {e}")
            return {
                "step_index": 0, "description": "Decision model unavailable: server overload.",
                "type": "NOOP", "code": "", "conclusion": "",
                "plan_text": ["Step 0: Decision model returned a 503. Exiting to avoid loop."],
                "raw_text": str(e)
            }
        except Exception as e:
            print(f"🚫 Decision LLM API call failed: {e}")
            return {
                "step_index": 0, "description": f"Decision model API call failed: {e}",
                "type": "NOOP", "code": "", "conclusion": "",
                "plan_text": ["Step 0: LLM API call failed."],
                "raw_text": str(e)
            }

        if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
            print("🚫 Decision LLM response is empty or malformed.")
            return {
                "step_index": 0, "description": "Decision model returned an empty or malformed response.",
                "type": "NOOP", "code": "", "conclusion": "",
                "plan_text": ["Step 0: LLM response was empty."],
                "raw_text": str(response) 
            }

        raw_text = response.candidates[0].content.parts[0].text.strip()

        try:
            match = re.search(r"```json\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
            if not match:
                print(f"⚠️ No JSON block found in Decision LLM response. Raw text: {raw_text[:500]}")
                return {
                    "step_index": 0,
                    "description": "LLM did not return a valid JSON plan step. It might be asking for clarification or refusing.",
                    "type": "NOOP",
                    "code": "",
                    "conclusion": raw_text[:500],
                    "plan_text": ["Step 0: LLM response was not a structured step. See conclusion."],
                    "raw_text": raw_text[:1000]
                }

            json_block = match.group(1)
            try:
                output = json.loads(json_block)
            except json.JSONDecodeError as e:
                print(f"⚠️ JSON decode failed in Decision: {e}. Raw JSON block: {json_block[:500]}")
                return {
                    "step_index": 0, 
                    "description": "Failed to parse JSON from LLM. The LLM output was malformed.",
                    "type": "NOOP",
                    "code": "", 
                    "conclusion": f"Malformed JSON from LLM: {json_block[:200]}...",
                    "plan_text": ["Step 0: Critical error parsing LLM decision output."],
                    "raw_text": raw_text[:1000]
                }

            if "next_step" in output and isinstance(output["next_step"], dict):
                output.update(output.pop("next_step"))

            defaults = {
                "step_index": 0, "description": "Missing from LLM response.",
                "type": "NOOP", "code": "", "conclusion": "",
                "plan_text": ["Step 0: No valid plan returned by LLM."]
            }
            for key, default_val in defaults.items():
                output.setdefault(key, default_val)
            
            if output.get("type") == "NOP":
                output["type"] = "NOOP"
            allowed_step_types = ["CODE", "CONCLUDE", "NOOP"]
            if output.get("type") not in allowed_step_types:
                print(f"⚠️ LLM returned invalid step type: '{output.get('type')}'. Defaulting to NOOP.")
                output["type"] = "NOOP"


            return output

        except Exception as e:
            print(f"❌ Unrecoverable exception while parsing LLM response in Decision.run: {str(e)}")
            raw_text_for_error = raw_text if 'raw_text' in locals() else "LLM response not available or error before receiving it."
            return {
                "step_index": 0, "description": f"Exception while parsing LLM output: {str(e)}",
                "type": "NOOP", "code": "", "conclusion": "",
                "plan_text": ["Step 0: Exception occurred while processing LLM response."],
                "raw_text": raw_text_for_error[:1000] 
            }





