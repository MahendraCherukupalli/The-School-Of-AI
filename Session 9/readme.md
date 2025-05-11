# Cortex-R Agent (Enhanced with Semantic Caching)

## 1. Overview

This project implements an interactive AI agent, "Cortex-R Agent," designed to process user queries and provide answers. A key feature is its advanced conversation history and caching mechanism, which uses semantic search to retrieve answers from past successful interactions, improving efficiency and consistency. The agent also incorporates a modular system for heuristic-based input/output validation and utility functions.

## 2. Features

*   **Interactive Q&A**: Engages with users via a command-line interface.
*   **Semantic Conversation Caching**:
    *   Remembers successful conversations.
    *   When a new question is asked, it searches for semantically similar past questions.
    *   If a sufficiently similar question is found, the cached answer is returned, saving processing time.
    *   Uses `sentence-transformers` for generating text embeddings and `FAISS` for efficient vector similarity search.
*   **Conversation History Storage**:
    *   Successful conversations (ID, timestamp, normalized question, final answer) are stored in `successful_conversations.json`.
*   **Question Normalization**: User questions are normalized (e.g., removing leading `#`, stripping whitespace) before processing for cache lookup or storage.
*   **Deduplication of Stored Conversations**: Before saving a new conversation, the system checks if a semantically very similar question already exists in the history to avoid redundant entries.
*   **Heuristic-Based Output Validation**: Uses rules to determine if an agent's output is a valid final answer or a system/error message before deciding to cache it.
*   **Modular Heuristics Utilities**: A dedicated module (`core/heuristics.py`) provides a collection of reusable, simple rule-based functions for various validation and utility tasks.

## 3. Core Components

*   **`agent.py`**:
    *   The main executable script for the agent.
    *   Handles the user interaction loop, session management, and orchestrates calls to the core processing units and the conversation history module.
*   **`core/conversation_history.py`**:
    *   Manages the storage, semantic indexing, and retrieval of past conversations.
    *   Responsible for initializing and using the `sentence-transformers` model and the `FAISS` index.
    *   Handles question normalization and deduplication logic.
*   **`core/heuristics.py`**:
    *   A library of simple, rule-based functions (heuristics) used for various checks and transformations (e.g., validating agent output, checking URL security, censoring bad words).

## 4. Setup and Installation

### Prerequisites
*   Python (3.11+ recommended)
*   `pip` (Python package installer)

### Dependencies
The agent relies on several Python libraries. It's recommended to use a virtual environment.
Key dependencies include:
*   `pyyaml` (for configuration)
*   `sentence-transformers` (for text embeddings)
*   `faiss-cpu` (for vector similarity search; `faiss-gpu` can be used if a compatible GPU and CUDA setup are available)
*   `numpy` (for numerical operations)
*   `asyncio` (for asynchronous operations, part of Python's standard library)

You can install them using pip:
```bash
pip install pyyaml sentence-transformers faiss-cpu numpy
```
*(Consider creating a `requirements.txt` file for easier dependency management.)*

### First-Time Run
*   **Model Download**: The `sentence-transformers` library will download a pre-trained language model (e.g., `all-MiniLM-L6-v2`) the first time it's used by `core/conversation_history.py`. An internet connection is required for this initial download.
*   **FAISS Index Creation**: On the first run after changes to `successful_conversations.json` or if the index doesn't exist, the FAISS index (`faiss_index/conversations.index`) will be built. This might take a few moments if there's a large history.

## 5. Running the Agent

Navigate to the project's root directory (e.g., `S9/`) in your terminal and run:
```bash
python agent.py
```
The agent will start, and you can begin interacting with it by typing your questions.

## 6. Conversation History & Caching

*   **JSON Store**: Successful conversations are logged in `S9/successful_conversations.json`. Each entry includes an ID, timestamp, the normalized question, and the final answer.
*   **FAISS Vector Index**: Semantic embeddings of the normalized questions are stored in `S9/faiss_index/conversations.index` for fast similarity searches.
*   **Normalization**: Questions are normalized (e.g., by stripping leading `#` and extra whitespace) before being used for lookup or storage. This helps in matching questions that have minor syntactic differences but are semantically similar.
*   **Deduplication**: To keep the history clean, the system attempts to avoid storing new questions that are highly similar (e.g., >95% cosine similarity, configurable) to already existing ones.
*   **Retrieval Threshold**: When searching for a past answer, a similarity threshold (e.g., >90% cosine similarity, configurable) is used to determine if a stored answer is relevant enough to be returned.

## 7. Heuristics Module (`core/heuristics.py`)

This module provides a collection of simple, rule-based functions for various utility and validation tasks. Examples include:
*   `is_valid_agent_output()`: Checks if an agent's response is a valid final answer suitable for caching (e.g., not a system error message like `"[Error]"`).
*   `check_url_is_secure()`: Checks if a URL uses "https://".
*   `censor_bad_words()`: Replaces predefined bad words in a text.
*   `is_valid_email_format()`: Basic email format validation.
*   And several others for length validation, digit checks, etc.

These heuristics can be used across the agent's components to enforce specific rules or perform quick checks efficiently.

## 8. Configuration

*   **Agent Profiles**: The agent uses `S9/config/profiles.yaml` to configure MCP (Multi-Component Processing) servers and other operational parameters.
*   **Caching Behavior**: Several constants within `S9/core/conversation_history.py` can be tuned:
    *   `EMBEDDING_MODEL_NAME`: To change the sentence transformer model.
    *   `DEFAULT_SIMILARITY_THRESHOLD_RETRIEVAL`: The minimum similarity for retrieving a cached answer.
    *   `DEFAULT_SIMILARITY_THRESHOLD_DEDUPLICATION`: The minimum similarity for skipping the storage of a new, near-duplicate question.
*   **Heuristics Configuration**: Some heuristics in `S9/core/heuristics.py` (like `DEFAULT_BAD_WORDS`) have internal constants that can be modified.

## 9. Potential Future Enhancements

*   More sophisticated error handling and reporting mechanisms.
*   Development of a graphical user interface (GUI) or an API for interaction.
*   Advanced text normalization and pre-processing techniques.
*   Automated cleanup, rotation, or archival of very old cached entries.
*   Ability to "forget" or re-evaluate specific cached answers.
*   More dynamic configuration for heuristic rules.
