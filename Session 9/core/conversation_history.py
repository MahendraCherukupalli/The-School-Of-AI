import json
import os
import datetime
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

# Define the path relative to the S9 directory (project root for the agent)
# This assumes conversation_history.py is in S9/core/
# and the main agent script (agent.py) is in S9/
# The JSON file will be created in S9/
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
CONVERSATION_HISTORY_FILE = os.path.join(PROJECT_ROOT, "successful_conversations.json")
FAISS_INDEX_DIR = os.path.join(PROJECT_ROOT, "faiss_index")
FAISS_INDEX_FILE = os.path.join(FAISS_INDEX_DIR, "conversations.index")

# Using a common, efficient model. Other models can be chosen based on needs.
# See: https://www.sbert.net/docs/pretrained_models.html
EMBEDDING_MODEL_NAME = 'all-MiniLM-L6-v2' 
DEFAULT_SIMILARITY_THRESHOLD_RETRIEVAL = 0.90 # For finding an answer
DEFAULT_SIMILARITY_THRESHOLD_DEDUPLICATION = 0.95 # For preventing storage of near-duplicates

# --- Global State Variables (managed by initialization) ---
embedding_model = None
faiss_index = None
conversations_data = [] # Holds the list of conversation dicts from JSON
is_initialized = False

def _normalize_question(question_text: str) -> str:
    """Normalizes a question string."""
    if not isinstance(question_text, str):
        return ""
    normalized_q = question_text.strip()
    if normalized_q.startswith("#"):
        normalized_q = normalized_q[1:].strip()
    return normalized_q # Keeping it case-sensitive for now for embeddings

def _get_embedding(text: str) -> np.ndarray:
    """Generates an embedding for the given text."""
    global embedding_model
    if embedding_model is None:
        # This should ideally be handled by ensure_initialized, but as a fallback.
        print("Error: Embedding model not initialized.")
        return None
    # Ensure text is a list for sentence_transformers batch processing, even if it's a single string
    embeddings = embedding_model.encode([text], convert_to_numpy=True)
    return embeddings[0] # Return the first (and only) embedding

def _load_conversations_from_json():
    """Loads conversation data from the JSON file."""
    global conversations_data
    if not os.path.exists(CONVERSATION_HISTORY_FILE):
        conversations_data = []
        return
    try:
        if os.path.getsize(CONVERSATION_HISTORY_FILE) == 0:
            conversations_data = []
            return
        with open(CONVERSATION_HISTORY_FILE, 'r', encoding='utf-8') as f:
            loaded_json = json.load(f)
            if isinstance(loaded_json, list):
                conversations_data = loaded_json
            else: # Handle case where JSON is not a list (e.g. corrupted or single object)
                print(f"Warning: {CONVERSATION_HISTORY_FILE} does not contain a list. Initializing as empty.")
                conversations_data = []
    except json.JSONDecodeError:
        print(f"Warning: JSONDecodeError in {CONVERSATION_HISTORY_FILE}. Initializing as empty.")
        conversations_data = []
    except Exception as e:
        print(f"Error loading conversation history from {CONVERSATION_HISTORY_FILE}: {e}")
        conversations_data = []

def _save_conversations_to_json():
    """Saves current conversation data to the JSON file."""
    global conversations_data
    try:
        os.makedirs(os.path.dirname(CONVERSATION_HISTORY_FILE), exist_ok=True)
        with open(CONVERSATION_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(conversations_data, f, indent=4)
    except Exception as e:
        print(f"Error saving conversation history to {CONVERSATION_HISTORY_FILE}: {e}")

def _search_faiss(normalized_query_text: str, k: int = 1):
    """Internal FAISS search, returns distances, matched_ids or None, None."""
    global faiss_index, embedding_model
    if faiss_index is None or faiss_index.ntotal == 0 or embedding_model is None:
        return None, None

    search_embedding = _get_embedding(normalized_query_text)
    if search_embedding is None: return None, None

    search_embedding_normalized = search_embedding.astype('float32').reshape(1, -1)
    faiss.normalize_L2(search_embedding_normalized)

    try:
        return faiss_index.search(search_embedding_normalized, k=k)
    except Exception as e:
        print(f"Error during FAISS search: {e}")
        return None, None

def _load_or_build_faiss_index():
    """Loads FAISS index from disk or builds it if not present or outdated."""
    global faiss_index, conversations_data, embedding_model
    
    os.makedirs(FAISS_INDEX_DIR, exist_ok=True)

    if embedding_model is None: # Should not happen if ensure_initialized is called
        print("Critical Error: Embedding model not available for FAISS index.")
        return

    dimension = embedding_model.get_sentence_embedding_dimension()
    
    if os.path.exists(FAISS_INDEX_FILE):
        try:
            print(f"Loading FAISS index from {FAISS_INDEX_FILE}...")
            faiss_index = faiss.read_index(FAISS_INDEX_FILE)
            print(f"FAISS index loaded with {faiss_index.ntotal} vectors.")
            # Simplistic check: if number of items in JSON is vastly different, rebuild.
            # A more robust check might involve storing metadata or versioning.
            if abs(faiss_index.ntotal - len(conversations_data)) > len(conversations_data) * 0.1: # e.g. > 10% discrepancy
                 print("Significant discrepancy between FAISS index size and JSON data. Rebuilding index.")
                 faiss_index = None # Force rebuild
            elif faiss_index.d != dimension:
                 print(f"FAISS index dimension mismatch (Index: {faiss_index.d}, Model: {dimension}). Rebuilding index.")
                 faiss_index = None # Force rebuild
        except Exception as e:
            print(f"Error loading FAISS index: {e}. Rebuilding index.")
            faiss_index = None

    if faiss_index is None:
        print("Building new FAISS index...")
        # Using IndexIDMap to map FAISS's internal sequential IDs to our conversation IDs
        # Using IndexFlatL2 for exact search. For normalized vectors, L2 distance relates to cosine similarity.
        index_l2 = faiss.IndexFlatL2(dimension)
        faiss_index = faiss.IndexIDMap(index_l2)
        
        if not conversations_data:
            print("No conversation data to build FAISS index from.")
        else:
            print(f"Processing {len(conversations_data)} conversations for FAISS index...")
            embeddings_to_add = []
            ids_to_add = []
            for i, conv in enumerate(conversations_data):
                if not isinstance(conv, dict) or "normalized_question" not in conv or "id" not in conv:
                    print(f"Skipping invalid conversation entry at index {i} for FAISS.")
                    continue
                
                question_text = conv.get("normalized_question", conv.get("question")) # Fallback for older data
                if not question_text: # Skip if no question text
                    continue

                emb = _get_embedding(question_text)
                if emb is not None:
                    # Normalize embeddings for cosine similarity using L2 index
                    faiss.normalize_L2(emb.reshape(1, -1)) 
                    embeddings_to_add.append(emb)
                    ids_to_add.append(conv["id"])

            if embeddings_to_add:
                embeddings_np = np.array(embeddings_to_add).astype('float32')
                ids_np = np.array(ids_to_add).astype('int64')
                faiss_index.add_with_ids(embeddings_np, ids_np)
                print(f"FAISS index built with {faiss_index.ntotal} vectors.")
            else:
                print("No valid embeddings generated to add to FAISS index.")

        try:
            faiss.write_index(faiss_index, FAISS_INDEX_FILE)
            print(f"FAISS index saved to {FAISS_INDEX_FILE}")
        except Exception as e:
            print(f"Error saving FAISS index: {e}")

def ensure_initialized():
    """Initializes embedding model, loads JSON data, and loads/builds FAISS index if not already done."""
    global is_initialized, embedding_model
    if is_initialized:
        return
    
    print("Initializing conversation history and semantic search...")
    try:
        embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        print(f"Embedding model '{EMBEDDING_MODEL_NAME}' loaded.")
    except Exception as e:
        print(f"FATAL: Could not load SentenceTransformer model '{EMBEDDING_MODEL_NAME}'. Semantic search disabled. Error: {e}")
        # Semantic search won't work, but basic JSON operations might still be attempted if faiss_index is None.
        # For now, we'll let it proceed and faiss_index ops will fail gracefully or be skipped.
        is_initialized = True # Mark as initialized to avoid retrying model load
        return


    _load_conversations_from_json()
    _load_or_build_faiss_index() # This now relies on embedding_model being loaded.
    is_initialized = True
    print("Initialization complete.")


def add_conversation(question: str, final_answer: str, 
                     deduplication_threshold: float = DEFAULT_SIMILARITY_THRESHOLD_DEDUPLICATION):
    """Adds a new successful conversation, stores normalized question, and updates FAISS index."""
    global conversations_data, faiss_index
    ensure_initialized()

    if not question or not final_answer:
        print("Warning: Attempted to save conversation with missing original question or answer.")
        return

    normalized_question_to_store = _normalize_question(question)
    if not normalized_question_to_store:
        print(f"Warning: Normalized question is empty (Original: '{question}'). Skipping save.")
        return
    
    # --- Deduplication Check ---
    if faiss_index is not None and faiss_index.ntotal > 0 and embedding_model is not None:
        distances_sq, matched_indices = _search_faiss(normalized_question_to_store)
        if matched_indices is not None and len(matched_indices) > 0 and matched_indices[0][0] != -1:
            distance_sq = distances_sq[0][0]
            cosine_similarity = 1 - (distance_sq / 2)
            if cosine_similarity >= deduplication_threshold:
                existing_id = matched_indices[0][0]
                # Find the existing question text for logging
                existing_q_text = "N/A"
                for conv_entry in conversations_data:
                    if isinstance(conv_entry, dict) and conv_entry.get("id") == existing_id:
                        existing_q_text = conv_entry.get("normalized_question", "N/A")
                        break
                print(f"Skipping save: New question '{normalized_question_to_store}' is too similar (Similarity: {cosine_similarity:.4f} >= {deduplication_threshold}) to existing Q ID {existing_id} ('{existing_q_text}').")
                return # Do not add
    # --- End Deduplication Check ---

    embedding = _get_embedding(normalized_question_to_store)
    if embedding is None and faiss_index is not None: # Only an issue if FAISS is active
        print(f"Warning: Could not generate embedding for '{normalized_question_to_store}'. FAISS index will not be updated for this entry.")
        # Note: JSON will still be saved.

    # Determine new ID
    new_id = 1
    if conversations_data:
        valid_ids = [c.get("id", 0) for c in conversations_data if isinstance(c, dict) and "id" in c]
        if valid_ids:
             new_id = max(valid_ids) + 1
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    new_entry = {
        "id": new_id,
        "timestamp": timestamp,
        "normalized_question": normalized_question_to_store,
        # "original_question": question, # Optionally store for display
        "final_answer": final_answer
        # We are NOT storing the embedding vector in the JSON anymore. FAISS handles it.
    }
    
    conversations_data.append(new_entry)
    _save_conversations_to_json() # Save to JSON first

    # Add to FAISS index if available
    if faiss_index is not None and embedding is not None:
        try:
            # Normalize embedding before adding (L2 norm = 1)
            embedding_normalized = embedding.astype('float32').reshape(1, -1)
            faiss.normalize_L2(embedding_normalized)
            
            faiss_index.add_with_ids(embedding_normalized, np.array([new_id], dtype=np.int64))
            faiss.write_index(faiss_index, FAISS_INDEX_FILE) # Save index after adding
            print(f"FAISS index updated with new entry (ID: {new_id}). Total items: {faiss_index.ntotal}")
        except Exception as e:
            print(f"Error updating FAISS index for new entry (ID: {new_id}): {e}")

    log_q_display = f"'{normalized_question_to_store}'"
    if question.strip() != normalized_question_to_store:
        log_q_display = f"'{normalized_question_to_store}' (Original: '{question.strip()}')"
    print(f"Conversation saved (ID: {new_id}, Q: {log_q_display}) to {CONVERSATION_HISTORY_FILE}")


def find_conversation_by_question(question: str, similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD_RETRIEVAL):
    """
    Finds a conversation by semantic similarity of the question using FAISS.
    Returns the final answer if a sufficiently similar match is found, otherwise None.
    """
    ensure_initialized()

    if not question:
        return None
        
    normalized_search_question = _normalize_question(question)
    if not normalized_search_question:
        print(f"Info: Normalized search question is empty (Original: '{question}'). No search performed.")
        return None

    if faiss_index is None or faiss_index.ntotal == 0 or embedding_model is None:
        if faiss_index is None: print("FAISS index not available for search.")
        elif faiss_index.ntotal == 0: print("FAISS index is empty. No items to search.")
        if embedding_model is None: print("Embedding model not available for search.")
        return None # Cannot perform semantic search

    search_embedding = _get_embedding(normalized_search_question)
    if search_embedding is None:
        print("Could not generate embedding for search query. No search performed.")
        return None

    # Normalize search embedding (L2 norm = 1)
    search_embedding_normalized = search_embedding.astype('float32').reshape(1, -1)
    faiss.normalize_L2(search_embedding_normalized)

    try:
        # D: distances (squared L2), I: indices (our conversation IDs)
        distances_sq, matched_indices = faiss_index.search(search_embedding_normalized, k=1)
    except Exception as e:
        print(f"Error during FAISS search: {e}")
        return None

    if len(matched_indices) == 0 or matched_indices[0][0] == -1 : # -1 can mean no result for some index types
        print("No match found in FAISS index.")
        return None

    matched_id = matched_indices[0][0]
    distance_sq = distances_sq[0][0]
    
    # For L2-normalized vectors, cosine_similarity = 1 - (L2_distance^2 / 2)
    cosine_similarity = 1 - (distance_sq / 2)

    print(f"Semantic search: Closest match ID {matched_id}, Cosine Similarity: {cosine_similarity:.4f} (Threshold: {similarity_threshold})")

    if cosine_similarity >= similarity_threshold:
        # Find the conversation in our loaded JSON data by ID
        for conv_entry in conversations_data: # Could be optimized with a dict lookup if IDs are dense and list is large
            if isinstance(conv_entry, dict) and conv_entry.get("id") == matched_id:
                print(f"Found sufficiently similar previous answer (ID: {matched_id}, Similarity: {cosine_similarity:.4f}). Question: '{conv_entry.get('normalized_question')}'")
                return conv_entry.get("final_answer")
        print(f"Warning: Matched ID {matched_id} from FAISS not found in current conversations_data. Data inconsistency?")
    else:
        print(f"Match found (ID: {matched_id}) but similarity {cosine_similarity:.4f} is below threshold {similarity_threshold}.")
        
    return None

# --- Basic Test/Initialization hook ---
# You would call ensure_initialized() from your agent.py once at startup,
# or it will be called lazily on first use of add_conversation or find_conversation_by_question.
if __name__ == '__main__':
    print("Running standalone conversation_history.py (for testing/manual init)...")
    ensure_initialized() # Load / Build index

    # Example Usage:
    if is_initialized and embedding_model is not None and faiss_index is not None:
        print("\n--- Example Usage ---")
        test_q1 = "What is the current weather in London?"
        test_q2 = "Tell me about London's weather today."
        test_q3 = "How is the weather in Paris now?"
        ans_q1 = "It's sunny in London."

        # Clean slate for this specific test run
        # print("Resetting data for test run...")
        # conversations_data = [] 
        # if os.path.exists(FAISS_INDEX_FILE): os.remove(FAISS_INDEX_FILE)
        # faiss_index = None # Force rebuild
        # ensure_initialized() # Re-init with empty
        # _save_conversations_to_json() # Save empty state

        print(f"\n1. Adding: '{test_q1}' -> '{ans_q1}'")
        add_conversation(test_q1, ans_q1)
        
        print(f"\n2. Finding: '{test_q1}' (exact)")
        found_ans = find_conversation_by_question(test_q1)
        print(f"Result: {found_ans}")
        assert found_ans == ans_q1

        print(f"\n3. Finding: '{test_q2}' (semantically similar)")
        found_ans_similar = find_conversation_by_question(test_q2)
        print(f"Result: {found_ans_similar}")
        # This assertion depends on the model and threshold; it might or might not match.
        # For a good model and reasonable threshold, it should.
        if found_ans_similar is not None:
             assert found_ans_similar == ans_q1
        else:
            print("Similar question did not meet threshold or no match.")


        print(f"\n4. Finding: '{test_q3}' (different topic)")
        found_ans_different = find_conversation_by_question(test_q3)
        print(f"Result: {found_ans_different}")
        assert found_ans_different is None
        
        print("\n--- Example Test with '#'-prefixed question ---")
        test_q_hash = "#What is the current weather in London?"
        print(f"Finding: '{test_q_hash}' (semantically same as Q1, with hash)")
        found_ans_hash = find_conversation_by_question(test_q_hash)
        print(f"Result: {found_ans_hash}")
        if found_ans_hash is not None:
            assert found_ans_hash == ans_q1
        else:
            print("Hash-prefixed question did not meet threshold or no match (should have).")

        print("\n--- Test complete ---")
        # You might want to clean up the created files after testing:
        # if os.path.exists(CONVERSATION_HISTORY_FILE): os.remove(CONVERSATION_HISTORY_FILE)
        # if os.path.exists(FAISS_INDEX_FILE): os.remove(FAISS_INDEX_FILE)
    else:
        print("Initialization failed (likely embedding model issue). Cannot run example usage.")
