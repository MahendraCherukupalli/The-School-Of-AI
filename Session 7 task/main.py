import streamlit as st
import time
import numpy as np
import requests
import faiss  # Keep faiss import if MemoryManager uses it directly
import logging
from typing import Dict, List
import html # <--- Step 1: Import the html module
import json       # <-- Add import
import hashlib    # <-- Add import
from pathlib import Path # <-- Add import

# --- Project Modules ---
from memory import MemoryManager
from perception import extract_perception
from decision import generate_plan
from action import execute_action
# models.py is used by the above modules, but maybe not directly here

# --- External Libraries ---
from youtube_search import YoutubeSearch # Corrected import based on original script usage
from youtube_transcript_api import YouTubeTranscriptApi

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Cache Configuration ---
CACHE_DIR = Path("topic_cache") # Define base cache directory name
CACHE_DIR.mkdir(exist_ok=True) # Create the directory if it doesn't exist

# --- Streamlit Page Config ---
# Should be the first Streamlit command
st.set_page_config(page_title="TubeTalk AI", layout="centered", initial_sidebar_state="collapsed")

# Immediate CSS to remove top spacing
st.markdown('''
<style>
    /* Reduced CSS for brevity - Copy the full CSS from streamlit_app.py if needed */
    .main .block-container {padding-top: 0rem;}
    .title { text-align: center; color: white; padding-top: 0; padding-bottom: 0.5rem; margin-top: -3rem !important; margin-bottom: 1rem; font-size: 2rem; }
    .chat-title { color: white; font-size: 1.2em; margin: 1rem 0; display: flex; align-items: center; }
    .chat-title::before { content: ''; display: inline-block; width: 4px; height: 24px; background-color: #2E7BF6; margin-right: 10px; border-radius: 2px; }
    .message-row { display: flex; width: 100%; margin: 8px 0; }
    .message-row.user { justify-content: flex-end; }
    .message-row.assistant { justify-content: flex-start; }
    .user-bubble { background-color: #2E7BF6; color: white; padding: 15px 20px; border-radius: 15px; max-width: 85%; word-wrap: break-word; display: inline-block; text-align: left; }
    .assistant-bubble { background-color: #2D2D2D; color: white; padding: 15px 20px; border-radius: 15px; max-width: 85%; word-wrap: break-word; display: inline-block; }
    .chat-container { border: 1px solid #2D2D2D; border-radius: 10px; background-color: #1E1E1E; padding: 15px; margin-bottom: 20px; min-height: 200px; max-height: 600px; width: 100%; overflow-y: auto; transition: height 0.3s ease; box-sizing: border-box; }
    .empty-chat { color: #555; text-align: center; font-style: italic; padding: 30px 0; }
    /* Add other necessary CSS rules from original file (buttons, inputs, expander, etc.) */
    /* Dynamic height classes (.message-count-*) */
    .message-count-1 { height: 200px; } .message-count-2 { height: 250px; } .message-count-3 { height: 300px; } .message-count-4 { height: 350px; } .message-count-5 { height: 400px; } .message-count-6 { height: 450px; } .message-count-7 { height: 500px; } .message-count-8 { height: 550px; } .message-count-9, .message-count-10, .message-count-many { height: 600px; }
    .stButton>button { background-color: #2E7BF6 !important; color: white !important; border: none !important; border-radius: 5px !important; padding: 0.5rem 1rem !important; font-weight: 500 !important; }
    .clear-button button { background-color: rgba(255, 75, 75, 0.1) !important; color: #ff4b4b !important; }
    div[data-testid="stExpander"] { border: 1px solid #2D2D2D; border-radius: 10px; background-color: #1E1E1E; margin: 1rem 0; }
    div[data-testid="stExpander"] > div:first-child { background-color: #1E1E1E; border-bottom: 1px solid #2D2D2D; padding: 8px 15px; }
    div[data-testid="stExpander"] > div:last-child { background-color: #1E1E1E; padding: 15px; }
    div[data-testid="stExpander"] svg { color: #4B8BF5; }
    #MainMenu, footer, header, div[data-testid="stToolbar"] { visibility: hidden; display:none; }
    .stApp { background-color: #1E1E1E; margin-top: 0 !important; padding-top: 0 !important; }
    .stTextInput input { background-color: #2D2D2D; color: white; border: none; border-radius: 20px; padding: 12px 20px; }
    .stTextInput input::placeholder { color: #909090; }
    /* Video Item Styles */
    .video-item { padding: 10px; margin-bottom: 8px; background-color: #252525; border-radius: 8px; }
    .video-title { color: white; font-weight: 500; margin-bottom: 5px; }
    .video-link { color: #4B8BF5; text-decoration: none; font-size: 0.9rem; }
    .video-info { color: #909090; font-size: 0.8rem; }
    .status-message { color: #ccc; margin-top: 5px; } /* Style for status messages */
</style>
''', unsafe_allow_html=True)

# --- Session State Initialization ---
if 'memory_manager' not in st.session_state:
    st.session_state.memory_manager = MemoryManager()
    logging.info("Initialized MemoryManager in session state.")
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'processing_done' not in st.session_state:
    st.session_state.processing_done = False
if 'show_chat' not in st.session_state:
    st.session_state.show_chat = False
if 'processed_videos' not in st.session_state:
    st.session_state.processed_videos = []
if 'show_videos' not in st.session_state:
    st.session_state.show_videos = False
if 'question_input' not in st.session_state:
    st.session_state.question_input = "" # Initialize to prevent errors

# --- Helper Functions (Kept from original script) ---
def convert_duration_to_minutes(duration: str) -> float:
    try:
        parts = duration.split(':')
        if len(parts) == 2: return float(parts[0]) + float(parts[1])/60
        elif len(parts) == 3: return float(parts[0])*60 + float(parts[1]) + float(parts[2])/60
        return 0
    except: return 0

def check_has_transcript(video_id: str) -> bool:
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        return 'en' in [t.language_code for t in transcript_list]
    except Exception as e:
        logging.warning(f"Could not check transcript availability for {video_id}: {e}")
        return False

def get_transcript(video_id: str) -> str:
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        # Attempt to find 'en', then the first available transcript
        target_lang = 'en' if 'en' in [t.language_code for t in transcript_list] else transcript_list.find_generated_transcript(['en']).language_code
        transcript = transcript_list.find_transcript([target_lang]).fetch()
        logging.info(f"Successfully fetched transcript for {video_id} (lang: {target_lang})")
        return ' '.join([entry['text'] for entry in transcript])
    except Exception as e:
        logging.error(f"Failed to get transcript for {video_id}: {e}")
        return ""

def search_youtube(query: str, max_results: int = 30):
    """Searches YouTube, filters by duration/transcript, sorts by views/duration."""
    logging.info(f"Searching YouTube for: '{query}'")
    try:
        # Using youtube-search-python based on original streamlit_app.py import
        # Note: Original app used 'YoutubeSearch', ensure library consistency
        results_raw = YoutubeSearch(query, max_results=max_results).to_dict()

        eligible_videos = []
        for video in results_raw:
            video_id = video.get('id')
            duration_str = video.get('duration')
            if not video_id or not duration_str:
                 logging.debug(f"Skipping video due to missing id/duration: {video.get('title')}")
                 continue

            duration_mins = convert_duration_to_minutes(duration_str)

            # Check duration and transcript availability
            if 10 <= duration_mins <= 30 and check_has_transcript(video_id):
                views_str = video.get('views', '0 views').lower().replace('views', '').replace(',', '').strip()
                try:
                    views = int(views_str) if views_str else 0
                except ValueError:
                    views = 0

                eligible_videos.append({
                    'id': video_id,
                    'title': video['title'],
                    'duration': duration_str,
                    'duration_mins': duration_mins,
                    'url': f"https://youtube.com{video.get('url_suffix','')}",
                    'views': views
                })
            else:
                logging.debug(f"Skipping video (duration/transcript mismatch): {video.get('title')}")


        if not eligible_videos:
            logging.warning("No eligible videos found after filtering.")
            return []

        # Sort and select top videos
        most_viewed = sorted(eligible_videos, key=lambda x: x['views'], reverse=True)[:10]
        final_videos = sorted(most_viewed, key=lambda x: x['duration_mins'], reverse=True)[:2] # Get top 2 longest among most viewed
        logging.info(f"Selected {len(final_videos)} final videos for processing.")
        return final_videos

    except Exception as e:
        logging.error(f"Error during YouTube search: {e}")
        st.error(f"An error occurred during YouTube search: {e}")
        return []

def clear_chat():
    """Clears only the chat messages and hides the chat display."""
    st.session_state.messages = []
    st.session_state.show_chat = False
    st.session_state.question_input = "" # Clear the input field as well
    logging.info("Chat messages cleared.")
    # No need to clear memory_manager, processed_videos, processing_done, show_videos

def get_topic_cache_path(topic: str) -> Path | None:
    """Normalizes, hashes a topic, and returns its cache directory Path."""
    if not topic:
        return None
    # Normalize: lowercase, strip whitespace
    normalized_topic = topic.lower().strip()
    # Hash: using md5 for simplicity, ensure it's filesystem-safe
    topic_hash = hashlib.md5(normalized_topic.encode()).hexdigest()
    # Return the specific path within the base cache directory
    return CACHE_DIR / topic_hash

# --- Q&A Handling (Uses new modules) ---
def handle_question():
    """Callback function for chat input. Processes question using modular pipeline."""
    question = st.session_state.question_input
    if not question:
        return # Do nothing if input is empty

    logging.info(f"Handling question: '{question[:50]}...'")
    st.session_state.show_chat = True
    st.session_state.messages.append({"role": "user", "content": question})

    # Modular Pipeline
    perception = extract_perception(question)
    retrieved_chunks = st.session_state.memory_manager.retrieve(perception.user_input)
    plan = generate_plan(perception, retrieved_chunks)
    final_answer = execute_action(plan)

    st.session_state.messages.append({"role": "assistant", "content": final_answer})

    # Clear the input field after processing
    # Setting the key directly is more reliable than relying on Streamlit's internal reset
    st.session_state.question_input = ""
    # We might need st.rerun() here if the input doesn't clear visually

# --- Main Streamlit UI ---
with st.container():
    # Title
    st.markdown('<h1 class="title">TubeTalk AI</h1>', unsafe_allow_html=True)

    # Topic Search Input
    topic = st.text_input("", placeholder="Enter topic to search on YouTube", key="search_input", label_visibility="collapsed")

    # Search Button & Processing Logic
    if st.button("Search Videos", use_container_width=True, key="search_button"):
        if not topic:
            st.warning("Please enter a topic to search")
        else:
            # --- Caching Logic Start ---
            topic_cache_path = get_topic_cache_path(topic)
            if topic_cache_path: # Check if path generation was successful
                index_file = topic_cache_path / "index.bin"
                metadata_file = topic_cache_path / "metadata.json"
                videos_file = topic_cache_path / "videos.json"

                # Check if all necessary cache files exist
                if index_file.exists() and metadata_file.exists() and videos_file.exists():
                    logging.info(f"Cache hit for topic: '{topic}' (hash: {topic_cache_path.name})")
                    st.info(f"Loading cached results for '{topic}'...")

                    try:
                        # Clear previous chat/state BUT keep the memory manager instance for now
                        st.session_state.messages = []
                        st.session_state.show_chat = False
                        st.session_state.question_input = ""
                        # We will replace the memory manager below

                        # Load data from cache
                        with open(videos_file, 'r') as f:
                            st.session_state.processed_videos = json.load(f)
                        with open(metadata_file, 'r') as f:
                            loaded_metadata = json.load(f)
                        loaded_index = faiss.read_index(str(index_file))

                        # Create a new MemoryManager and populate it with loaded data
                        loaded_memory_manager = MemoryManager()
                        loaded_memory_manager.index = loaded_index
                        loaded_memory_manager.metadata_store = loaded_metadata

                        # Replace the session state memory manager
                        st.session_state.memory_manager = loaded_memory_manager

                        # Update UI state
                        st.session_state.processing_done = True
                        st.session_state.show_videos = True

                        logging.info(f"Successfully loaded cache for topic '{topic}'. Index size: {loaded_index.ntotal}")
                        st.success(f"Loaded cached results for '{topic}'. Ask your questions below.")
                        time.sleep(1) # Brief pause to show success message
                        st.rerun() # Rerun to update the UI fully

                    except Exception as e:
                        logging.error(f"Failed to load cache for topic '{topic}': {e}", exc_info=True)
                        st.error(f"Error loading cached data for '{topic}'. Re-processing...")
                        # Clear potentially corrupted state before proceeding to re-process
                        clear_chat() # Use the corrected clear_chat which clears only chat state
                        st.session_state.processed_videos = []
                        st.session_state.processing_done = False
                        st.session_state.show_videos = False
                        # Ensure a fresh memory manager for reprocessing
                        st.session_state.memory_manager = MemoryManager()
                        # Fall through to the cache miss logic below


                else:
                    # --- Cache Miss Logic ---
                    logging.info(f"Cache miss for topic: '{topic}'. Starting processing...")
                    # Existing logic starts here...
                    # Ensure we start with a clean slate for this topic
                    clear_chat() # Clears only chat state now
                    st.session_state.processed_videos = []
                    st.session_state.processing_done = False
                    st.session_state.show_videos = False
                    # Ensure a fresh MemoryManager instance for the new topic processing
                    st.session_state.memory_manager = MemoryManager()

                    progress_container = st.container()

                    try:
                        with progress_container:
                            progress_bar = st.progress(0)
                            status_placeholder = st.empty()
                            status_placeholder.markdown('<div class="status-message">🔍 Searching YouTube...</div>', unsafe_allow_html=True)

                            # Step 1: Search YouTube (existing code)
                            videos_to_process = search_youtube(topic)
                            progress_bar.progress(25)

                            if not videos_to_process:
                                status_placeholder.error("No suitable videos found matching criteria (10-30 min, English transcript). Please try a different topic.")
                                progress_bar.empty()
                            else:
                                st.session_state.processed_videos = videos_to_process
                                num_videos = len(videos_to_process)
                                processing_successful = True # Flag to track if all videos processed okay

                                for i, video in enumerate(videos_to_process):
                                    current_progress = 25 + int(((i + 1) / num_videos) * 75)
                                    status_placeholder.markdown(f'<div class="status-message">📝 Processing video {i+1}/{num_videos}: {video["title"]}...</div>', unsafe_allow_html=True)
                                    progress_bar.progress(min(current_progress, 95))
                                    transcript = get_transcript(video['id'])
                                    if transcript:
                                        success = st.session_state.memory_manager.add_document(video['id'], transcript)
                                        if not success:
                                             logging.warning(f"Failed to add document to memory for video: {video['id']}")
                                    else:
                                         logging.warning(f"Could not retrieve transcript for video: {video['id']} - {video['title']}")
                                         # Consider if missing one transcript should halt caching? For now, we proceed.

                                # --- Caching Logic: Save Results (Inside Cache Miss) ---
                                if st.session_state.memory_manager.index.ntotal > 0: # Only save if we actually added something
                                    logging.info(f"Saving results to cache for topic: '{topic}'")
                                    try:
                                        topic_cache_path.mkdir(parents=True, exist_ok=True) # Ensure directory exists
                                        # Save FAISS index
                                        faiss.write_index(st.session_state.memory_manager.index, str(index_file))
                                        # Save metadata
                                        with open(metadata_file, 'w') as f:
                                            json.dump(st.session_state.memory_manager.metadata_store, f, indent=4) # Added indent for readability
                                        # Save video list
                                        with open(videos_file, 'w') as f:
                                            json.dump(st.session_state.processed_videos, f, indent=4) # Added indent
                                        logging.info(f"Successfully saved cache to {topic_cache_path}")
                                    except Exception as e:
                                        logging.error(f"Failed to save cache for topic '{topic}': {e}", exc_info=True)
                                        st.warning("Could not save results to cache.") # Inform user, but don't block

                                # ... (rest of the existing cache miss UI update: progress bar 100%, status message, state updates, clear progress, rerun) ...
                                progress_bar.progress(100)
                                status_placeholder.markdown('<div class="status-message">✅ Processing complete! Ask your questions below.</div>', unsafe_allow_html=True)
                                st.session_state.processing_done = True
                                st.session_state.show_videos = True
                                time.sleep(2)
                                progress_container.empty()
                                st.rerun()

                    except Exception as e:
                        logging.error(f"Error during video processing: {e}", exc_info=True)
                        st.error(f"An unexpected error occurred during processing: {e}")
                        clear_chat()
                        st.session_state.processed_videos = []
                        st.session_state.processing_done = False
                        st.session_state.show_videos = False
                        st.session_state.memory_manager = MemoryManager() # Reset memory manager on error
                        st.rerun()

            else: # Handle case where topic_cache_path is None (empty topic input, though already checked)
                 st.warning("Cannot generate cache path for empty topic.")


    # --- Videos Dropdown Section ---
    if st.session_state.show_videos and st.session_state.processed_videos:
        expander_title = f"Processed YouTube Videos ({len(st.session_state.processed_videos)})"
        with st.expander(expander_title, expanded=False):
            for i, video in enumerate(st.session_state.processed_videos):
                # Using markdown with CSS classes for styling
                st.markdown(f"""
                <div class="video-item">
                    <div class="video-title">{i+1}. {video['title']}</div>
                    <a href="{video['url']}" class="video-link" target="_blank">{video['url']}</a>
                    <div class="video-info">Duration: {video['duration']} | Views: {video.get('views', 'N/A'):,}</div>
                </div>
                """, unsafe_allow_html=True)


# --- Chat Section ---
if st.session_state.processing_done:
    # Chat Header & Clear Button
    col1, col2 = st.columns([5, 1])
    with col1:
        st.markdown('<div class="chat-title">Ask follow-up questions</div>', unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="clear-button">', unsafe_allow_html=True)
        # The on_click call remains the same, pointing to the corrected function
        if st.button("🗑 Clear", key="clear_chat_button", use_container_width=True, on_click=clear_chat):
             st.rerun() # Keep rerun to update the UI immediately after clearing messages
        st.markdown('</div>', unsafe_allow_html=True)

    # Chat Message Display Area
    if st.session_state.show_chat:
        messages_placeholder = st.container() # Use a container for the chat display

        with messages_placeholder:
            messages_html = ""
            msg_count = len(st.session_state.messages)

            # Determine height class based on message count
            if msg_count == 0:
                messages_html = '<div class="empty-chat">No messages yet. Ask a question!</div>'
                height_class = "message-count-1" # Min height
            else:
                if msg_count <= 8: height_class = f"message-count-{msg_count}"
                else: height_class = "message-count-many" # Max height after 8 messages

                for message in st.session_state.messages:
                    bubble_class = "user-bubble" if message["role"] == "user" else "assistant-bubble"
                    row_class = "user" if message["role"] == "user" else "assistant"
                    # Basic HTML escaping for content display
                    # Use Python's html.escape for safety when building HTML manually
                    escaped_content = html.escape(str(message["content"])) # <--- Step 2: Use html.escape()
                    messages_html += f'<div class="message-row {row_class}"><div class="{bubble_class}">{escaped_content}</div></div>'

            # Display all messages in a scrollable container
            # We use unsafe_allow_html=True here because we constructed the HTML string manually
            st.markdown(f'<div class="chat-container {height_class}">{messages_html}</div>', unsafe_allow_html=True)

    # Chat Input (Uses on_change callback)
    st.text_input("Ask a question:",
                  placeholder="Type your follow-up question here...",
                  key="question_input",
                  label_visibility="collapsed",
                  on_change=handle_question) # handle_question is called when Enter is pressed or focus lost


# --- Debug Info (Optional) ---
# with st.sidebar:
#     st.header("Debug Info")
#     if 'memory_manager' in st.session_state:
#         st.write("Memory Status:", st.session_state.memory_manager.get_status())
#     st.write("Session State:", st.session_state)
