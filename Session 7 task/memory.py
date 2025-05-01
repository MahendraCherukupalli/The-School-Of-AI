import numpy as np
import faiss
import requests
from typing import List, Dict, Any
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Constants moved from streamlit_app.py
EMBED_URL = "http://localhost:1234/v1/embeddings"
EMBED_MODEL = "text-embedding-nomic-embed-text-v1.5"
CHUNK_SIZE = 256
CHUNK_OVERLAP = 40
EMBED_DIM = 768

class MemoryManager:
    """Manages the vector store (FAISS) and metadata for video transcripts."""

    def __init__(self):
        """Initializes the FAISS index and metadata store."""
        self.index = faiss.IndexFlatL2(EMBED_DIM)
        self.metadata_store: List[Dict[str, Any]] = []
        logging.info("MemoryManager initialized with empty FAISS index and metadata store.")

    def _get_embedding(self, text: str) -> np.ndarray | None:
        """Gets the embedding for a given text using the configured service."""
        try:
            response = requests.post(
                EMBED_URL,
                json={
                    'model': EMBED_MODEL,
                    'input': text
                }
            )
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            embedding_data = response.json()["data"]
            if embedding_data and "embedding" in embedding_data[0]:
                 return np.array(embedding_data[0]["embedding"], dtype=np.float32)
            else:
                logging.error(f"Unexpected response format from embedding service: {response.json()}")
                return None
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to get embedding: {e}")
            return None
        except Exception as e:
            logging.error(f"An unexpected error occurred during embedding: {e}")
            return None


    def _chunk_text(self, text: str) -> List[str]:
        """Chunks the text into smaller segments."""
        words = text.split()
        chunks = []
        for i in range(0, len(words), CHUNK_SIZE - CHUNK_OVERLAP):
            chunk = ' '.join(words[i:i + CHUNK_SIZE])
            chunks.append(chunk)
        return chunks

    def add_document(self, video_id: str, transcript_text: str) -> bool:
        """Chunks, embeds, and adds a document's transcript to the memory."""
        logging.info(f"Adding document for video_id: {video_id}")
        if not transcript_text:
            logging.warning(f"Transcript text is empty for video_id: {video_id}. Skipping.")
            return False

        chunks = self._chunk_text(transcript_text)
        added_count = 0
        for chunk in chunks:
            embedding = self._get_embedding(chunk)
            if embedding is not None and embedding.shape[0] == EMBED_DIM:
                try:
                    # FAISS expects a 2D array (batch_size, dim)
                    embedding_batch = np.array([embedding]).astype('float32')
                    self.index.add(embedding_batch)
                    self.metadata_store.append({
                        'text': chunk,
                        'video_id': video_id
                    })
                    added_count += 1
                except Exception as e:
                    logging.error(f"Failed to add chunk to FAISS index: {e}")
            else:
                 logging.warning(f"Skipping chunk due to embedding error or dimension mismatch for video_id: {video_id}.")


        logging.info(f"Successfully added {added_count}/{len(chunks)} chunks for video_id: {video_id}. Total index size: {self.index.ntotal}")
        return added_count > 0


    def retrieve(self, query: str, k: int = 3) -> List[str]:
        """Retrieves the top k relevant text chunks for a given query."""
        if self.index.ntotal == 0:
            logging.warning("Attempted to retrieve from an empty index.")
            return []

        logging.info(f"Retrieving top {k} chunks for query: '{query[:50]}...'")
        query_vector = self._get_embedding(query)

        if query_vector is None or query_vector.shape[0] != EMBED_DIM :
            logging.error("Failed to get valid embedding for the query. Cannot retrieve.")
            return []

        try:
            # Ensure query_vector is 2D for FAISS search
            query_batch = np.array([query_vector]).astype('float32')
            distances, indices = self.index.search(query_batch, k)

            results = []
            for i, idx in enumerate(indices[0]):
                # FAISS returns -1 for indices if fewer than k results are found
                if idx != -1 and idx < len(self.metadata_store):
                    results.append(self.metadata_store[idx]['text'])
                    logging.debug(f"Retrieved chunk index {idx} with distance {distances[0][i]}")
                else:
                    # Handle cases where FAISS returns fewer results than k or invalid index
                    logging.debug(f"Invalid index {idx} returned by FAISS search or index out of bounds.")


            logging.info(f"Retrieved {len(results)} relevant chunks.")
            return results
        except Exception as e:
            logging.error(f"An error occurred during FAISS search: {e}")
            return []

    def clear_memory(self):
        """Resets the FAISS index and metadata store."""
        self.index = faiss.IndexFlatL2(EMBED_DIM)
        self.metadata_store = []
        logging.info("Memory cleared. FAISS index and metadata store reset.")

    def get_status(self) -> Dict[str, Any]:
        """Returns the current status of the memory manager."""
        return {
            "index_size": self.index.ntotal,
            "metadata_count": len(self.metadata_store),
            "embedding_dimension": EMBED_DIM,
            "is_trained": self.index.is_trained,
        }
