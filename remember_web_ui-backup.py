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
            <div style="margin-bottom: 15px; display: flex; gap: 5px; flex-wrap: wrap;">
                <button class="btn extract" id="extract-urls-btn">
                    🚀 Extract URLs
                </button>
                <button class="btn batch" id="batch-process-btn" disabled>
                    Batch Process All
                </button>
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
               
           } catch (error) {
               addMessage('system', `❌ Batch process error: ${error.message}`);
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

if __name__ == "__main__":
    import uvicorn
    print("\n🔗 Remember Legal AI War Room Starting...")
    print(f"📊 Groq Keys: {len(groq_client.router.api_manager.api_keys)}")
    print(f"🎯 System Ready: http://localhost:8080")
    print("="*50)
    
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
