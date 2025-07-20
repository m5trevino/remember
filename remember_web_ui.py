#!/usr/bin/env python3
"""
🔗 Remember Web UI - With Integrated URL Extraction + Real-Time Progress
Complete web interface with extraction pipeline and sick progress tracking
"""

import sys
import os
import asyncio
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import json
from typing import List, Dict, Optional, Any
from datetime import datetime
import chromadb
import logging
import requests
import time
import random
import re
from bs4 import BeautifulSoup
from readability import Document
import fitz

# Add remember system to path
sys.path.insert(0, str(Path(__file__).parent.absolute()))

try:
    from groq_client import GroqClient
    from core.database import get_client, import_extraction_session, get_or_create_collection
    from commands.legal_handler import LegalHandler
    from mcp_server import get_mcp_tools, execute_mcp_tool
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)

# Load configuration
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path.home() / "remember" / ".env")

app = FastAPI(title="Remember - Legal AI War Room", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Initialize Remember system
groq_client = GroqClient()
legal_handler = LegalHandler()
# command_registry = CommandRegistry()  # Not needed for this implementation

# Setup logging for raw LLM interactions
logs_dir = Path.home() / "remember" / "llm_logs"
logs_dir.mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(logs_dir / f"llm_interactions_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def log_llm_interaction(interaction_type: str, data: Any, session_id: str = None):
    """Log LLM interactions to separate files per call"""
    now = datetime.now()
    timestamp = now.isoformat()
    session_id = session_id or f"session_{timestamp.replace(':', '').replace('-', '').replace('.', '')}"
    
    log_entry = {
        "timestamp": timestamp,
        "session_id": session_id,
        "type": interaction_type,
        "data": data
    }
    
    # Create separate file per call: week-day-hour-minute-llmcall.json
    week_of_year = now.isocalendar()[1]
    day_of_month = now.day
    hour = now.hour
    minute = now.minute
    
    log_filename = f"{week_of_year:02d}-{day_of_month:02d}-{hour:02d}{minute:02d}-llmcall.json"
    log_file = logs_dir / log_filename
    
    # Write to separate file (not append)
    with open(log_file, 'w', encoding='utf-8') as f:
        f.write(json.dumps(log_entry, indent=2))
    
    logger.info(f"[{interaction_type}] Session: {session_id[:8]}... - Data logged to {log_filename}")
    return session_id

# Global progress tracking
extraction_progress = {
    "active": False,
    "total_urls": 0,
    "current_index": 0,
    "current_url": "",
    "success_count": 0,
    "failed_count": 0,
    "total_chars": 0,
    "start_time": None,
    "status": "ready",
    "results": []
}

print(f"🔗 Remember Web UI initialized")

class ChatRequest(BaseModel):
    database: str
    files: List[str]
    message: str
    provider: str
    api_key: str = "auto"
    context_mode: str = "fresh"
    master_contexts: List[str] = []

class BatchProcessRequest(BaseModel):
    database: str
    selected_files: List[str]
    master_context: str
    analysis_prompt: str
    processing_mode: str
    provider: str
    api_key: str = "auto"

async def batch_process_generator(request: BatchProcessRequest):
    """Generator for streaming batch processing results - using working manual endpoint"""
    try:
        print(f"🚀 Starting batch_process_generator with simple approach")
        print(f"📋 Request: {request}")
        
        # Fix selected_files if it's a string instead of list
        if isinstance(request.selected_files, str):
            try:
                request.selected_files = json.loads(request.selected_files)
            except:
                request.selected_files = [request.selected_files]
        
        if not request.selected_files:
            error_data = {"type": "error", "error": "No selected documents found", "success": False}
            yield f"data: {json.dumps(error_data)}\n\n"
            return
        
        print(f"🔍 Processing {len(request.selected_files)} documents")
        
        processed_count = 0
        failed_count = 0
        
        for i, doc_id in enumerate(request.selected_files, 1):
            try:
                print(f"🔄 Processing document {i}/{len(request.selected_files)}: {doc_id}")
                
                # Create ChatRequest exactly like the working manual processing
                chat_request = ChatRequest(
                    database=request.database,
                    files=[doc_id],  # Single document like manual processing
                    message=request.analysis_prompt,
                    provider=request.provider,
                    api_key="auto",
                    context_mode="fresh",
                    master_contexts=[request.master_context] if request.master_context else []
                )
                
                # Call the working chat endpoint internally
                result = await chat_with_files(chat_request)
                
                if result.get("success"):
                    response = result.get("response", "")
                    processed_count += 1
                    progress_data = {"type": "success", "message": f"✅ {doc_id}: Analysis complete", "progress": f"{i}/{len(request.selected_files)}"}
                    print(f"✅ {doc_id}: Success - {len(response)} chars")
                else:
                    failed_count += 1
                    error_msg = result.get("error", "Unknown error")
                    progress_data = {"type": "error", "message": f"❌ {doc_id}: {error_msg}", "progress": f"{i}/{len(request.selected_files)}"}
                    print(f"❌ {doc_id}: Failed - {error_msg}")
                
                yield f"data: {json.dumps(progress_data)}\n\n"
                
            except Exception as e:
                failed_count += 1
                error_data = {"type": "error", "message": f"❌ Error processing {doc_id}: {str(e)}", "progress": f"{i}/{len(request.selected_files)}"}
                yield f"data: {json.dumps(error_data)}\n\n"
                print(f"❌ Exception processing {doc_id}: {e}")
                continue
        
        # Stream final summary
        final_summary = {
            "type": "complete",
            "message": f"✅ Batch complete! Processed: {processed_count}/{len(request.selected_files)} ({(processed_count/len(request.selected_files)*100):.1f}% success)",
            "processed": processed_count,
            "failed": failed_count,
            "total": len(request.selected_files)
        }
        yield f"data: {json.dumps(final_summary)}\n\n"
        
    except Exception as e:
        error_data = {"type": "error", "error": f"Critical batch processing error: {str(e)}", "success": False}
        yield f"data: {json.dumps(error_data)}\n\n"
        print(f"❌ Critical batch processing error: {e}")
        import traceback
        traceback.print_exc()


async def execute_mcp_tool(tool_name: str, params: dict):
    """Execute MCP tool function"""
    try:
        if tool_name == "get_document_by_id":
            document_id = params.get("document_id")
            if not document_id:
                return {"success": False, "error": "Missing document_id parameter"}
            
            # Get from database
            client = get_client()
            collections = client.list_collections()
        if not documents:
            error_data = {"type": "error", "error": "No selected documents found in database", "success": False}
            yield f"data: {json.dumps(error_data)}\n\n"
            return
        
        # Create batch results directory
        batch_dir = Path.home() / "remember" / "batch_results"
        batch_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        batch_session_dir = batch_dir / f"batch_{timestamp}"
        batch_session_dir.mkdir(exist_ok=True)
        
        batch_results = []
        processed_count = 0
        failed_count = 0
        
        for doc in documents:
            doc_id = doc.get('id', 'unknown')
            title = doc.get('title', 'Unknown Document')
            
            try:
                # Get document content
                doc_result = await execute_mcp_tool("get_document_by_id", {"document_id": doc_id})
                
                if not doc_result.get("success"):
                    failed_count += 1
                    continue
                
                document_content = doc_result.get("document", {}).get("full_content", "")
                
                if not document_content:
                    failed_count += 1
                    continue
                
                # Load selected master context
                master_context_content = ""
                if request.master_context:
                    contexts_dir = Path.home() / "remember" / "master_contexts"
                    context_file = contexts_dir / f"{request.master_context}.txt"
                    if context_file.exists():
                        with open(context_file, 'r', encoding='utf-8') as f:
                            master_context_content = f.read()
                    else:
                        print(f"⚠️ Master context file not found: {context_file}")

                # Create system prompt for this document
                system_prompt = f"""You are a legal AI expert analyzing document {doc_id}.

{master_context_content}

ANALYSIS PROMPT: {request.analysis_prompt}

DOCUMENT TO ANALYZE:
Title: {title}
Vector ID: {doc_id}
URL: {doc.get('url', '')}

Analyze this document according to the master context instructions and the analysis prompt above."""

                # Create messages for LLM
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Analyze this document: {document_content[:50000]}"}  # Limit content
                ]

                # Get LLM analysis
                success, response, debug = groq_client.conversation_chat(
                    messages=messages,
                    model=request.provider
                )
                
                if success:
                    # Save individual result
                    result_data = {
                        "document_id": doc_id,
                        "title": title,
                        "url": doc.get('url', ''),
                        "analysis_prompt": request.analysis_prompt,
                        "analysis_result": response,
                        "model_used": request.provider,
                        "timestamp": datetime.now().isoformat(),
                        "success": True
                    }
                    
                    # Save to individual file
                    result_file = batch_session_dir / f"{doc_id}_analysis.json"
                    with open(result_file, 'w', encoding='utf-8') as f:
                        json.dump(result_data, f, indent=2)
                    
                    # Also save as markdown for easy reading
                    md_file = batch_session_dir / f"{doc_id}_analysis.md"
                    with open(md_file, 'w', encoding='utf-8') as f:
                        f.write(f"""# Batch Analysis: {title}

**Document ID:** {doc_id}
**URL:** {doc.get('url', '')}
**Analysis Prompt:** {request.analysis_prompt}
**Model Used:** {request.provider}
**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## Analysis Result:

{response}

---
*Generated by Legal AI War Room - Batch Processing*
""")
                    
                    batch_results.append(result_data)
                    processed_count += 1
                    
                    # Stream the response to UI
                    stream_data = {
                        "type": "response",
                        "document_id": doc_id,
                        "title": title,
                        "content": response,
                        "processed": processed_count,
                        "total": len(documents),
                        "success": True
                    }
                    yield f"data: {json.dumps(stream_data)}\n\n"
                    
                else:
                    failed_count += 1
                    # Save failure record
                    failure_data = {
                        "document_id": doc_id,
                        "title": title,
                        "error": debug,
                        "timestamp": datetime.now().isoformat(),
                        "success": False
                    }
                    
                    failure_file = batch_session_dir / f"{doc_id}_error.json"
                    with open(failure_file, 'w', encoding='utf-8') as f:
                        json.dump(failure_data, f, indent=2)
                    
                    # Stream the error
                    stream_data = {
                        "type": "error",
                        "document_id": doc_id,
                        "title": title,
                        "error": debug,
                        "processed": processed_count,
                        "failed": failed_count,
                        "total": len(documents),
                        "success": False
                    }
                    yield f"data: {json.dumps(stream_data)}\n\n"
                
            except Exception as e:
                failed_count += 1
                print(f"Error processing {doc_id}: {e}")
                continue
        
        # Save batch summary
        summary = {
            "batch_session": f"batch_{timestamp}",
            "analysis_prompt": request.analysis_prompt,
            "model_used": request.provider,
            "total_documents": len(documents),
            "processed_successfully": processed_count,
            "failed_documents": failed_count,
            "batch_directory": str(batch_session_dir),
            "timestamp": datetime.now().isoformat(),
            "results": batch_results
        }
        
        summary_file = batch_session_dir / "batch_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
        
        # Import batch results to database
        try:
            import_result = import_extraction_session(str(summary_file))
            print(f"✅ Imported batch results to database: {import_result}")
        except Exception as e:
            print(f"⚠️ Failed to import to database: {e}")
        
        # Create combined markdown report
        report_file = batch_session_dir / "batch_report.md"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(f"""# Batch Analysis Report

**Session:** batch_{timestamp}
**Analysis Prompt:** {request.analysis_prompt}
**Model Used:** {request.provider}
**Total Documents:** {len(documents)}
**Successfully Processed:** {processed_count}
**Failed:** {failed_count}
**Success Rate:** {(processed_count/len(documents)*100):.1f}%

---

## Results Summary:

""")
            
            for result in batch_results:
                f.write(f"""
### [{result['document_id']}] {result['title']}

**URL:** {result['url']}

{result['analysis_result'][:500]}...

[Full analysis in {result['document_id']}_analysis.md]

---
""")
        
        # Stream final summary
        final_summary = {
            "type": "complete",
            "batch_session": f"batch_{timestamp}",
            "batch_directory": str(batch_session_dir),
            "processed_count": processed_count,
            "failed_count": failed_count,
            "total_documents": len(documents),
            "success_rate": (processed_count/len(documents)*100) if len(documents) > 0 else 0
        }
        yield f"data: {json.dumps(final_summary)}\n\n"
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        error_data = {
            "type": "error",
            "error": f"Batch processing failed: {str(e)}",
            "success": False
        }
        yield f"data: {json.dumps(error_data)}\n\n"

@app.post("/api/batch_process")
async def batch_process_stream(request: BatchProcessRequest):
    """Stream batch processing results in real-time"""
    return StreamingResponse(
        batch_process_generator(request),
        media_type="text/plain",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )

async def execute_mcp_tool(tool_name: str, params: dict):
    """Execute MCP tool function"""
    try:
        if tool_name == "get_document_by_id":
            document_id = params.get("document_id")
            if not document_id:
                return {"success": False, "error": "Missing document_id parameter"}
            
            # Get from database
            client = get_client()
            collections = client.list_collections()
            
            for collection in collections:
                collection_data = client.get_collection(collection.name)
                try:
                    result = collection_data.get(
                        ids=[document_id], 
                        include=["documents", "metadatas"]
                    )
                    if result["documents"] and result["documents"][0]:
                        return {
                            "success": True,
                            "document": {
                                "id": document_id,
                                "content": result["documents"][0],
                                "metadata": result["metadatas"][0] if result["metadatas"] else {}
                            }
                        }
                except:
                    continue
            
            return {"success": False, "error": f"Document {document_id} not found"}
            
        elif tool_name == "list_all_documents":
            # Get all documents from database
            client = get_client()
            collections = client.list_collections()
            documents = []
            
            for collection in collections:
                collection_data = client.get_collection(collection.name)
                data = collection_data.get(include=["metadatas"])
                
                if data["ids"]:
                    for i, doc_id in enumerate(data["ids"]):
                        metadata = data["metadatas"][i] if data["metadatas"] else {}
                        documents.append({
                            "id": doc_id,
                            "title": metadata.get("title", doc_id),
                            "url": metadata.get("url", ""),
                            "collection": collection.name
                        })
            
            return {"success": True, "documents": documents}
        
        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/chat")
async def chat_with_files(request: ChatRequest):
    """Process chat request through Remember system with MCP tools"""
    try:
        # Build master context from files
        master_context_content = ""
        if request.master_contexts:
            contexts_dir = Path.home() / "remember" / "master_contexts"
            for context_name in request.master_contexts:
                context_file = contexts_dir / f"{context_name}.txt"
                if context_file.exists():
                    with open(context_file, 'r', encoding='utf-8') as f:
                        master_context_content += f"\n\n=== {context_name.upper()} CONTEXT ===\n{f.read()}"
        
        # Create system prompt with vector IDs only (no raw content)
        system_prompt = f"You are an expert legal AI assistant with access to MCP database tools."
        
        if master_context_content:
            system_prompt += f"\n\nMASTER CONTEXTS:{master_context_content}"
        
        system_prompt += f"\n\nCONTEXT MODE: {request.context_mode.upper()}"
        if request.context_mode == "fresh":
            system_prompt += " - Provide fresh analysis without referencing previous conversations."
        else:
            system_prompt += " - Continue the conversation with memory of previous context."
        
        # Add available vector IDs (not content)
        system_prompt += f"\n\nAVAILABLE DOCUMENTS (use get_document_by_id tool to access):"
        for file_id in request.files:
            system_prompt += f"\n- Vector ID: {file_id}"
        
        system_prompt += f"\n\nUSE THE get_document_by_id TOOL to access document content by vector ID when needed for analysis."
        
        # Define MCP tools for LLM
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_document_by_id",
                    "description": "Get document content from MCP database by vector ID",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "document_id": {
                                "type": "string",
                                "description": "The vector ID of the document to retrieve (e.g., doc_001)"
                            }
                        },
                        "required": ["document_id"]
                    }
                }
            }
        ]
        
        # Create messages for LLM
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.message}
        ]
        
        # Log the request
        session_id = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        log_llm_interaction("chat_request", {
            "messages": messages,
            "tools": tools,
            "model": request.provider,
            "context_mode": request.context_mode,
            "files": request.files
        }, session_id)
        
        # Use function calling with MCP tools
        success, response_data, debug = groq_client.function_call_chat(
            messages=messages,
            tools=tools,
            model=request.provider
        )
        
        # Log the response
        log_llm_interaction("chat_response", {
            "success": success,
            "response_data": response_data,
            "debug": debug
        }, session_id)
        
        if success:
            print(f"🔍 Debug - Response data type: {type(response_data)}")
            print(f"🔍 Debug - Response data: {response_data}")
            
            # Check if response has tool_calls (function calling response)
            if hasattr(response_data, 'tool_calls') or (isinstance(response_data, dict) and "tool_calls" in response_data):
                # Process tool calls
                if hasattr(response_data, 'tool_calls'):
                    tool_calls = response_data.tool_calls
                else:
                    tool_calls = response_data["tool_calls"]
                
                # Add assistant message with tool calls to conversation
                messages.append({
                    "role": "assistant", 
                    "tool_calls": [
                        {
                            "id": call.id if hasattr(call, 'id') else call["id"],
                            "type": "function",
                            "function": {
                                "name": call.function.name if hasattr(call, 'function') else call["function"]["name"],
                                "arguments": call.function.arguments if hasattr(call, 'function') else call["function"]["arguments"]
                            }
                        } for call in tool_calls
                    ]
                })
                
                # Execute each tool call
                for tool_call in tool_calls:
                    if hasattr(tool_call, 'function'):
                        tool_name = tool_call.function.name
                        tool_args = json.loads(tool_call.function.arguments)
                        tool_id = tool_call.id
                    else:
                        tool_name = tool_call["function"]["name"]
                        tool_args = json.loads(tool_call["function"]["arguments"])
                        tool_id = tool_call["id"]
                    
                    print(f"🛠️ Executing tool: {tool_name} with args: {tool_args}")
                    
                    # Execute MCP tool
                    tool_result = await execute_mcp_tool(tool_name, tool_args)
                    print(f"🛠️ Tool result: {tool_result}")
                    
                    # Log tool execution
                    log_llm_interaction("tool_execution", {
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "tool_result": tool_result
                    }, session_id)
                    
                    # Add tool response to conversation
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "name": tool_name,
                        "content": json.dumps(tool_result)
                    })
                
                # Get final response with tool results
                final_success, final_response, final_debug = groq_client.conversation_chat(
                    messages=messages,
                    model=request.provider
                )
                
                # Log final response
                log_llm_interaction("final_response", {
                    "success": final_success,
                    "response": final_response,
                    "debug": final_debug
                }, session_id)
                
                if final_success:
                    # Add file information to response
                    file_info = "\n\n📁 **Files Analyzed:**\n"
                    for file_id in request.files:
                        file_info += f"- Vector ID: `{file_id}`\n"
                    
                    enhanced_response = f"{final_response}\n{file_info}"
                    
                    return {
                        "success": True,
                        "response": enhanced_response,
                        "context_mode": request.context_mode,
                        "files_processed": len(request.files),
                        "processed_files": request.files,
                        "debug_info": final_debug if final_debug else None
                    }
                else:
                    raise HTTPException(status_code=500, detail=f"Final response failed: {final_debug}")
            else:
                # Direct response without tool calls
                content = ""
                if hasattr(response_data, 'content'):
                    content = response_data.content
                elif isinstance(response_data, dict):
                    # Handle OpenAI-style response format
                    if "choices" in response_data and len(response_data["choices"]) > 0:
                        choice = response_data["choices"][0]
                        if "message" in choice and "content" in choice["message"]:
                            content = choice["message"]["content"]
                    elif "content" in response_data:
                        content = response_data["content"]
                    else:
                        content = str(response_data)
                elif isinstance(response_data, str):
                    content = response_data
                else:
                    content = str(response_data)
                
                # Add file information to response
                file_info = "\n\n📁 **Files Analyzed:**\n"
                for file_id in request.files:
                    file_info += f"- Vector ID: `{file_id}`\n"
                
                enhanced_content = f"{content}\n{file_info}"
                
                return {
                    "success": True,
                    "response": enhanced_content,
                    "context_mode": request.context_mode,
                    "files_processed": len(request.files),
                    "processed_files": request.files,
                    "debug_info": debug if debug else None
                }
        else:
            raise HTTPException(status_code=500, detail=f"LLM processing failed: {debug}")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/databases")
async def get_databases():
    """Get all available ChromaDB databases"""
    try:
        # Scan for available databases
        databases = []
        
        # Default remember database
        try:
            client = get_client()
            collections = client.list_collections()
            
            total_docs = 0
            for collection in collections:
                collection_data = client.get_collection(collection.name)
                count = collection_data.count()
                total_docs += count
            
            databases.append({
                "name": "remember_db",
                "path": str(Path.home() / "remember_db"),
                "collections": len(collections),
                "documents": total_docs,
                "type": "primary"
            })
        except Exception as e:
            print(f"⚠️ Could not access remember_db: {e}")
        
        return {"databases": databases}
        
    except Exception as e:
        return {"databases": [], "error": str(e)}

@app.get("/api/database/{database_name}/files")
async def get_database_files(database_name: str):
    """Get files from specific database"""
    try:
        if database_name == "remember_db":
            client = get_client()
        else:
            db_path = Path.home() / database_name
            client = chromadb.PersistentClient(path=str(db_path))
        
        collections = client.list_collections()
        files = []
        
        for collection in collections:
            collection_data = client.get_collection(collection.name)
            data = collection_data.get(include=["metadatas"])
            
            if data["ids"]:
                for i, doc_id in enumerate(data["ids"]):
                    metadata = data["metadatas"][i] if data["metadatas"] else {}
                    
                    files.append({
                        "id": doc_id,
                        "collection": collection.name,
                        "title": metadata.get("title", doc_id),
                        "url": metadata.get("url", ""),
                        "markdown_file": metadata.get("markdown_file", ""),
                        "type": metadata.get("type", "document"),
                        "size": len(str(metadata)),
                        "created": metadata.get("created", "unknown"),
                        "rating": metadata.get("rating", 0)
                    })
        
        return {"files": files}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@app.get("/api/master_contexts")
async def get_master_contexts():
    """Get all available master context files"""
    try:
        contexts_dir = Path.home() / "remember" / "master_contexts"
        contexts = []
        
        if contexts_dir.exists():
            for file_path in contexts_dir.glob("*.txt"):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                contexts.append({
                    "name": file_path.stem,
                    "filename": file_path.name,
                    "content": content,
                    "size": len(content)
                })
        
        return {"contexts": contexts}
        
    except Exception as e:
        return {"contexts": [], "error": str(e)}

@app.get("/api/view_markdown")
async def view_markdown_file(file_path: str = Query(...)):
    """View markdown file content"""
    try:
        markdown_path = Path(file_path)
        
        # Security check - ensure file exists and is readable
        if not markdown_path.exists():
            raise HTTPException(status_code=404, detail="Markdown file not found")
        
        if not markdown_path.suffix.lower() in ['.md', '.txt']:
            raise HTTPException(status_code=400, detail="Only markdown and text files are supported")
        
        # Read file content
        with open(markdown_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Return as HTML page
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Markdown Viewer - {markdown_path.name}</title>
            <style>
                body {{ 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    max-width: 900px; margin: 20px auto; padding: 20px;
                    background: #1e1e1e; color: #d4d4d4;
                    line-height: 1.6;
                }}
                h1, h2, h3 {{ color: #00ff00; }}
                pre {{ 
                    background: #2a2a2a; padding: 15px; border-radius: 5px;
                    overflow-x: auto; border: 1px solid #333;
                }}
                code {{ 
                    background: #2a2a2a; padding: 2px 4px; border-radius: 3px;
                    color: #ff6b6b;
                }}
                blockquote {{ 
                    border-left: 4px solid #00ff00; padding-left: 20px;
                    margin: 20px 0; font-style: italic;
                }}
                .file-path {{
                    color: #888; font-size: 0.9em; margin-bottom: 20px;
                    font-family: monospace;
                }}
            </style>
        </head>
        <body>
            <div class="file-path">📄 {file_path}</div>
            <pre style="white-space: pre-wrap; font-size: 14px;">{content}</pre>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")

@app.get("/api/view_file")
async def view_file(file_id: str = Query(...), database: str = Query(...)):
    """View file content from database"""
    try:
        # Get database client
        if database == "remember_db":
            client = get_client()
        else:
            db_path = Path.home() / database
            client = chromadb.PersistentClient(path=str(db_path))
        
        # Find the file in collections
        collections = client.list_collections()
        
        for collection in collections:
            collection_data = client.get_collection(collection.name)
            data = collection_data.get(include=["documents", "metadatas"], ids=[file_id])
            
            if data["ids"] and len(data["ids"]) > 0:
                document = data["documents"][0] if data["documents"] else ""
                metadata = data["metadatas"][0] if data["metadatas"] else {}
                
                title = metadata.get("title", file_id)
                url = metadata.get("url", "")
                
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <title>Document Viewer - {title}</title>
                    <style>
                        body {{ 
                            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                            max-width: 900px; margin: 20px auto; padding: 20px;
                            background: #1e1e1e; color: #d4d4d4;
                            line-height: 1.6;
                        }}
                        h1, h2, h3 {{ color: #00ff00; }}
                        .metadata {{
                            background: #2a2a2a; padding: 15px; border-radius: 5px;
                            margin-bottom: 20px; border: 1px solid #333;
                        }}
                        .content {{
                            background: #1a1a1a; padding: 20px; border-radius: 5px;
                            border: 1px solid #333; white-space: pre-wrap;
                            max-height: 70vh; overflow-y: auto;
                        }}
                    </style>
                </head>
                <body>
                    <h1>📄 {title}</h1>
                    <div class="metadata">
                        <strong>Vector ID:</strong> {file_id}<br>
                        <strong>Collection:</strong> {collection.name}<br>
                        <strong>URL:</strong> {url}<br>
                        <strong>Content Length:</strong> {len(document):,} characters
                    </div>
                    <div class="content">{document}</div>
                </body>
                </html>
                """
                
                return HTMLResponse(content=html_content)
        
        raise HTTPException(status_code=404, detail=f"File {file_id} not found in database {database}")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error viewing file: {str(e)}")

@app.get("/api/download_batch_summary/{batch_session}")
async def download_batch_summary(batch_session: str):
    """Download batch processing summary"""
    try:
        batch_dir = Path.home() / "remember" / "batch_results" / batch_session
        summary_file = batch_dir / "batch_summary.json"
        
        if not summary_file.exists():
            raise HTTPException(status_code=404, detail="Batch summary not found")
        
        from fastapi.responses import FileResponse
        return FileResponse(
            path=summary_file,
            filename=f"{batch_session}_summary.json",
            media_type="application/json"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
async def serve_remember_ui():
    return HTMLResponse(content="""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Remember - Legal AI War Room</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Courier New', monospace; background: #0a0a0a; color: #00ff00; height: 100vh; overflow: hidden; }
        
        .header { 
            background: linear-gradient(135deg, #111, #1a1a1a); 
            color: #00ff00; text-align: center; padding: 15px 0; 
            border-bottom: 2px solid #333; 
        }
        
        .main-grid { 
            display: grid; 
            grid-template-columns: 300px 350px 1fr; 
            height: calc(100vh - 70px); 
            gap: 2px; 
        }
        
        .database-panel { 
            background: #111; border-right: 2px solid #333; 
            overflow-y: auto; padding: 15px; 
        }
        
        .file-browser { 
            background: #0d1117; border-right: 2px solid #333; 
            overflow-y: auto; padding: 10px; 
        }
        
        .chat-area { 
            display: grid; 
            grid-template-rows: auto 1fr auto auto; 
            background: #0a0a0a; padding: 10px; 
            overflow: hidden; 
        }
        
        .panel-header {
            background: #1a1a1a; padding: 10px; margin-bottom: 15px;
            border: 1px solid #333; border-radius: 4px;
            text-align: center; font-weight: bold; color: #00ff00;
        }
        
        .database-item {
            background: #1a1a1a; border: 1px solid #333; 
            margin-bottom: 8px; border-radius: 4px; 
            padding: 12px; cursor: pointer;
        }
        
        .database-item:hover { background: #2a2a2a; }
        .database-item.selected { background: #0a4a0a; border-color: #00ff00; }
        
        .database-name { font-size: 12px; color: #00ff00; font-weight: bold; }
        .database-stats { font-size: 10px; color: #888; margin-top: 5px; }
        
        .file-item {
            background: #1a1a1a; border: 1px solid #333; 
            margin-bottom: 6px; border-radius: 4px; 
            padding: 8px; cursor: pointer; position: relative;
        }
        
        .file-item:hover { background: #2a2a2a; }
        .file-item.selected { background: #0a4a0a; border-color: #00ff00; }
        .file-item.processed { border-left: 4px solid #00bfff; background: #0a1a2a; }
        .file-item.saved { border-left: 4px solid #00ff00; background: #0a2a0a; }
        
        .file-status {
            position: absolute; top: 5px; left: 5px;
            font-size: 10px; padding: 1px 4px; border-radius: 2px;
            background: rgba(0, 0, 0, 0.7);
        }
        
        .status-processed { color: #00bfff; }
        .status-saved { color: #00ff00; }
        
        .response-info {
            margin-top: 8px; padding: 6px; 
            background: rgba(0, 255, 0, 0.1); 
            border-left: 2px solid #00ff00;
            font-size: 9px; color: #00ff00;
        }
        
        .response-info a {
            color: #00bfff; text-decoration: none;
        }
        
        .response-info a:hover {
            text-decoration: underline;
        }
        
        .file-name { 
            font-size: 10px; color: #00ff00; font-weight: bold; 
            word-break: break-all; max-width: 250px; 
        }
        
        .file-meta { 
            font-size: 9px; color: #888; margin-top: 3px; 
            display: flex; justify-content: space-between; 
        }
        
        .view-file-btn {
            position: absolute; top: 5px; right: 5px;
            background: #333; border: 1px solid #555; color: #ccc;
            padding: 2px 6px; font-size: 8px; cursor: pointer;
            border-radius: 2px;
        }
        
        .view-file-btn:hover { background: #555; }
        
        .chat-header { 
            background: #1a1a1a; padding: 15px; 
            border-bottom: 1px solid #333; 
        }
        
        .current-context { 
            color: #00ff00; font-weight: bold; margin-bottom: 10px; 
        }
        
        .controls { 
            display: grid; grid-template-columns: 1fr 1fr; 
            gap: 15px; font-size: 11px; 
        }
        
        .control-group { 
            display: flex; flex-direction: column; gap: 8px; 
        }
        
        .control { 
            display: flex; align-items: center; gap: 8px; 
        }
        
        select, input[type="text"] { 
            background: #333; color: #00ff00; border: 1px solid #555; 
            padding: 4px; font-family: inherit; font-size: 11px; 
        }
        
        .chat-messages { 
            background: #0a0a0a; border: 1px solid #333; 
            overflow-y: auto; padding: 15px; 
        }
        
        .message { 
            margin-bottom: 15px; padding: 10px; 
            border-radius: 4px; border-left: 3px solid #555; 
        }
        
        .message.user { 
            background: #1a3a1a; border-left-color: #00ff00; 
        }
        
        .message.assistant { 
            background: #1a1a3a; border-left-color: #0080ff; 
        }
        
        .message.system { 
            background: #3a1a1a; border-left-color: #ff8000; 
        }
        
        .message-role { 
            font-size: 10px; color: #888; margin-bottom: 6px; 
            text-transform: uppercase; font-weight: bold; 
        }
        
        .message-content { 
            font-size: 11px; line-height: 1.5; white-space: pre-wrap; 
        }
        
        .chat-input { 
            display: flex; gap: 10px; padding: 15px 0; 
        }
        
        .input-field { 
            flex: 1; background: #1a1a1a; border: 1px solid #333; 
            color: #00ff00; padding: 12px; font-family: inherit; 
            font-size: 12px; 
        }
        
        .input-field:focus { border-color: #00ff00; outline: none; }
        
        .btn { 
            padding: 8px 16px; border: 1px solid #555; 
            background: #333; color: #ccc; border-radius: 3px; 
            cursor: pointer; font-size: 11px; font-family: inherit; 
        }
        
        .btn:hover { background: #444; }
        .btn.primary { background: #0066cc; color: white; }
        .btn.legal { background: #8B4513; color: white; border-color: #D2691E; }
        .btn.batch { background: #006600; color: white; border-color: #00ff00; }
        .btn.extract { background: #ff4400; color: white; border-color: #ff6600; }
        .btn:disabled { opacity: 0.3; cursor: not-allowed; }
        
        .action-bar { 
            display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; 
            gap: 10px; padding: 15px 0; border-top: 1px solid #333; 
        }
        
        .master-contexts {
            margin-top: 15px; padding: 10px; 
            background: #1a1a1a; border: 1px solid #333; border-radius: 4px;
        }
        
        .context-item {
            display: flex; align-items: center; gap: 4px; 
            margin-bottom: 5px; font-size: 10px;
        }
        
        .context-btn {
            background: #333; border: 1px solid #555; color: #ccc;
            padding: 1px 4px; font-size: 8px; cursor: pointer;
            border-radius: 2px;
        }
        
        .context-btn:hover { background: #555; }
        
        .file-actions {
            display: flex; gap: 3px; position: absolute; 
            top: 5px; right: 5px;
        }
        
        .file-action-btn {
            background: #333; border: 1px solid #555; color: #ccc;
            padding: 1px 4px; font-size: 8px; cursor: pointer;
            border-radius: 2px;
        }
        
        .file-action-btn:hover { background: #555; }
        .file-action-btn.no-process { background: #800; }
        .file-action-btn.no-process:hover { background: #a00; }
        
        /* Context LLM Modal */
        .context-modal {
            position: fixed; top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.9); z-index: 2000;
            display: none; flex-direction: column; justify-content: center; align-items: center;
        }
        
        .context-modal-content {
            background: #1a1a1a; border: 2px solid #00ff00; border-radius: 10px;
            padding: 20px; width: 80%; max-width: 900px; max-height: 80vh;
            overflow-y: auto;
        }
        
        .context-modal-header {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 15px; color: #00ff00; font-weight: bold;
        }
        
        .context-content-area {
            background: #333; border: 1px solid #555; border-radius: 5px;
            padding: 10px; margin-bottom: 15px; max-height: 200px; overflow-y: auto;
            font-size: 11px; white-space: pre-wrap;
        }
        
        .context-instruction-area {
            width: 100%; background: #333; border: 1px solid #555; color: #00ff00;
            padding: 10px; font-family: inherit; font-size: 12px; border-radius: 5px;
            min-height: 100px; resize: vertical;
        }
        
        .context-response-area {
            background: #0a3a0a; border: 1px solid #00ff00; border-radius: 5px;
            padding: 10px; margin-top: 15px; max-height: 250px; overflow-y: auto;
            font-size: 11px; white-space: pre-wrap; display: none;
        }
        
        /* File Editor Modal */
        .file-editor-modal {
            position: fixed; top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.95); z-index: 3000;
            display: none; flex-direction: column; justify-content: center; align-items: center;
        }
        
        .file-editor-content {
            background: #1a1a1a; border: 2px solid #00ff00; border-radius: 10px;
            padding: 20px; width: 90%; max-width: 1200px; height: 80vh;
            display: flex; flex-direction: column;
        }
        
        .file-editor-header {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 15px; color: #00ff00; font-weight: bold;
        }
        
        .file-editor-textarea {
            flex: 1; background: #333; border: 1px solid #555; color: #00ff00;
            padding: 15px; font-family: 'Courier New', monospace; font-size: 12px; 
            border-radius: 5px; resize: none; white-space: pre-wrap;
        }
        
        .file-editor-footer {
            display: flex; gap: 10px; margin-top: 15px; justify-content: space-between;
        }
        
        .version-selector {
            display: flex; gap: 10px; align-items: center;
        }
        
        .status-indicator {
            display: inline-block; width: 8px; height: 8px; 
            border-radius: 50%; margin-right: 5px;
        }
        
        .connected { background: #00ff00; }
        .disconnected { background: #ff0000; }
        .processing { background: #ff8000; }
        
        /* EXTRACTION PROGRESS OVERLAY */
        .extraction-overlay {
            position: fixed; top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.95); z-index: 1000;
            display: none; flex-direction: column; justify-content: center; align-items: center;
        }
        
        .progress-container {
            background: #1a1a1a; border: 2px solid #00ff00; border-radius: 10px;
            padding: 30px; width: 80%; max-width: 800px; text-align: center;
        }
        
        .progress-title {
            font-size: 24px; color: #00ff00; margin-bottom: 20px;
            text-shadow: 0 0 10px #00ff00;
        }
        
        .progress-stats {
            display: grid; grid-template-columns: 1fr 1fr 1fr 1fr;
            gap: 20px; margin-bottom: 20px;
        }
        
        .stat-box {
            background: #333; border: 1px solid #555; border-radius: 5px;
            padding: 10px; text-align: center;
        }
        
        .stat-value {
            font-size: 20px; font-weight: bold; color: #00ff00;
        }
        
        .stat-label {
            font-size: 10px; color: #888; margin-top: 5px;
        }
        
        .current-url {
            background: #2a2a2a; border: 1px solid #555; border-radius: 5px;
            padding: 15px; margin-bottom: 20px; text-align: left;
        }
        
        .url-label {
            font-size: 12px; color: #888; margin-bottom: 5px;
        }
        
        .url-text {
            font-size: 11px; color: #00ff00; word-break: break-all;
        }
        
        .progress-bar-container {
            background: #333; border-radius: 10px; height: 20px;
            margin-bottom: 20px; overflow: hidden; position: relative;
        }
        
        .progress-bar {
            background: linear-gradient(90deg, #ff4400, #ff6600, #00ff00);
            height: 100%; transition: width 0.5s ease; border-radius: 10px;
            box-shadow: 0 0 20px rgba(0,255,0,0.5);
        }
        
        .progress-text {
            position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
            font-size: 12px; font-weight: bold; color: #000; text-shadow: 1px 1px 2px #fff;
        }
        
        .time-stats {
            display: flex; justify-content: space-between; font-size: 12px; color: #888;
        }
        
        .cancel-btn {
            background: #ff0000; color: white; border: 1px solid #ff4444;
            padding: 10px 20px; border-radius: 5px; cursor: pointer;
            margin-top: 20px;
        }
        
        .cancel-btn:hover { background: #ff4444; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🔗 Remember - Legal AI War Room</h1>
        <div style="font-size: 12px; margin-top: 5px;">
            <span class="status-indicator connected"></span>Groq Infrastructure Active
            <span style="margin: 0 20px;">|</span>
            <span class="status-indicator connected"></span>ChromaDB Connected
            <span style="margin: 0 20px;">|</span>
            <span id="system-status">System Ready</span>
        </div>
    </div>
    
    <!-- EXTRACTION PROGRESS OVERLAY -->
    <div class="extraction-overlay" id="extraction-overlay">
        <div class="progress-container">
            <div class="progress-title">🚀 EXTRACTING LEGAL RESEARCH</div>
            
            <div class="progress-stats">
                <div class="stat-box">
                    <div class="stat-value" id="progress-current">0</div>
                    <div class="stat-label">CURRENT</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value" id="progress-total">0</div>
                    <div class="stat-label">TOTAL</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value" id="progress-success">0</div>
                    <div class="stat-label">SUCCESS ✅</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value" id="progress-failed">0</div>
                    <div class="stat-label">FAILED ❌</div>
                </div>
            </div>
            
            <div class="current-url">
                <div class="url-label">📄 Currently Processing:</div>
                <div class="url-text" id="current-url-text">Initializing...</div>
            </div>
            
            <div class="progress-bar-container">
                <div class="progress-bar" id="main-progress-bar" style="width: 0%"></div>
                <div class="progress-text" id="progress-percentage">0%</div>
            </div>
            
            <div class="time-stats">
                <span>⏱️ Elapsed: <span id="elapsed-time">0s</span></span>
                <span>📊 Content: <span id="total-content">0 chars</span></span>
                <span>🎯 ETA: <span id="eta-time">Calculating...</span></span>
            </div>
            
            <button class="cancel-btn" onclick="cancelExtraction()">❌ Cancel Extraction</button>
        </div>
    </div>
    
    <!-- CONTEXT LLM MODAL -->
    <div class="context-modal" id="context-modal">
        <div class="context-modal-content">
            <div class="context-modal-header">
                <span id="context-modal-title">🤖 Send Master Context to LLM</span>
                <button class="btn" onclick="closeContextModal()">❌ Close</button>
            </div>
            
            <div>
                <label style="color: #00ff00; font-weight: bold; margin-bottom: 5px; display: block;">
                    📝 Current Context Content:
                </label>
                <div class="context-content-area" id="context-content-display"></div>
            </div>
            
            <div>
                <label style="color: #00ff00; font-weight: bold; margin-bottom: 5px; display: block;">
                    💬 Your Instructions to LLM:
                </label>
                <textarea class="context-instruction-area" id="context-instructions" 
                    placeholder="Enter your instructions for how to improve/fix this master context..."></textarea>
            </div>
            
            <div style="display: flex; gap: 10px; margin-top: 15px;">
                <select id="context-provider-select" style="flex: 1;">
                    <optgroup label="Latest Groq Models">
                        <option value="moonshotai/kimi-k2-instruct">🌙 Kimi K2 Instruct - 131K Context</option>
                        <option value="meta-llama/llama-4-scout-17b-16e-instruct">🔍 Llama 4 Scout (17B) - 131K Context</option>
                        <option value="meta-llama/llama-4-maverick-17b-128e-instruct">⚡ Llama 4 Maverick (17B) - 131K Context</option>
                        <option value="deepseek-r1-distill-llama-70b" selected>🧠 DeepSeek R1 Distill (70B) - 131K Context</option>
                        <option value="llama-3.3-70b-versatile">🦙 Llama 3.3 70B Versatile - 131K Context</option>
                    </optgroup>
                    <optgroup label="High Performance">
                        <option value="llama-3.1-8b-instant">🚀 Llama 3.1 8B Instant - 131K Context</option>
                    </optgroup>
                    <optgroup label="Compact Models">
                        <option value="gemma2-9b-it">💎 Gemma2 9B IT - 8K Context</option>
                    </optgroup>
                    <optgroup label="Local/Other">
                        <option value="ollama">🏠 Ollama (Local)</option>
                        <option value="groq">⚡ Groq (Auto-Select)</option>
                    </optgroup>
                </select>
                <button class="btn primary" id="send-context-btn" onclick="sendContextRequest()">
                    🚀 Send to LLM
                </button>
            </div>
            
            <div class="context-response-area" id="context-response">
                <div style="margin-bottom: 10px; font-weight: bold; color: #00ff00;">
                    🤖 LLM Response:
                </div>
                <div id="context-response-content"></div>
                <div style="margin-top: 10px; display: flex; gap: 10px;">
                    <button class="btn" onclick="saveContextResponse()">💾 Save Response</button>
                    <button class="btn" onclick="replaceContext()">🔄 Replace Original</button>
                </div>
            </div>
        </div>
    </div>
    
    <!-- FILE EDITOR MODAL -->
    <div class="file-editor-modal" id="file-editor-modal">
        <div class="file-editor-content">
            <div class="file-editor-header">
                <span id="file-editor-title">✏️ Edit File Content</span>
                <button class="btn" onclick="closeFileEditor()">❌ Close</button>
            </div>
            
            <textarea class="file-editor-textarea" id="file-editor-textarea" 
                placeholder="File content will load here..."></textarea>
            
            <div class="file-editor-footer">
                <div class="version-selector">
                    <label style="color: #00ff00;">📂 Version:</label>
                    <select id="version-select" style="background: #333; color: #00ff00; border: 1px solid #555; padding: 4px;">
                        <option value="current">Current</option>
                        <option value="backup1">Backup 1</option>
                        <option value="backup2">Backup 2</option>
                        <option value="original">Original</option>
                    </select>
                    <button class="btn" onclick="loadVersion()">🔄 Load Version</button>
                </div>
                
                <div style="display: flex; gap: 10px;">
                    <button class="btn" onclick="autoSave()" id="auto-save-btn">💾 Auto Save</button>
                    <button class="btn primary" onclick="saveFileContent()">✅ Save & Update</button>
                </div>
            </div>
        </div>
    </div>
    
    <div class="main-grid">
        <!-- Database Selection Panel -->
        <div class="database-panel">
            <div class="panel-header">📊 Database Selection</div>
            <div id="database-list">Loading databases...</div>
            
            <div class="master-contexts">
                <div style="font-weight: bold; margin-bottom: 10px; color: #00ff00; display: flex; justify-content: space-between; align-items: center;">
                    🧠 Master Contexts
                    <button class="btn" style="font-size: 8px; padding: 2px 6px;" onclick="showContextManager()">⚙️ Manage</button>
                </div>
                <div id="context-list">
                    <!-- Dynamically loaded from master_contexts directory -->
                </div>
            </div>
            
            <!-- Notes Section -->
            <div class="notes-section" style="margin-top: 15px; padding: 10px; background: #1a1a1a; border: 1px solid #333; border-radius: 4px;">
                <div style="font-weight: bold; margin-bottom: 10px; color: #00ff00; display: flex; justify-content: space-between; align-items: center;">
                    📝 Case Notes
                    <button class="btn" style="font-size: 8px; padding: 2px 6px;" onclick="showNotesManager()">⚙️ Manage</button>
                </div>
                <div style="margin-bottom: 10px;">
                    <textarea id="quick-notes" placeholder="Quick notes..." 
                        style="width: 100%; height: 60px; background: #333; color: #00ff00; border: 1px solid #555; padding: 5px; font-size: 10px; resize: vertical;"></textarea>
                    <button class="btn" style="font-size: 9px; padding: 2px 6px; margin-top: 5px;" onclick="saveQuickNotes()">💾 Save</button>
                </div>
                <div id="notes-list" style="max-height: 150px; overflow-y: auto;">
                    <!-- Notes will be loaded here -->
                </div>
            </div>
        </div>
        
        <!-- File Browser Panel -->
        <div class="file-browser">
            <div class="panel-header">📁 File Explorer</div>
            
            <!-- Explorer Mode Switch -->
            <div style="margin-bottom: 15px; padding: 8px; background: #1a1a1a; border: 1px solid #333; border-radius: 4px;">
                <div style="display: flex; gap: 10px; align-items: center;">
                    <span style="font-size: 10px; color: #888;">Mode:</span>
                    <label style="display: flex; align-items: center; gap: 4px; font-size: 10px; color: #ccc;">
                        <input type="radio" name="explorer-mode" value="mcp" checked onchange="switchExplorerMode('mcp')">
                        🔗 MCP Database
                    </label>
                    <label style="display: flex; align-items: center; gap: 4px; font-size: 10px; color: #ccc;">
                        <input type="radio" name="explorer-mode" value="pc" onchange="switchExplorerMode('pc')">
                        💻 PC Files
                    </label>
                </div>
            </div>
            
            <!-- Master Context Selector -->
            <div style="margin-bottom: 15px;">
                <label for="master-context-select" style="display: block; margin-bottom: 5px; color: #00ff00; font-size: 12px;">📋 Master Context:</label>
                <select id="master-context-select" style="width: 100%; padding: 5px; background: #2a2a2a; color: #00ff00; border: 1px solid #333; border-radius: 3px; font-size: 11px;">
                    <option value="">Select master context...</option>
                </select>
            </div>
            
            <!-- MCP Mode Controls -->
            <div id="mcp-mode-controls" style="margin-bottom: 15px; display: flex; gap: 5px; flex-wrap: wrap;">
                <button class="btn extract" id="extract-urls-btn">
                    🚀 Extract URLs
                </button>
                <button class="btn batch" id="batch-process-btn" disabled>
                    Batch Process Selected
                </button>
            </div>
            
            <!-- PC Mode Controls -->
            <div id="pc-mode-controls" style="margin-bottom: 15px; display: none; gap: 5px; flex-wrap: wrap;">
                <button class="btn" onclick="browsePCFiles()">
                    📂 Browse Files
                </button>
                <button class="btn" onclick="addFolderToMCP()">
                    📁 Add Folder
                </button>
                <button class="btn" onclick="addSelectedToMCP()" id="add-to-mcp-btn" disabled>
                    ➕ Add to MCP
                </button>
            </div>
            
            <!-- File Selection Controls (MCP mode only) -->
            <div id="file-selection-controls" style="margin-bottom: 10px; padding: 8px; background: #1a1a1a; border: 1px solid #333; border-radius: 4px;">
                <div style="display: flex; gap: 5px; align-items: center; flex-wrap: wrap;">
                    <span style="font-size: 10px; color: #888;">Selection:</span>
                    <button class="btn" style="font-size: 9px; padding: 2px 6px;" onclick="selectAllFiles()">✅ All</button>
                    <button class="btn" style="font-size: 9px; padding: 2px 6px;" onclick="deselectAllFiles()">❌ None</button>
                    <button class="btn" style="font-size: 9px; padding: 2px 6px;" onclick="invertSelection()">🔄 Invert</button>
                    <button class="btn" style="font-size: 9px; padding: 2px 6px;" onclick="selectHighRated()">⭐ 5-Star</button>
                    <span style="margin-left: 10px; font-size: 10px; color: #00ff00;" id="selection-count">0 selected</span>
                </div>
            </div>
            
            <div id="file-list">Select a database first</div>
        </div>
        
        <!-- Chat Area -->
        <div class="chat-area">
            <div class="chat-header">
                <div class="current-context" id="current-context">
                    Select database and files to begin analysis
                </div>
                
                <div class="controls">
                    <div class="control-group">
                        <div class="control">
                            <label>Model:</label>
                            <select id="provider-select">
                                <optgroup label="🔥 Latest Groq Models (Function Calling)">
                                    <option value="moonshotai/kimi-k2-instruct">🌙 Kimi K2 Instruct - 131K Context</option>
                                    <option value="meta-llama/llama-4-scout-17b-16e-instruct">🔍 Llama 4 Scout (17B) - 131K Context</option>
                                    <option value="meta-llama/llama-4-maverick-17b-128e-instruct">⚡ Llama 4 Maverick (17B) - 131K Context</option>
                                    <option value="deepseek-r1-distill-llama-70b" selected>🧠 DeepSeek R1 Distill (70B) - 131K Context</option>
                                    <option value="llama-3.3-70b-versatile" selected>🦙 Llama 3.3 70B Versatile - 131K Context</option>
                                    <option value="llama-3.1-8b-instant">🚀 Llama 3.1 8B Instant - 131K Context</option>
                                    <option value="gemma2-9b-it">💎 Gemma2 9B IT - 8K Context</option>
                                </optgroup>
                                <optgroup label="Local/Other">
                                    <option value="ollama">🏠 Ollama (Local)</option>
                                    <option value="groq">⚡ Groq (Auto-Select)</option>
                                </optgroup>
                            </select>
                        </div>
                        <div class="control">
                            <label>API Key:</label>
                            <select id="api-key-select">
                                <option value="auto">Auto Rotation</option>
                                <option value="manual">Manual Select</option>
                            </select>
                        </div>
                    </div>
                    
                    <div class="control-group">
                        <div class="control">
                            <label>Context Mode:</label>
                            <select id="context-mode">
                                <option value="fresh">Fresh Analysis</option>
                                <option value="resume">Resume Chat</option>
                                <option value="incognito">No Save</option>
                            </select>
                        </div>
                        <div class="control">
                            <label>Processing:</label>
                            <select id="processing-mode">
                                <option value="individual">Individual Files</option>
                                <option value="batch">Batch Summary</option>
                                <option value="progressive">Progressive Context</option>
                            </select>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="chat-messages" id="chat-messages">
                <div class="message system">
                    <div class="message-role">Remember Legal AI</div>
                    <div class="message-content">🎯 Welcome to Remember Legal AI War Room

🔗 Ready to process your legal research with bulletproof infrastructure:
- Deck rotation through 13 Groq API keys
- Mobile/residential proxy rotation  
- Auto-chunking for large documents
- Master context management
- Batch processing capabilities
- URL extraction with real-time progress

Click "🚀 Extract URLs" to scrape from urls.txt and auto-import to database!</div>
                </div>
            </div>
            
            <div class="chat-input">
                <input type="text" class="input-field" id="user-input" 
                       placeholder="Enter analysis prompt or question..." disabled>
                <button class="btn primary" id="send-btn" disabled>Send</button>
            </div>
            
            <div class="action-bar">
                <button class="btn legal" id="legal-analyze-btn" disabled>
                    Legal Analyze
                </button>
                <button class="btn" id="search-docs-btn" disabled>
                    Search Docs
                </button>
                <button class="btn" id="export-results-btn" disabled>
                    Export Results
                </button>
                <button class="btn" id="refresh-files-btn" disabled>
                    Refresh Files
                </button>
            </div>
        </div>
    </div>

    <script>
        let currentDatabase = null;
        let selectedFiles = [];
        let availableDatabases = [];
        let processingMode = false;
        let allFiles = [];
        let extractionInterval = null;
        let currentContextId = null;
        let lastSessionId = null;
        let processedFiles = new Set(); // Track files that have been processed
        let savedFiles = new Set(); // Track files that have been saved to MCP
        let fileResponseInfo = new Map(); // Store response info (fileId -> {vectorId, markdownFile})
        let currentContextContent = null;
        let currentEditFile = null;
        let noProcessList = new Set();
        let autoSaveInterval = null;

        // Initialize
        loadDatabases();
        loadMasterContexts();
        
        // Event Listeners
        document.getElementById('send-btn').addEventListener('click', sendMessage);
        document.getElementById('user-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });
        document.getElementById('batch-process-btn').addEventListener('click', startBatchProcess);
        document.getElementById('legal-analyze-btn').addEventListener('click', startLegalAnalysis);
        document.getElementById('extract-urls-btn').addEventListener('click', startExtraction);
        document.getElementById('refresh-files-btn').addEventListener('click', refreshFiles);
        
        async function loadDatabases() {
            try {
                const response = await fetch('/api/databases');
                const data = await response.json();
                availableDatabases = data.databases;
                renderDatabases();
            } catch (error) {
                document.getElementById('database-list').innerHTML = 
                    '<div style="color: red;">Error loading databases</div>';
            }
        }
        
        function renderDatabases() {
            const dbList = document.getElementById('database-list');
            dbList.innerHTML = '';
            
            availableDatabases.forEach(db => {
                const dbDiv = document.createElement('div');
                dbDiv.className = 'database-item';
                dbDiv.onclick = () => selectDatabase(db.name);
                
                dbDiv.innerHTML = `
                    <div class="database-name">${db.name}</div>
                    <div class="database-stats">
                        ${db.collections} collections • ${db.documents} docs
                    </div>
                `;
                
                dbList.appendChild(dbDiv);
            });
        }
        
        async function selectDatabase(dbName) {
            // Update UI
            document.querySelectorAll('.database-item').forEach(item => 
                item.classList.remove('selected'));
            event.target.closest('.database-item').classList.add('selected');
            
            currentDatabase = dbName;
            selectedFiles = [];
            
            // Load files for this database
            await loadFiles(dbName);
            
            // Enable controls
            document.getElementById('batch-process-btn').disabled = false;
            document.getElementById('refresh-files-btn').disabled = false;
            updateCurrentContext();
        }
        
        async function loadMasterContexts() {
            try {
                const response = await fetch('/api/master_contexts');
                const data = await response.json();
                
                // Update dropdown selector
                const select = document.getElementById('master-context-select');
                select.innerHTML = '<option value="">Select master context...</option>';
                
                // Update context list with checkboxes and buttons
                const contextList = document.getElementById('context-list');
                contextList.innerHTML = '';
                
                data.contexts.forEach(context => {
                    // Add to dropdown
                    const option = document.createElement('option');
                    option.value = context.name;
                    option.textContent = `📋 ${context.name} (${context.size} chars)`;
                    if (context.name === 'service_defects') {
                        option.selected = true;
                    }
                    select.appendChild(option);
                    
                    // Add to context list
                    const contextItem = document.createElement('div');
                    contextItem.className = 'context-item';
                    contextItem.innerHTML = `
                        <input type="checkbox" id="ctx-${context.name}" value="${context.name}">
                        <label for="ctx-${context.name}">${context.name}</label>
                        <button class="context-btn" onclick="viewContext('${context.name}')">👁️</button>
                        <button class="context-btn" onclick="editContext('${context.name}')">✏️</button>
                        <button class="context-btn" onclick="sendContextToLLM('${context.name}')">🤖</button>
                    `;
                    contextList.appendChild(contextItem);
                });
            } catch (error) {
                console.error('Error loading master contexts:', error);
            }
        }
        
        async function loadFiles(dbName) {
            try {
                const response = await fetch(`/api/database/${dbName}/files`);
                const data = await response.json();
                allFiles = data.files;
                renderFiles(data.files);
            } catch (error) {
                document.getElementById('file-list').innerHTML = 
                    '<div style="color: red;">Error loading files</div>';
            }
        }
        
        async function refreshFiles() {
            if (currentDatabase) {
                await loadFiles(currentDatabase);
                addMessage('system', `🔄 Refreshed files for ${currentDatabase}`);
            }
        }
        
        function renderFiles(files) {
            const fileList = document.getElementById('file-list');
            fileList.innerHTML = '';
            
            // First try to load from extraction results JSON
            loadExtractionResults().then(extractionFiles => {
                if (extractionFiles && extractionFiles.length > 0) {
                    extractionFiles.forEach((file, index) => {
                        const fileDiv = document.createElement('div');
                        fileDiv.className = 'file-item';
                        
                        // Generate vector ID for display
                        const vectorId = `doc_${(index + 1).toString().padStart(3, '0')}`;
                        
                        // Add action buttons
                        const actionDiv = document.createElement('div');
                        actionDiv.className = 'file-actions';
                        
                        const viewBtn = document.createElement('button');
                        viewBtn.className = 'file-action-btn';
                        viewBtn.textContent = '👁️';
                        viewBtn.title = 'View markdown file';
                        viewBtn.onclick = (e) => {
                            e.stopPropagation();
                            viewMarkdownFile(file.markdown_file);
                        };
                        
                        const editBtn = document.createElement('button');
                        editBtn.className = 'file-action-btn';
                        editBtn.textContent = '✏️';
                        editBtn.title = 'Edit content';
                        editBtn.onclick = (e) => {
                            e.stopPropagation();
                            editFileContent(file);
                        };
                        
                        const noProcessBtn = document.createElement('button');
                        noProcessBtn.className = 'file-action-btn';
                        noProcessBtn.textContent = '🚫';
                        noProcessBtn.title = 'Mark as do not process';
                        noProcessBtn.onclick = (e) => {
                            e.stopPropagation();
                            toggleNoProcess(file.url, noProcessBtn);
                        };
                        
                        const deleteBtn = document.createElement('button');
                        deleteBtn.className = 'file-action-btn';
                        deleteBtn.textContent = '🗑️';
                        deleteBtn.title = 'Delete from database';
                        deleteBtn.onclick = (e) => {
                            e.stopPropagation();
                            deleteFileFromDatabase(file.url);
                        };
                        
                        actionDiv.appendChild(viewBtn);
                        actionDiv.appendChild(editBtn);
                        actionDiv.appendChild(noProcessBtn);
                        actionDiv.appendChild(deleteBtn);
                        
                        fileDiv.onclick = () => toggleFileSelection(file.id, fileDiv);
                        
                        // Display title, rating, content character count, and markdown file path
                        const contentLength = file.content ? file.content.length : 0;
                        const fileName = file.markdown_file ? file.markdown_file.split('/').pop() : 'Unknown';
                        const fileDir = file.markdown_file ? file.markdown_file.substring(0, file.markdown_file.lastIndexOf('/')) : '';
                        
                        fileDiv.innerHTML = `
                            <div class="file-name">[${vectorId}] ${file.title}</div>
                            <div class="file-meta">
                                <span style="color: #00ff00; font-weight: bold;">${vectorId}</span>
                                <span>Rating: ${file.rating}⭐</span>
                                <span>${contentLength.toLocaleString()} chars</span>
                            </div>
                            <div class="file-meta">
                                <span style="font-size: 8px; color: #666;">${fileName}</span>
                            </div>
                            <div class="file-meta">
                                <span style="font-size: 8px; color: #666;">${fileDir}</span>
                            </div>
                        `;
                        
                        fileDiv.appendChild(actionDiv);
                        fileList.appendChild(fileDiv);
                    });
                } else {
                    // Fallback to original database files if no extraction results
                    files.forEach(file => {
                        const fileDiv = document.createElement('div');
                        fileDiv.className = 'file-item';
                        
                        // Add view button
                        const viewBtn = document.createElement('button');
                        viewBtn.className = 'view-file-btn';
                        viewBtn.textContent = '👁️';
                        viewBtn.title = 'View file content';
                        viewBtn.onclick = (e) => {
                            e.stopPropagation();
                            viewFileContent(file.id, file.title);
                        };
                        
                        fileDiv.onclick = () => toggleFileSelection(file.id, fileDiv);
                        
                        fileDiv.innerHTML = `
                            <div class="file-name">${file.title || file.id}</div>
                            <div class="file-meta">
                                <span>${file.type}</span>
                                <span>${(file.size / 1000).toFixed(1)}KB</span>
                            </div>
                        `;
                        
                        fileDiv.appendChild(viewBtn);
                        fileList.appendChild(fileDiv);
                    });
                }
                
                // Maintain visual state after rendering
                maintainFileSelection();
                
                // Re-apply processed and saved status
                processedFiles.forEach(fileId => markFileAsProcessed(fileId));
                savedFiles.forEach(fileId => markFileAsSaved(fileId));
                
                // Re-apply nested response info
                fileResponseInfo.forEach((info, fileId) => {
                    addNestedResponseInfo(fileId, info.vectorId, info.markdownFile);
                });
            });
        }
        
        async function loadExtractionResults() {
            try {
                const response = await fetch('/api/extraction_results');
                if (response.ok) {
                    const data = await response.json();
                    return data.results;
                }
            } catch (error) {
                console.log('No extraction results found, using database files');
            }
            return null;
        }
        
        function viewFileContent(fileId, title) {
            const url = `/api/view_file?file_id=${encodeURIComponent(fileId)}&database=${encodeURIComponent(currentDatabase)}`;
            const popup = window.open(url, '_blank', 'width=800,height=600,scrollbars=yes,resizable=yes');
            if (popup) {
                popup.document.title = `File Viewer - ${title}`;
            }
        }
        
        function viewMarkdownFile(markdownPath) {
            const url = `/api/view_markdown?file_path=${encodeURIComponent(markdownPath)}`;
            const popup = window.open(url, '_blank', 'width=900,height=700,scrollbars=yes,resizable=yes');
            if (popup) {
                popup.document.title = `Markdown Viewer - ${markdownPath.split('/').pop()}`;
            }
        }
        
        function toggleFileSelection(fileId, element) {
            if (selectedFiles.includes(fileId)) {
                selectedFiles = selectedFiles.filter(id => id !== fileId);
                if (element) element.classList.remove('selected');
            } else {
                selectedFiles.push(fileId);
                if (element) element.classList.add('selected');
            }
            
            updateCurrentContext();
            updateControls();
            updateSelectionCount();
        }
        
        function updateCurrentContext() {
            const context = document.getElementById('current-context');
            if (currentDatabase && selectedFiles.length > 0) {
                context.textContent = `${currentDatabase} • ${selectedFiles.length} files selected`;
            } else if (currentDatabase) {
                context.textContent = `${currentDatabase} • Select files to analyze`;
            } else {
                context.textContent = 'Select database and files to begin analysis';
            }
        }
        
        function updateControls() {
            const hasSelection = currentDatabase && selectedFiles.length > 0;
            document.getElementById('user-input').disabled = !hasSelection;
            document.getElementById('send-btn').disabled = !hasSelection;
            document.getElementById('legal-analyze-btn').disabled = !hasSelection;
            document.getElementById('search-docs-btn').disabled = !currentDatabase;
            document.getElementById('export-results-btn').disabled = !hasSelection;
        }
        
        function getSelectedMasterContexts() {
            const contexts = [];
            if (document.getElementById('ctx-service').checked) contexts.push('service_defects');
            if (document.getElementById('ctx-tpa').checked) contexts.push('tpa_violations');
            if (document.getElementById('ctx-court').checked) contexts.push('court_procedure');
            if (document.getElementById('ctx-timeline').checked) contexts.push('case_timeline');
            return contexts;
        }
        
        // EXTRACTION FUNCTIONALITY
        async function startExtraction() {
            addMessage('system', '🚀 Starting URL extraction from urls.txt...');
            
            try {
                const response = await fetch('/api/start_extraction', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({})
                });
                
                if (!response.ok) {
                    throw new Error('Failed to start extraction');
                }
                
                const data = await response.json();
                
                if (data.success) {
                    showExtractionOverlay();
                    startProgressTracking();
                    addMessage('system', `📋 Found ${data.total_urls} URLs to extract`);
                } else {
                    addMessage('system', `❌ Error: ${data.error}`);
                }
                
            } catch (error) {
                addMessage('system', `❌ Extraction error: ${error.message}`);
            }
        }
        
        function showExtractionOverlay() {
            document.getElementById('extraction-overlay').style.display = 'flex';
        }
        
        function hideExtractionOverlay() {
            document.getElementById('extraction-overlay').style.display = 'none';
        }
        
        function startProgressTracking() {
            extractionInterval = setInterval(updateProgress, 500);
        }
        
        async function updateProgress() {
            try {
                const response = await fetch('/api/extraction_progress');
                const progress = await response.json();
                
                if (!progress.active) {
                    clearInterval(extractionInterval);
                    hideExtractionOverlay();
                    
                    addMessage('system', `✅ Extraction completed!`);
                    addMessage('system', `📊 Results: ${progress.success_count}/${progress.total_urls} successful`);
                    
                    if (currentDatabase) {
                        await refreshFiles();
                    }
                    return;
                }
                
                // Update progress display
                const percentage = Math.round((progress.current_index / progress.total_urls) * 100);
                
                document.getElementById('progress-current').textContent = progress.current_index;
                document.getElementById('progress-total').textContent = progress.total_urls;
                document.getElementById('progress-success').textContent = progress.success_count;
                document.getElementById('progress-failed').textContent = progress.failed_count;
                
                document.getElementById('current-url-text').textContent = progress.current_url || 'Processing...';
                document.getElementById('main-progress-bar').style.width = percentage + '%';
                document.getElementById('progress-percentage').textContent = percentage + '%';
                // Time calculations
               if (progress.start_time) {
                   const elapsed = (Date.now() - new Date(progress.start_time)) / 1000;
                   document.getElementById('elapsed-time').textContent = formatTime(elapsed);
                   
                   if (progress.current_index > 0) {
                       const avgTimePerUrl = elapsed / progress.current_index;
                       const remaining = (progress.total_urls - progress.current_index) * avgTimePerUrl;
                       document.getElementById('eta-time').textContent = formatTime(remaining);
                   }
               }
               
               document.getElementById('total-content').textContent = formatBytes(progress.total_chars);
               
           } catch (error) {
               console.error('Progress update error:', error);
           }
       }
       
       function formatTime(seconds) {
           if (seconds < 60) return Math.round(seconds) + 's';
           const minutes = Math.floor(seconds / 60);
           const secs = Math.round(seconds % 60);
           return `${minutes}m ${secs}s`;
       }
       
       function formatBytes(bytes) {
           if (bytes < 1024) return bytes + ' chars';
           if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + 'KB';
           return (bytes / (1024 * 1024)).toFixed(1) + 'MB';
       }
       
       async function cancelExtraction() {
           try {
               await fetch('/api/cancel_extraction', { method: 'POST' });
               clearInterval(extractionInterval);
               hideExtractionOverlay();
               addMessage('system', '❌ Extraction cancelled by user');
           } catch (error) {
               console.error('Cancel error:', error);
           }
       }
       
       async function sendMessage() {
           const userInput = document.getElementById('user-input');
           const message = userInput.value.trim();
           if (!message || !currentDatabase || selectedFiles.length === 0) return;
           
           addMessage('user', message);
           userInput.value = '';
           
           // Prepare request
           const requestData = {
               database: currentDatabase,
               files: selectedFiles,
               message: message,
               provider: document.getElementById('provider-select').value,
               api_key: document.getElementById('api-key-select').value,
               context_mode: document.getElementById('context-mode').value,
               master_contexts: getSelectedMasterContexts()
           };
           
           try {
               addMessage('system', '🔄 Processing through Remember infrastructure...');
               
               const response = await fetch('/api/chat', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify(requestData)
               });
               
               if (!response.ok) {
                   const errorData = await response.json();
                   throw new Error(errorData.detail || 'Server error');
               }
               
               const data = await response.json();
               
               // Capture session ID for raw log viewing
               if (data.session_id) {
                   lastSessionId = data.session_id;
               }
               
               addMessage('assistant', data.response);
               
               // Mark processed files
               if (data.processed_files && data.processed_files.length > 0) {
                   data.processed_files.forEach(fileId => {
                       processedFiles.add(fileId);
                       markFileAsProcessed(fileId);
                   });
               }
               
               // Show function call results if available
               if (data.function_calls && data.function_calls.length > 0) {
                   displayFunctionResults(data.function_calls);
               }
               
               if (data.debug_info) {
                   addMessage('system', `Debug: ${data.debug_info}`);
               }
               
           } catch (error) {
               addMessage('system', `❌ Error: ${error.message}`);
           }
       }
       
       async function startBatchProcess() {
           if (!currentDatabase) return;
           
           const prompt = window.prompt('Enter analysis prompt for batch processing:', 'LEGAL RESEARCH ANALYSIS PROMPT:\\n"You are a California legal expert analyzing documents for service of process defects in an unlawful detainer case. The defendant was substitute served on June 20th but claims the service was defective and fraudulent.\\nANALYZE these documents for ALL possible legal challenges to service of process, focusing on California CCP 415.20(b) substitute service requirements.\\nCASE FACTS: Defendant at work during service, girlfriend received papers, missing documents discovered June 22nd, waited for required certified mail that never came, court filed proof claiming PERSONAL service (fraud), default judgment entered.\\nEXTRACT every legal angle that could challenge this service, including jurisdiction arguments, procedural defects, fraud claims, due process violations, and any uncommon legal theories.\\nFocus on case-winning arguments with solid legal foundation."');
           
           if (!prompt) return;
           
           addMessage('system', `🚀 Starting batch processing with DeepSeek R1...`);
           addMessage('system', `📋 Analysis Prompt: ${prompt.substring(0, 200)}...`);
           
           // Get selected files
           const selectedFiles = [];
           document.querySelectorAll('.file-checkbox:checked').forEach(cb => {
               selectedFiles.push(cb.value);
           });
           
           if (selectedFiles.length === 0) {
               alert('Please select files to process');
               return;
           }
           
           const masterContext = document.getElementById('master-context-select').value;
           if (!masterContext) {
               alert('Please select a master context');
               return;
           }
           
           const requestData = {
               database: currentDatabase,
               selected_files: selectedFiles,
               master_context: masterContext,
               analysis_prompt: prompt,
               processing_mode: 'batch',
               provider: document.getElementById('provider-select').value || 'deepseek-r1-distill-llama-70b',
               api_key: 'auto'
           };
           
           try {
               addMessage('system', '⏳ Starting batch processing... Responses will stream in real-time.');
               
               const response = await fetch('/api/batch_process', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify(requestData)
               });
               
               const reader = response.body.getReader();
               const decoder = new TextDecoder();
               
               while (true) {
                   const { done, value } = await reader.read();
                   if (done) break;
                   
                   const chunk = decoder.decode(value);
                   const lines = chunk.split('\\n');
                   
                   for (const line of lines) {
                       if (line.startsWith('data: ')) {
                           try {
                               const data = JSON.parse(line.slice(6));
                               
                               if (data.type === 'response') {
                                   addMessage('system', `📄 Processing: ${data.title} (${data.processed}/${data.total})`);
                                   addMessage('assistant', data.content);
                               } else if (data.type === 'error') {
                                   addMessage('system', `❌ Error processing ${data.title}: ${data.error}`);
                               } else if (data.type === 'complete') {
                                   addMessage('system', `✅ Batch complete! Processed: ${data.processed_count}/${data.total_documents} (${data.success_rate.toFixed(1)}% success)`);
                                   
                                   // Add download buttons
                                   const chatMessages = document.getElementById('chat-messages');
                                   const lastMessage = chatMessages.lastElementChild;
                                   
                                   const actionsDiv = document.createElement('div');
                                   actionsDiv.style.cssText = 'margin-top: 10px; display: flex; gap: 5px; flex-wrap: wrap;';
                                   
                                   const viewDirBtn = document.createElement('button');
                                   viewDirBtn.textContent = '📁 Open Results Folder';
                                   viewDirBtn.className = 'btn';
                                   viewDirBtn.onclick = () => {
                                       alert('Results saved to: ' + data.batch_directory + '\\n\\nFiles created:\\n- Individual analyses: ' + data.processed_count + ' JSON + MD files\\n- Combined report: batch_report.md\\n- Summary: batch_summary.json');
                                   };
                                   
                                   const downloadBtn = document.createElement('button');
                                   downloadBtn.textContent = '💾 Download Summary';
                                   downloadBtn.className = 'btn';
                                   downloadBtn.onclick = () => downloadBatchSummary(data.batch_session);
                                   
                                   actionsDiv.appendChild(viewDirBtn);
                                   actionsDiv.appendChild(downloadBtn);
                                   lastMessage.appendChild(actionsDiv);
                               }
                           } catch (parseError) {
                               console.error('Error parsing stream data:', parseError);
                           }
                       }
                   }
               }
           } catch (error) {
               addMessage('system', `❌ Batch process error: ${error.message}`);
           }
       }
       
       async function downloadBatchSummary(batchSession) {
           try {
               const response = await fetch(`/api/download_batch_summary/${batchSession}`);
               if (response.ok) {
                   const blob = await response.blob();
                   const url = window.URL.createObjectURL(blob);
                   const a = document.createElement('a');
                   a.href = url;
                   a.download = `${batchSession}_summary.json`;
                   document.body.appendChild(a);
                   a.click();
                   window.URL.revokeObjectURL(url);
                   document.body.removeChild(a);
               }
           } catch (error) {
               alert(`Error downloading summary: ${error.message}`);
           }
       }
       
       async function startLegalAnalysis() {
           if (!currentDatabase || selectedFiles.length === 0) return;
           
           addMessage('system', '⚖️ Starting legal analysis on selected documents...');
           
           const message = 'Perform comprehensive legal analysis focusing on procedural issues, service defects, and statutory violations.';
           
           const requestData = {
               database: currentDatabase,
               files: selectedFiles,
               message: message,
               provider: document.getElementById('provider-select').value,
               api_key: document.getElementById('api-key-select').value,
               context_mode: 'fresh',
               master_contexts: ['service_defects', 'tpa_violations', 'court_procedure']
           };
           
           try {
               const response = await fetch('/api/chat', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify(requestData)
               });
               
               if (!response.ok) {
                   const errorData = await response.json();
                   throw new Error(errorData.detail || 'Server error');
               }
               
               const data = await response.json();
               addMessage('assistant', data.response);
               
           } catch (error) {
               addMessage('system', `❌ Legal analysis error: ${error.message}`);
           }
       }
       
       function addMessage(role, content) {
           const chatMessages = document.getElementById('chat-messages');
           const messageDiv = document.createElement('div');
           messageDiv.className = `message ${role}`;
           
           const roleSpan = document.createElement('div');
           roleSpan.className = 'message-role';
           roleSpan.textContent = role.toUpperCase();
           
           const contentDiv = document.createElement('div');
           contentDiv.className = 'message-content';
           contentDiv.textContent = content;
           
           messageDiv.appendChild(roleSpan);
           messageDiv.appendChild(contentDiv);
           
           // Add action buttons for assistant responses
           if (role === 'assistant' && !content.startsWith('❌')) {
               const actionsDiv = document.createElement('div');
               actionsDiv.style.cssText = 'margin-top: 10px; display: flex; gap: 5px; flex-wrap: wrap;';
               
               const saveBtn = document.createElement('button');
               saveBtn.textContent = '💾 Save to MCP';
               saveBtn.className = 'btn';
               saveBtn.onclick = () => saveResponseToMCP(content);
               
               const editBtn = document.createElement('button');
               editBtn.textContent = '✏️ Edit';
               editBtn.className = 'btn';
               editBtn.onclick = () => editResponse(contentDiv, content);
               
               const viewBtn = document.createElement('button');
               viewBtn.textContent = '👁️ View Full';
               viewBtn.className = 'btn';
               viewBtn.onclick = () => viewFullResponse(content);
               
               const rawLogsBtn = document.createElement('button');
               rawLogsBtn.textContent = '🔍 Raw Logs';
               rawLogsBtn.className = 'btn';
               rawLogsBtn.style.backgroundColor = '#2a2a2a';
               rawLogsBtn.onclick = () => viewRawLogs(lastSessionId);
               
               actionsDiv.appendChild(saveBtn);
               actionsDiv.appendChild(editBtn);
               actionsDiv.appendChild(viewBtn);
               actionsDiv.appendChild(rawLogsBtn);
               messageDiv.appendChild(actionsDiv);
           }
           
           chatMessages.appendChild(messageDiv);
           chatMessages.scrollTop = chatMessages.scrollHeight;
       }
       
       async function saveAnalysis(content) {
           const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
           const filename = `legal_analysis_${timestamp}.md`;
           
           try {
               const response = await fetch('/api/save_analysis', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify({
                       filename: filename,
                       content: content,
                       database: currentDatabase,
                       files: selectedFiles
                   })
               });
               
               const data = await response.json();
               if (data.success) {
                   addMessage('system', `✅ Analysis saved: ${filename}`);
               }
               
           } catch (error) {
               addMessage('system', `❌ Save error: ${error.message}`);
           }
       }
       
       // CONTEXT LLM FUNCTIONS
       async function sendContextToLLM(contextId) {
           try {
               // Load the context content
               const response = await fetch(`/api/master_context/${contextId}`);
               const data = await response.json();
               
               if (data.success) {
                   currentContextId = contextId;
                   currentContextContent = data.content;
                   
                   document.getElementById('context-modal-title').textContent = `🤖 Send "${data.name}" to LLM`;
                   document.getElementById('context-content-display').textContent = data.content;
                   document.getElementById('context-instructions').value = '';
                   document.getElementById('context-response').style.display = 'none';
                   document.getElementById('context-modal').style.display = 'flex';
               } else {
                   addMessage('system', `❌ Error loading context: ${data.error}`);
               }
           } catch (error) {
               addMessage('system', `❌ Error loading context: ${error.message}`);
           }
       }
       
       function closeContextModal() {
           document.getElementById('context-modal').style.display = 'none';
           currentContextId = null;
           currentContextContent = null;
       }
       
       async function sendContextRequest() {
           const instructions = document.getElementById('context-instructions').value.trim();
           if (!instructions || !currentContextContent) {
               alert('Please enter instructions for the LLM');
               return;
           }
           
           const sendBtn = document.getElementById('send-context-btn');
           sendBtn.disabled = true;
           sendBtn.textContent = '🔄 Processing...';
           
           try {
               const requestData = {
                   context_content: currentContextContent,
                   instructions: instructions,
                   provider: document.getElementById('context-provider-select').value,
                   api_key: "auto"
               };
               
               const response = await fetch('/api/improve_context', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify(requestData)
               });
               
               if (!response.ok) {
                   const errorData = await response.json();
                   throw new Error(errorData.detail || 'Server error');
               }
               
               const data = await response.json();
               document.getElementById('context-response-content').textContent = data.response;
               document.getElementById('context-response').style.display = 'block';
               
           } catch (error) {
               alert(`Error: ${error.message}`);
           } finally {
               sendBtn.disabled = false;
               sendBtn.textContent = '🚀 Send to LLM';
           }
       }
       
       async function saveContextResponse() {
           const responseContent = document.getElementById('context-response-content').textContent;
           if (!responseContent || !currentContextId) return;
           
           try {
               const response = await fetch('/api/save_context_response', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify({
                       context_id: currentContextId,
                       response: responseContent,
                       timestamp: new Date().toISOString()
                   })
               });
               
               const data = await response.json();
               if (data.success) {
                   alert(`✅ Response saved: ${data.filename}`);
               }
           } catch (error) {
               alert(`❌ Save error: ${error.message}`);
           }
       }
       
       async function replaceContext() {
           const responseContent = document.getElementById('context-response-content').textContent;
           if (!responseContent || !currentContextId) return;
           
           if (!confirm('Replace the original master context with this response?')) return;
           
           try {
               const response = await fetch('/api/update_master_context', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify({
                       context_id: currentContextId,
                       content: responseContent
                   })
               });
               
               const data = await response.json();
               if (data.success) {
                   alert('✅ Master context updated successfully!');
                   closeContextModal();
               }
           } catch (error) {
               alert(`❌ Update error: ${error.message}`);
           }
       }
       
       function viewContext(contextId) {
           sendContextToLLM(contextId);
           // Hide the instruction area and send button for view-only
           document.getElementById('context-instructions').style.display = 'none';
           document.querySelector('.context-instruction-area').previousElementSibling.style.display = 'none';
           document.getElementById('send-context-btn').parentElement.style.display = 'none';
       }
       
       function editContext(contextId) {
           // For now, just show view - we can enhance this later
           sendContextToLLM(contextId);
       }
       
       // FILE EDITING FUNCTIONS
       async function editFileContent(file) {
           currentEditFile = file;
           
           try {
               // Load content from both JSON and markdown file
               const response = await fetch('/api/load_file_content', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify({
                       url: file.url,
                       markdown_file: file.markdown_file,
                       json_content: file.content
                   })
               });
               
               const data = await response.json();
               
               if (data.success) {
                   document.getElementById('file-editor-title').textContent = `✏️ Edit: ${file.title}`;
                   document.getElementById('file-editor-textarea').value = data.content;
                   document.getElementById('file-editor-modal').style.display = 'flex';
                   
                   // Start auto-save
                   startAutoSave();
               } else {
                   alert(`Error loading file: ${data.error}`);
               }
           } catch (error) {
               alert(`Error: ${error.message}`);
           }
       }
       
       function closeFileEditor() {
           document.getElementById('file-editor-modal').style.display = 'none';
           stopAutoSave();
           currentEditFile = null;
       }
       
       function startAutoSave() {
           stopAutoSave(); // Clear any existing interval
           autoSaveInterval = setInterval(() => {
               autoSave();
           }, 30000); // Auto-save every 30 seconds
       }
       
       function stopAutoSave() {
           if (autoSaveInterval) {
               clearInterval(autoSaveInterval);
               autoSaveInterval = null;
           }
       }
       
       async function autoSave() {
           if (!currentEditFile) return;
           
           const content = document.getElementById('file-editor-textarea').value;
           
           try {
               const response = await fetch('/api/auto_save_file', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify({
                       url: currentEditFile.url,
                       content: content,
                       file_path: currentEditFile.markdown_file
                   })
               });
               
               const data = await response.json();
               if (data.success) {
                   // Update button text to indicate success
                   const saveBtn = document.getElementById('auto-save-btn');
                   saveBtn.textContent = '✅ Auto Saved';
                   setTimeout(() => {
                       saveBtn.textContent = '💾 Auto Save';
                   }, 2000);
               } else {
                   // Update button text to indicate failure
                   const saveBtn = document.getElementById('auto-save-btn');
                   saveBtn.textContent = '❌ Save Failed';
                   setTimeout(() => {
                       saveBtn.textContent = '💾 Auto Save';
                   }, 2000);
               }
           } catch (error) {
               // Update button text to indicate failure
               const saveBtn = document.getElementById('auto-save-btn');
               saveBtn.textContent = '❌ Save Failed';
               setTimeout(() => {
                       saveBtn.textContent = '💾 Auto Save';
                   }, 2000);
           }
       }
       
       async function saveFileContent() {
           if (!currentEditFile) return;
           
           const content = document.getElementById('file-editor-textarea').value;
           
           try {
               const response = await fetch('/api/save_file_content', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify({
                       url: currentEditFile.url,
                       content: content,
                       markdown_file: currentEditFile.markdown_file,
                       title: currentEditFile.title
                   })
               });
               
               const data = await response.json();
               if (data.success) {
                   alert('✅ File saved successfully! JSON and markdown file updated.');
                   closeFileEditor();
                   
                   // Refresh the file list
                   if (currentDatabase) {
                       await loadFiles(currentDatabase);
                   }
               } else {
                   alert(`❌ Save error: ${data.error}`);
               }
           } catch (error) {
               alert(`❌ Save error: ${error.message}`);
           }
       }
       
       async function loadVersion() {
           if (!currentEditFile) return;
           
           const version = document.getElementById('version-select').value;
           
           try {
               const response = await fetch('/api/load_file_version', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify({
                       url: currentEditFile.url,
                       version: version,
                       file_path: currentEditFile.markdown_file
                   })
               });
               const data = await response.json();
               if (data.success) {
                   document.getElementById('edit-content').value = data.content;
               }
           } catch (error) {
               console.error('Error loading version:', error);
           }
       }
       
       function selectAllFiles() {
           const fileItems = document.querySelectorAll('.file-item');
           selectedFiles = [];
           
           // Get file IDs from allFiles global array if available
           if (window.allFiles && window.allFiles.length > 0) {
               window.allFiles.forEach(file => {
                   const fileId = file.id;  // Use the actual document ID, not URL
                   if (fileId) {
                       selectedFiles.push(fileId);
                   }
               });
           } else {
               // Fallback: try to get from file list elements
               fileItems.forEach(item => {
                   // Look for vector ID in the content
                   const vectorMatch = item.innerHTML.match(/\[([^\]]+)\]/);
                   if (vectorMatch) {
                       selectedFiles.push(vectorMatch[1]);
                   }
               });
           }
           
           // Mark all file items as selected visually
           fileItems.forEach(item => item.classList.add('selected'));
           
           updateSelectionCount();
           updateCurrentContext();
           updateControls();
       }
       
       function deselectAllFiles() {
           const fileItems = document.querySelectorAll('.file-item');
           selectedFiles = [];
           fileItems.forEach(item => item.classList.remove('selected'));
           updateSelectionCount();
           updateCurrentContext();
           updateControls();
       }
       
       function updateSelectionCount() {
           const selected = selectedFiles.length;
           const selectionInfo = document.getElementById('selection-info');
           if (selectionInfo) {
               selectionInfo.textContent = `${selected} files selected`;
           }
       }
       
       async function viewContext(contextName) {
           try {
               const response = await fetch('/api/master_contexts');
               const data = await response.json();
               const context = data.contexts.find(c => c.name === contextName);
               
               if (context) {
                   const modal = window.open('', '_blank', 'width=800,height=600,scrollbars=yes');
                   modal.document.write(`
                       <html>
                       <head><title>Master Context: ${context.name}</title></head>
                       <body style="font-family: monospace; padding: 20px; background: #1e1e1e; color: #d4d4d4;">
                           <h2 style="color: #00ff00;">📋 ${context.name}</h2>
                           <p><strong>Size:</strong> ${context.size} characters</p>
                           <hr style="border-color: #333;">
                           <pre style="white-space: pre-wrap; font-size: 14px;">${context.content}</pre>
                       </body>
                       </html>
                   `);
               }
           } catch (error) {
               alert('Error loading context: ' + error.message);
           }
       }
       
       async function saveResponseToMCP(content) {
           try {
               const response = await fetch('/api/save_response_to_mcp', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify({
                       content: content,
                       database: currentDatabase,
                       timestamp: new Date().toISOString()
                   })
               });
               
               const data = await response.json();
               if (data.success) {
                   console.log('Save response data:', data);
                   console.log('Selected files:', selectedFiles);
                   console.log('Processed files:', processedFiles);
                   
                   alert('✅ Response saved to MCP database!');
                   
                   // Mark all currently processed files as saved and add nested info
                   selectedFiles.forEach(fileId => {
                       console.log(`Checking file ${fileId}, is processed:`, processedFiles.has(fileId));
                       if (processedFiles.has(fileId)) {
                           markFileAsSaved(fileId);
                           addNestedResponseInfo(fileId, data.vector_id, data.markdown_file);
                       }
                   });
                   
                   if (currentDatabase) await refreshFiles();
               } else {
                   alert('❌ Save error: ' + data.error);
               }
           } catch (error) {
               alert('❌ Save error: ' + error.message);
           }
       }
       
       function editResponse(contentDiv, content) {
           const textarea = document.createElement('textarea');
           textarea.value = content;
           textarea.style.cssText = 'width: 100%; height: 200px; background: #2a2a2a; color: #d4d4d4; border: 1px solid #333; padding: 10px; font-family: monospace;';
           
           const saveBtn = document.createElement('button');
           saveBtn.textContent = 'Save Changes';
           saveBtn.className = 'btn';
           saveBtn.onclick = () => {
               contentDiv.textContent = textarea.value;
               contentDiv.style.display = 'block';
               textarea.remove();
               saveBtn.remove();
               cancelBtn.remove();
           };
           
           const cancelBtn = document.createElement('button');
           cancelBtn.textContent = 'Cancel';
           cancelBtn.className = 'btn';
           cancelBtn.onclick = () => {
               contentDiv.style.display = 'block';
               textarea.remove();
               saveBtn.remove();
               cancelBtn.remove();
           };
           
           contentDiv.style.display = 'none';
           contentDiv.parentNode.insertBefore(textarea, contentDiv.nextSibling);
           contentDiv.parentNode.insertBefore(saveBtn, textarea.nextSibling);
           contentDiv.parentNode.insertBefore(cancelBtn, saveBtn.nextSibling);
       }
       
       function viewFullResponse(content) {
           const modal = window.open('', '_blank', 'width=1000,height=700,scrollbars=yes');
           modal.document.write(`
               <html>
               <head><title>Full Response</title></head>
               <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 20px; background: #1e1e1e; color: #d4d4d4; line-height: 1.6;">
                   <h2 style="color: #00ff00;">🤖 Full LLM Response</h2>
                   <hr style="border-color: #333;">
                   <pre style="white-space: pre-wrap; font-size: 14px; background: #2a2a2a; padding: 20px; border-radius: 5px; border: 1px solid #333;">${content}</pre>
               </body>
               </html>
           `);
       }
       
       function viewRawLogs(sessionId) {
           if (!sessionId) {
               alert('No session ID available');
               return;
           }
           window.open(`/api/view_session_logs/${sessionId}`, '_blank');
       }
       
       function markFileAsProcessed(fileId) {
           console.log('Marking file as processed:', fileId);
           const fileItems = document.querySelectorAll('.file-item');
           let found = false;
           fileItems.forEach(item => {
               // Check if this file item corresponds to the processed file
               const vectorMatch = item.innerHTML.match(/\[([^\]]+)\]/);
               if (vectorMatch && vectorMatch[1] === fileId) {
                   found = true;
                   console.log('Found matching file item for:', fileId);
                   item.classList.add('processed');
                   // Add status indicator if not already present
                   if (!item.querySelector('.file-status')) {
                       const statusDiv = document.createElement('div');
                       statusDiv.className = 'file-status status-processed';
                       statusDiv.textContent = '🔄 Processed';
                       item.appendChild(statusDiv);
                       console.log('Added processed status to:', fileId);
                   }
               }
           });
           if (!found) {
               console.log('No matching file item found for:', fileId);
           }
       }
       
       function markFileAsSaved(fileId) {
           const fileItems = document.querySelectorAll('.file-item');
           fileItems.forEach(item => {
               const vectorMatch = item.innerHTML.match(/\[([^\]]+)\]/);
               if (vectorMatch && vectorMatch[1] === fileId) {
                   item.classList.remove('processed');
                   item.classList.add('saved');
                   savedFiles.add(fileId);
                   
                   // Update status indicator
                   const existingStatus = item.querySelector('.file-status');
                   if (existingStatus) {
                       existingStatus.className = 'file-status status-saved';
                       existingStatus.textContent = '✅ Saved';
                   } else {
                       const statusDiv = document.createElement('div');
                       statusDiv.className = 'file-status status-saved';
                       statusDiv.textContent = '✅ Saved';
                       item.appendChild(statusDiv);
                   }
               }
           });
       }
       
       function maintainFileSelection() {
           // Re-apply selection highlighting for currently selected files
           const fileItems = document.querySelectorAll('.file-item');
           fileItems.forEach(item => {
               const vectorMatch = item.innerHTML.match(/\[([^\]]+)\]/);
               if (vectorMatch && selectedFiles.includes(vectorMatch[1])) {
                   item.classList.add('selected');
               }
           });
       }
       
       function addNestedResponseInfo(fileId, vectorId, markdownFile) {
           console.log('Adding nested response info for:', fileId, vectorId, markdownFile);
           // Store the info persistently
           fileResponseInfo.set(fileId, { vectorId, markdownFile });
           
           const fileItems = document.querySelectorAll('.file-item');
           let found = false;
           fileItems.forEach(item => {
               const vectorMatch = item.innerHTML.match(/\[([^\]]+)\]/);
               if (vectorMatch && vectorMatch[1] === fileId) {
                   found = true;
                   console.log('Adding response info to file item:', fileId);
                   
                   // Remove existing response info if any
                   const existingInfo = item.querySelector('.response-info');
                   if (existingInfo) {
                       existingInfo.remove();
                   }
                   
                   // Create new response info
                   const responseInfo = document.createElement('div');
                   responseInfo.className = 'response-info';
                   responseInfo.innerHTML = `
                       <strong>📄 Saved Response:</strong><br>
                       🆔 Vector ID: <code>${vectorId}</code><br>
                       📋 <a href="/api/view_markdown?file_path=${encodeURIComponent(markdownFile)}" target="_blank">View Markdown File</a>
                   `;
                   
                   item.appendChild(responseInfo);
                   console.log('Response info added successfully');
               }
           });
           if (!found) {
               console.log('No matching file item found for response info:', fileId);
           }
       }
   </script>
</body>
</html>""")

@app.post("/api/save_response_to_mcp")
async def save_response_to_mcp(request: dict):
    """Save LLM response to MCP database"""
    try:
        content = request.get("content", "")
        database = request.get("database", "remember_db")
        timestamp = request.get("timestamp", datetime.now().isoformat())
        
        if not content:
            return {"success": False, "error": "No content provided"}
        
        # Get database client
        if database == "remember_db":
            client = get_client()
        else:
            db_path = Path.home() / database
            client = chromadb.PersistentClient(path=str(db_path))
        
        # Create collection for LLM responses
        collection_name = f"llm_responses_{datetime.now().strftime('%Y%m')}"
        collection = get_or_create_collection(collection_name)
        
        # Generate vector ID
        doc_count = collection.count()
        vector_id = f"llm_response_{doc_count + 1:03d}"
        
        # Create metadata
        metadata = {
            "title": f"LLM Response {timestamp[:19]}",
            "type": "llm_response", 
            "timestamp": timestamp,
            "source": "chat_interface",
            "model": "deepseek-r1-distill-llama-70b"
        }
        
        # Add to collection
        collection.add(
            documents=[content],
            metadatas=[metadata],
            ids=[vector_id]
        )
        
        # Also save as markdown file
        responses_dir = Path.home() / "remember" / "llm_responses"
        responses_dir.mkdir(exist_ok=True)
        
        md_filename = f"response_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        md_file = responses_dir / md_filename
        
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(f"# LLM Response - {timestamp[:19]}\n\n")
            f.write(f"**Vector ID:** {vector_id}\n")
            f.write(f"**Timestamp:** {timestamp}\n")
            f.write(f"**Model:** deepseek-r1-distill-llama-70b\n\n")
            f.write("---\n\n")
            f.write(content)
        
        return {
            "success": True,
            "vector_id": vector_id,
            "collection": collection_name,
            "markdown_file": str(md_file)
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/view_session_logs/{session_id}")
async def view_session_logs(session_id: str):
    """View all logs for a specific session"""
    try:
        logs_dir = Path.home() / "remember" / "llm_logs"
        log_file = logs_dir / f"raw_llm_data_{datetime.now().strftime('%Y%m%d')}.json"
        
        if not log_file.exists():
            return {"success": False, "error": "No log file found for today"}
        
        # Read the log file
        with open(log_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split by separator and filter by session
        entries = content.split("=" * 50)
        session_entries = []
        
        for entry in entries:
            if entry.strip():
                try:
                    log_data = json.loads(entry.strip())
                    if log_data.get('session_id') == session_id:
                        session_entries.append(log_data)
                except json.JSONDecodeError:
                    continue
        
        # Sort by timestamp
        session_entries.sort(key=lambda x: x.get('timestamp', ''))
        
        html_content = """<html><head><title>Session Logs</title>
        <style>
            body { font-family: monospace; background-color: #1e1e1e; color: #d4d4d4; }
            .log-entry { border: 1px solid #333; padding: 10px; margin-bottom: 10px; border-radius: 5px; }
            .user { background-color: #2a2a2a; }
            .assistant { background-color: #253525; }
            .tool { background-color: #352525; }
            .timestamp { font-size: 0.8em; color: #888; }
            .session-title { color: #4ec9b0; font-size: 1.5em; margin-bottom: 20px; }
        </style>
        </head><body>
        """
        
        html_content += f"<div class='session-title'>Log for Session: {session_id}</div>"
        
        for log in session_entries:
            log_type = log.get('type', 'unknown')
            timestamp = log.get('timestamp', '')
            data = log.get('data', {})
            
            html_content += f"<div class='log-entry {log_type}'>"
            html_content += f"<div class='timestamp'>{timestamp}</div>"
            html_content += f"<strong>Type:</strong> {log_type}<br>"
            
            if isinstance(data, dict):
                for key, value in data.items():
                    # Pretty print nested JSON
                    if isinstance(value, (dict, list)):
                        value_str = json.dumps(value, indent=2)
                        html_content += f"<strong>{key}:</strong><br><pre>{value_str}</pre>"
                    else:
                        html_content += f"<strong>{key}:</strong> {value}<br>"
            else:
                html_content += f"<pre>{data}</pre>"
            
            html_content += "</div>"
            
        html_content += "</body></html>"
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    # Check for --headless argument
    is_headless = "--headless" in sys.argv

    # Get the script's directory
    script_dir = Path(__file__).parent.absolute()
    
    # Set the Uvicorn log level to warning to reduce console noise
    log_level = "info"
    
    # Start Uvicorn server
    uvicorn.run(
        "remember_web_ui:app", 
        host="0.0.0.0", 
        port=8080, 
        reload=False,
        log_level=log_level,
        reload_dirs=[str(script_dir)] 
    )