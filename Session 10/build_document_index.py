import asyncio
import sys
import os
from pathlib import Path

def print_status(message):
    """Print a stylized status message"""
    print(f"\n{'='*50}")
    print(f"  {message}")
    print(f"{'='*50}\n")

async def build_document_index():
    """Build the document index needed for RAG search"""
    print_status("Building document index for simulation...")
    
    # Import the necessary module
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.append(current_dir)
    
    try:
        # Create a symbolic link to models.py in the root directory if it doesn't exist
        mcp_server_dir = os.path.join(current_dir, "mcp_servers")
        models_source = os.path.join(mcp_server_dir, "models.py")
        models_target = os.path.join(current_dir, "models.py")
        
        # Check if models.py exists in mcp_servers directory
        if os.path.exists(models_source):
            print(f"Found models.py in {mcp_server_dir}")
            
            # Copy models.py to the current directory to fix import issues
            if not os.path.exists(models_target):
                with open(models_source, 'r') as source_file:
                    models_content = source_file.read()
                    
                with open(models_target, 'w') as target_file:
                    target_file.write(models_content)
                print(f"Created temporary copy of models.py in {current_dir}")
        else:
            print(f"WARNING: models.py not found in {mcp_server_dir}")
            print("Creating a minimal models.py file...")
            
            # Create a minimal models.py file with just the needed classes
            with open(models_target, 'w') as f:
                f.write("""
from pydantic import BaseModel, Field
from typing import List

class SearchDocumentsInput(BaseModel):
    query: str

class UrlInput(BaseModel):
    url: str

class FilePathInput(BaseModel):
    file_path: str

class MarkdownOutput(BaseModel):
    markdown: str
""")
        
        # Now import the modules
        from mcp_servers.mcp_server_2 import process_documents, ensure_faiss_ready
        
        # Create faiss_index directory if needed
        faiss_dir = Path("mcp_servers/faiss_index")
        faiss_dir.mkdir(exist_ok=True, parents=True)
        
        # Process the documents
        print("Starting document processing...")
        process_documents()
        
        # Verify the index was created
        index_path = Path("mcp_servers/faiss_index/index.bin")
        meta_path = Path("mcp_servers/faiss_index/metadata.json")
        
        if index_path.exists() and meta_path.exists():
            print_status("Document index successfully built!")
            print(f"Index file created: {index_path}")
            print(f"Metadata file created: {meta_path}")
        else:
            print_status("WARNING: Index files were not created!")
            print("Please check for errors above.")
        
        # Clean up the temporary models.py file
        if os.path.exists(models_target):
            os.remove(models_target)
            print("Cleaned up temporary models.py file")
    
    except Exception as e:
        print_status(f"ERROR: Failed to build document index")
        print(f"Exception: {str(e)}")
        
        # Clean up the temporary models.py file
        if 'models_target' in locals() and os.path.exists(models_target):
            os.remove(models_target)
            print("Cleaned up temporary models.py file")
        
        return False
    
    return True

if __name__ == "__main__":
    success = asyncio.run(build_document_index())
    if success:
        print("\nYou can now run the simulator with: python tool_performance_simulator.py")
    else:
        print("\nPlease fix the issues before running the simulator.") 