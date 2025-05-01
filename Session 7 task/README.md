# Modular YouTube Q&A Agent (Streamlit RAG Application)

## Overview

This project implements a Streamlit web application that allows users to search for YouTube videos on a specific topic, processes the transcripts of relevant videos, and enables users to ask follow-up questions answered using a Retrieval-Augmented Generation (RAG) approach with the Google Gemini API.

The application features a modular design inspired by agent architectures, separating concerns like memory management, perception, decision-making, and action execution. It also includes a topic-based caching mechanism to significantly speed up subsequent searches for the same topic.

## Features

*   **Topic-Based YouTube Search:** Find YouTube videos based on a user-provided topic.
*   **Video Filtering:** Automatically filters videos based on duration (10-30 minutes) and the availability of English transcripts. Selects the top 2 longest videos among the top 10 most viewed.
*   **Transcript Processing:** Fetches transcripts for selected videos.
*   **Vector Embeddings & Storage:** Chunks transcripts, generates embeddings using a local embedding service, and stores them in an in-memory FAISS index managed by the `MemoryManager`.
*   **RAG Q&A:** Answers user questions by:
    *   Retrieving relevant transcript chunks from FAISS based on the question's semantic similarity.
    *   Generating a prompt containing the retrieved context and the user's question.
    *   Calling the Google Gemini API to generate an answer based *only* on the provided context.
*   **Topic Caching:** Persistently caches the FAISS index, metadata, and processed video list for each unique search topic in the `topic_cache/` directory. Subsequent searches for the same topic load directly from the cache, skipping YouTube search, transcript fetching, and embedding.
*   **Interactive UI:** Streamlit interface for searching, viewing processed videos, and engaging in a chat-like Q&A session.
*   **Modular Design:** Code is structured into logical components for better maintainability.

## Architecture / Project Structure

The application is divided into the following Python modules:

*   **`main.py`**:
    *   The main Streamlit application file.
    *   Handles UI elements (search bar, buttons, chat display, video expander).
    *   Orchestrates the overall workflow (search, processing, Q&A).
    *   Manages the topic caching logic (checking, loading, saving).
    *   Contains YouTube-specific helper functions (`search_youtube`, `get_transcript`, etc.).
*   **`memory.py`**:
    *   Defines the `MemoryManager` class.
    *   Handles interaction with the embedding service (`_get_embedding`).
    *   Performs text chunking (`_chunk_text`).
    *   Manages the FAISS index (`self.index`) and metadata (`self.metadata_store`).
    *   Provides methods to add documents (`add_document`) and retrieve relevant chunks (`retrieve`).
    *   Includes methods to clear memory (`clear_memory`) and get status (`get_status`).
*   **`perception.py`**:
    *   Defines `extract_perception`, which currently packages the raw user input into a `PerceptionResult` model. (Can be extended for more complex intent/entity extraction).
*   **`decision.py`**:
    *   Defines `generate_plan`, which takes the perception and retrieved memory chunks.
    *   Formats the final prompt string (`RAG_PROMPT_TEMPLATE`) to be sent to the LLM for the RAG step. Returns `None` if no relevant context was found.
*   **`action.py`**:
    *   Defines `execute_action`, which takes the plan (RAG prompt or `None`).
    *   Calls the configured Google Gemini API (`gemini-1.5-flash`) if a prompt is provided.
    *   Returns the final answer from the LLM or a predefined "no context" message.
    *   Handles Gemini API configuration and basic error handling for the API call.
*   **`models.py`**:
    *   Defines Pydantic models used for data structures (e.g., `PerceptionResult`).
*   **`topic_cache/`**:
    *   A directory created automatically to store persistent cache data.
    *   Each sub-directory within `topic_cache/` corresponds to a hashed search topic and contains:
        *   `index.bin`: The serialized FAISS index for the topic.
        *   `metadata.json`: The list of metadata associated with the index entries.
        *   `videos.json`: The list of video details processed for the topic.

## Prerequisites

*   **Python:** 3.9 or higher recommended.
*   **Local Embedding Service:** An OpenAI API-compatible embedding service running locally. The application is configured to use:
    *   URL: `http://localhost:1234/v1/embeddings`
    *   Model: `text-embedding-nomic-embed-text-v1.5`
    *   Expected Dimension: 768
    *(You can use tools like Ollama with an appropriate embedding model, LM Studio, or others that provide this compatible endpoint).*
*   **Google Gemini API Key:** You need an API key from Google AI Studio.

## Setup

1.  **Clone Repository:**
    ```bash
    git clone <your-repo-url>
    cd <repository-directory>
    ```
2.  **Create Virtual Environment:**
    ```bash
    python -m venv env
    ```
3.  **Activate Environment:**
    *   macOS/Linux: `source env/bin/activate`
    *   Windows: `.\env\Scripts\activate`
4.  **Install Dependencies:**
    *   *(Recommended)* Create a `requirements.txt` file with necessary libraries:
        ```txt
        streamlit
        numpy
        requests
        faiss-cpu # or faiss-gpu if you have CUDA setup
        google-generativeai
        youtube-search-python
        youtube-transcript-api
        pydantic
        # Add any other specific dependencies if needed
        ```
    *   Install using pip:
        ```bash
        pip install -r requirements.txt
        ```
5.  **Configure API Key:**
    *   Currently, the Gemini API key is hardcoded in `action.py`.
    *   **Strongly recommended:** Modify `action.py` to load the key from an environment variable or a secure configuration file instead.
    ```python
    # action.py - Example using environment variable
    import os
    # ...
    # API_KEY = os.getenv("GEMINI_API_KEY")
    # if not API_KEY:
    #     logging.error("GEMINI_API_KEY environment variable not set.")
    #     # Handle error...
    # else:
    #    genai.configure(api_key=API_KEY)
    # ...
    ```
6.  **Start Embedding Service:** Ensure your local embedding service (e.g., Ollama, LM Studio) is running and accessible at `http://localhost:1234/v1/embeddings` with the model `text-embedding-nomic-embed-text-v1.5`.

## Running the Application

1.  Make sure your virtual environment is activated and the embedding service is running.
2.  Navigate to the project directory in your terminal.
3.  Run the Streamlit application:
    ```bash
    streamlit run main.py
    ```
4.  Open the URL provided by Streamlit (usually `http://localhost:8501`) in your web browser.

## Configuration

Key configuration points can be found in:

*   **`action.py`**: Gemini API Key (`API_KEY`).
*   **`memory.py`**: Embedding service URL (`EMBED_URL`), model name (`EMBED_MODEL`), embedding dimension (`EMBED_DIM`), chunk size/overlap (`CHUNK_SIZE`, `CHUNK_OVERLAP`).
*   **`main.py`**: Video duration/view filters (within `search_youtube`), cache directory path (`CACHE_DIR`).

## Caching

The application uses a directory named `topic_cache` in the root project folder. When you search for a topic for the first time, the processed data (FAISS index, metadata, video list) is saved into a subdirectory named after the MD5 hash of the normalized topic string. On subsequent searches for the exact same topic, the application detects the cache and loads the data directly, significantly speeding up the process. 