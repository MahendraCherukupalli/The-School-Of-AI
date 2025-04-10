# LLM-Powered Task Orchestration with MCP

This project demonstrates how to use a Large Language Model (LLM) like Google's Gemini to orchestrate tasks by interacting with a Multi-Capability Protocol (MCP) server. The LLM interprets a natural language query, breaks it down into steps, and instructs the client script to call specific tools provided by the MCP server.

## Components

1.  **`example2-3.py` (MCP Server)**
    *   Acts as the MCP server using the `FastMCP` library.
    *   Defines various "tools" that can be called remotely via MCP. These tools include:
        *   Basic Arithmetic (`add`, `subtract`, `multiply`, `divide`)
        *   Advanced Math (`power`, `sqrt`, `factorial`, `log`, trig functions)
        *   List/String Operations (`add_list`, `strings_to_chars_to_int`, `int_list_to_exponential_sum`)
        *   Sequence Generation (`fibonacci_numbers`)
        *   Image Manipulation (`create_thumbnail`)
        *   System Interaction (MS Paint control: `open_paint`, `draw_rectangle`, `add_text_in_paint`)
        *   Communication (`send_gmail`)
    *   Listens for connections from an MCP client.

2.  **`talk2mcp_session5_task.py` (MCP Client & Orchestrator)**
    *   Acts as the MCP client, connecting to the `example2-3.py` server (running it as a subprocess).
    *   Uses the Google Generative AI client (`genai`) to interact with the Gemini LLM.
    *   Retrieves the list of available tools from the MCP server.
    *   Sends a system prompt, the tool list, the user query, and the conversation history to the LLM.
    *   **Orchestration Logic:**
        *   The LLM is prompted to follow a specific TASK FLOW (parse -> calculate -> format -> email).
        *   The LLM must respond with a `FUNCTION_CALL: function_name|param1|param2|...` command.
        *   The script parses this command, validates the function name, prepares arguments based on the tool's schema, and calls the tool on the MCP server.
        *   Handles specific parameter mapping for the `send_gmail` tool.
        *   Captures the result (or error) from the tool call.
        *   Appends the result/error to the conversation history.
        *   Sends the updated history back to the LLM for the next step.
        *   Continues this loop until the task is complete (email sent), an error occurs, or `max_iterations` is reached.
    *   Requires environment variables for configuration.

## Setup

1.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    # Make sure you have the necessary libraries like google-generativeai, python-dotenv, mcp-package, pywinauto, etc.
    # (You might need to create a requirements.txt file if one doesn't exist)
    ```
2.  **Environment Variables:**
    *   Create a `.env` file in the project root directory.
    *   Add your Google Generative AI API key and the recipient email address:
        ```dotenv
        GEMINI_API_KEY="YOUR_API_KEY_HERE"
        RECIPIENT_EMAIL="your_recipient_email@example.com"
        # For send_gmail tool to work:
        GMAIL_APP_PASSWORD="YOUR_GMAIL_APP_PASSWORD"
        SENDER_EMAIL="your_sender_email@gmail.com"
        ```
    *   Note: The `send_gmail` tool in `example2-3.py` requires `SENDER_EMAIL` and `GMAIL_APP_PASSWORD` environment variables to be set up for sending emails via Gmail SMTP. Ensure you have generated an App Password for your Gmail account if using 2-Step Verification.

## Running the Example

1.  Ensure the `.env` file is correctly configured.
2.  Run the orchestrator script from your terminal:
    ```bash
    python talk2mcp_session5_task.py
    ```
3.  The script will:
    *   Start the `example2-3.py` server in the background.
    *   Connect to the server and get the tool list.
    *   Begin the interaction loop with the LLM, using the hardcoded query: *"Calculate ASCII values for INDIA, find sum of their exponentials, and send the result via email"*
    *   Print extensive DEBUG messages showing the LLM responses, function calls, parameters, and tool results.
    *   Eventually, call the `send_gmail` tool to send the final result to the configured recipient email.

## How it Works

The core idea is leveraging the LLM's reasoning capabilities to bridge the gap between a natural language request and a series of concrete API/tool calls. The MCP protocol provides the standardized way for the client and server to communicate about available tools and execute them. The `talk2mcp_session5_task.py` script acts as the "glue", managing the conversation state with the LLM and translating its desired actions into actual MCP tool calls. The structured prompt guides the LLM to perform the task step-by-step.
