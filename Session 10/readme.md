# Tool Performance Simulator

This tool allows you to test the agentic assistant against a batch of queries and gather performance metrics on the tools used.

## Setup

1. Make sure all dependencies are installed:
   ```
   pip install -r requirements.txt
   ```

2. Ensure your environment variables are set, especially `GEMINI_API_KEY`.

3. Build the document index for RAG search (only needed once or when documents change):
   ```
   python build_document_index.py
   ```

## Running the Simulator

1. Configure the settings at the top of `tool_performance_simulator.py`:
   - `MAX_QUERIES`: Number of queries to run (set to `None` for all)
   - `START_INDEX`: Which query to start with in the list
   - `AUTO_HITL`: Set to `True` to handle common failures automatically before asking the user
   - `MAX_AUTO_HITL_ATTEMPTS`: Maximum number of automatic HITL attempts before asking the user
   - `SLEEP_SECONDS`: Time to wait between queries (to avoid API rate limits)
   - `FORCE_TOOL_USE`: Forces the agent to use tools even for simple queries (set to `True` to test all tools)
   - `SKIP_COMPLETED`: Skip queries that were already processed successfully (set to `False` to reprocess everything)
   - `RESET_STATS`: Reset tool statistics at the beginning of each run (set to `False` to accumulate stats)
   - `CLEAR_PREVIOUS_RESULTS`: Clear previous result files before starting a new run (creates backups)

2. Run the simulator:
   ```
   python tool_performance_simulator.py
   ```

3. The simulator will attempt to automatically handle HITL requests up to MAX_AUTO_HITL_ATTEMPTS times. If the automatic responses don't resolve the issue, you'll be prompted to provide responses manually.

## Output Files

The simulator generates several output files:

- **tool_performance_log.csv**: Statistics on each tool's usage and success rate
- **query_results.csv**: The queries processed, the plans used, and final answers
- **simulation_summary.csv**: Overall metrics about the simulation run
- **tool_performance_log_[timestamp].csv**: Backup of previous tool statistics when RESET_STATS is enabled
- **query_results_[timestamp].csv**: Backup of previous query results when CLEAR_PREVIOUS_RESULTS is enabled

## Key Features

### Force Tool Use

By default, the simulator forces the agent to use tools even for simple queries that might otherwise be answered directly. This ensures you get comprehensive tool usage statistics.

### Skip Completed Queries

The simulator can skip queries that have already been processed successfully, allowing you to resume a simulation run without repeating work.

### Progressive Auto-HITL

The AUTO_HITL feature automatically provides responses to common HITL requests for a limited number of attempts (default: 2). If the automatic responses don't resolve the issue, the simulator asks for user input. This provides a balance between automation and user control.

The feature automatically handles:

1. Corrects input format for `search_stored_documents` and `search_stored_documents_rag`
2. Suggests simplifications when too many function calls are detected
3. Provides fixes for common errors like invalid await expressions
4. Recommends proper tool usage when undefined tools are referenced
5. Removes await keywords that cause issues with web search tools
6. Fixes type conversion issues (strings vs integers) for math operations
7. Falls back to a generic response for other errors

## Customizing

To modify the query list, edit `queries.csv`. Each query should be in the format:

```
Query
What is 2+2?
What is the factorial of 5?
...
``` 