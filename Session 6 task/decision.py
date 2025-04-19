import asyncio
from concurrent.futures import TimeoutError
from typing import Any

# Import necessary components from other modules
from memory import AppState, get_full_prompt_context
from perception import PerceptionOutput, parse_llm_response

async def generate_with_timeout(client: Any, prompt: str, timeout: int = 20) -> str:
    """Generate content with the LLM with a timeout."""
    print("DEBUG (Decision): Starting LLM generation...")
    try:
        # Ensure we have the client object from the state
        if not client:
            raise ValueError("Gemini client is not available in state.")
            
        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(
                None, 
                lambda: client.models.generate_content( 
                    model="gemini-1.5-flash",
                    contents=prompt
                )
            ),
            timeout=timeout
        )
        # Access the text content correctly based on the genai library structure
        # This might need adjustment depending on the exact response object structure
        response_text = ""
        if hasattr(response, 'text'):
            response_text = response.text
        elif hasattr(response, 'parts') and response.parts:
             # Handle potential multipart responses if applicable
             response_text = " ".join(part.text for part in response.parts if hasattr(part, 'text'))
        # Handle potential lack of response text or errors more gracefully
        elif hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
             reason = response.prompt_feedback.block_reason
             error_msg = f"LLM generation blocked. Reason: {reason}"
             print(f"ERROR (Decision): {error_msg}")
             # If safety settings blocked, it might be better to raise or return specific error
             # For now, return an empty string or the error message itself
             raise RuntimeError(error_msg) # Raising error is often better
        else:
             # Attempt a fallback conversion if the structure is unexpected
             response_text = str(response)
             print(f"WARN (Decision): Unexpected LLM response structure or empty response. Using str(): {response_text[:100]}...")
             # If the response is consistently empty or unusual, investigate response object details

        print("DEBUG (Decision): LLM generation completed.")
        return response_text.strip()
        
    except TimeoutError:
        print("ERROR (Decision): LLM generation timed out!")
        raise TimeoutError("LLM generation timed out")
    except Exception as e:
        print(f"ERROR (Decision): Error during LLM generation: {e}")
        # Consider logging traceback here if needed
        # import traceback
        # traceback.print_exc()
        raise RuntimeError(f"LLM generation failed: {e}")

async def decide_next_action(state: AppState) -> PerceptionOutput:
    """Decides the next action by querying the LLM based on the current state."""
    print(f"\n--- Iteration {state.current_iteration + 1} (Decision) ---")
    llm_raw_response = ""
    perception_result = None
    error_message = None

    try:
        # 1. Get the context for the LLM
        prompt_context = get_full_prompt_context(state)
        print(f"DEBUG (Decision): Generated LLM Prompt Context:\n{prompt_context}")
        
        # 2. Call the LLM
        llm_raw_response = await generate_with_timeout(state.gemini_client, prompt_context)
        print(f"DEBUG (Decision): Raw LLM Response:\n{llm_raw_response}")

        # 3. Parse the LLM response
        perception_result = parse_llm_response(llm_raw_response)
        
        # Check if parsing itself resulted in an error
        if perception_result.error:
            error_message = perception_result.error
            # No need to raise here, the error is captured in PerceptionOutput

    except TimeoutError as e:
        error_message = f"LLM call timed out: {e}"
        print(f"ERROR (Decision): {error_message}")
    except RuntimeError as e:
        error_message = f"LLM call failed: {e}"
        print(f"ERROR (Decision): {error_message}")
    except Exception as e:
        error_message = f"Unexpected error in decision step: {e}"
        print(f"ERROR (Decision): {error_message}")
        # import traceback
        # traceback.print_exc()

    # Return the perception result, even if errors occurred during LLM call/parsing
    # The error will be captured within the PerceptionOutput object if generated
    if perception_result:
        # If an error occurred *during* decision making (e.g., LLM call timeout),
        # update the perception_result's error field if it's not already set from parsing.
        if error_message and not perception_result.error:
            perception_result.error = error_message
        return perception_result
    else:
        # If perception_result couldn't be created at all (e.g., early exception)
        # Create a PerceptionOutput indicating the error
        return PerceptionOutput(
            llm_raw_response=llm_raw_response, # Include raw response if available
            error=error_message or "Unknown error prevented perception result generation"
        )

# --- Removed old code ---
# from pydantic import BaseModel
# from typing import List, Dict

# class DecisionInput(BaseModel):
#     func_name: str
#     parameters: List[str]

# class DecisionOutput(BaseModel):
#     action: str
#     args: Dict[str, str]

# def decide(input_data: DecisionInput) -> DecisionOutput:
#     if input_data.func_name == "error":
#         raise ValueError("LLM returned error: " + " ".join(input_data.parameters))

#     return DecisionOutput(
#         action=input_data.func_name,
#         args={f"param_{i}": p for i, p in enumerate(input_data.parameters)}
#     )
