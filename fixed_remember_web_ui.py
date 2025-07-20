#!/usr/bin/env python3
"""
🔗 Remember Web UI - Fixed Batch Processing + File Viewer
Complete web interface for Remember with working batch processing and file popup viewer
"""

import sys
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import json
from typing import List, Dict, Optional, Any
from datetime import datetime
import chromadb

# Add remember system to path
sys.path.insert(0, str(Path(__file__).parent.absolute()))

try:
    from groq_client import GroqClient
    from core.database import get_client
    from commands.legal_handler import LegalHandler
    from commands.command_registry import CommandRegistry
except ImportError as e:
    print(f"❌ FATAL: Could not import Remember system. Error: {e}")
    sys.exit(1)

# Load configuration
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path.home() / "remember" / ".env")

app = FastAPI(title="Remember - Legal AI War Room", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Initialize Remember system
groq_client = GroqClient()
legal_handler = LegalHandler()
command_registry = CommandRegistry()

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
        .btn:disabled { opacity: 0.3; cursor: not-allowed; }
        
        .action-bar { 
            display: grid; grid-template-columns: 1fr 1fr 1fr; 
            gap: 10px; padding: 15px 0; border-top: 1px solid #333; 
        }
        
        .master-contexts {
            margin-top: 15px; padding: 10px; 
            background: #1a1a1a; border: 1px solid #333; border-radius: 4px;
        }
        
        .context-item {
            display: flex; align-items: center; gap: 8px; 
            margin-bottom: 5px; font-size: 10px;
        }
        
        .status-indicator {
            display: inline-block; width: 8px; height: 8px; 
            border-radius: 50%; margin-right: 5px;
        }
        
        .connected { background: #00ff00; }
        .disconnected { background: #ff0000; }
        .processing { background: #ff8000; }
        
        .batch-progress {
            background: #1a1a1a; border: 1px solid #333;
            padding: 10px; margin: 10px 0; border-radius: 4px;
            display: none;
        }
        
        .progress-bar {
            background: #333; height: 20px; border-radius: 2px;
            margin: 5px 0; overflow: hidden;
        }
        
        .progress-fill {
            background: #00ff00; height: 100%; 
            transition: width 0.3s ease;
        }
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
    
    <div class="main-grid">
        <!-- Database Selection Panel -->
        <div class="database-panel">
            <div class="panel-header">📊 Database Selection</div>
            <div id="database-list">Loading databases...</div>
            
            <div class="master-contexts">
                <div style="font-weight: bold; margin-bottom: 10px; color: #00ff00;">
                    🧠 Master Contexts
                </div>
                <div class="context-item">
                    <input type="checkbox" id="ctx-service" value="service_defects">
                    <label for="ctx-service">Service of Process Expert</label>
                </div>
                <div class="context-item">
                    <input type="checkbox" id="ctx-tpa" value="tpa_violations">
                    <label for="ctx-tpa">TPA Violation Specialist</label>
                </div>
                <div class="context-item">
                    <input type="checkbox" id="ctx-court" value="court_procedure">
                    <label for="ctx-court">Court Procedure Guide</label>
                </div>
                <div class="context-item">
                    <input type="checkbox" id="ctx-timeline" value="case_timeline">
                    <label for="ctx-timeline">Case Timeline Master</label>
                </div>
            </div>
        </div>
        
        <!-- File Browser Panel -->
        <div class="file-browser">
            <div class="panel-header">📁 File Explorer</div>
            <div style="margin-bottom: 15px; display: flex; gap: 5px;">
                <button class="btn batch" id="batch-process-btn" disabled>
                    Batch Process All
                </button>
            </div>
            
            <div class="batch-progress" id="batch-progress">
                <div style="font-size: 11px; margin-bottom: 5px;">
                    Processing: <span id="current-file-name">Loading...</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill" id="progress-fill"></div>
                </div>
                <div style="font-size: 10px; color: #888;">
                    <span id="progress-text">0/0 files processed</span>
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
                            <label>Provider:</label>
                            <select id="provider-select">
                                <option value="groq">Groq (Cloud)</option>
                                <option value="ollama">Ollama (Local)</option>
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
• Deck rotation through 13 Groq API keys
• Mobile/residential proxy rotation  
• Auto-chunking for large documents
• Master context management
• Batch processing capabilities

Select a database and files to begin analysis.</div>
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
            </div>
        </div>
    </div>

    <script>
        let currentDatabase = null;
        let selectedFiles = [];
        let availableDatabases = [];
        let processingMode = false;
        let allFiles = [];

        // Initialize
        loadDatabases();
        
        // Event Listeners
        document.getElementById('send-btn').addEventListener('click', sendMessage);
        document.getElementById('user-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });
        document.getElementById('batch-process-btn').addEventListener('click', startBatchProcess);
        document.getElementById('legal-analyze-btn').addEventListener('click', startLegalAnalysis);
        
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
        
        function renderFiles(files) {
            const fileList = document.getElementById('file-list');
            fileList.innerHTML = '';
            
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
        
        function viewFileContent(fileId, title) {
            const url = `/api/view_file?file_id=${encodeURIComponent(fileId)}&database=${encodeURIComponent(currentDatabase)}`;
            const popup = window.open(url, '_blank', 'width=800,height=600,scrollbars=yes,resizable=yes');
            if (popup) {
                popup.document.title = `File Viewer - ${title}`;
            }
        }
        
        function toggleFileSelection(fileId, element) {
            if (selectedFiles.includes(fileId)) {
                selectedFiles = selectedFiles.filter(id => id !== fileId);
                element.classList.remove('selected');
            } else {
                selectedFiles.push(fileId);
                element.classList.add('selected');
            }
            
            updateCurrentContext();
            updateControls();
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
                addMessage('assistant', data.response);
                
                if (data.debug_info) {
                    addMessage('system', `Debug: ${data.debug_info}`);
                }
                
            } catch (error) {
                addMessage('system', `❌ Error: ${error.message}`);
            }
        }
        
        async function startBatchProcess() {
            if (!currentDatabase || allFiles.length === 0) return;
            
            const prompt = window.prompt('Enter analysis prompt for batch processing:', 
                'Analyze this document for legal significance, service defects, and key arguments.');
            
            if (!prompt) return;
            
            // Show progress
            const progressDiv = document.getElementById('batch-progress');
            progressDiv.style.display = 'block';
            
            addMessage('system', `🚀 Starting batch processing of ${allFiles.length} documents in ${currentDatabase}...`);
            
            const requestData = {
                database: currentDatabase,
                analysis_prompt: prompt,
                processing_mode: document.getElementById('processing-mode').value,
                provider: document.getElementById('provider-select').value,
                api_key: document.getElementById('api-key-select').value
            };
            
            try {
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
                addMessage('assistant', data.result);
                
                // Hide progress
                progressDiv.style.display = 'none';
                
            } catch (error) {
                addMessage('system', `❌ Batch process error: ${error.message}`);
                progressDiv.style.display = 'none';
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
            
            // Add save button for assistant responses
            if (role === 'assistant' && !content.startsWith('❌')) {
                const saveBtn = document.createElement('button');
                saveBtn.textContent = '💾 Save Analysis';
                saveBtn.className = 'btn';
                saveBtn.style.marginTop = '10px';
                saveBtn.onclick = () => saveAnalysis(content);
                messageDiv.appendChild(saveBtn);
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
    </script>
</body>
</html>""")

@app.get("/api/view_file", response_class=HTMLResponse)
async def view_file_content(file_id: str = Query(...), database: str = Query(...)):
    """View file content in popup window"""
    try:
        # Get database client
        if database == "remember_db":
            client = get_client()
        else:
            db_path = Path.home() / database
            client = chromadb.PersistentClient(path=str(db_path))
        
        # Find the file
        collections = client.list_collections()
        file_content = None
        file_metadata = {}
        
        for collection in collections:
            collection_data = client.get_collection(collection.name)
            try:
                result = collection_data.get(
                    ids=[file_id], 
                    include=["documents", "metadatas"]
                )
                if result["documents"]:
                    file_content = result["documents"][0]
                    file_metadata = result["metadatas"][0] if result["metadatas"] else {}
                    break
            except:
                continue
        
        if not file_content:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Return formatted HTML viewer
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>File Viewer - {file_metadata.get('title', file_id)}</title>
    <style>
        body {{ 
            font-family: 'Courier New', monospace; 
            background: #0a0a0a; color: #00ff00; 
            padding: 20px; line-height: 1.6; 
        }}
        
        .header {{ 
            background: #1a1a1a; padding: 15px; 
            border: 1px solid #333; border-radius: 4px; 
            margin-bottom: 20px; 
        }}
        
        .file-title {{ 
            color: #00ff00; font-size: 18px; 
            font-weight: bold; margin-bottom: 10px; 
        }}
        
        .file-meta {{ 
            color: #888; font-size: 12px; 
            display: grid; grid-template-columns: 1fr 1fr; gap: 10px; 
        }}
        
        .content {{ 
            background: #111; padding: 20px; 
            border: 1px solid #333; border-radius: 4px; 
            white-space: pre-wrap; word-wrap: break-word; 
            max-height: 70vh; overflow-y: auto; 
        }}
        
        .actions {{ 
            position: fixed; top: 10px; right: 10px; 
            display: flex; gap: 10px; 
        }}
        
        .btn {{ 
            background: #333; border: 1px solid #555; 
            color: #ccc; padding: 8px 12px; 
            border-radius: 3px; cursor: pointer; 
            font-size: 11px; 
        }}
        
        .btn:hover {{ background: #444; }}
        .btn.primary {{ background: #0066cc; color: white; }}
    </style>
</head>
<body>
    <div class="actions">
        <button class="btn" onclick="window.print()">🖨️ Print</button>
        <button class="btn primary" onclick="copyToClipboard()">📋 Copy</button>
        <button class="btn" onclick="window.close()">❌ Close</button>
    </div>
    
    <div class="header">
        <div class="file-title">{file_metadata.get('title', file_id)}</div>
        <div class="file-meta">
            <div><strong>ID:</strong> {file_id}</div>
            <div><strong>Database:</strong> {database}</div>
            <div><strong>Type:</strong> {file_metadata.get('type', 'Unknown')}</div>
            <div><strong>Size:</strong> {len(file_content):,} characters</div>
            <div><strong>Created:</strong> {file_metadata.get('created', 'Unknown')}</div>
            <div><strong>Rating:</strong> {file_metadata.get('rating', 'N/A')}/5</div>
        </div>
    </div>
    
    <div class="content" id="file-content">{file_content}</div>
    
    <script>
        function copyToClipboard() {{
            const content = document.getElementById('file-content').textContent;
            navigator.clipboard.writeText(content).then(() => {{
                alert('Content copied to clipboard!');
            }}).catch(err => {{
                console.error('Failed to copy: ', err);
                // Fallback for older browsers
                const textArea = document.createElement('textarea');
                textArea.value = content;
                document.body.appendChild(textArea);
                textArea.select();
                document.execCommand('copy');
                document.body.removeChild(textArea);
                alert('Content copied to clipboard!');
            }});
        }}
        
        // Auto-focus for easier reading
        window.addEventListener('load', () => {{
            document.getElementById('file-content').focus();
        }});
    </script>
</body>
</html>"""
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File viewer error: {e}")

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
        
        # Scan for other databases in common locations
        common_paths = [
            Path.home() / "peacock_db",
            Path.home() / "legal_research_db", 
            Path.home() / "eviction_defense_db"
        ]
        
        for db_path in common_paths:
            if db_path.exists():
                try:
                    client = chromadb.PersistentClient(path=str(db_path))
                    collections = client.list_collections()
                    
                    total_docs = 0
                    for collection in collections:
                        collection_data = client.get_collection(collection.name)
                        count = collection_data.count()
                        total_docs += count
                    
                    databases.append({
                        "name": db_path.name,
                        "path": str(db_path),
                        "collections": len(collections),
                        "documents": total_docs,
                        "type": "secondary"
                    })
                except Exception as e:
                    print(f"⚠️ Could not access {db_path}: {e}")
        
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

@app.post("/api/chat")
async def chat_with_files(request: ChatRequest):
    """Process chat request through Remember system"""
    try:
        # Get database client
        if request.database == "remember_db":
            client = get_client()
        else:
            db_path = Path.home() / request.database
            client = chromadb.PersistentClient(path=str(db_path))
        
        # Get selected documents
        documents = []
        for file_id in request.files:
            # Find which collection contains this file
            collections = client.list_collections()
            for collection in collections:
                collection_data = client.get_collection(collection.name)
                try:
                    result = collection_data.get(
                        ids=[file_id], 
                        include=["documents", "metadatas"]
                    )
                    if result["documents"]:
                        documents.append({
                            "content": result["documents"][0],
                            "metadata": result["metadatas"][0] if result["metadatas"] else {}
                        })
                        break
                except:
                    continue
        
        if not documents:
            raise HTTPException(status_code=404, detail="No documents found")
        
        # Combine documents
        combined_content = "\n\n---DOCUMENT SEPARATOR---\n\n".join([
            f"Document: {doc['metadata'].get('title', 'Unknown')}\n{doc['content']}"
            for doc in documents
        ])
        
        # Add master contexts if selected
        context_prompts = {
            'service_defects': """You are a California legal expert specializing in service of process defects under CCP 415.20.
Focus on: substitute service requirements, proof of service fraud, certified mail completion, personal vs substitute service analysis.""",
            
            'tpa_violations': """You are a California tenant rights expert specializing in Tenant Protection Act violations.
Focus on: Civil Code 1946.2 requirements, just cause eviction protections, 10+ year occupancy rights, fraudulent exemption claims.""",
            
            'court_procedure': """You are a court procedure expert specializing in California civil litigation.
Focus on: motion practice, evidence rules, procedural deadlines, jurisdiction issues, due process requirements.""",
            
            'case_timeline': """You are a legal timeline expert tracking case progression and deadlines.
Focus on: statute of limitations, procedural deadlines, notice requirements, hearing schedules, appeal timelines."""
        }
        
        master_context = ""
        for context_type in request.master_contexts:
            if context_type in context_prompts:
                master_context += f"\n{context_prompts[context_type]}\n"
        
        # Build analysis prompt
        analysis_prompt = f"""
{master_context}

LEGAL ANALYSIS REQUEST:
{request.message}

DOCUMENTS TO ANALYZE:
{combined_content}

Provide detailed legal analysis addressing the user's request with specific attention to any master contexts selected.
"""
        
        # Process through Groq client
        success, response, debug = groq_client.simple_chat(
            message=analysis_prompt,
            system_prompt="You are an expert legal analyst. Provide thorough, accurate analysis."
        )
        
        if success:
            return {
                "response": response,
                "debug_info": debug,
                "documents_processed": len(documents),
                "database": request.database
            }
        else:
            raise HTTPException(status_code=500, detail=f"Analysis failed: {debug}")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat processing error: {e}")

@app.post("/api/batch_process")
async def batch_process_documents(request: BatchProcessRequest):
    """Batch process all documents in database - FIXED VERSION"""
    try:
        print(f"🚀 Starting batch processing: {request.database}")
        
        # Get database client
        if request.database == "remember_db":
            client = get_client()
        else:
            db_path = Path.home() / request.database
            if not db_path.exists():
                raise HTTPException(status_code=404, detail=f"Database not found: {request.database}")
            client = chromadb.PersistentClient(path=str(db_path))
        
        # Get all documents
        collections = client.list_collections()
        all_documents = []
        
        print(f"📊 Found {len(collections)} collections")
        
        for collection in collections:
            collection_data = client.get_collection(collection.name)
            data = collection_data.get(include=["documents", "metadatas"])
            
            if data["documents"]:
                print(f"📁 Collection '{collection.name}': {len(data['documents'])} documents")
                for i, doc in enumerate(data["documents"]):
                    metadata = data["metadatas"][i] if data["metadatas"] else {}
                    all_documents.append({
                        "content": doc[:5000],  # Limit content to prevent token overflow
                        "metadata": metadata,
                        "collection": collection.name,
                        "id": data["ids"][i]
                    })
        
        if not all_documents:
            return {"result": "❌ No documents found in database"}
        
        print(f"📋 Total documents to process: {len(all_documents)}")
        
        # Process based on mode
        if request.processing_mode == "individual":
            # Process each document individually with progress
            results = []
            
            for i, doc in enumerate(all_documents):
                doc_title = doc['metadata'].get('title', doc['id'])
                print(f"📄 Processing {i+1}/{len(all_documents)}: {doc_title}")
                
                prompt = f"""ANALYSIS PROMPT: {request.analysis_prompt}

DOCUMENT TITLE: {doc_title}
DOCUMENT CONTENT:
{doc['content']}

Provide focused analysis based on the prompt above."""
                
                try:
                    success, response, debug = groq_client.simple_chat(
                        message=prompt,
                        system_prompt="You are an expert legal analyst. Provide concise, focused analysis."
                    )
                    
                    if success:
                        # Truncate response for batch view
                        truncated_response = response[:800] + "..." if len(response) > 800 else response
                        results.append({
                            "document": doc_title,
                            "analysis": truncated_response,
                            "status": "✅ Success"
                        })
                    else:
                        results.append({
                            "document": doc_title,
                            "analysis": f"❌ Analysis failed: {debug}",
                            "status": "❌ Failed"
                        })
                        
                except Exception as e:
                    results.append({
                        "document": doc_title,
                        "analysis": f"❌ Error: {str(e)}",
                        "status": "❌ Error"
                    })
            
            # Format results
            successful = len([r for r in results if r["status"] == "✅ Success"])
            result_text = f"""📊 BATCH PROCESSING COMPLETE

📋 Documents Processed: {len(results)}
✅ Successful: {successful}
❌ Failed: {len(results) - successful}

📄 INDIVIDUAL ANALYSIS RESULTS:

"""
            
            for i, result in enumerate(results, 1):
                result_text += f"""#{i} {result['status']} {result['document']}
{result['analysis']}

{'='*80}

"""
            
            return {"result": result_text}
            
        elif request.processing_mode == "batch":
            # Combine documents for single analysis
            print("🔄 Processing in batch mode...")
            
            # Create summary of all documents
            doc_summaries = []
            for doc in all_documents[:50]:  # Limit to 50 docs to prevent token overflow
                doc_title = doc['metadata'].get('title', doc['id'])
                doc_preview = doc['content'][:1000]  # First 1000 chars
                doc_summaries.append(f"Document: {doc_title}\nPreview: {doc_preview}\n")
            
            combined_summary = "\n---DOCUMENT SEPARATOR---\n".join(doc_summaries)
            
            prompt = f"""BATCH ANALYSIS REQUEST: {request.analysis_prompt}

DOCUMENTS TO ANALYZE ({len(all_documents)} total documents):
{combined_summary}

Provide comprehensive batch analysis addressing the prompt for all documents."""
            
            try:
                success, response, debug = groq_client.simple_chat(
                    message=prompt,
                    system_prompt="You are an expert legal analyst. Provide comprehensive batch analysis."
                )
                
                if success:
                    result_text = f"""📊 BATCH ANALYSIS COMPLETE

📋 Documents Analyzed: {len(all_documents)}
🔄 Processing Mode: Batch Summary

📄 COMPREHENSIVE ANALYSIS:

{response}

{'='*80}

💡 This analysis covers {len(all_documents)} documents from the {request.database} database.
"""
                    return {"result": result_text}
                else:
                    return {"result": f"❌ Batch analysis failed: {debug}"}
                    
            except Exception as e:
                return {"result": f"❌ Batch processing error: {str(e)}"}
                
        else:  # progressive mode
            print("🔄 Processing in progressive mode...")
            
            progressive_context = ""
            result_text = f"""📊 PROGRESSIVE ANALYSIS

📋 Documents: {len(all_documents)}
🔄 Mode: Progressive Context Building

📄 PROGRESSIVE RESULTS:

"""
            
            for i, doc in enumerate(all_documents[:20]):  # Limit to 20 for progressive
                doc_title = doc['metadata'].get('title', doc['id'])
                print(f"📄 Progressive analysis {i+1}/20: {doc_title}")
                
                context_prompt = f"""ANALYSIS PROMPT: {request.analysis_prompt}

PREVIOUS ANALYSIS CONTEXT:
{progressive_context[-2000:]}  

NEW DOCUMENT TO ANALYZE:
Title: {doc_title}
Content: {doc['content'][:1500]}

Analyze this document in context of previous analysis."""
                
                try:
                    success, response, debug = groq_client.simple_chat(
                        message=context_prompt,
                        system_prompt="Analyze this document in context of previous analysis. Build cumulative understanding."
                    )
                    
                    if success:
                        progressive_context += f"\n\nDocument {i+1} Analysis: {response}"
                        
                        # Add to results (truncated for display)
                        truncated_response = response[:500] + "..." if len(response) > 500 else response
                        result_text += f"""#{i+1} ✅ {doc_title}
{truncated_response}

"""
                    else:
                        result_text += f"#{i+1} ❌ {doc_title}\nAnalysis failed: {debug}\n\n"
                        
                except Exception as e:
                    result_text += f"#{i+1} ❌ {doc_title}\nError: {str(e)}\n\n"
            
            result_text += f"""
{'='*80}

💡 Progressive analysis built cumulative understanding across {min(20, len(all_documents))} documents.
"""
            
            return {"result": result_text}
            
    except Exception as e:
        print(f"❌ Batch processing error: {e}")
        raise HTTPException(status_code=500, detail=f"Batch processing error: {e}")

@app.post("/api/save_analysis")
async def save_analysis(request: dict):
    """Save analysis results to file"""
    try:
        # Create results directory
        results_dir = Path.home() / "remember" / "legal_results"
        results_dir.mkdir(exist_ok=True)
        
        # Save analysis
        file_path = results_dir / request["filename"]
        
        analysis_content = f"""# Legal Analysis Results
Generated: {datetime.now().isoformat()}
Database: {request['database']}
Files Analyzed: {len(request['files'])}

## Analysis

{request['content']}

## Metadata
- Database: {request['database']}
- Files: {', '.join(request['files'])}
- Generated by: Remember Legal AI System
"""
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(analysis_content)
        
        return {"success": True, "path": str(file_path)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Save error: {e}")

if __name__ == "__main__":
    print("\n🔗 Remember Legal AI War Room Starting...")
    print(f"📊 Groq Keys: {len(groq_client.router.api_manager.api_keys)}")
    print(f"🎯 System Ready: http://localhost:8080")
    print("="*50)
    
    uvicorn.run(app, host="0.0.0.0", port=8080)