# 🤖 Agentic AI Project: Modular Cognitive Agent

This project implements a modular AI agent designed to perform calculations and communicate results via email. It follows a cognitive architecture pattern, separating responsibilities into distinct layers. The agent uses Google's Gemini LLM for decision-making, interacts with tools provided by an MCP server (`example2-4.py`), and utilizes Python's asyncio for asynchronous operations.

---

## 🧠 Cognitive Architecture

The agent is structured into the following modules:

| Module        | Description |
|---------------|-------------|
| **`main.py`** | Orchestrates the agent's lifecycle, collects user preferences, manages the main loop, and handles setup/teardown. |
| **`memory.py`** | Defines the agent's state (`AppState`) using Pydantic, stores iteration history and user preferences, and constructs the prompt context for the LLM. |
| **`decision.py`** | Interacts with the Gemini LLM (`generate_with_timeout`) using the context from `memory.py` to decide the next action. |
| **`perception.py`** | Parses the LLM's response (e.g., `FUNCTION_CALL`), structures parameters for tool calls based on tool schemas, and formats tool results into strings for memory. |
| **`action.py`** | Executes the decided action by calling the appropriate tool on the MCP server via the MCP session, handling errors during execution. |
| **`example2-4.py`** | (MCP Server) Provides the actual tools (functions) that the agent can execute, such as mathematical operations and email sending. |

---

## 📌 Features

- ✅ Modular agent architecture (Main, Memory, Decision, Perception, Action).
- ✅ Iterative execution loop driven by LLM decisions.
- ✅ State management with iteration history using Pydantic.
- ✅ Collection of user preferences (name, email subject) at runtime.
- ✅ Integration with Google Gemini LLM for reasoning and tool selection.
- ✅ Interaction with external tools via the MCP.
- ✅ Example tool provider (`example2-4.py`) with calculation and email capabilities.
- ✅ Asynchronous operation using `asyncio`.

---

## 🗂️ Project Structure

```
.
├── main.py           # Orchestrator, runs the agent
├── memory.py         # State management (AppState, history, preferences)
├── decision.py       # LLM interaction and decision logic
├── perception.py     # LLM response parsing, parameter structuring, result formatting
├── action.py         # MCP tool execution logic
├── example2-4.py     # MCP server providing tools (math, email, etc.)
├── mcp/              # Directory for MCP library code (if included)
├── .env              # Environment variables (API keys, email config)
└── README.md         # This file
```

---

## 🧑‍💻 Setup Instructions

### 1. 🔧 Prerequisites

- Python 3.10+ (due to potential asyncio/library features)
- An `.env` file in the root directory with the following variables:
  ```dotenv
  # Required
  GEMINI_API_KEY=YOUR_GEMINI_API_KEY
  RECIPIENT_EMAIL=your_email@example.com

  # Required for sending email via example2-4.py's send_gmail tool
  GMAIL_USER=your_gmail_address@gmail.com
  GMAIL_PASSWORD=your_gmail_app_password 
  # Note: Use an App Password if you have 2FA enabled on your Gmail account.
  ```

### 2. 📦 Required Packages

Install the necessary Python libraries:

```bash
pip install google-generativeai python-dotenv mcp pydantic Pillow pywinauto pywin32
# Add any other specific dependencies required by example2-4.py
```
*(Note: `Pillow`, `pywinauto`, `pywin32` are likely needed by `example2-4.py` based on previous reviews)*

---

## 🚀 Running the Agent

Execute the main script from your terminal:

```bash
python main.py
```

### 🧾 Preference Prompts

The agent will first ask for the following preferences:

- **Your name for the email greeting?** (Used to personalize the email body)
- **Preferred email subject? (Optional)** (Used as the subject line for the results email; if skipped, a default subject is generated)

These preferences are included in the context provided to the LLM for its decision-making process.

---

## 🔁 Agent Behavior

1.  **Preference Collection:** Starts by asking for user's name and optional email subject.
2.  **Initialization:** Connects to the MCP server (`example2-4.py`), retrieves the list of available tools, and initializes the agent's state.
3.  **Iteration Loop:**
    *   **Decision:** Sends the current context (including preferences and history) to the Gemini LLM to get the next action (usually a `FUNCTION_CALL`).
    *   **Action:** Executes the requested tool via the MCP protocol.
    *   **Memory Update:** Records the LLM response, action taken, and result (or error) in the state.
4.  **Termination:** The loop stops if the email is successfully sent, an unrecoverable error occurs, or the maximum number of iterations is reached.

---

## 📄 Example Task Flow

**Initial Query:**
> "Calculate ASCII values for INDIA, find sum of their exponentials, and send the result via email."

**Agent Flow Example:**
1.  LLM decides to call `strings_to_chars_to_int('INDIA')`.
2.  Agent executes tool, gets result `[73, 78, 68, 73, 65]`.
3.  LLM (seeing previous result) decides to call `int_list_to_exponential_sum([73, 78, 68, 73, 65])`.
4.  Agent executes tool, gets the numerical sum.
5.  LLM (seeing the sum and user preferences) decides to call the email tool (e.g., `send_gmail`), constructing the `subject` (using the preferred subject or generating one) and `body` (using the user's name for greeting and including the final sum).
6.  Agent executes the email tool.
7.  Agent detects successful email sending and terminates.

---

## 🧠 Memory / Context Example

Part of the context sent to the LLM before deciding Step 3 might look like:

```
--- User Preferences ---
User Name for Greeting: Mahendra
Preferred Email Subject: Project Results
------------------------

You are a calculator assistant...

Available tools:
1. add(a: int, b: int) - Add two numbers
...
15. strings_to_chars_to_int(string: str) - Return the ASCII values...
16. int_list_to_exponential_sum(int_list: list) - Return sum of exponentials...
17. send_gmail(recipient: str, subject: str, body: str) - Send an email...
...

Initial Query: Calculate ASCII values for INDIA, find sum of their exponentials, and send the result via email

--- History ---
Previous Action: ParsedFunctionCall(func_name='strings_to_chars_to_int', raw_params=['INDIA'])
Previous Result: [73, 78, 68, 73, 65]

What should I do next based on the previous result/error and user preferences?
```

---