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
from fastapi.responses import HTMLResponse, PlainTextResponse
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
    from core.database import get_client, import_extraction_session
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
    """Log LLM interactions to file with timestamp"""
    timestamp = datetime.now().isoformat()
    session_id = session_id or f"session_{timestamp.replace(':', '').replace('-', '').replace('.', '')}"
    
    log_entry = {
        "timestamp": timestamp,
        "session_id": session_id,
        "type": interaction_type,
        "data": data
    }
    
    # Log to file
    log_file = logs_dir / f"raw_llm_data_{datetime.now().strftime('%Y%m%d')}.json"
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(log_entry, indent=2) + "\n" + "="*50 + "\n")
    
    logger.info(f"[{interaction_type}] Session: {session_id[:8]}... - Data logged")
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
    analysis_prompt: str
    processing_mode: str
    provider: str
    api_key: str = "auto"

@app.post("/api/batch_process")
async def batch_process_handler(request: BatchProcessRequest):
    """Handle batch processing with auto-save functionality"""
    try:
        # Get all documents from MCP
        mcp_result = await execute_mcp_tool("list_all_documents", {})
        
        if not mcp_result.get("success"):
            return {"success": False, "error": "Failed to load documents from MCP"}
        
        documents = mcp_result.get("documents", [])
        if not documents:
            return {"success": False, "error": "No documents found in MCP database"}
        
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
                
                # Load master contexts (use service_defects by default for batch)
                master_context_content = ""
                contexts_dir = Path.home() / "remember" / "master_contexts"
                context_file = contexts_dir / "service_defects.txt"
                if context_file.exists():
                    with open(context_file, 'r', encoding='utf-8') as f:
                        master_context_content = f.read()

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
        
        return {
            "success": True,
            "result": f"✅ Batch processing completed!\n\n📊 **Results:**\n- Processed: {processed_count}/{len(documents)} documents\n- Success Rate: {(processed_count/len(documents)*100):.1f}%\n- Failed: {failed_count}\n\n💾 **Auto-saved to:**\n- {batch_session_dir}\n- Individual analyses: {processed_count} JSON + MD files\n- Combined report: batch_report.md\n- Summary: batch_summary.json",
            "batch_session": f"batch_{timestamp}",
            "processed_count": processed_count,
            "failed_count": failed_count,
            "total_documents": len(documents),
            "batch_directory": str(batch_session_dir)
        }
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return {"success": False, "error": f"Batch processing failed: {str(e)}"}

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
                        <option value="deepseek-r1-distill-llama-70b">🧠 DeepSeek R1 Distill (70B) - 131K Context</option>
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
                    <div class="context-item">
                        <input type="checkbox" id="ctx-service" value="service_defects">
                        <label for="ctx-service">Service of Process Expert</label>
                        <button class="context-btn" onclick="viewContext('service_defects')">👁️</button>
                        <button class="context-btn" onclick="editContext('service_defects')">✏️</button>
                        <button class="context-btn" onclick="sendContextToLLM('service_defects')">🤖</button>
                    </div>
                    <div class="context-item">
                        <input type="checkbox" id="ctx-tpa" value="tpa_violations">
                        <label for="ctx-tpa">TPA Violation Specialist</label>
                        <button class="context-btn" onclick="viewContext('tpa_violations')">👁️</button>
                        <button class="context-btn" onclick="editContext('tpa_violations')">✏️</button>
                        <button class="context-btn" onclick="sendContextToLLM('tpa_violations')">🤖</button>
                    </div>
                    <div class="context-item">
                        <input type="checkbox" id="ctx-court" value="court_procedure">
                        <label for="ctx-court">Court Procedure Guide</label>
                        <button class="context-btn" onclick="viewContext('court_procedure')">👁️</button>
                        <button class="context-btn" onclick="editContext('court_procedure')">✏️</button>
                        <button class="context-btn" onclick="sendContextToLLM('court_procedure')">🤖</button>
                    </div>
                    <div class="context-item">
                        <input type="checkbox" id="ctx-timeline" value="case_timeline">
                        <label for="ctx-timeline">Case Timeline Master</label>
                        <button class="context-btn" onclick="viewContext('case_timeline')">👁️</button>
                        <button class="context-btn" onclick="editContext('case_timeline')">✏️</button>
                        <button class="context-btn" onclick="sendContextToLLM('case_timeline')">🤖</button>
                    </div>
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
            
            <!-- MCP Mode Controls -->
            <div id="mcp-mode-controls" style="margin-bottom: 15px; display: flex; gap: 5px; flex-wrap: wrap;">
                <button class="btn extract" id="extract-urls-btn">
                    🚀 Extract URLs
                </button>
                <button class="btn batch" id="batch-process-btn" disabled>
                    Batch Process All
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
                                    <option value="deepseek-r1-distill-llama-70b">🧠 DeepSeek R1 Distill (70B) - 131K Context</option>
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
        let currentContextContent = null;
        let currentEditFile = null;
        let noProcessList = new Set();
        let autoSaveInterval = null;

        // Initialize
        loadDatabases();
        
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
                        
                        fileDiv.onclick = () => toggleFileSelection(file.url, fileDiv);
                        
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
           
           const prompt = window.prompt('Enter analysis prompt for batch processing:', 
               'LEGAL RESEARCH ANALYSIS PROMPT:\n"You are a California legal expert analyzing documents for service of process defects in an unlawful detainer case. The defendant was substitute served on June 20th but claims the service was defective and fraudulent.\nANALYZE these documents for ALL possible legal challenges to service of process, focusing on California CCP 415.20(b) substitute service requirements.\nCASE FACTS: Defendant at work during service, girlfriend received papers, missing documents discovered June 22nd, waited for required certified mail that never came, court filed proof claiming PERSONAL service (fraud), default judgment entered.\nEXTRACT every legal angle that could challenge this service, including jurisdiction arguments, procedural defects, fraud claims, due process violations, and any uncommon legal theories.\nFocus on case-winning arguments with solid legal foundation."');
           
           if (!prompt) return;
           
           addMessage('system', `🚀 Starting batch processing with DeepSeek R1...`);
           addMessage('system', `📋 Analysis Prompt: ${prompt.substring(0, 200)}...`);
           
           const requestData = {
               database: currentDatabase,
               analysis_prompt: prompt,
               processing_mode: 'batch',
               provider: document.getElementById('provider-select').value || 'deepseek-r1-distill-llama-70b',
               api_key: 'auto'
           };
           
           try {
               addMessage('system', '⏳ Processing all documents... This may take several minutes.');
               
               const response = await fetch('/api/batch_process', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify(requestData)
               });
               
               if (!response.ok) {
                   const errorData = await response.json();
                   throw new Error(errorData.detail || 'Server error');
               }
               
               const data = await response.json();
               
               if (data.success) {
                   addMessage('assistant', data.result);
                   
                   // Add buttons to view batch results
                   const chatMessages = document.getElementById('chat-messages');
                   const lastMessage = chatMessages.lastElementChild;
                   
                   const actionsDiv = document.createElement('div');
                   actionsDiv.style.cssText = 'margin-top: 10px; display: flex; gap: 5px; flex-wrap: wrap;';
                   
                   const viewDirBtn = document.createElement('button');
                   viewDirBtn.textContent = '📁 Open Results Folder';
                   viewDirBtn.className = 'btn';
                   viewDirBtn.onclick = () => {
                       // Show path to user
                       alert(`Results saved to: ${data.batch_directory}\n\nFiles created:\n- Individual analyses: ${data.processed_count} JSON + MD files\n- Combined report: batch_report.md\n- Summary: batch_summary.json`);
                   };
                   
                   const downloadBtn = document.createElement('button');
                   downloadBtn.textContent = '💾 Download Summary';
                   downloadBtn.className = 'btn';
                   downloadBtn.onclick = () => downloadBatchSummary(data.batch_session);
                   
                   actionsDiv.appendChild(viewDirBtn);
                   actionsDiv.appendChild(downloadBtn);
                   lastMessage.appendChild(actionsDiv);
               } else {
                   addMessage('system', `❌ Batch processing failed: ${data.error}`);
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
           const saveBtn = document.getElementById('auto-save-btn');
           
           try {
               saveBtn.textContent = '💾 Saving...';
               
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
                   saveBtn.textContent = '✅ Auto Saved';
                   setTimeout(() => {
                       saveBtn.textContent = '💾 Auto Save';
                   }, 2000);
               }
           } catch (error) {
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
                   document.getElementById('file-editor-textarea').value = data.content;
               } else {
                   alert(`Error loading version: ${data.error}`);
               }
           } catch (error) {
               alert(`Error: ${error.message}`);
           }
       }
       
       function toggleNoProcess(url, button) {
           if (noProcessList.has(url)) {
               noProcessList.delete(url);
               button.classList.remove('no-process');
               button.title = 'Mark as do not process';
           } else {
               noProcessList.add(url);
               button.classList.add('no-process');
               button.title = 'Remove from do not process';
           }
           
           // Save to localStorage
           localStorage.setItem('noProcessList', JSON.stringify([...noProcessList]));
       }
       
       // Load no-process list on startup
       function loadNoProcessList() {
           const saved = localStorage.getItem('noProcessList');
           if (saved) {
               noProcessList = new Set(JSON.parse(saved));
           }
       }
       
       // Call on page load
       loadNoProcessList();
       
       // ===============================
       // MASTER CONTEXT MANAGEMENT
       // ===============================
       
       function showContextManager() {
           // Create and show context manager modal
           const modal = document.createElement('div');
           modal.className = 'context-manager-modal';
           modal.innerHTML = `
               <div class="context-manager-content">
                   <div class="context-manager-header">
                       <span>🧠 Master Context Manager</span>
                       <button class="btn" onclick="closeContextManager()">❌ Close</button>
                   </div>
                   <div class="context-manager-body">
                       <div class="context-tabs">
                           <button class="tab-btn active" onclick="showContextTab('list')">📋 List</button>
                           <button class="tab-btn" onclick="showContextTab('create')">➕ Create</button>
                           <button class="tab-btn" onclick="showContextTab('edit')">✏️ Edit</button>
                       </div>
                       <div id="context-tab-content">
                           <div id="context-list-tab">Loading contexts...</div>
                           <div id="context-create-tab" style="display: none;">
                               <div class="create-context-form">
                                   <label>Context Name:</label>
                                   <input type="text" id="new-context-name" placeholder="e.g., Service_Expert">
                                   <label>Context Content:</label>
                                   <textarea id="new-context-content" rows="15" placeholder="Enter master context content..."></textarea>
                                   <button class="btn primary" onclick="createNewContext()">💾 Create Context</button>
                               </div>
                           </div>
                           <div id="context-edit-tab" style="display: none;">
                               <div class="edit-context-form">
                                   <label>Select Context to Edit:</label>
                                   <select id="edit-context-select">
                                       <option value="">Choose context...</option>
                                   </select>
                                   <label>Context Content:</label>
                                   <textarea id="edit-context-content" rows="15" placeholder="Context content will load here..."></textarea>
                                   <div style="display: flex; gap: 10px; margin-top: 10px;">
                                       <button class="btn primary" onclick="saveContextChanges()">💾 Save Changes</button>
                                       <button class="btn warning" onclick="deleteContext()">🗑️ Delete Context</button>
                                       <button class="btn" onclick="revertContext()">↩️ Revert</button>
                                   </div>
                               </div>
                           </div>
                       </div>
                   </div>
               </div>
           `;
           
           // Add CSS for modal
           const style = document.createElement('style');
           style.textContent = `
               .context-manager-modal {
                   position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                   background: rgba(0,0,0,0.8); z-index: 1000; display: flex;
                   justify-content: center; align-items: center;
               }
               .context-manager-content {
                   background: #1a1a1a; border: 1px solid #333; border-radius: 8px;
                   width: 80%; max-width: 900px; height: 80%; display: flex; flex-direction: column;
               }
               .context-manager-header {
                   padding: 15px; background: #2a2a2a; border-bottom: 1px solid #333;
                   display: flex; justify-content: space-between; align-items: center;
                   font-weight: bold; color: #00ff00;
               }
               .context-manager-body { flex: 1; padding: 15px; overflow: hidden; }
               .context-tabs { display: flex; gap: 5px; margin-bottom: 15px; }
               .tab-btn { padding: 8px 15px; background: #333; border: 1px solid #555; color: #ccc; cursor: pointer; }
               .tab-btn.active { background: #0a4a0a; border-color: #00ff00; color: #00ff00; }
               #context-tab-content { height: calc(100% - 60px); overflow-y: auto; }
               .create-context-form, .edit-context-form { display: flex; flex-direction: column; gap: 10px; }
               .create-context-form input, .create-context-form textarea,
               .edit-context-form select, .edit-context-form textarea {
                   background: #333; color: #00ff00; border: 1px solid #555; padding: 8px;
                   font-family: inherit; font-size: 12px;
               }
               .context-item { 
                   background: #2a2a2a; border: 1px solid #333; margin-bottom: 10px; 
                   padding: 10px; border-radius: 4px; display: flex; justify-content: space-between; 
               }
               .context-info { flex: 1; }
               .context-name { font-weight: bold; color: #00ff00; }
               .context-meta { font-size: 10px; color: #888; margin-top: 5px; }
               .context-actions { display: flex; gap: 5px; }
               .context-action-btn { 
                   padding: 2px 6px; font-size: 8px; background: #333; 
                   border: 1px solid #555; color: #ccc; cursor: pointer; 
               }
           `;
           
           document.head.appendChild(style);
           document.body.appendChild(modal);
           
           // Load initial context list
           loadMasterContextsList();
       }
       
       function closeContextManager() {
           const modal = document.querySelector('.context-manager-modal');
           if (modal) modal.remove();
       }
       
       function showContextTab(tabName) {
           // Update tab buttons
           document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
           event.target.classList.add('active');
           
           // Show/hide tab content
           document.getElementById('context-list-tab').style.display = tabName === 'list' ? 'block' : 'none';
           document.getElementById('context-create-tab').style.display = tabName === 'create' ? 'block' : 'none';
           document.getElementById('context-edit-tab').style.display = tabName === 'edit' ? 'block' : 'none';
           
           if (tabName === 'edit') {
               loadContextsForEdit();
           }
       }
       
       async function loadMasterContextsList() {
           try {
               const response = await fetch('/api/master_contexts/list');
               const data = await response.json();
               
               const listTab = document.getElementById('context-list-tab');
               if (data.success) {
                   listTab.innerHTML = data.contexts.map(ctx => `
                       <div class="context-item">
                           <div class="context-info">
                               <div class="context-name">${ctx.id}</div>
                               <div class="context-meta">${ctx.size} chars | Modified: ${ctx.modified}</div>
                           </div>
                           <div class="context-actions">
                               <button class="context-action-btn" onclick="viewContext('${ctx.id}')">👁️ View</button>
                               <button class="context-action-btn" onclick="editContextDirect('${ctx.id}')">✏️ Edit</button>
                               <button class="context-action-btn" onclick="deleteContextDirect('${ctx.id}')">🗑️ Delete</button>
                           </div>
                       </div>
                   `).join('');
               } else {
                   listTab.innerHTML = '<div style="color: red;">Error loading contexts</div>';
               }
           } catch (error) {
               document.getElementById('context-list-tab').innerHTML = '<div style="color: red;">Failed to load contexts</div>';
           }
       }
       
       async function loadContextsForEdit() {
           try {
               const response = await fetch('/api/master_contexts/list');
               const data = await response.json();
               
               const select = document.getElementById('edit-context-select');
               if (data.success) {
                   select.innerHTML = '<option value="">Choose context...</option>' +
                       data.contexts.map(ctx => `<option value="${ctx.id}">${ctx.id}</option>`).join('');
               }
           } catch (error) {
               console.error('Failed to load contexts for edit:', error);
           }
       }
       
       async function createNewContext() {
           const name = document.getElementById('new-context-name').value.trim();
           const content = document.getElementById('new-context-content').value.trim();
           
           if (!name || !content) {
               alert('Please provide both name and content');
               return;
           }
           
           try {
               const response = await fetch('/api/master_contexts/create', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify({id: name, content: content})
               });
               
               const result = await response.json();
               if (result.success) {
                   alert('✅ Context created successfully!');
                   document.getElementById('new-context-name').value = '';
                   document.getElementById('new-context-content').value = '';
                   loadMasterContextsList();
               } else {
                   alert(`❌ Error: ${result.error}`);
               }
           } catch (error) {
               alert(`❌ Error creating context: ${error.message}`);
           }
       }
       
       // Add event listener for context selection
       document.addEventListener('change', async function(e) {
           if (e.target.id === 'edit-context-select') {
               const contextId = e.target.value;
               if (contextId) {
                   try {
                       const response = await fetch(`/api/master_context/${contextId}`);
                       const data = await response.json();
                       
                       if (data.success) {
                           document.getElementById('edit-context-content').value = data.content;
                       } else {
                           alert(`❌ Error loading context: ${data.error}`);
                       }
                   } catch (error) {
                       alert(`❌ Error: ${error.message}`);
                   }
               }
           }
       });
       
       async function saveContextChanges() {
           const contextId = document.getElementById('edit-context-select').value;
           const content = document.getElementById('edit-context-content').value;
           
           if (!contextId) {
               alert('Please select a context to edit');
               return;
           }
           
           try {
               const response = await fetch('/api/update_master_context', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify({context_id: contextId, content: content})
               });
               
               const result = await response.json();
               if (result.success) {
                   alert('✅ Context saved successfully!');
                   loadMasterContextsList();
               } else {
                   alert(`❌ Error: ${result.error}`);
               }
           } catch (error) {
               alert(`❌ Error saving context: ${error.message}`);
           }
       }
       
       async function deleteContext() {
           const contextId = document.getElementById('edit-context-select').value;
           if (!contextId) {
               alert('Please select a context to delete');
               return;
           }
           
           if (!confirm(`Are you sure you want to delete context "${contextId}"?`)) return;
           
           try {
               const response = await fetch(`/api/master_contexts/delete/${contextId}`, {
                   method: 'DELETE'
               });
               
               const result = await response.json();
               if (result.success) {
                   alert('✅ Context deleted successfully!');
                   document.getElementById('edit-context-select').value = '';
                   document.getElementById('edit-context-content').value = '';
                   loadMasterContextsList();
                   loadContextsForEdit();
               } else {
                   alert(`❌ Error: ${result.error}`);
               }
           } catch (error) {
               alert(`❌ Error deleting context: ${error.message}`);
           }
       }
       
       // ===============================
       // FILE SELECTION CONTROLS
       // ===============================
       
       function selectAllFiles() {
           const fileItems = document.querySelectorAll('.file-item');
           fileItems.forEach(item => {
               if (!item.classList.contains('selected')) {
                   item.click();
               }
           });
           updateSelectionCount();
       }
       
       function deselectAllFiles() {
           selectedFiles = [];
           document.querySelectorAll('.file-item.selected').forEach(item => {
               item.classList.remove('selected');
           });
           updateSelectionCount();
           updateCurrentContext();
       }
       
       function invertSelection() {
           const fileItems = document.querySelectorAll('.file-item');
           fileItems.forEach(item => {
               item.click();
           });
           updateSelectionCount();
       }
       
       function selectHighRated() {
           deselectAllFiles();
           
           // Load from extraction results and select 5-star files
           loadExtractionResults().then(extractionFiles => {
               if (extractionFiles) {
                   extractionFiles.forEach(file => {
                       if (file.rating === 5) {
                           toggleFileSelection(file.url, null);
                       }
                   });
                   updateSelectionCount();
               }
           });
       }
       
       function updateSelectionCount() {
           const count = selectedFiles.length;
           const countEl = document.getElementById('selection-count');
           if (countEl) {
               countEl.textContent = `${count} selected`;
           }
       }
       
       async function deleteFileFromDatabase(fileUrl) {
           if (!confirm(`Are you sure you want to delete this file from the database?\n\nURL: ${fileUrl}`)) {
               return;
           }
           
           try {
               // Get file ID (hash of URL)
               const fileId = `url_${await digestMessage(fileUrl)}`;
               
               const response = await fetch(`/api/database/${currentDatabase}/file/${fileId}`, {
                   method: 'DELETE'
               });
               
               const result = await response.json();
               if (result.success) {
                   alert('✅ File deleted from database!');
                   // Refresh file list
                   if (currentDatabase) {
                       await loadFiles(currentDatabase);
                   }
               } else {
                   alert(`❌ Error: ${result.error}`);
               }
           } catch (error) {
               alert(`❌ Error deleting file: ${error.message}`);
           }
       }
       
       // Helper function to create MD5 hash
       async function digestMessage(message) {
           const msgUint8 = new TextEncoder().encode(message);
           const hashBuffer = await crypto.subtle.digest('MD5', msgUint8);
           const hashArray = Array.from(new Uint8Array(hashBuffer));
           const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
           return hashHex;
       }
       
       // ===============================
       // NOTES MANAGEMENT
       // ===============================
       
       async function saveQuickNotes() {
           const content = document.getElementById('quick-notes').value.trim();
           if (!content) {
               alert('Please enter some notes first');
               return;
           }
           
           try {
               const response = await fetch('/api/notes/quick', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify({
                       content: content,
                       timestamp: new Date().toISOString()
                   })
               });
               
               const result = await response.json();
               if (result.success) {
                   document.getElementById('quick-notes').value = '';
                   loadNotesList();
                   alert('✅ Notes saved!');
               } else {
                   alert(`❌ Error: ${result.error}`);
               }
           } catch (error) {
               alert(`❌ Error saving notes: ${error.message}`);
           }
       }
       
       async function loadNotesList() {
           try {
               const response = await fetch('/api/notes/list');
               const data = await response.json();
               
               const notesList = document.getElementById('notes-list');
               if (data.success && data.notes.length > 0) {
                   notesList.innerHTML = data.notes.map(note => `
                       <div class="note-item" style="background: #2a2a2a; border: 1px solid #333; margin-bottom: 5px; padding: 5px; border-radius: 2px;">
                           <div style="font-size: 9px; color: #888; margin-bottom: 2px;">${note.timestamp}</div>
                           <div style="font-size: 10px; color: #ccc;">${note.content}</div>
                           <div style="margin-top: 3px;">
                               <button class="btn" style="font-size: 8px; padding: 1px 4px;" onclick="editNote('${note.id}')">✏️</button>
                               <button class="btn" style="font-size: 8px; padding: 1px 4px;" onclick="deleteNote('${note.id}')">🗑️</button>
                           </div>
                       </div>
                   `).join('');
               } else {
                   notesList.innerHTML = '<div style="font-size: 10px; color: #666;">No notes yet</div>';
               }
           } catch (error) {
               document.getElementById('notes-list').innerHTML = '<div style="color: red; font-size: 10px;">Error loading notes</div>';
           }
       }
       
       function showNotesManager() {
           // Create notes manager modal (similar to context manager)
           const modal = document.createElement('div');
           modal.className = 'notes-manager-modal';
           modal.innerHTML = `
               <div class="notes-manager-content" style="background: #1a1a1a; border: 1px solid #333; border-radius: 8px; width: 70%; max-width: 800px; height: 70%; display: flex; flex-direction: column;">
                   <div class="notes-manager-header" style="padding: 15px; background: #2a2a2a; border-bottom: 1px solid #333; display: flex; justify-content: space-between; align-items: center; font-weight: bold; color: #00ff00;">
                       <span>📝 Notes Manager</span>
                       <button class="btn" onclick="closeNotesManager()">❌ Close</button>
                   </div>
                   <div class="notes-manager-body" style="flex: 1; padding: 15px; overflow-y: auto;">
                       <div style="margin-bottom: 15px;">
                           <label>New Note:</label>
                           <textarea id="new-note-content" rows="5" style="width: 100%; background: #333; color: #00ff00; border: 1px solid #555; padding: 8px; font-family: inherit; font-size: 12px;" placeholder="Enter your note..."></textarea>
                           <button class="btn primary" style="margin-top: 5px;" onclick="createNewNote()">💾 Save Note</button>
                       </div>
                       <div id="all-notes-list">Loading notes...</div>
                   </div>
               </div>
           `;
           
           // Add modal styles
           modal.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 1000; display: flex; justify-content: center; align-items: center;';
           
           document.body.appendChild(modal);
           loadAllNotes();
       }
       
       function closeNotesManager() {
           const modal = document.querySelector('.notes-manager-modal');
           if (modal) modal.remove();
       }
       
       async function createNewNote() {
           const content = document.getElementById('new-note-content').value.trim();
           if (!content) {
               alert('Please enter note content');
               return;
           }
           
           try {
               const response = await fetch('/api/notes/create', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify({content: content})
               });
               
               const result = await response.json();
               if (result.success) {
                   document.getElementById('new-note-content').value = '';
                   loadAllNotes();
                   loadNotesList(); // Refresh sidebar notes
                   alert('✅ Note created!');
               } else {
                   alert(`❌ Error: ${result.error}`);
               }
           } catch (error) {
               alert(`❌ Error: ${error.message}`);
           }
       }
       
       async function loadAllNotes() {
           try {
               const response = await fetch('/api/notes/list');
               const data = await response.json();
               
               const notesList = document.getElementById('all-notes-list');
               if (data.success && data.notes.length > 0) {
                   notesList.innerHTML = data.notes.map(note => `
                       <div class="note-item" style="background: #2a2a2a; border: 1px solid #333; margin-bottom: 10px; padding: 10px; border-radius: 4px;">
                           <div style="font-size: 10px; color: #888; margin-bottom: 5px;">${note.timestamp}</div>
                           <div style="font-size: 12px; color: #ccc; white-space: pre-wrap;">${note.content}</div>
                           <div style="margin-top: 10px; display: flex; gap: 5px;">
                               <button class="btn" onclick="editNote('${note.id}')">✏️ Edit</button>
                               <button class="btn warning" onclick="deleteNote('${note.id}')">🗑️ Delete</button>
                           </div>
                       </div>
                   `).join('');
               } else {
                   notesList.innerHTML = '<div style="color: #666;">No notes yet</div>';
               }
           } catch (error) {
               document.getElementById('all-notes-list').innerHTML = '<div style="color: red;">Error loading notes</div>';
           }
       }
       
       async function deleteNote(noteId) {
           if (!confirm('Are you sure you want to delete this note?')) return;
           
           try {
               const response = await fetch(`/api/notes/delete/${noteId}`, {
                   method: 'DELETE'
               });
               
               const result = await response.json();
               if (result.success) {
                   loadAllNotes();
                   loadNotesList();
                   alert('✅ Note deleted!');
               } else {
                   alert(`❌ Error: ${result.error}`);
               }
           } catch (error) {
               alert(`❌ Error: ${error.message}`);
           }
       }
       
       // Load notes on page load
       document.addEventListener('DOMContentLoaded', function() {
           loadNotesList();
       });
       
       // ===============================
       // FUNCTION CALL RESULTS DISPLAY
       // ===============================
       
       function displayFunctionResults(functionCalls) {
           const messagesContainer = document.getElementById('chat-messages');
           
           functionCalls.forEach(call => {
               if (call.function === 'search_documents' && call.result.success) {
                   const results = call.result.results || [];
                   
                   if (results.length > 0) {
                       const resultsDiv = document.createElement('div');
                       resultsDiv.className = 'message system';
                       resultsDiv.innerHTML = `
                           <div class="message-role">📋 Search Results (${results.length} documents found)</div>
                           <div class="message-content">
                               <div class="function-results">
                                   ${results.map((doc, index) => `
                                       <div class="result-item" style="background: #2a2a2a; border: 1px solid #333; margin: 8px 0; padding: 10px; border-radius: 4px;">
                                           <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                                               <div style="flex: 1;">
                                                   <div style="font-weight: bold; color: #00ff00; margin-bottom: 5px;">${doc.title}</div>
                                                   <div style="font-size: 10px; color: #888; margin-bottom: 5px;">
                                                       Rating: ${doc.rating}⭐ | Length: ${doc.content_length.toLocaleString()} chars
                                                   </div>
                                                   <div style="font-size: 11px; color: #ccc; margin-bottom: 8px;">
                                                       ${doc.content_preview}
                                                   </div>
                                                   <div style="font-size: 9px; color: #666;">
                                                       URL: ${doc.url}
                                                   </div>
                                               </div>
                                               <div style="display: flex; flex-direction: column; gap: 4px; margin-left: 10px;">
                                                   ${doc.markdown_file ? `
                                                       <button class="btn" style="font-size: 8px; padding: 3px 6px;" 
                                                               onclick="viewMarkdownFromResult('${doc.markdown_file}', '${doc.title}')">
                                                           👁️ View
                                                       </button>
                                                       <button class="btn" style="font-size: 8px; padding: 3px 6px;" 
                                                               onclick="editMarkdownFromResult('${doc.markdown_file}', '${doc.title}', '${doc.url}')">
                                                           ✏️ Edit
                                                       </button>
                                                   ` : ''}
                                                   <button class="btn" style="font-size: 8px; padding: 3px 6px;" 
                                                           onclick="getFullDocument('${doc.url}')">
                                                       📄 Full
                                                   </button>
                                               </div>
                                           </div>
                                       </div>
                                   `).join('')}
                               </div>
                           </div>
                       `;
                       
                       messagesContainer.appendChild(resultsDiv);
                       messagesContainer.scrollTop = messagesContainer.scrollHeight;
                   }
               }
           });
       }
       
       function viewMarkdownFromResult(markdownPath, title) {
           // Open markdown file in popup
           const url = `/api/view_markdown?file_path=${encodeURIComponent(markdownPath)}`;
           const popup = window.open(url, '_blank', 'width=1000,height=800,scrollbars=yes,resizable=yes');
           if (popup) {
               popup.document.title = `Markdown Viewer - ${title}`;
           }
       }
       
       function editMarkdownFromResult(markdownPath, title, originalUrl) {
           // Create edit modal for markdown content
           openMarkdownEditor(markdownPath, title, originalUrl);
       }
       
       async function openMarkdownEditor(markdownPath, title, originalUrl) {
           try {
               // Load current content
               const response = await fetch(`/api/load_markdown_content?file_path=${encodeURIComponent(markdownPath)}`);
               const data = await response.json();
               
               if (!data.success) {
                   alert(`Error loading file: ${data.error}`);
                   return;
               }
               
               // Create editor modal
               const modal = document.createElement('div');
               modal.className = 'markdown-editor-modal';
               modal.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 1000; display: flex; justify-content: center; align-items: center;';
               
               modal.innerHTML = `
                   <div class="markdown-editor-content" style="background: #1a1a1a; border: 1px solid #333; border-radius: 8px; width: 90%; height: 90%; display: flex; flex-direction: column;">
                       <div class="markdown-editor-header" style="padding: 15px; background: #2a2a2a; border-bottom: 1px solid #333; display: flex; justify-content: space-between; align-items: center; font-weight: bold; color: #00ff00;">
                           <span>✏️ Edit Document: ${title}</span>
                           <div>
                               <button class="btn primary" onclick="saveMarkdownContent('${markdownPath}', '${originalUrl}')">💾 Save</button>
                               <button class="btn" onclick="closeMarkdownEditor()">❌ Close</button>
                           </div>
                       </div>
                       <div class="markdown-editor-body" style="flex: 1; padding: 15px; overflow: hidden;">
                           <div style="margin-bottom: 10px; font-size: 10px; color: #888;">
                               File: ${markdownPath}
                           </div>
                           <textarea id="markdown-content-editor" style="width: 100%; height: calc(100% - 30px); background: #333; color: #00ff00; border: 1px solid #555; padding: 10px; font-family: monospace; font-size: 12px; resize: none;">${data.content}</textarea>
                       </div>
                   </div>
               `;
               
               document.body.appendChild(modal);
               
           } catch (error) {
               alert(`Error opening editor: ${error.message}`);
           }
       }
       
       function closeMarkdownEditor() {
           const modal = document.querySelector('.markdown-editor-modal');
           if (modal) modal.remove();
       }
       
       async function saveMarkdownContent(markdownPath, originalUrl) {
           const content = document.getElementById('markdown-content-editor').value;
           
           try {
               const response = await fetch('/api/save_markdown_content', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify({
                       file_path: markdownPath,
                       content: content,
                       url: originalUrl
                   })
               });
               
               const result = await response.json();
               if (result.success) {
                   alert('✅ Markdown file saved successfully!');
                   closeMarkdownEditor();
               } else {
                   alert(`❌ Error saving: ${result.error}`);
               }
           } catch (error) {
               alert(`❌ Error: ${error.message}`);
           }
       }
       
       async function getFullDocument(url) {
           try {
               // Use MCP to get full document content
               const response = await fetch('/api/mcp_get_document', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify({document_id: url})
               });
               
               const data = await response.json();
               if (data.success) {
                   // Display full content in a modal
                   showFullDocumentModal(data.document);
               } else {
                   alert(`Error getting full document: ${data.error}`);
               }
           } catch (error) {
               alert(`Error: ${error.message}`);
           }
       }
       
       function showFullDocumentModal(document) {
           const modal = document.createElement('div');
           modal.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 1000; display: flex; justify-content: center; align-items: center;';
           
           modal.innerHTML = `
               <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 8px; width: 80%; height: 80%; display: flex; flex-direction: column;">
                   <div style="padding: 15px; background: #2a2a2a; border-bottom: 1px solid #333; display: flex; justify-content: space-between; align-items: center; font-weight: bold; color: #00ff00;">
                       <span>📄 ${document.title}</span>
                       <button class="btn" onclick="this.closest('div').parentElement.parentElement.remove()">❌ Close</button>
                   </div>
                   <div style="flex: 1; padding: 15px; overflow-y: auto;">
                       <div style="font-size: 10px; color: #888; margin-bottom: 10px;">
                           Rating: ${document.rating}⭐ | Length: ${document.content_length} chars
                       </div>
                       <div style="white-space: pre-wrap; font-size: 12px; color: #ccc; line-height: 1.4;">
                           ${document.full_content}
                       </div>
                   </div>
               </div>
           `;
           
           document.body.appendChild(modal);
       }
       
       // ===============================
       // LLM RESPONSE MANAGEMENT
       // ===============================
       
       async function saveResponseToMCP(content) {
           const title = prompt('Enter title for this analysis:');
           if (!title) return;
           
           try {
               const response = await fetch('/api/save_response_to_mcp', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify({
                       title: title,
                       content: content,
                       timestamp: new Date().toISOString()
                   })
               });
               
               const result = await response.json();
               if (result.success) {
                   alert('✅ Response saved to MCP database!');
                   // Refresh MCP file list if in MCP mode
                   if (currentDatabase && document.querySelector('input[name="explorer-mode"]:checked').value === 'mcp') {
                       await loadFiles(currentDatabase);
                   }
               } else {
                   alert(`❌ Error: ${result.error}`);
               }
           } catch (error) {
               alert(`❌ Error: ${error.message}`);
           }
       }
       
       async function viewRawLogs(sessionId) {
           if (!sessionId) {
               alert('No session ID available. Please send a message first.');
               return;
           }
           
           try {
               const response = await fetch(`/api/view_session_logs/${sessionId}`);
               const data = await response.json();
               
               if (!data.success) {
                   alert(`Error loading logs: ${data.error}`);
                   return;
               }
               
               const modal = document.createElement('div');
               modal.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 1000; display: flex; justify-content: center; align-items: center;';
               
               const logEntries = data.entries.map(entry => {
                   const timestamp = new Date(entry.timestamp).toLocaleString();
                   const entryData = JSON.stringify(entry.data, null, 2);
                   
                   return `
                       <div style="border: 1px solid #333; margin-bottom: 10px; border-radius: 4px; background: #2a2a2a;">
                           <div style="padding: 8px; background: #333; font-weight: bold; color: #00ff00;">
                               [${entry.type}] ${timestamp}
                           </div>
                           <div style="padding: 10px; max-height: 300px; overflow-y: auto;">
                               <pre style="font-size: 10px; color: #ccc; white-space: pre-wrap; margin: 0;">${entryData}</pre>
                           </div>
                       </div>
                   `;
               }).join('');
               
               modal.innerHTML = `
                   <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 8px; width: 90%; height: 90%; display: flex; flex-direction: column;">
                       <div style="padding: 15px; background: #2a2a2a; border-bottom: 1px solid #333; display: flex; justify-content: space-between; align-items: center;">
                           <span style="font-weight: bold; color: #00ff00;">🔍 Raw LLM Logs - Session: ${sessionId.substring(0, 16)}...</span>
                           <div>
                               <button class="btn" onclick="downloadLogs('${sessionId}')" style="margin-right: 10px;">💾 Download</button>
                               <button class="btn" onclick="this.closest('div').parentElement.parentElement.remove()">❌ Close</button>
                           </div>
                       </div>
                       <div style="flex: 1; padding: 15px; overflow-y: auto;">
                           <div style="font-size: 12px; color: #888; margin-bottom: 15px;">
                               Total entries: ${data.total_entries} | Session: ${sessionId}
                           </div>
                           ${logEntries || '<div style="color: #666;">No log entries found for this session.</div>'}
                       </div>
                   </div>
               `;
               
               document.body.appendChild(modal);
               
           } catch (error) {
               alert(`Error loading logs: ${error.message}`);
           }
       }
       
       async function downloadLogs(sessionId) {
           try {
               const response = await fetch(`/api/view_session_logs/${sessionId}`);
               const data = await response.json();
               
               if (data.success) {
                   const logContent = JSON.stringify(data.entries, null, 2);
                   const blob = new Blob([logContent], { type: 'application/json' });
                   const url = window.URL.createObjectURL(blob);
                   
                   const a = document.createElement('a');
                   a.href = url;
                   a.download = `llm_logs_${sessionId.substring(0, 16)}_${new Date().toISOString().slice(0, 10)}.json`;
                   document.body.appendChild(a);
                   a.click();
                   window.URL.revokeObjectURL(url);
                   document.body.removeChild(a);
                   
                   alert('✅ Logs downloaded successfully!');
               }
           } catch (error) {
               alert(`Error downloading logs: ${error.message}`);
           }
       }
       
       function editResponse(contentDiv, originalContent) {
           // Replace content div with textarea for editing
           const textarea = document.createElement('textarea');
           textarea.value = originalContent;
           textarea.style.cssText = 'width: 100%; height: 200px; background: #333; color: #00ff00; border: 1px solid #555; padding: 8px; font-family: inherit; font-size: 12px;';
           
           const saveBtn = document.createElement('button');
           saveBtn.textContent = '💾 Save Changes';
           saveBtn.className = 'btn primary';
           saveBtn.style.marginTop = '5px';
           saveBtn.onclick = () => {
               contentDiv.textContent = textarea.value;
               contentDiv.parentNode.replaceChild(contentDiv, textarea);
               saveBtn.remove();
           };
           
           contentDiv.parentNode.replaceChild(textarea, contentDiv);
           textarea.parentNode.insertBefore(saveBtn, textarea.nextSibling);
       }
       
       function viewFullResponse(content) {
           const modal = document.createElement('div');
           modal.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 1000; display: flex; justify-content: center; align-items: center;';
           
           modal.innerHTML = `
               <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 8px; width: 80%; height: 80%; display: flex; flex-direction: column;">
                   <div style="padding: 15px; background: #2a2a2a; border-bottom: 1px solid #333; display: flex; justify-content: space-between; align-items: center; font-weight: bold; color: #00ff00;">
                       <span>📄 LLM Response</span>
                       <button class="btn" onclick="this.closest('div').parentElement.parentElement.remove()">❌ Close</button>
                   </div>
                   <div style="flex: 1; padding: 15px; overflow-y: auto;">
                       <div style="white-space: pre-wrap; font-size: 12px; color: #ccc; line-height: 1.4;">
                           ${content}
                       </div>
                   </div>
               </div>
           `;
           
           document.body.appendChild(modal);
       }
       
       // ===============================
       // DUAL FILE EXPLORER MODES
       // ===============================
       
       let currentExplorerMode = 'mcp';
       let pcFiles = [];
       let selectedPCFiles = [];
       
       function switchExplorerMode(mode) {
           currentExplorerMode = mode;
           
           if (mode === 'mcp') {
               document.getElementById('mcp-mode-controls').style.display = 'flex';
               document.getElementById('pc-mode-controls').style.display = 'none';
               document.getElementById('file-selection-controls').style.display = 'block';
               
               // Load MCP files
               if (currentDatabase) {
                   loadFiles(currentDatabase);
               } else {
                   document.getElementById('file-list').innerHTML = 'Select a database first';
               }
           } else {
               document.getElementById('mcp-mode-controls').style.display = 'none';
               document.getElementById('pc-mode-controls').style.display = 'flex';
               document.getElementById('file-selection-controls').style.display = 'none';
               
               // Load PC file browser
               loadPCFiles();
           }
       }
       
       async function browsePCFiles() {
           try {
               const response = await fetch('/api/browse_pc_files', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify({path: '/home/flintx/remember'})
               });
               
               const data = await response.json();
               if (data.success) {
                   pcFiles = data.files;
                   renderPCFiles();
               } else {
                   alert(`Error: ${data.error}`);
               }
           } catch (error) {
               alert(`Error: ${error.message}`);
           }
       }
       
       function loadPCFiles() {
           document.getElementById('file-list').innerHTML = `
               <div style="text-align: center; padding: 20px; color: #888;">
                   <div style="margin-bottom: 10px;">💻 PC File Explorer Mode</div>
                   <div style="font-size: 10px;">Click "📂 Browse Files" to explore your file system</div>
               </div>
           `;
       }
       
       function renderPCFiles() {
           const fileList = document.getElementById('file-list');
           fileList.innerHTML = '';
           
           pcFiles.forEach(file => {
               const fileDiv = document.createElement('div');
               fileDiv.className = 'file-item';
               fileDiv.style.cursor = 'pointer';
               
               const isSelected = selectedPCFiles.includes(file.path);
               if (isSelected) fileDiv.classList.add('selected');
               
               fileDiv.onclick = () => togglePCFileSelection(file.path, fileDiv);
               
               fileDiv.innerHTML = `
                   <div class="file-name">${file.name}</div>
                   <div class="file-meta">
                       <span>${file.type}</span>
                       <span>${file.size}</span>
                   </div>
                   <div class="file-meta">
                       <span style="font-size: 8px; color: #666;">${file.path}</span>
                   </div>
               `;
               
               fileList.appendChild(fileDiv);
           });
           
           updateAddToMCPButton();
       }
       
       function togglePCFileSelection(filePath, element) {
           if (selectedPCFiles.includes(filePath)) {
               selectedPCFiles = selectedPCFiles.filter(path => path !== filePath);
               element.classList.remove('selected');
           } else {
               selectedPCFiles.push(filePath);
               element.classList.add('selected');
           }
           updateAddToMCPButton();
       }
       
       function updateAddToMCPButton() {
           const btn = document.getElementById('add-to-mcp-btn');
           btn.disabled = selectedPCFiles.length === 0;
           btn.textContent = `➕ Add ${selectedPCFiles.length} to MCP`;
       }
       
       async function addSelectedToMCP() {
           if (selectedPCFiles.length === 0) return;
           
           try {
               const response = await fetch('/api/add_files_to_mcp', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify({
                       files: selectedPCFiles,
                       database: currentDatabase
                   })
               });
               
               const result = await response.json();
               if (result.success) {
                   alert(`✅ ${result.files_added} files added to MCP database!`);
                   selectedPCFiles = [];
                   renderPCFiles();
               } else {
                   alert(`❌ Error: ${result.error}`);
               }
           } catch (error) {
               alert(`❌ Error: ${error.message}`);
           }
       }
       
       async function addFolderToMCP() {
           const folderPath = prompt('Enter folder path to add to MCP:');
           if (!folderPath) return;
           
           try {
               const response = await fetch('/api/add_folder_to_mcp', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify({
                       folder_path: folderPath,
                       database: currentDatabase
                   })
               });
               
               const result = await response.json();
               if (result.success) {
                   alert(`✅ ${result.files_added} files added from folder to MCP!`);
               } else {
                   alert(`❌ Error: ${result.error}`);
               }
           } catch (error) {
               alert(`❌ Error: ${error.message}`);
           }
       }
       
   </script>
</body>
</html>""")

# EXTRACTION BACKEND ENDPOINTS

PROXY_ORDER = [
   ("Local", None),
   ("Mobile", "http://52fb2fcd77ccbf54b65c:5a02792bf800a049@gw.dataimpulse.com:823"),
   ("Residential", "http://0aa180faa467ad67809b__cr.us:6dc612d4a08ca89d@gw.dataimpulse.com:823")
]

USER_AGENTS = [
   'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
   'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
]

@app.post("/api/start_extraction")
async def start_extraction(background_tasks: BackgroundTasks):
   """Start URL extraction process"""
   global extraction_progress
   
   if extraction_progress["active"]:
       return {"success": False, "error": "Extraction already in progress"}
   
   # Load URLs from urls.txt
   urls_file = Path.home() / "remember" / "urls.txt"
   if not urls_file.exists():
       return {"success": False, "error": "urls.txt not found"}
   
   try:
       with open(urls_file, 'r') as f:
           urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
       
       if not urls:
           return {"success": False, "error": "No URLs found in urls.txt"}
       
       # Reset progress
       extraction_progress.update({
           "active": True,
           "total_urls": len(urls),
           "current_index": 0,
           "current_url": "",
           "success_count": 0,
           "failed_count": 0,
           "total_chars": 0,
           "start_time": datetime.now(),
           "status": "processing",
           "results": []
       })
       
       # Start extraction in background
       background_tasks.add_task(run_extraction, urls)
       
       return {"success": True, "total_urls": len(urls)}
       
   except Exception as e:
       return {"success": False, "error": str(e)}

@app.get("/api/extraction_progress")
async def get_extraction_progress():
   """Get current extraction progress"""
   global extraction_progress
   
   progress_data = extraction_progress.copy()
   if progress_data["start_time"]:
       progress_data["start_time"] = progress_data["start_time"].isoformat()
   
   return progress_data

@app.post("/api/cancel_extraction")
async def cancel_extraction():
   """Cancel extraction process"""
   global extraction_progress
   extraction_progress["active"] = False
   extraction_progress["status"] = "cancelled"
   return {"success": True}

async def run_extraction(urls: List[str]):
    """Run the actual extraction process with proper progress updates"""
    global extraction_progress
    
    remember_dir = Path.home() / "remember"
    content_dir = remember_dir / "scraped_content"
    content_dir.mkdir(exist_ok=True, parents=True)
    
    all_results = []
    
    for i, url in enumerate(urls):
        if not extraction_progress["active"]:
            break
        
        # Update progress BEFORE processing
        extraction_progress.update({
            "current_index": i + 1,
            "current_url": url
        })
        
        # Add small delay for UI updates
        await asyncio.sleep(0.1)
        
        success = False
        
        for attempt, (proxy_name, proxy_url) in enumerate(PROXY_ORDER):
            try:
                session = requests.Session()
                session.headers.update({"User-Agent": random.choice(USER_AGENTS)})
                if proxy_url:
                    session.proxies = {"http": proxy_url, "https": proxy_url}
                
                response = session.get(url, timeout=30, stream=True)
                response.raise_for_status()
                
                content_type = response.headers.get("Content-Type", "").lower()
                
                if "application/pdf" in content_type:
                    pdf_bytes = response.content
                    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                    pdf_text = "".join(page.get_text() for page in doc)
                    doc.close()
                    
                    title = f"[PDF] {Path(url).name}"
                    best_content = pdf_text
                else:
                    clean_content = response.text.replace("\x00", "")
                    doc = Document(clean_content)
                    title = doc.title()
                    best_content = BeautifulSoup(doc.summary(), "html.parser").get_text(separator="\n", strip=True)
                    
                    if not best_content or len(best_content) < 100:
                        soup = BeautifulSoup(clean_content, "html.parser")
                        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
                            tag.decompose()
                        best_content = soup.get_text(separator="\n", strip=True)
                
                md_filename = clean_filename(url, "md")
                md_filepath = content_dir / md_filename
                
                with open(md_filepath, "w", encoding="utf-8") as f:
                    f.write(f"# {title}\n\n_Source: {url}_\n\n---\n\n{best_content}")
                
                rating = calculate_rating(len(best_content))
                
                result = {
                    "url": url,
                    "title": title,
                    "rating": rating,
                    "markdown_file": str(md_filepath),
                    "content": best_content
                }
                
                all_results.append(result)
                extraction_progress["success_count"] += 1
                extraction_progress["total_chars"] += len(best_content)
                
                success = True
                break
                
            except Exception as e:
                continue
        
        if not success:
            extraction_progress["failed_count"] += 1
    
    # Save results and auto-import
    if all_results:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = remember_dir / f"extraction_results_{timestamp}.json"
        
        with open(results_file, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2)
        
        try:
            import_result = import_extraction_session(str(results_file))
            extraction_progress["import_result"] = import_result
        except Exception as e:
            extraction_progress["import_error"] = str(e)
    
    extraction_progress["active"] = False
    extraction_progress["status"] = "completed"

def clean_filename(url: str, extension: str) -> str:
    """Clean URL for filename"""
    clean = re.sub(r'^https?:\/\/', '', url).replace('/', '_')
    clean = re.sub(r'[\\?%*:|"<>]', '', clean)
    return f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{clean[:70]}.{extension}"

def calculate_rating(length: int) -> int:
    """Calculate content rating"""
    if length > 8000: return 5
    if length > 4000: return 4
    if length > 1500: return 3
    if length > 500: return 2


@app.get("/api/databases")
async def get_databases():
    """Get all available ChromaDB databases"""
    try:
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
                        "type": metadata.get("type", "document"),
                        "size": len(str(metadata)),
                        "created": metadata.get("created", "unknown"),
                        "rating": metadata.get("rating", 0)
                    })
        
        return {"files": files}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@app.get("/api/extraction_results")
async def get_extraction_results():
    """Get the latest extraction results JSON"""
    try:
        remember_dir = Path.home() / "remember"
        
        # Find the most recent extraction results file
        pattern = remember_dir / "extraction_results_*.json"
        json_files = list(remember_dir.glob("extraction_results_*.json"))
        
        if not json_files:
            return {"results": []}
        
        # Sort by modification time and get the latest
        latest_file = max(json_files, key=lambda f: f.stat().st_mtime)
        
        with open(latest_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
        
        return {"results": results}
        
    except Exception as e:
        return {"results": [], "error": str(e)}

@app.get("/api/view_markdown")
async def view_markdown(file_path: str):
    """View markdown file content in a popup"""
    try:
        markdown_path = Path(file_path)
        
        if not markdown_path.exists():
            raise HTTPException(status_code=404, detail="Markdown file not found")
        
        with open(markdown_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Create HTML response with markdown content
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Markdown Viewer - {markdown_path.name}</title>
    <style>
        body {{ 
            font-family: 'Courier New', monospace; 
            background: #0a0a0a; 
            color: #00ff00; 
            padding: 20px; 
            line-height: 1.6;
        }}
        .header {{
            background: #1a1a1a;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
            border: 1px solid #333;
        }}
        .content {{
            background: #111;
            padding: 20px;
            border-radius: 5px;
            border: 1px solid #333;
            white-space: pre-wrap;
            overflow-wrap: break-word;
        }}
        h1, h2, h3 {{ color: #00ff00; }}
        a {{ color: #0080ff; }}
    </style>
</head>
<body>
    <div class="header">
        <h2>📄 {markdown_path.name}</h2>
        <p>Path: {file_path}</p>
    </div>
    <div class="content">{content}</div>
</body>
</html>
"""
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading markdown file: {e}")

@app.get("/api/master_context/{context_id}")
async def get_master_context(context_id: str):
    """Get master context content"""
    try:
        contexts_dir = Path.home() / "remember" / "master_contexts"
        contexts_dir.mkdir(exist_ok=True)
        
        context_file = contexts_dir / f"{context_id}.txt"
        
        # Context names mapping
        context_names = {
            "service_defects": "Service of Process Expert",
            "tpa_violations": "TPA Violation Specialist", 
            "court_procedure": "Court Procedure Guide",
            "case_timeline": "Case Timeline Master"
        }
        
        if context_file.exists():
            with open(context_file, 'r', encoding='utf-8') as f:
                content = f.read()
        else:
            # Create default content if file doesn't exist
            content = f"Default {context_names.get(context_id, context_id)} context content. Please customize this with your specific requirements and instructions."
            with open(context_file, 'w', encoding='utf-8') as f:
                f.write(content)
        
        return {
            "success": True,
            "content": content,
            "name": context_names.get(context_id, context_id)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def chat_handler(request: ChatRequest):
    """Handle chat requests using LLM function calling to MCP server with comprehensive logging"""
    session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    
    try:
        # Log incoming request
        log_llm_interaction("INCOMING_REQUEST", {
            "message": request.message,
            "files": request.files,
            "provider": request.provider,
            "master_contexts": request.master_contexts,
            "database": request.database
        }, session_id)

        # 1. Load Master Contexts
        master_context_content = ""
        if request.master_contexts:
            contexts_dir = Path.home() / "remember" / "master_contexts"
            for context_id in request.master_contexts:
                context_file = contexts_dir / f"{context_id}.txt"
                if context_file.exists():
                    with open(context_file, 'r', encoding='utf-8') as f:
                        context_text = f.read()
                        master_context_content += f"""--- MASTER CONTEXT: {context_id} ---
{context_text}

"""
        
        log_llm_interaction("MASTER_CONTEXTS_LOADED", {
            "contexts": request.master_contexts,
            "content_length": len(master_context_content)
        }, session_id)

        # 2. Construct system prompt with master contexts
        file_instructions = ""
        if request.files:
            # Convert file URLs to vector IDs for direct access
            vector_ids = []
            for i, file_url in enumerate(request.files, 1):
                vector_id = f"doc_{i:03d}"
                vector_ids.append(vector_id)
            
            vector_list = '\n'.join([f"- {vid}" for vid in vector_ids])
            file_instructions = f"""

PRIORITY DOCUMENTS TO ANALYZE:
{vector_list}

INSTRUCTIONS: Use get_document_by_id() to retrieve the exact content of these documents. Each document has a vector ID that directly accesses the content."""
        else:
            file_instructions = "\n\nINSTRUCTIONS: Use list_all_documents() to see available documents and their vector IDs, then use get_document_by_id() to retrieve specific documents."

        system_prompt = f"""You are a Legal AI expert with access to a ChromaDB database through function calls.

{master_context_content}

USER QUERY: {request.message}
{file_instructions}

You have access to these function calling tools:
- get_document_by_id: Get full content of a document by its vector ID (e.g., doc_001, doc_002)
- list_all_documents: List all available documents with their vector IDs and titles
- get_multiple_documents: Get content of multiple documents at once

WORKFLOW:
1. If specific document IDs are listed above, use get_document_by_id() to retrieve them directly
2. If no specific documents are listed, use list_all_documents() to see what's available
3. Analyze the retrieved documents according to the master context instructions provided
4. Follow the exact output format specified in the master context"""

        # 3. Get MCP tools for function calling
        tools = get_mcp_tools()
        
        log_llm_interaction("TOOLS_LOADED", {
            "tools_count": len(tools),
            "available_tools": [tool["function"]["name"] for tool in tools]
        }, session_id)
        
        # 4. Create messages for LLM
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Please analyze the legal documents related to: {request.message}"}
        ]

        log_llm_interaction("LLM_REQUEST_PREPARED", {
            "messages": messages,
            "tools": tools,
            "model": request.provider,
            "system_prompt_length": len(system_prompt)
        }, session_id)

        # 5. Make function call to LLM
        success, response, debug = groq_client.function_call_chat(
            messages=messages,
            tools=tools,
            model=request.provider
        )

        log_llm_interaction("LLM_RESPONSE_RAW", {
            "success": success,
            "response": response,
            "debug": debug,
            "model_used": request.provider
        }, session_id)

        if not success:
            error_msg = f"LLM function call failed: {debug}"
            log_llm_interaction("LLM_ERROR", {"error": error_msg}, session_id)
            raise HTTPException(status_code=500, detail=error_msg)

        # 6. Process function calls if any
        response_content = ""
        function_results = []
        
        # Check if LLM made function calls
        choices = response.get('choices', [])
        if choices:
            message = choices[0].get('message', {})
            tool_calls = message.get('tool_calls', [])
            
            log_llm_interaction("FUNCTION_CALLS_DETECTED", {
                "tool_calls_count": len(tool_calls),
                "tool_calls": tool_calls
            }, session_id)
            
            if tool_calls:
                # Execute each function call
                for tool_call in tool_calls:
                    function_name = tool_call['function']['name']
                    function_args = json.loads(tool_call['function']['arguments'])
                    
                    log_llm_interaction("EXECUTING_FUNCTION", {
                        "function_name": function_name,
                        "function_args": function_args
                    }, session_id)
                    
                    # Execute the MCP tool
                    tool_result = await execute_mcp_tool(function_name, function_args)
                    
                    log_llm_interaction("FUNCTION_RESULT", {
                        "function_name": function_name,
                        "result": tool_result
                    }, session_id)
                    
                    function_results.append({
                        "function": function_name,
                        "arguments": function_args,
                        "result": tool_result
                    })
                
                # Create follow-up message with function results
                messages.append({
                    "role": "assistant",
                    "content": message.get('content', ''),
                    "tool_calls": tool_calls
                })
                
                # Add function results
                for i, tool_call in enumerate(tool_calls):
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call['id'],
                        "content": json.dumps(function_results[i]['result'])
                    })
                
                log_llm_interaction("FINAL_LLM_REQUEST_PREPARED", {
                    "messages_count": len(messages),
                    "with_function_results": True
                }, session_id)
                
                # Get final response from LLM
                final_success, final_response, final_debug = groq_client.conversation_chat(
                    messages=messages,
                    model=request.provider
                )
                
                log_llm_interaction("FINAL_LLM_RESPONSE", {
                    "success": final_success,
                    "response": final_response,
                    "debug": final_debug
                }, session_id)
                
                if final_success:
                    response_content = final_response
                else:
                    response_content = f"Function calls executed but final response failed: {final_debug}"
            else:
                # No function calls, just direct response
                response_content = message.get('content', 'No response content')
        else:
            response_content = "No response from LLM"

        final_result = {
            "response": response_content,
            "debug_info": f"Function calls made: {len(function_results)}. Tools available: {len(tools)}",
            "function_calls": function_results,
            "model_used": request.provider,
            "show_function_results": True,
            "session_id": session_id,  # Include session ID for log viewing
            "log_file": f"raw_llm_data_{datetime.now().strftime('%Y%m%d')}.json"
        }
        
        log_llm_interaction("FINAL_RESULT", final_result, session_id)
        
        return final_result

    except Exception as e:
        import traceback
        error_details = {
            "error": str(e),
            "traceback": traceback.format_exc()
        }
        log_llm_interaction("EXCEPTION", error_details, session_id)
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

class ContextRequest(BaseModel):
    context_content: str
    instructions: str
    provider: str
    api_key: str = "auto"

@app.post("/api/improve_context")
async def improve_context(request: ContextRequest):
    """Send context to LLM for improvement"""
    try:
        # Prepare the message for the LLM
        system_prompt = "You are an expert legal AI assistant. The user will provide you with a master context and instructions on how to improve it. Please follow their instructions carefully and provide an improved version."
        
        user_message = f"""
CURRENT MASTER CONTEXT:
{request.context_content}

USER INSTRUCTIONS:
{request.instructions}

Please provide an improved version of this master context following the user's instructions.
"""
        
        # Use the existing groq client
        response = await groq_client.complete(
            provider=request.provider,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            api_key=request.api_key
        )
        
        return {"response": response}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM request failed: {e}")

class SaveContextResponse(BaseModel):
    context_id: str
    response: str
    timestamp: str

@app.post("/api/save_context_response")
async def save_context_response(request: SaveContextResponse):
    """Save LLM response as a new context version"""
    try:
        responses_dir = Path.home() / "remember" / "context_responses"
        responses_dir.mkdir(exist_ok=True)
        
        timestamp = request.timestamp.replace(':', '-').replace('.', '-')
        filename = f"{request.context_id}_response_{timestamp}.txt"
        
        response_file = responses_dir / filename
        
        with open(response_file, 'w', encoding='utf-8') as f:
            f.write(request.response)
        
        return {"success": True, "filename": filename}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

class UpdateContextRequest(BaseModel):
    context_id: str
    content: str

@app.post("/api/update_master_context")
async def update_master_context(request: UpdateContextRequest):
    """Update the master context with new content"""
    try:
        contexts_dir = Path.home() / "remember" / "master_contexts"
        contexts_dir.mkdir(exist_ok=True)
        
        context_file = contexts_dir / f"{request.context_id}.txt"
        
        # Backup current version
        if context_file.exists():
            backup_file = contexts_dir / f"{request.context_id}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(context_file, 'r', encoding='utf-8') as f:
                backup_content = f.read()
            with open(backup_file, 'w', encoding='utf-8') as f:
                f.write(backup_content)
        
        # Save new content
        with open(context_file, 'w', encoding='utf-8') as f:
            f.write(request.content)
        
        return {"success": True}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

class LoadFileContentRequest(BaseModel):
    url: str
    markdown_file: str
    json_content: str

@app.post("/api/load_file_content")
async def load_file_content(request: LoadFileContentRequest):
    """Load file content for editing"""
    try:
        # Try to load from markdown file first, fallback to JSON content
        markdown_path = Path(request.markdown_file)
        
        if markdown_path.exists():
            with open(markdown_path, 'r', encoding='utf-8') as f:
                content = f.read()
        else:
            content = request.json_content
        
        return {"success": True, "content": content}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

class SaveFileContentRequest(BaseModel):
    url: str
    content: str
    markdown_file: str
    title: str

@app.post("/api/save_file_content")
async def save_file_content(request: SaveFileContentRequest):
    """Save edited file content to both JSON and markdown"""
    try:
        # Save to markdown file with auto-backup
        markdown_path = Path(request.markdown_file)
        
        # Create backups
        if markdown_path.exists():
            backup_dir = markdown_path.parent / "backups"
            backup_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = backup_dir / f"{markdown_path.stem}_backup_{timestamp}.md"
            
            # Keep only last 3 backups
            backup_files = sorted(backup_dir.glob(f"{markdown_path.stem}_backup_*.md"))
            if len(backup_files) >= 3:
                # Remove oldest backups, keep only 2
                for old_backup in backup_files[:-2]:
                    old_backup.unlink()
            
            # Create new backup
            with open(markdown_path, 'r', encoding='utf-8') as f:
                backup_content = f.read()
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(backup_content)
        
        # Save new content to markdown file
        with open(markdown_path, 'w', encoding='utf-8') as f:
            f.write(request.content)
        
        # Update JSON file
        remember_dir = Path.home() / "remember"
        json_files = list(remember_dir.glob("extraction_results_*.json"))
        
        if json_files:
            latest_json = max(json_files, key=lambda f: f.stat().st_mtime)
            
            with open(latest_json, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Find and update the matching entry
            for item in data:
                if item.get('url') == request.url:
                    item['content'] = request.content
                    break
            
            # Save updated JSON
            with open(latest_json, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        
        return {"success": True}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

class AutoSaveRequest(BaseModel):
    url: str
    content: str
    file_path: str

@app.post("/api/auto_save_file")
async def auto_save_file(request: AutoSaveRequest):
    """Auto-save file content"""
    try:
        # Create auto-save directory
        file_path = Path(request.file_path)
        autosave_dir = file_path.parent / "autosave"
        autosave_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        autosave_path = autosave_dir / f"{file_path.stem}_autosave_{timestamp}.md"
        
        # Save auto-save copy
        with open(autosave_path, 'w', encoding='utf-8') as f:
            f.write(request.content)
        
        # Keep only last 5 auto-saves
        autosave_files = sorted(autosave_dir.glob(f"{file_path.stem}_autosave_*.md"))
        if len(autosave_files) > 5:
            for old_file in autosave_files[:-5]:
                old_file.unlink()
        
        return {"success": True}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

class LoadVersionRequest(BaseModel):
    url: str
    version: str
    file_path: str

@app.post("/api/load_file_version")
async def load_file_version(request: LoadVersionRequest):
    """Load specific version of file"""
    try:
        file_path = Path(request.file_path)
        
        if request.version == "current":
            # Load current version
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            else:
                content = ""
        else:
            # Load backup version
            backup_dir = file_path.parent / "backups"
            backup_files = sorted(backup_dir.glob(f"{file_path.stem}_backup_*.md"))
            
            if request.version == "backup1" and len(backup_files) >= 1:
                with open(backup_files[-1], 'r', encoding='utf-8') as f:
                    content = f.read()
            elif request.version == "backup2" and len(backup_files) >= 2:
                with open(backup_files[-2], 'r', encoding='utf-8') as f:
                    content = f.read()
            elif request.version == "original" and len(backup_files) >= 1:
                with open(backup_files[0], 'r', encoding='utf-8') as f:
                    content = f.read()
            else:
                return {"success": False, "error": "Version not found"}
        
        return {"success": True, "content": content}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

# ===============================
# MASTER CONTEXT API ENDPOINTS
# ===============================

@app.get("/api/master_contexts/list")
async def list_master_contexts():
    """List all master contexts with metadata"""
    try:
        contexts_dir = Path.home() / "remember" / "master_contexts"
        contexts_dir.mkdir(exist_ok=True)
        
        contexts = []
        for context_file in contexts_dir.glob("*.txt"):
            try:
                stat = context_file.stat()
                with open(context_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                contexts.append({
                    "id": context_file.stem,
                    "size": len(content),
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                })
            except Exception:
                continue
        
        contexts.sort(key=lambda x: x["id"])
        return {"success": True, "contexts": contexts}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

class CreateContextRequest(BaseModel):
    id: str
    content: str

@app.post("/api/master_contexts/create")
async def create_master_context(request: CreateContextRequest):
    """Create new master context"""
    try:
        contexts_dir = Path.home() / "remember" / "master_contexts"
        contexts_dir.mkdir(exist_ok=True)
        
        # Clean context ID
        context_id = re.sub(r'[^a-zA-Z0-9_-]', '_', request.id.strip())
        if not context_id:
            return {"success": False, "error": "Invalid context ID"}
        
        context_file = contexts_dir / f"{context_id}.txt"
        
        # Check if already exists
        if context_file.exists():
            return {"success": False, "error": f"Context '{context_id}' already exists"}
        
        # Save context
        with open(context_file, 'w', encoding='utf-8') as f:
            f.write(request.content)
        
        return {"success": True, "message": f"Context '{context_id}' created successfully"}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.delete("/api/master_contexts/delete/{context_id}")
async def delete_master_context(context_id: str):
    """Delete master context"""
    try:
        contexts_dir = Path.home() / "remember" / "master_contexts"
        context_file = contexts_dir / f"{context_id}.txt"
        
        if not context_file.exists():
            return {"success": False, "error": f"Context '{context_id}' not found"}
        
        # Create backup before deletion
        backup_dir = contexts_dir / "deleted_backups"
        backup_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"{context_id}_deleted_{timestamp}.txt"
        
        # Copy to backup
        import shutil
        shutil.copy2(context_file, backup_file)
        
        # Delete original
        context_file.unlink()
        
        return {"success": True, "message": f"Context '{context_id}' deleted (backup saved)"}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

# ===============================
# NOTES API ENDPOINTS
# ===============================

class CreateNoteRequest(BaseModel):
    content: str

class QuickNoteRequest(BaseModel):
    content: str
    timestamp: str

@app.post("/api/notes/create")
async def create_note(request: CreateNoteRequest):
    """Create a new note"""
    try:
        notes_dir = Path.home() / "remember" / "notes"
        notes_dir.mkdir(exist_ok=True)
        
        # Generate note ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        note_id = f"note_{timestamp}"
        
        note_data = {
            "id": note_id,
            "content": request.content,
            "timestamp": datetime.now().isoformat(),
            "created": datetime.now().isoformat()
        }
        
        note_file = notes_dir / f"{note_id}.json"
        with open(note_file, 'w', encoding='utf-8') as f:
            json.dump(note_data, f, indent=2)
        
        return {"success": True, "note_id": note_id}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/notes/quick")
async def save_quick_note(request: QuickNoteRequest):
    """Save quick note from sidebar"""
    try:
        notes_dir = Path.home() / "remember" / "notes"
        notes_dir.mkdir(exist_ok=True)
        
        # Use timestamp from request or generate new one
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        note_id = f"quick_{timestamp}"
        
        note_data = {
            "id": note_id,
            "content": request.content,
            "timestamp": request.timestamp,
            "type": "quick",
            "created": datetime.now().isoformat()
        }
        
        note_file = notes_dir / f"{note_id}.json"
        with open(note_file, 'w', encoding='utf-8') as f:
            json.dump(note_data, f, indent=2)
        
        return {"success": True, "note_id": note_id}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/notes/list")
async def list_notes():
    """List all notes"""
    try:
        notes_dir = Path.home() / "remember" / "notes"
        notes_dir.mkdir(exist_ok=True)
        
        notes = []
        for note_file in notes_dir.glob("*.json"):
            try:
                with open(note_file, 'r', encoding='utf-8') as f:
                    note_data = json.load(f)
                notes.append(note_data)
            except Exception:
                continue
        
        # Sort by creation time (newest first)
        notes.sort(key=lambda x: x.get("created", ""), reverse=True)
        
        return {"success": True, "notes": notes}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.delete("/api/notes/delete/{note_id}")
async def delete_note(note_id: str):
    """Delete a note"""
    try:
        notes_dir = Path.home() / "remember" / "notes"
        note_file = notes_dir / f"{note_id}.json"
        
        if not note_file.exists():
            return {"success": False, "error": f"Note '{note_id}' not found"}
        
        # Create backup before deletion
        backup_dir = notes_dir / "deleted_backups"
        backup_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"{note_id}_deleted_{timestamp}.json"
        
        # Copy to backup
        import shutil
        shutil.copy2(note_file, backup_file)
        
        # Delete original
        note_file.unlink()
        
        return {"success": True, "message": f"Note '{note_id}' deleted (backup saved)"}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

# ===============================
# FILE MANAGEMENT API ENDPOINTS  
# ===============================

@app.delete("/api/database/{db_name}/file/{file_id}")
async def delete_database_file(db_name: str, file_id: str):
    """Delete a file from the database"""
    try:
        client = get_client()
        
        # Get the collection
        try:
            collection = client.get_collection(db_name)
        except Exception:
            return {"success": False, "error": f"Database '{db_name}' not found"}
        
        # Delete the document
        collection.delete(ids=[file_id])
        
        return {"success": True, "message": f"File '{file_id}' deleted from '{db_name}'"}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

# ===============================
# MARKDOWN FILE API ENDPOINTS
# ===============================

@app.get("/api/load_markdown_content")
async def load_markdown_content(file_path: str):
    """Load markdown file content for editing"""
    try:
        markdown_path = Path(file_path)
        
        if not markdown_path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}
        
        with open(markdown_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return {"success": True, "content": content}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

class SaveMarkdownRequest(BaseModel):
    file_path: str
    content: str
    url: str

@app.post("/api/save_markdown_content")
async def save_markdown_content(request: SaveMarkdownRequest):
    """Save markdown file and update JSON + re-import to MCP"""
    try:
        markdown_path = Path(request.file_path)
        
        # 1. Create backup of markdown file
        if markdown_path.exists():
            backup_dir = markdown_path.parent / "backups"
            backup_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = backup_dir / f"{markdown_path.stem}_backup_{timestamp}.md"
            
            import shutil
            shutil.copy2(markdown_path, backup_file)
        
        # 2. Save updated markdown file
        with open(markdown_path, 'w', encoding='utf-8') as f:
            f.write(request.content)
        
        # 3. Find and update the corresponding JSON file
        remember_dir = Path.home() / "remember"
        json_files = list(remember_dir.glob("extraction_results_*.json"))
        
        if not json_files:
            return {"success": False, "error": "No extraction JSON files found"}
        
        # Find the latest JSON file
        latest_json = max(json_files, key=lambda f: f.stat().st_mtime)
        
        # 4. Update JSON entry
        with open(latest_json, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        # Find the entry by URL and update content
        updated = False
        for entry in json_data:
            if entry.get('url') == request.url:
                # Extract title and content from markdown for JSON
                lines = request.content.split('\n')
                title = lines[0].lstrip('# ') if lines and lines[0].startswith('#') else entry.get('title', 'Unknown')
                
                # Remove markdown header for clean content
                content_lines = lines[1:] if lines and lines[0].startswith('#') else lines
                clean_content = '\n'.join(content_lines).strip()
                
                entry['content'] = clean_content
                entry['title'] = title
                updated = True
                break
        
        if not updated:
            return {"success": False, "error": f"No JSON entry found for URL: {request.url}"}
        
        # 5. Save updated JSON
        backup_json = remember_dir / f"{latest_json.stem}_backup_{timestamp}.json"
        shutil.copy2(latest_json, backup_json)
        
        with open(latest_json, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2)
        
        # 6. Re-import to MCP ChromaDB
        try:
            import_result = import_extraction_session(str(latest_json))
            return {
                "success": True, 
                "message": "Markdown saved, JSON updated, and re-imported to MCP",
                "import_result": import_result
            }
        except Exception as import_error:
            return {
                "success": True,
                "message": "Markdown and JSON updated, but MCP re-import failed",
                "import_error": str(import_error)
            }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

class GetDocumentRequest(BaseModel):
    document_id: str

@app.post("/api/mcp_get_document")
async def mcp_get_document(request: GetDocumentRequest):
    """Get full document content via MCP server"""
    try:
        result = await execute_mcp_tool("get_document_content", {"document_id": request.document_id})
        
        if result.get("success"):
            return {"success": True, "document": result["document"]}
        else:
            return {"success": False, "error": result.get("error", "Unknown error")}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

# ===============================
# LLM RESPONSE MANAGEMENT API
# ===============================

class SaveResponseRequest(BaseModel):
    title: str
    content: str
    timestamp: str

@app.post("/api/save_response_to_mcp")
async def save_response_to_mcp(request: SaveResponseRequest):
    """Save LLM response to MCP database"""
    try:
        # Create a unique ID for the response
        response_id = f"llm_response_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Add to ChromaDB
        client = get_client()
        collection_name = "llm_responses"
        
        try:
            collection = client.get_collection(collection_name)
        except:
            # Create collection if it doesn't exist
            collection = client.create_collection(collection_name)
        
        metadata = {
            "title": str(request.title),
            "timestamp": str(request.timestamp),
            "type": "llm_response",
            "created": datetime.now().isoformat(),
            "rating": 5  # Default high rating for LLM responses
        }
        
        collection.add(
            documents=[request.content],
            metadatas=[metadata],
            ids=[response_id]
        )
        
        return {"success": True, "response_id": response_id, "message": "Response saved to MCP database"}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

# ===============================
# PC FILE BROWSER API
# ===============================

class BrowsePCFilesRequest(BaseModel):
    path: str

@app.post("/api/browse_pc_files")
async def browse_pc_files(request: BrowsePCFilesRequest):
    """Browse PC file system"""
    try:
        path = Path(request.path)
        
        if not path.exists():
            return {"success": False, "error": f"Path not found: {request.path}"}
        
        files = []
        for item in path.iterdir():
            try:
                stat = item.stat()
                files.append({
                    "name": item.name,
                    "path": str(item),
                    "type": "folder" if item.is_dir() else "file",
                    "size": f"{stat.st_size} bytes" if item.is_file() else "",
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                })
            except Exception:
                continue
        
        # Sort: folders first, then files
        files.sort(key=lambda x: (x["type"] != "folder", x["name"].lower()))
        
        return {"success": True, "files": files[:100]}  # Limit to 100 items
        
    except Exception as e:
        return {"success": False, "error": str(e)}

class AddFilesToMCPRequest(BaseModel):
    files: List[str]
    database: str

@app.post("/api/add_files_to_mcp")
async def add_files_to_mcp(request: AddFilesToMCPRequest):
    """Add selected PC files to MCP database"""
    try:
        client = get_client()
        
        # Get or create collection
        collection_name = f"pc_files_{datetime.now().strftime('%Y%m%d')}"
        try:
            collection = client.get_collection(collection_name)
        except:
            collection = client.create_collection(collection_name)
        
        added_count = 0
        for file_path in request.files:
            try:
                path = Path(file_path)
                if not path.exists() or not path.is_file():
                    continue
                
                # Read file content
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except UnicodeDecodeError:
                    # Skip binary files
                    continue
                
                # Create metadata
                stat = path.stat()
                file_id = f"pc_file_{hashlib.md5(str(path).encode()).hexdigest()}"
                metadata = {
                    "title": str(path.name),
                    "file_path": str(path),
                    "type": "pc_file",
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "created": datetime.now().isoformat(),
                    "rating": 3  # Default rating for PC files
                }
                
                collection.add(
                    documents=[content],
                    metadatas=[metadata],
                    ids=[file_id]
                )
                
                added_count += 1
                
            except Exception as e:
                print(f"Error adding file {file_path}: {e}")
                continue
        
        return {"success": True, "files_added": added_count, "collection": collection_name}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

class AddFolderToMCPRequest(BaseModel):
    folder_path: str
    database: str

@app.post("/api/add_folder_to_mcp")
async def add_folder_to_mcp(request: AddFolderToMCPRequest):
    """Add all files from a folder to MCP database"""
    try:
        folder_path = Path(request.folder_path)
        
        if not folder_path.exists() or not folder_path.is_dir():
            return {"success": False, "error": f"Folder not found: {request.folder_path}"}
        
        # Get all files recursively
        all_files = []
        for file_path in folder_path.rglob('*'):
            if file_path.is_file():
                all_files.append(str(file_path))
        
        # Use existing add_files_to_mcp logic
        add_request = AddFilesToMCPRequest(files=all_files, database=request.database)
        return await add_files_to_mcp(add_request)
        
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/test_mcp")
async def test_mcp_integration():
    """Test MCP function calling integration"""
    try:
        # Test 1: Get available tools
        tools = get_mcp_tools()
        
        # Test 2: Test basic search
        search_result = await execute_mcp_tool("search_documents", {"query": "service", "limit": 3})
        
        # Test 3: Test collections
        collections_result = await execute_mcp_tool("list_collections", {})
        
        return {
            "success": True,
            "tools_count": len(tools),
            "available_tools": [tool["name"] for tool in tools],
            "search_test": {
                "success": search_result.get("success", False),
                "documents_found": search_result.get("count", 0)
            },
            "collections_test": {
                "success": collections_result.get("success", False),
                "collections_count": len(collections_result.get("collections", []))
            },
            "status": "MCP integration working correctly"
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "status": "MCP integration failed"
        }

@app.get("/api/view_llm_logs")
async def view_llm_logs(session_id: Optional[str] = None, limit: int = 50):
    """View raw LLM interaction logs"""
    try:
        logs_dir = Path.home() / "remember" / "llm_logs"
        log_file = logs_dir / f"raw_llm_data_{datetime.now().strftime('%Y%m%d')}.json"
        
        if not log_file.exists():
            return {"success": False, "error": "No log file found for today"}
        
        # Read the log file
        with open(log_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split by separator
        entries = content.split("=" * 50)
        log_entries = []
        
        for entry in entries:
            if entry.strip():
                try:
                    log_data = json.loads(entry.strip())
                    # Filter by session_id if provided
                    if session_id is None or log_data.get('session_id', '').startswith(session_id):
                        log_entries.append(log_data)
                except json.JSONDecodeError:
                    continue
        
        # Sort by timestamp and limit
        log_entries.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        log_entries = log_entries[:limit]
        
        return {
            "success": True,
            "entries": log_entries,
            "total_entries": len(log_entries),
            "log_file": str(log_file)
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
        
        return {
            "success": True,
            "session_id": session_id,
            "entries": session_entries,
            "total_entries": len(session_entries)
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    print("\n🔗 Remember Legal AI War Room Starting...")
    print(f"📊 Groq Keys: {len(groq_client.router.api_manager.api_keys)}")
    print(f"🤖 MCP Tools: {len(get_mcp_tools())}")
    print(f"🎯 System Ready: http://localhost:8080")
    print(f"🧪 Test MCP: http://localhost:8080/api/test_mcp")
    print("="*50)
    
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
