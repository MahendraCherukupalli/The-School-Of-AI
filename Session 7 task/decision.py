from models import PerceptionResult
from typing import List
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Constant for the prompt template
RAG_PROMPT_TEMPLATE = """
Context from relevant YouTube videos:
{context}

User question: {question}

Please provide a detailed answer based ONLY on the context provided. If the context doesn't contain relevant information to answer the question, please state that clearly. Do not use prior knowledge.
"""

NO_CONTEXT_RESPONSE = "I couldn't find any relevant information in the processed videos to answer your question."

def generate_plan(perception: PerceptionResult, memory_chunks: List[str]) -> str | None:
    """
    Generates the plan (prompt) for the RAG action based on perception and retrieved memories.

    Args:
        perception: The result from the perception phase containing the user input.
        memory_chunks: A list of relevant text chunks retrieved from memory.

    Returns:
        The formatted RAG prompt string if context is found,
        or None if no context is available (indicating a direct response is needed).
    """
    user_question = perception.user_input
    logging.info(f"Generating plan for question: '{user_question[:50]}...'")

    if not memory_chunks:
        logging.warning("No memory chunks provided for plan generation.")
        # Signal that no RAG call is needed, the action layer should use NO_CONTEXT_RESPONSE
        return None
    else:
        context = "\n---\n".join(memory_chunks) # Join chunks with separator
        prompt = RAG_PROMPT_TEMPLATE.format(context=context, question=user_question)
        logging.info(f"Generated RAG prompt based on {len(memory_chunks)} context chunks.")
        return prompt
