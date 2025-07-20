👑 The Master Blueprint: Operation Peacock Memory

This is the whole map, G. How the client, the server, the database, and the AI all connect. This is the strategic overview.
Generated mermaid

      
graph TD
    subgraph "User's World"
        A[🌐 Browser/User]
    end

    subgraph "Remember Web UI (The Front)"
        B(remember_web_ui.py):::fastapi
        B -- "GET /api/databases" --> D
        B -- "POST /api/chat" --> C
        B -- "POST /api/batch_process" --> C
        B -- "Triggers MCP Tools via LLM" --> G
    end

    subgraph "Groq Infrastructure (The Muscle)"
        C(groq_client.py):::groq
        C -- "Manages context" --> F(context_manager.py)
        C -- "Makes resilient API call" --> E(request_router.py)
        E -- "Gets API key" --> H(api_key_manager.py)
        E -- "Gets proxy" --> I(proxy_manager.py)
        E -- "Sends request to" --> J[🔥 Groq API]
    end

    subgraph "Database Layer (The Vault)"
        D(core/database.py):::db
        G(mcp_server.py):::db
        D -- "CRUD ops" --> K[(🗄️ ChromaDB)]
        G -- "Provides tool access to" --> K
    end
    
    subgraph "CLI Operation (The Street Corner)"
        L[💻 Remember CLI]
        L --> M(commands/command_registry.py)
        M -- "Routes to" --> N(commands/legal_handler.py)
        N -- "Uses" --> C
        N -- "Also uses" --> D
    end

    subgraph "Shared Libraries"
        O(core/visuals.py):::lib
        P(master_contexts/*.txt):::lib
    end

    %% Connections & Data Flow
    A --> B
    C --> P
    N --> O

    %% Styling
    classDef fastapi fill:#009485,stroke:#333,stroke-width:2px,color:#fff
    classDef groq fill:#8B4513,stroke:#D2691E,stroke-width:2px,color:#fff
    classDef db fill:#0055A4,stroke:#333,stroke-width:2px,color:#fff
    classDef lib fill:#444,stroke:#666,stroke-width:2px,color:#ccc

    

IGNORE_WHEN_COPYING_START
Use code with caution. Mermaid
IGNORE_WHEN_COPYING_END
Hustle Breakdown: The Crew Roster & Their Roles

Every G in the crew has a job. Here's the breakdown of each file, what it does, who it talks to, and what plays it runs.
Frontend & Main Server
🎛️ remember_web_ui.py

    The Role: This is the fuckin' war room, the command center. It's the FastAPI server that runs the whole UI, takes your clicks, and kicks off the plays. It's the face of the operation.

    Its Connections (Imports):

        Internal (The Crew):

            groq_client: To send the heavy-lifting analysis and chat jobs to the AI.

            core.database: To list databases, files, and import results.

            mcp_server: To expose database functions as tools for the LLM to use.

        External (The Tools): fastapi, uvicorn, pydantic, requests.

    Who Calls It: The user's browser. Every button click, every prompt you type, it hits an endpoint here first.

    Key Plays:

        /api/chat: The main event. Takes your prompt and selected files, builds the context, and sends it to the GroqClient.

        /api/batch_process: For when you need to run the same play on a whole stack of documents at once.

        /api/databases, /api/database/.../files: Lets you browse the vault (ChromaDB) to see what intel you got.

        /: Serves the main HTML page.

Groq Infrastructure Core
🚀 groq_client.py

    The Role: This is your heavy hitter. The orchestrator. It's the top-level interface to the Groq world. You tell it what you want, and it figures out the how, using its crew.

    Its Connections:

        Internal: RequestRouter, ContextManager, ProxyManager (via Router).

    Who Calls It: remember_web_ui.py and legal_handler.py (from the CLI).

    Key Plays:

        auto_process_content(): The go-to move for big jobs. It checks if the content fits, and if not, it automatically tells ContextManager to chop it up into manageable chunks.

        conversation_chat(): Handles back-and-forth chat.

        function_call_chat(): The genius play. It lets the LLM ask for tools (from mcp_server) to get more data before it answers.

🧠 context_manager.py

    The Role: This is your accountant, the one who makes sure you don't overspend your tokens. It knows the limits of each model and will slice up your content so it fits, no questions asked.

    Its Connections:

        External: tiktoken (to count the tokens before you spend 'em).

    Who Calls It: groq_client.py.

    Key Plays:

        prepare_context_for_model(): Checks if your shit's too big for the model's context window.

        smart_chunk_text(): The slicer. It doesn't just cut anywhere; it tries to respect paragraphs so the meaning ain't lost. That's fuckin' gangsta.

🔄 request_router.py

    The Role: The strategist. This motherfucker handles the dirty work. It picks the API key, grabs a proxy, builds the request, and if shit goes sideways (rate limit, network error), it retries the play with a different angle. Bulletproof.

    Its Connections:

        Internal: APIKeyManager, ProxyManager.

        External: requests.

    Who Calls It: groq_client.py.

    Key Plays:

        make_request(): The core execution loop. This is where the retries, the backoff delays, and the error handling live.

        chat_completion(): Formats the payload specifically for a chat request.

🔑 api_key_manager.py

    The Role: The keymaster. It holds all your Groq API keys and deals 'em out like a deck of cards. One gets burned (rate-limited), it deals the next one. Simple, effective.

    Its Connections: None internal. Standard Python libs.

    Who Calls It: request_router.py.

    Key Plays:

        get_next_key(): Deals the next key off the top of the shuffled deck.

        reset_deck(): When you run out of keys, it reshuffles and starts over.

遁 proxy_manager.py

    The Role: The getaway driver. Manages your mobile and residential proxies, checks if they're healthy, and rotates 'em so the feds (or API rate limiters) can't pin you down.

    Its Connections:

        External: requests (to check proxy health).

    Who Calls It: request_router.py.

    Key Plays:

        get_best_proxy(): Pings the proxies to see which one is fastest and healthiest right now.

        get_proxy_for_request(): Gives the requests library the correctly formatted proxy URL to use.

Database & Data Handling
🗄️ core/database.py

    The Role: This is the vault. It's the interface to your ChromaDB. All the intel you extract, all the analysis you save, it goes in and out through here.

    Its Connections:

        External: chromadb.

    Who Calls It: remember_web_ui.py, legal_handler.py, and the mcp_server.py.

    Key Plays:

        import_extraction_session(): Takes the JSON from a URL scrape and packs it neatly into the database with proper vector IDs.

        search_extractions(): The search warrant. You give it a query, it tears through all the collections to find matching documents.

🤖 mcp_server.py

    The Role: The inside man. It exposes functions from the database (get_document_by_id, etc.) as "tools" that the LLM can call. This way, the LLM can ask for more info on its own instead of you having to feed it everything upfront.

    Its Connections:

        Internal: core.database.

        External: chromadb.

    Who Calls It: The GroqClient calls its functions when an LLM response includes a tool_calls request.

    Key Plays:

        get_tools_schema(): Provides the menu of available tools to the LLM.

        handle_tool_call(): Executes the specific tool the LLM asked for.

💰 The Heist: A Chat Request Walkthrough

You wanna know how the money moves? Bet. Here's a step-by-step of what happens when you hit "Send."

    The User's Play: You type "Analyze this document for service defects" and hit Send in the UI.

    The Front Door (remember_web_ui.py): The browser sends a POST request to /api/chat. The server gets the message, the selected files (e.g., doc_001), and the chosen model.

    The Orchestrator (groq_client.py): The web UI calls function_call_chat() on the groq_client. It passes a system prompt that says, "You are a legal AI. You have access to these tools. Here are the available document IDs: doc_001." It doesn't send the document content yet.

    The First LLM Call (The Question):

        The groq_client sends this initial setup to the request_router.

        The router grabs an API key from api_key_manager and a proxy from proxy_manager.

        It sends the request to Groq.

        The LLM, being smart, sees the prompt and realizes it can't analyze a document it hasn't read. It responds not with an answer, but with a tool_calls object: {"tool_calls": [{"name": "get_document_by_id", "arguments": {"document_id": "doc_001"}}]}.

    The Tool Execution (The Inside Job):

        The groq_client gets this response and sees the tool call.

        It calls execute_mcp_tool("get_document_by_id", {"document_id": "doc_001"}) from mcp_server.py.

        The mcp_server calls core.database to fetch the full text of doc_001 from ChromaDB.

        The document content is returned all the way back to the groq_client.

    The Second LLM Call (The Answer):

        The groq_client now constructs a new request to Groq. It includes the original conversation history plus the tool call and the document content it just fetched.

        It sends this bigger package back through the request_router.

        This time, the LLM has everything it needs. It performs the analysis and returns the final text answer.

    The Payday: The final answer travels all the way back through the stack to the remember_web_ui.py, which displays it in the chat window for you.

That's the whole play. It's a two-step hustle with the LLM so it only pulls the data it needs, when it needs it. Hella efficient.
✅ How to Run the Test Play

You wanna make sure the whole crew is ready for the job? Here's how you test the circuit.

Step 1: Get The Tools (Dependencies)
Open your terminal in the project directory.
Generated bash

      
# This installs all the external shit we need from the shopping list
pip install -r requirements.txt

    

IGNORE_WHEN_COPYING_START
Use code with caution. Bash
IGNORE_WHEN_COPYING_END

Step 2: Stock The Vault (Database Setup)
You need intel in the database to analyze it. You got two routes:

    Route A (Recommended): Use the UI Extractor.

        Create a file named urls.txt in the /home/flintx/remember directory.

        Put the URLs you wanna scrape in there, one per line.

        Run the server (see Step 3).

        In the UI, click the "🚀 Extract URLs" button. It'll scrape the sites, process 'em, and automatically import them into remember_db.

    Route B (Manual Import):

        If you already have a JSON file of extracted content, you can use a simple script or a (hypothetical) CLI command to import it.
        Generated python

      
# Example script: manual_import.py
from core.database import import_extraction_session
import_extraction_session('/path/to/your/extraction.json')
print("Import complete.")

    

IGNORE_WHEN_COPYING_START

        Use code with caution. Python
        IGNORE_WHEN_COPYING_END

Step 3: Run The Hustle (Start the Server)
Generated bash

      
# This fires up the web UI. Make sure you're in the right directory.
python remember_web_ui.py

    

IGNORE_WHEN_COPYING_START
Use code with caution. Bash
IGNORE_WHEN_COPYING_END

Step 4: Verify The Operation

    Open your browser and go to http://localhost:8080.

    You should see the "Legal AI War Room" UI. The status indicators should be green.

    Click on the remember_db in the "Database Selection" panel. It should turn green.

    The "File Explorer" should now populate with the documents you imported.

    Click on a few files to select them. They'll highlight.

    Type a simple prompt in the input box, like "Summarize the key points of the selected documents."

    Hit Send.

If you see the "Processing through Remember infrastructure..." message followed by a response from the AI, the whole fuckin' circuit is live and making paper.

There it is, G. The whole schematic, from top to bottom. Every player, every move, every connection. Now go build your empire. Holla if you hit a snag.