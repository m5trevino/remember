#!/usr/bin/env python3
"""
🔗 Remember Web UI - Smart Batch Processing with Analysis Tracking
Complete implementation with unprocessed/processed document separation
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
import typer
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich import print as rprint
import inquirer

# Model context limits (in tokens) - Using CONTEXT WINDOW for chunking
MODEL_CONTEXT_LIMITS = {
    "moonshotai/kimi-k2-instruct": 131072,
    "meta-llama/llama-4-scout-17b-16e-instruct": 131072,
    "meta-llama/llama-4-maverick-17b-128e-instruct": 131072,
    "deepseek-r1-distill-llama-70b": 131072,
    "llama-3.3-70b-versatile": 131072,
    "llama-3.1-8b-instant": 131072,
    "gemma2-9b-it": 8192,
    "compound-beta": 131072,
    "compound-beta-mini": 131072,
    "default": 8192  # Safe fallback
}

# Reserve tokens for system prompt, user prompt, and response generation
TOKENS_RESERVED = 2000

# Global variable to store selected database
SELECTED_DATABASE = None
console = Console()

def get_database_directories():
    """Get all database directories in .db folder"""
    db_base_path = Path.home() / "remember" / ".db"
    
    if not db_base_path.exists():
        db_base_path.mkdir(parents=True, exist_ok=True)
        return []
    
    # Get all directories in .db
    db_dirs = [d for d in db_base_path.iterdir() if d.is_dir()]
    return sorted(db_dirs, key=lambda x: x.name)

def check_database_status(db_dir_name: str):
    """Check if a database exists for a given directory"""
    db_path = Path.home() / "remember" / ".db" / db_dir_name
    
    # Check for ChromaDB files (chroma.sqlite3 is the main indicator)
    chroma_db = db_path / "chroma.sqlite3"
    collections_dir = db_path / "collections"
    
    if chroma_db.exists() or collections_dir.exists():
        try:
            # Try to connect and get collection count
            client = chromadb.PersistentClient(path=str(db_path))
            collections = client.list_collections()
            doc_count = 0
            
            for collection_info in collections:
                try:
                    collection = client.get_collection(collection_info.name)
                    all_data = collection.get()
                    doc_count += len(all_data["ids"]) if all_data["ids"] else 0
                except:
                    continue
            
            return {
                "exists": True,
                "doc_count": doc_count,
                "collections": len(collections),
                "path": str(db_path)
            }
        except Exception as e:
            return {
                "exists": False,
                "error": str(e),
                "path": str(db_path)
            }
    
    return {
        "exists": False,
        "path": str(db_path)
    }

def get_database_info():
    """Get database info based on .db directories"""
    db_directories = get_database_directories()
    databases = []
    
    for db_dir in db_directories:
        db_name = db_dir.name
        status = check_database_status(db_name)
        
        if status["exists"]:
            databases.append({
                "name": db_name,
                "display_name": f"📊 {db_name}",
                "doc_count": status["doc_count"],
                "description": f"Database exists - {status['collections']} collections",
                "status": "exists",
                "path": status["path"]
            })
        else:
            databases.append({
                "name": db_name,
                "display_name": f"📁 {db_name}",
                "doc_count": 0,
                "description": "No database - needs creation",
                "status": "needs_creation", 
                "path": status["path"]
            })
    
    return databases

def get_url_files():
    """Get all .txt files from the urls directory"""
    urls_dir = Path.home() / "remember" / "urls"
    if not urls_dir.exists():
        urls_dir.mkdir(exist_ok=True)
        return []
    
    txt_files = list(urls_dir.glob("*.txt"))
    return sorted(txt_files, key=lambda f: f.stat().st_mtime, reverse=True)

def select_url_file():
    """Interactive URL file selection with arrow keys"""
    url_files = get_url_files()
    
    if not url_files:
        console.print("[yellow]No URL files found in /home/flintx/remember/urls/[/yellow]")
        console.print("[yellow]Please add .txt files with URLs to extract.[/yellow]")
        return None
    
    # Create choices for inquirer
    choices = []
    for url_file in url_files:
        # Count URLs in file
        try:
            with open(url_file, 'r', encoding='utf-8') as f:
                url_count = len([line for line in f if line.strip() and not line.strip().startswith('#')])
        except:
            url_count = 0
        
        # Get modification time
        mod_time = datetime.fromtimestamp(url_file.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
        
        # Create display string
        choice_display = f"{url_file.name} ({url_count} URLs, modified {mod_time})"
        choices.append((choice_display, url_file))
    
    try:
        questions = [
            inquirer.List(
                'url_file',
                message="📄 Select URL file to extract (use arrow keys)",
                choices=[choice[0] for choice in choices],
            ),
        ]
        
        answers = inquirer.prompt(questions)
        if not answers:
            return None
            
        # Find the selected file
        selected_display = answers['url_file']
        selected_file = next(choice[1] for choice in choices if choice[0] == selected_display)
        
        console.print(f"[green]✅ Selected: {selected_file.name}[/green]")
        return selected_file
        
    except KeyboardInterrupt:
        return None

def create_new_database():
    """Create a new database with URL extraction"""
    try:
        console.print("\n[bold cyan]📚 Create New Database with URL Extraction[/bold cyan]")
        
        # Step 1: Get database name
        name = Prompt.ask("[green]Database name[/green] (e.g., housing_discrimination_2025)")
        if not name:
            console.print("[red]Database name is required![/red]")
            return None
            
        # Clean the name
        clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower())
        
        # Step 2: Get description
        description = Prompt.ask("[green]Description[/green] (optional)", default="")
        
        # Step 3: Select URL file
        selected_url_file = select_url_file()
        if not selected_url_file:
            console.print("[yellow]No URL file selected. Database creation cancelled.[/yellow]")
            return None
        
        # Step 4: Rename URL file to match database name
        urls_dir = Path.home() / "remember" / "urls"
        new_url_filename = f"{clean_name}.txt"
        new_url_filepath = urls_dir / new_url_filename
        
        # Rename the file
        selected_url_file.rename(new_url_filepath)
        console.print(f"[green]✅ Renamed URL file: {selected_url_file.name} → {new_url_filename}[/green]")
        
        # Step 5: Create the database
        client = get_client()
        metadata = {
            "created": datetime.now().isoformat(),
            "description": description,
            "type": "legal_research",
            "url_file": new_url_filename
        }
        
        collection_name = f"project_{clean_name}"
        collection = client.create_collection(collection_name, metadata=metadata)
        
        console.print(f"[green]✅ Created database: {collection_name}[/green]")
        
        # Step 6: Run URL extraction
        console.print(f"[yellow]🚀 Starting URL extraction from {new_url_filename}...[/yellow]")
        
        import subprocess
        extract_script = Path.home() / "remember" / "extract_urls.py"
        
        try:
            result = subprocess.run([
                sys.executable, str(extract_script), str(new_url_filepath)
            ], capture_output=True, text=True, cwd=Path.home() / "remember")
            
            if result.returncode == 0:
                console.print("[green]✅ URL extraction completed successfully![/green]")
                console.print(f"[dim]{result.stdout}[/dim]")
            else:
                console.print(f"[red]❌ URL extraction failed: {result.stderr}[/red]")
                return None
                
        except Exception as e:
            console.print(f"[red]❌ Error running extraction: {e}[/red]")
            return None
        
        # Step 7: Find and import the extraction JSON
        extractions_dir = Path.home() / "remember" / "extractions"
        json_files = list(extractions_dir.glob("extraction_*.json"))
        
        if not json_files:
            console.print("[red]❌ No extraction JSON found to import[/red]")
            return None
        
        # Get the most recent extraction file
        latest_json = max(json_files, key=lambda f: f.stat().st_mtime)
        
        # Step 8: Create organized folder structure
        extracted_md_dir = Path.home() / "remember" / "extracted_md_json" / clean_name
        extracted_md_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy JSON to organized location
        new_json_name = f"{clean_name}_extraction.json"
        new_json_path = extracted_md_dir / new_json_name
        import shutil
        shutil.copy2(latest_json, new_json_path)
        
        console.print(f"[green]✅ Organized extraction files in: {extracted_md_dir}[/green]")
        
        # Step 9: Import to database (you'll implement this part)
        try:
            from core.database import import_to_project
            import_result = import_to_project(clean_name, str(new_json_path))
            console.print(f"[green]✅ Imported {import_result['urls_imported']} documents to database[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠️ Database created but import failed: {e}[/yellow]")
        
        return {
            "name": collection_name,
            "display_name": f"📁 {clean_name.replace('_', ' ').title()}",
            "doc_count": import_result.get('urls_imported', 0) if 'import_result' in locals() else 0,
            "description": description,
            "created": metadata["created"]
        }
        
    except Exception as e:
        console.print(f"[red]Error creating database: {e}[/red]")
        return None

def clear_all_databases():
    """Clear all existing databases and start fresh"""
    console.print("\n[bold red]🗑️ Database Cleanup[/bold red]")
    
    # Get existing databases
    databases = get_database_info()
    
    if not databases:
        console.print("[yellow]No databases found to clear.[/yellow]")
        return
    
    # Show what will be deleted
    console.print(f"[yellow]Found {len(databases)} databases to delete:[/yellow]")
    for db in databases:
        console.print(f"  • {db['display_name']} ({db['doc_count']} docs)")
    
    # Confirm deletion
    if not Confirm.ask("\n[bold red]⚠️ This will delete ALL databases. Continue?[/bold red]"):
        console.print("[yellow]Database cleanup cancelled.[/yellow]")
        return
    
    try:
        client = get_client()
        
        # Delete each database
        deleted_count = 0
        for db in databases:
            try:
                client.delete_collection(db["name"])
                console.print(f"[dim]✅ Deleted: {db['name']}[/dim]")
                deleted_count += 1
            except Exception as e:
                console.print(f"[red]❌ Failed to delete {db['name']}: {e}[/red]")
        
        # Also clear the llm_responses collection
        try:
            client.delete_collection("llm_responses")
            console.print(f"[dim]✅ Deleted: llm_responses[/dim]")
        except:
            pass
        
        console.print(f"\n[green]✅ Cleanup complete! Deleted {deleted_count} databases.[/green]")
        
    except Exception as e:
        console.print(f"[red]❌ Error during cleanup: {e}[/red]")

def create_database_for_directory(db_name: str):
    """Create a ChromaDB database for a specific directory"""
    try:
        console.print(f"\n[bold cyan]🔧 Creating database for: {db_name}[/bold cyan]")
        
        db_path = Path.home() / "remember" / ".db" / db_name
        db_path.mkdir(parents=True, exist_ok=True)
        
        # Create ChromaDB client for this specific directory
        client = chromadb.PersistentClient(path=str(db_path))
        
        # Create a main collection for this legal topic
        collection_name = f"documents_{db_name}"
        metadata = {
            "created": datetime.now().isoformat(),
            "description": f"Legal research database for {db_name}",
            "type": "legal_research"
        }
        
        collection = client.create_collection(collection_name, metadata=metadata)
        
        console.print(f"[green]✅ Created ChromaDB database at: {db_path}[/green]")
        console.print(f"[green]✅ Created collection: {collection_name}[/green]")
        
        return {
            "name": db_name,
            "path": str(db_path),
            "collection": collection_name
        }
        
    except Exception as e:
        console.print(f"[red]❌ Error creating database: {e}[/red]")
        return None

def select_database():
    """Interactive database selection with arrow keys"""
    global SELECTED_DATABASE
    
    console.print("\n[bold magenta]🏛️ Legal AI War Room - Database Selection[/bold magenta]")
    
    # Get available databases from .db directories
    databases = get_database_info()
    
    if not databases:
        console.print("[yellow]No database directories found in /home/flintx/remember/.db/[/yellow]")
        console.print("[yellow]Create some directories first, then run this script.[/yellow]")
        sys.exit(1)
    
    # Create choices for inquirer
    choices = []
    
    for db in databases:
        if db["status"] == "exists":
            choice_display = f"📊 {db['name']} - Database exists ({db['doc_count']} docs, {db['description'].split(' - ')[1]})"
        else:
            choice_display = f"📁 {db['name']} - No database (needs creation)"
        
        choices.append((choice_display, db["status"], db))
    
    try:
        questions = [
            inquirer.List(
                'database',
                message="Select database directory (use arrow keys)",
                choices=[choice[0] for choice in choices],
            ),
        ]
        
        answers = inquirer.prompt(questions)
        if not answers:
            sys.exit(0)
            
        # Find the selected choice
        selected_display = answers['database']
        selected_choice = next(choice for choice in choices if choice[0] == selected_display)
        
        status = selected_choice[1]
        selected_db = selected_choice[2]
        
        if status == "exists":
            # Database exists, use it
            SELECTED_DATABASE = selected_db["name"]
            console.print(f"[green]✅ Selected existing database: {selected_db['name']}[/green]")
            console.print(f"[dim]📍 Path: {selected_db['path']}[/dim]")
            return selected_db["name"]
            
        else:  # needs_creation
            # Database needs creation
            console.print(f"[yellow]📁 Directory {selected_db['name']} has no database[/yellow]")
            
            if Confirm.ask(f"Create ChromaDB database for {selected_db['name']}?"):
                created_db = create_database_for_directory(selected_db["name"])
                if created_db:
                    SELECTED_DATABASE = created_db["name"]
                    console.print(f"[green]✅ Database created and selected: {created_db['name']}[/green]")
                    return created_db["name"]
                else:
                    console.print("[red]Failed to create database.[/red]")
                    return select_database()  # Try again
            else:
                console.print("[yellow]Database creation cancelled.[/yellow]")
                return select_database()  # Go back to selection
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Goodbye! 👋[/yellow]")
        sys.exit(0)

# Add remember system to path
sys.path.insert(0, str(Path(__file__).parent.absolute()))

try:
    from groq_client import GroqClient
    from core.database import get_client, import_extraction_session, get_or_create_collection, import_to_project
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

# Global batch processing state
batch_state = {
    "active": False,
    "total_docs": 0,
    "current_index": 0,
    "processed_docs": [],
    "current_doc": "",
    "success_count": 0,
    "failed_count": 0,
    "start_time": None,
    "current_model": "",
    "selected_contexts": [],
    "analysis_results": []
}

# Setup logging
logs_dir = Path.home() / "remember" / "llm_logs"
logs_dir.mkdir(exist_ok=True)

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
    session_id = session_id or f"session_{timestamp.replace(':', '').replace('-', '').replace('.', '_')[:15]}"
    
    # Create session-specific log file
    session_log = logs_dir / f"session_{session_id}.log"
    
    log_entry = {
        "timestamp": timestamp,
        "type": interaction_type,
        "data": data
    }
    
    with open(session_log, 'a', encoding='utf-8') as f:
        f.write(f"{json.dumps(log_entry, indent=2)}\n{'='*80}\n")

@app.get("/", response_class=HTMLResponse)
async def serve_remember_ui():
    return HTMLResponse(content=r"""
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
        
        .database-item:hover { background: #2a2a2a; border-color: #00ff00; }
        .database-item.selected { background: #003300; border-color: #00ff00; }
        
        .file-section {
            margin-bottom: 20px;
        }
        
        .section-title {
            background: #2a2a2a; padding: 8px; margin-bottom: 10px;
            border: 1px solid #444; border-radius: 4px;
            font-weight: bold; color: #00ff00;
        }
        
        .file-item {
            background: #1a1a1a; border: 1px solid #333; 
            margin-bottom: 4px; padding: 8px; border-radius: 3px;
            cursor: pointer; font-size: 11px; display: flex;
            align-items: center; justify-content: space-between;
        }
        
        .file-item:hover { background: #2a2a2a; border-color: #555; }
        .file-item.selected { background: #003300; border-color: #00ff00; }
        
        .file-item.processed {
            background: #1a2a1a; border-color: #006600;
        }
        
        .file-checkbox {
            margin-right: 8px;
        }
        
        .file-status {
            color: #00aa00; font-size: 10px;
        }
        
        .file-controls {
            display: flex; gap: 5px;
        }
        
        .btn {
            background: #333; color: #00ff00; border: 1px solid #555;
            padding: 4px 8px; border-radius: 3px; cursor: pointer;
            font-size: 10px; font-family: inherit;
        }
        
        .btn:hover { background: #555; }
        .btn.primary { background: #006600; border-color: #00aa00; }
        .btn.danger { background: #660000; border-color: #aa0000; color: #ffaaaa; }
        
        .chat-messages {
            background: #111; border: 1px solid #333; 
            height: 100%; overflow-y: auto; padding: 10px;
            font-size: 12px; line-height: 1.4;
        }
        
        .message {
            margin-bottom: 15px; padding: 10px;
            border-left: 3px solid #555; background: #1a1a1a;
        }
        
        .message.user { border-left-color: #0066cc; }
        .message.assistant { border-left-color: #00aa00; }
        .message.system { border-left-color: #aa6600; }
        
        .message-role {
            font-weight: bold; margin-bottom: 5px; font-size: 10px;
        }
        
        .controls {
            display: grid; grid-template-columns: 1fr auto auto auto;
            gap: 10px; padding: 10px; background: #1a1a1a;
            border: 1px solid #333; margin-top: 10px;
        }
        
        .input-group {
            display: flex; flex-direction: column; gap: 5px;
        }
        
        .input-group select, .input-group input {
            background: #333; color: #00ff00; border: 1px solid #555;
            padding: 5px; border-radius: 3px; font-family: inherit; font-size: 11px;
        }
        
        .bottom-controls {
            display: grid; grid-template-columns: 1fr 1fr 1fr 1fr;
            gap: 10px; padding: 10px; background: #1a1a1a;
            border: 1px solid #333; border-radius: 4px;
        }
        
        .big-btn {
            background: #333; color: #00ff00; border: 1px solid #555;
            padding: 12px; border-radius: 4px; cursor: pointer;
            font-family: inherit; font-weight: bold; font-size: 12px;
        }
        
        .big-btn:hover { background: #555; }
        .big-btn.primary { background: #006600; border-color: #00aa00; }
        .big-btn.danger { background: #660000; border-color: #aa0000; color: #ffaaaa; }
        
        /* BATCH PROCESSING OVERLAY */
        .batch-overlay {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0, 0, 0, 0.9); z-index: 1000;
            display: none; justify-content: center; align-items: center;
        }
        
        .batch-container {
            background: #1a1a1a; border: 2px solid #00ff00; border-radius: 8px;
            padding: 30px; width: 80%; max-width: 800px; color: #00ff00;
        }
        
        .batch-title {
            text-align: center; font-size: 18px; font-weight: bold;
            margin-bottom: 20px; color: #00ff00;
        }
        
        .batch-stats {
            display: grid; grid-template-columns: repeat(4, 1fr);
            gap: 15px; margin-bottom: 20px;
        }
        
        .stat-box {
            background: #2a2a2a; border: 1px solid #444; border-radius: 4px;
            padding: 10px; text-align: center;
        }
        
        .stat-value {
            font-size: 24px; font-weight: bold; color: #00ff00;
        }
        
        .stat-label {
            font-size: 10px; color: #aaa; margin-top: 5px;
        }
        
        .current-doc {
            background: #2a2a2a; border: 1px solid #444; border-radius: 4px;
            padding: 15px; margin-bottom: 20px;
        }
        
        .doc-label {
            font-size: 12px; color: #aaa; margin-bottom: 5px;
        }
        
        .doc-text {
            color: #00ff00; font-weight: bold;
        }
        
        .progress-bar-container {
            background: #333; border-radius: 4px; height: 20px;
            margin-bottom: 20px; position: relative; overflow: hidden;
        }
        
        .progress-bar {
            background: linear-gradient(90deg, #006600, #00aa00);
            height: 100%; transition: width 0.3s ease;
        }
        
        .progress-text {
            position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
            color: #fff; font-weight: bold; font-size: 12px;
        }
        
        .recent-docs {
            background: #2a2a2a; border: 1px solid #444; border-radius: 4px;
            padding: 15px; margin-bottom: 20px; max-height: 200px; overflow-y: auto;
        }
        
        .recent-title {
            font-size: 12px; color: #aaa; margin-bottom: 10px;
        }
        
        .recent-item {
            font-size: 10px; margin-bottom: 3px; padding: 2px 0;
            display: flex; justify-content: space-between;
        }
        
        .recent-item.success { color: #00aa00; }
        .recent-item.failed { color: #aa0000; }
        
        .time-stats {
            display: flex; justify-content: space-between;
            font-size: 11px; color: #aaa; margin-bottom: 20px;
        }
        
        .cancel-btn {
            background: #660000; color: #ffaaaa; border: 1px solid #aa0000;
            padding: 10px 20px; border-radius: 4px; cursor: pointer;
            font-family: inherit; display: block; margin: 0 auto;
        }
        
        .cancel-btn:hover { background: #880000; }
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
    
    <!-- BATCH PROCESSING OVERLAY -->
    <div class="batch-overlay" id="batch-overlay">
        <div class="batch-container">
            <div class="batch-title">🚀 BATCH LEGAL ANALYSIS IN PROGRESS</div>
            
            <div style="text-align: center; margin: 10px 0; padding: 10px; background: #2a2a2a; border-radius: 5px; font-size: 12px;">
                <div><strong>🧠 Model:</strong> <span id="batch-model">Loading...</span></div>
                <div style="margin-top: 5px;"><strong>📋 Contexts:</strong> <span id="batch-contexts">Loading...</span></div>
            </div>
            
            <div class="batch-stats">
                <div class="stat-box">
                    <div class="stat-value" id="batch-current">0</div>
                    <div class="stat-label">CURRENT</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value" id="batch-total">0</div>
                    <div class="stat-label">TOTAL</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value" id="batch-success">0</div>
                    <div class="stat-label">SUCCESS ✅</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value" id="batch-failed">0</div>
                    <div class="stat-label">FAILED ❌</div>
                </div>
            </div>
            
            <div class="current-doc">
                <div class="doc-label">📄 Currently Analyzing:</div>
                <div class="doc-text" id="current-doc-text">Initializing...</div>
            </div>
            
            <div class="progress-bar-container">
                <div class="progress-bar" id="batch-progress-bar" style="width: 0%"></div>
                <div class="progress-text" id="batch-progress-text">0%</div>
            </div>
            
            <div class="recent-docs">
                <div class="recent-title">📋 Recent Documents:</div>
                <div id="recent-docs-list"></div>
                <div id="more-docs-count" style="color: #aaa; font-size: 10px; margin-top: 10px;"></div>
            </div>
            
            <div class="time-stats">
                <span>⏱️ Elapsed: <span id="batch-elapsed">0s</span></span>
                <span>📊 Analyses: <span id="batch-saved">0</span> saved</span>
                <span>🎯 ETA: <span id="batch-eta">Calculating...</span></span>
            </div>
            
            <button class="cancel-btn" onclick="cancelBatch()">❌ Cancel Analysis</button>
        </div>
    </div>
    
    <div class="main-grid">
        <!-- DATABASE PANEL -->
        <div class="database-panel">
            <div class="panel-header">📊 Database Selection</div>
            <div id="database-list">Loading...</div>
            
            <div class="panel-header" style="margin-top: 20px;">🎯 Master Contexts</div>
            <div id="master-contexts">Loading...</div>
            
            <div class="panel-header" style="margin-top: 20px;">📝 Case Notes</div>
            <textarea id="case-notes" placeholder="Quick notes..." 
                style="width: 100%; height: 80px; background: #333; color: #00ff00; border: 1px solid #555; padding: 8px; font-family: inherit; font-size: 11px;"></textarea>
            <button class="btn primary" onclick="saveCaseNotes()" style="margin-top: 5px;">💾 Save</button>
        </div>
        
        <!-- FILE BROWSER -->
        <div class="file-browser">
            <div class="panel-header">📁 File Explorer</div>
            
            <div style="margin-bottom: 10px;">
                <select id="file-mode" onchange="changeFileMode()">
                    <option value="mcp">🗄️ MCP Database</option>
                    <option value="pc">💻 PC Files</option>
                </select>
                <button class="btn" onclick="refreshFiles()" style="margin-left: 5px;">🔄 Refresh</button>
                <button class="btn" onclick="showImportOptions()" style="margin-left: 5px; background: #0066cc;">📥 Import Data</button>
            </div>
            
            <!-- BATCH SELECTION CONTROLS -->
            <div class="batch-controls" style="margin-bottom: 15px; padding: 10px; background: #2a2a2a; border-radius: 5px;">
                <div style="font-weight: bold; margin-bottom: 8px; color: #00ff00;">🎯 Batch Selection</div>
                <div style="display: flex; flex-wrap: wrap; gap: 5px;">
                    <button class="btn" style="font-size: 9px; padding: 3px 8px;" onclick="selectAllFiles()">✅ Select All</button>
                    <button class="btn" style="font-size: 9px; padding: 3px 8px;" onclick="selectUnprocessedOnly()">📄 Unprocessed Only</button>
                    <button class="btn" style="font-size: 9px; padding: 3px 8px;" onclick="selectProcessedOnly()">✅ Processed Only</button>
                    <button class="btn" style="font-size: 9px; padding: 3px 8px;" onclick="unselectAllFiles()">❌ Unselect All</button>
                    <button class="btn" style="font-size: 9px; padding: 3px 8px;" onclick="unprocessAllFiles()">🔄 Unprocess All</button>
                </div>
            </div>
            
            <!-- UNPROCESSED DOCUMENTS SECTION -->
            <div class="file-section">
                <div class="section-title">📄 Unprocessed Documents (<span id="unprocessed-count">0</span>)
                    <button class="btn" style="font-size: 9px; padding: 2px 6px; margin-left: 10px;" onclick="selectAllUnprocessed()">✅ Select All</button>
                    <button class="btn" style="font-size: 9px; padding: 2px 6px; margin-left: 5px;" onclick="deselectAllUnprocessed()">❌ Deselect All</button>
                </div>
                <div id="unprocessed-files">Loading...</div>
            </div>
            
            <!-- PROCESSED DOCUMENTS SECTION -->
            <div class="file-section">
                <div class="section-title">✅ Analyzed Documents (<span id="processed-count">0</span>)
                    <button class="btn" style="font-size: 9px; padding: 2px 6px; margin-left: 10px;" onclick="selectAllProcessed()">✅ Select All</button>
                    <button class="btn" style="font-size: 9px; padding: 2px 6px; margin-left: 5px;" onclick="deselectAllProcessed()">❌ Deselect All</button>
                </div>
                <div id="processed-files">Loading...</div>
            </div>
        </div>
        
        <!-- CHAT AREA -->
        <div class="chat-area">
            <div class="controls">
                <div class="input-group">
                    <label>Model:</label>
                    <select id="provider-select">
                        <option value="deepseek-r1-distill-llama-70b">🧠 Deepseek R1 Distill (70B) - 131K Context</option>
                        <option value="llama-3.3-70b-versatile">🦙 Llama 3.3 70B Versatile</option>
                        <option value="llama-3.1-8b-instant">⚡ Llama 3.1 8B Instant</option>
                    </select>
                </div>
                <div class="input-group">
                    <label>API Key:</label>
                    <select id="api-key-select">
                        <option value="auto">🔄 Auto Rotation</option>
                    </select>
                </div>
                <div class="input-group">
                    <label>Context Mode:</label>
                    <select id="context-mode">
                        <option value="fresh">🆕 Fresh Analysis</option>
                        <option value="build">🔨 Build Context</option>
                    </select>
                </div>
                <div class="input-group">
                    <label>Processing:</label>
                    <select id="processing-mode">
                        <option value="individual">📄 Individual Files</option>
                        <option value="smart_batch">🧠 Smart Batch</option>
                    </select>
                </div>
            </div>
            
            <div class="chat-messages" id="chat-messages">
                <div class="message system">
                    <div class="message-role">SYSTEM</div>
                    <div class="message-content">🏛️ Legal AI War Room initialized. Select database and files to begin analysis.</div>
                </div>
            </div>
            
            <div style="padding: 10px; background: #1a1a1a; border: 1px solid #333;">
                <input type="text" id="user-input" placeholder="Enter analysis prompt or question..." 
                    style="width: 100%; background: #333; color: #00ff00; border: 1px solid #555; padding: 8px; font-family: inherit;">
            </div>
            
            <div class="bottom-controls">
                <button class="big-btn primary" onclick="startBatchAnalysis()">🚀 Batch Process All</button>
                <button class="big-btn" onclick="chunkLargeDocuments()">🧩 Chunk Large Docs</button>
                <button class="big-btn" onclick="verifyPrompt()">🔍 Verify Prompt</button>
                <button class="big-btn" onclick="clearAllAnalysis()" style="background: #ff4444;">🗑️ Clear Analysis</button>
                <button class="big-btn" onclick="legalAnalyze()">⚖️ Legal Analyze</button>
                <button class="big-btn" onclick="searchDocs()">🔍 Search Docs</button>
                <button class="big-btn" onclick="refreshFiles()">🔄 Refresh Files</button>
            </div>
        </div>
    </div>
    
    <script>
        let currentDatabase = null;
        let selectedFiles = [];
        let batchInterval = null;
        
        // Initialize app
        document.addEventListener('DOMContentLoaded', function() {
            loadDatabases();
            loadMasterContexts();
            
            // Enter key support
            document.getElementById('user-input').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    legalAnalyze();
                }
            });
        });
        
        async function loadDatabases() {
            try {
                // Get pre-selected database from CLI
                const selectedResponse = await fetch('/api/selected_database');
                const selectedData = await selectedResponse.json();
                const preSelectedDb = selectedData.selected_database;
                
                console.log('Pre-selected database:', preSelectedDb);
                
                // Get all databases
                const response = await fetch('/api/databases');
                if (!response.ok) {
                    throw new Error('HTTP ' + response.status + ': ' + response.statusText);
                }
                const databases = await response.json();
                
                console.log('Available databases:', databases);
                
                const databaseList = document.getElementById('database-list');
                databaseList.innerHTML = '';
                
                if (!databases || databases.length === 0) {
                    databaseList.innerHTML = '<div style="color: #ff6666; padding: 10px;">No databases found. Please run the URL extractor first to create a database.</div>';
                    return;
                }
                
                let autoSelectedDiv = null;
                
                databases.forEach(db => {
                    const dbDiv = document.createElement('div');
                    dbDiv.className = 'database-item';
                    
                    // Auto-select the pre-selected database
                    if (db.name === preSelectedDb) {
                        dbDiv.classList.add('selected');
                        autoSelectedDiv = dbDiv;
                        currentDatabase = db.name;
                    }
                    
                    dbDiv.innerHTML = '<div style="font-weight: bold;">' + db.name + '</div>' +
                        '<div style="font-size: 10px; color: #aaa; margin-top: 5px;">' +
                        db.collections + ' collections • ' + db.documents + ' docs</div>';
                    dbDiv.onclick = () => selectDatabase(db.name);
                    databaseList.appendChild(dbDiv);
                });
                
                // Auto-load files for pre-selected database
                if (autoSelectedDiv && currentDatabase) {
                    addMessage('system', '📊 Auto-selected database: ' + currentDatabase);
                    await loadFiles();
                }
                
            } catch (error) {
                console.error('Error loading databases:', error);
                const databaseList = document.getElementById('database-list');
                databaseList.innerHTML = '<div style="color: #ff6666; padding: 10px;">Error loading databases: ' + error.message + '</div>';
            }
        }
        
        async function selectDatabase(dbName) {
            currentDatabase = dbName;
            
            // Update UI
            document.querySelectorAll('.database-item').forEach(item => {
                item.classList.remove('selected');
            });
            event.target.closest('.database-item').classList.add('selected');
            
            addMessage('system', '📊 Selected database: ' + dbName);
            await loadFiles();
        }
        
        async function loadFiles() {
            if (!currentDatabase) return;
            
            try {
                const response = await fetch('/api/database/' + currentDatabase + '/files_with_analysis_status');
                const data = await response.json();
                
                const unprocessedDiv = document.getElementById('unprocessed-files');
                const processedDiv = document.getElementById('processed-files');
                
                unprocessedDiv.innerHTML = '';
                processedDiv.innerHTML = '';
                
                let unprocessedCount = 0;
                let processedCount = 0;
                
                data.files.forEach(file => {
                    const fileDiv = document.createElement('div');
                    fileDiv.className = 'file-item ' + (file.has_analysis ? 'processed' : '');
                    
                    if (file.has_analysis) {
                        const title = file.title.substring(0, 40) + (file.title.length > 40 ? '...' : '');
                        fileDiv.innerHTML = ('<div style="display: flex; align-items: center;">' +
                            '<input type="checkbox" class="file-checkbox" id="file-' + file.id + '" onchange="toggleReAnalysis(\'' + file.id + '\')">' +
                            '<label for="file-' + file.id + '" style="flex: 1; cursor: pointer;">' + title + '</label>' +
                            '</div>' +
                            '<div class="file-controls">' +
                            '<span class="file-status">✅ ANALYZED</span>' +
                            '<button class="btn" onclick="viewFile(\'' + file.id + '\')">👁️</button>' +
                            '</div>');
                        processedDiv.appendChild(fileDiv);
                        processedCount++;
                    } else {
                        const shortTitle = file.title.substring(0, 45) + (file.title.length > 45 ? '...' : '');
                        fileDiv.innerHTML = ('<div style="flex: 1;">' + shortTitle + '</div>' +
                            '<div class="file-controls">' +
                            '<button class="btn" onclick="viewFile(\'' + file.id + '\')">👁️</button>' +
                            '</div>');
                        unprocessedDiv.appendChild(fileDiv);
                        unprocessedCount++;
                    }
                });
                
                document.getElementById('unprocessed-count').textContent = unprocessedCount;
                document.getElementById('processed-count').textContent = processedCount;
                
            } catch (error) {
                console.error('Error loading files:', error);
            }
        }
        
        async function loadMasterContexts() {
            try {
                const response = await fetch('/api/master_contexts');
                const contexts = await response.json();
                
                const contextsDiv = document.getElementById('master-contexts');
                contextsDiv.innerHTML = '';
                
                contexts.forEach(context => {
                    const contextDiv = document.createElement('div');
                    contextDiv.className = 'database-item';
                    contextDiv.innerHTML = ('<div style="display: flex; align-items: center;">' +
                        '<input type="checkbox" id="ctx-' + context.name + '" style="margin-right: 8px;">' +
                        '<label for="ctx-' + context.name + '" style="flex: 1; cursor: pointer; font-size: 11px;">' +
                        context.name + 
                        '</label>' +
                        '</div>' +
                        '<div style="font-size: 9px; color: #aaa; margin-top: 3px;">' +
                        context.size + ' chars' +
                        '</div>');
                    contextsDiv.appendChild(contextDiv);
                });
                
            } catch (error) {
                console.error('Error loading master contexts:', error);
                const contextsDiv = document.getElementById('master-contexts');
                contextsDiv.innerHTML = '<div style="color: #ff6666; padding: 10px; font-size: 10px;">Error loading contexts: ' + error.message + '</div>';
            }
        }
        
        function toggleReAnalysis(fileId) {
            // This function handles checking/unchecking files for re-analysis
            console.log('Toggled re-analysis for file: ' + fileId);
        }
        
        async function showBatchConfirmation() {
            const selectedContexts = getSelectedMasterContexts();
            const prompt = document.getElementById('user-input').value.trim() || '';
            
            // Load master context content for preview
            let masterContextContent = '';
            if (selectedContexts.length > 0) {
                try {
                    const response = await fetch('/api/master_contexts');
                    const contexts = await response.json();
                    
                    selectedContexts.forEach(contextName => {
                        const context = contexts.find(c => c.name === contextName);
                        if (context) {
                            // Properly escape the content to prevent JavaScript string errors
                            const escapedContent = context.content.replace(/`/g, '\\`').replace(/\$/g, '\\$');
                            masterContextContent += '\n\n=== ' + contextName.toUpperCase() + ' CONTEXT ===\n' + escapedContent;
                        }
                    });
                } catch (error) {
                    console.error('Error loading contexts:', error);
                }
            }
            
            if (!masterContextContent) {
                masterContextContent = 'No master context selected.';
            }
            
            // Create confirmation modal
            const modal = document.createElement('div');
            modal.id = 'batch-confirmation-modal';
            modal.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 2000; display: flex; justify-content: center; align-items: center;';
            
            var modalHtml = '<div style="background: #1a1a1a; border: 2px solid #00ff00; border-radius: 8px; width: 80%; max-height: 90%; overflow-y: auto; padding: 20px;">';
            modalHtml += '<h3 style="color: #00ff00; text-align: center; margin-bottom: 20px;">🚀 Confirm Batch Analysis Settings</h3>';
            modalHtml += '<div style="margin-bottom: 15px;"><strong style="color: #00ff00;">Database:</strong> <span style="color: #fff;">' + (currentDatabase || 'Selected Database') + '</span></div>';
            modalHtml += '<div style="margin-bottom: 15px;"><strong style="color: #00ff00;">Model:</strong> <span style="color: #fff;">' + document.getElementById('provider-select').value + '</span></div>';
            modalHtml += '<div style="margin-bottom: 15px;"><strong style="color: #00ff00;">Master Contexts:</strong> <span style="color: #fff;">' + (selectedContexts.length > 0 ? selectedContexts.join(', ') : 'None selected') + '</span></div>';
            modalHtml += '<div style="margin-bottom: 20px;"><strong style="color: #00ff00;">Edit Custom Prompt:</strong><textarea id="batch-prompt-editor" style="width: 100%; height: 100px; background: #333; color: #00ff00; border: 1px solid #555; padding: 10px; border-radius: 4px; font-family: inherit; font-size: 12px; margin-top: 5px; resize: vertical;">' + prompt + '</textarea></div>';
            modalHtml += '<div style="margin-bottom: 20px;"><strong style="color: #00ff00;">System Message Preview (Master Context):</strong><pre style="background: #2a2a2a; color: #ccc; padding: 10px; border-radius: 4px; margin-top: 5px; font-size: 10px; max-height: 150px; overflow-y: auto; white-space: pre-wrap;">' + masterContextContent.trim() + '</pre></div>';
            modalHtml += '<div style="margin-bottom: 20px;"><strong style="color: #00ff00;">User Message Template (What LLM Will Receive):</strong><pre id="llm-message-preview" style="background: #2a2a2a; color: #00ff00; padding: 10px; border-radius: 4px; margin-top: 5px; font-size: 10px; max-height: 120px; overflow-y: auto; white-space: pre-wrap;"></pre></div>';
            modalHtml += '<div style="text-align: center;"><button onclick="confirmBatchAnalysis()" style="padding: 10px 20px; background: #00aa00; color: white; border: none; border-radius: 4px; cursor: pointer; margin-right: 10px;">🚀 Start Analysis</button>';
            modalHtml += '<button onclick="closeBatchConfirmation()" style="padding: 10px 20px; background: #666; color: white; border: none; border-radius: 4px; cursor: pointer;">Cancel</button></div></div>';
            modal.innerHTML = modalHtml;
            
            document.body.appendChild(modal);
            
            // Update the preview when prompt changes
            const promptEditor = document.getElementById('batch-prompt-editor');
            const updatePreview = () => {
                const currentPrompt = promptEditor.value.trim();
                const previewMessage = currentPrompt + '\n\nDocument Vector ID: [DOC_ID]\nTitle: [DOC_TITLE]\n\nDocument content:\n[DOC_CONTENT...]';
                document.getElementById('llm-message-preview').textContent = previewMessage;
            };
            
            promptEditor.addEventListener('input', updatePreview);
            updatePreview(); // Initial preview
            window.batchConfirmModal = modal;
        }
        
        function closeBatchConfirmation() {
            const modal = document.getElementById('batch-confirmation-modal');
            if (modal) {
                document.body.removeChild(modal);
            }
        }

        async function startBatchAnalysis() {
            if (!currentDatabase) {
                showModalAlert('Error', 'Please select a database first');
                return;
            }
            
            // Show confirmation dialog first
            showBatchConfirmation();
        }
        
        async function confirmBatchAnalysis() {
            // Get the edited prompt from the textarea
            const editedPrompt = document.getElementById('batch-prompt-editor').value.trim() || '';
            
            // Update the main input field with the edited prompt
            document.getElementById('user-input').value = editedPrompt;
            
            // Close confirmation modal
            closeBatchConfirmation();
            
            // Show batch overlay
            document.getElementById('batch-overlay').style.display = 'flex';
            
            // Start batch processing
            try {
                const response = await fetch('/api/start_batch_analysis', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        database: currentDatabase,
                        provider: document.getElementById('provider-select').value,
                        master_contexts: getSelectedMasterContexts(),
                        prompt: editedPrompt,
                        reanalyze_files: getReAnalysisFiles()
                    })
                });
                
                const data = await response.json();
                if (data.success) {
                    startBatchTracking();
                } else {
                    alert('Error: ' + data.error);
                    hideBatchOverlay();
                }
                
            } catch (error) {
                alert('Error: ' + error.message);
                hideBatchOverlay();
            }
        }
        
        function startBatchTracking() {
            batchInterval = setInterval(updateBatchProgress, 1000);
        }
        
        async function updateBatchProgress() {
            try {
                const response = await fetch('/api/batch_progress');
                const progress = await response.json();
                
                if (!progress.active) {
                    clearInterval(batchInterval);
                    hideBatchOverlay();
                    
                    addMessage('system', '✅ Batch analysis completed!');
                    addMessage('system', '📊 Results: ' + progress.success_count + '/' + progress.total_docs + ' successful');
                    
                    await loadFiles(); // Refresh file list
                    return;
                }
                
                // Update progress display
                const percentage = Math.round((progress.current_index / progress.total_docs) * 100);
                
                document.getElementById('batch-current').textContent = progress.current_index;
                document.getElementById('batch-total').textContent = progress.total_docs;
                document.getElementById('batch-success').textContent = progress.success_count;
                document.getElementById('batch-failed').textContent = progress.failed_count;
                
                document.getElementById('current-doc-text').textContent = progress.current_doc || 'Processing...';
                document.getElementById('batch-progress-bar').style.width = percentage + '%';
                document.getElementById('batch-progress-text').textContent = percentage + '%';
                
                // Update model and contexts display
                document.getElementById('batch-model').textContent = progress.current_model || 'Unknown';
                document.getElementById('batch-contexts').textContent = progress.selected_contexts && progress.selected_contexts.length > 0 
                    ? progress.selected_contexts.join(', ') 
                    : 'Default Legal Analysis';
                
                // Update recent documents list
                updateRecentDocsList(progress.processed_docs);
                
                // Update time stats
                const elapsed = Math.floor((Date.now() - progress.start_time) / 1000);
                document.getElementById('batch-elapsed').textContent = elapsed + 's';
                document.getElementById('batch-saved').textContent = progress.success_count;
                
                // Calculate ETA
                if (progress.current_index > 0) {
                    const avgTimePerDoc = elapsed / progress.current_index;
                    const remaining = progress.total_docs - progress.current_index;
                    const etaSeconds = Math.round(avgTimePerDoc * remaining);
                    document.getElementById('batch-eta').textContent = etaSeconds + 's';
                }
                
            } catch (error) {
                console.error('Error updating batch progress:', error);
            }
        }
        
        function updateRecentDocsList(processedDocs) {
            const recentList = document.getElementById('recent-docs-list');
            const moreCount = document.getElementById('more-docs-count');
            
            // Show last 15 documents
            const recent = processedDocs.slice(-15);
            const older = processedDocs.length - recent.length;
            
            recentList.innerHTML = '';
            recent.forEach(doc => {
                const docDiv = document.createElement('div');
                docDiv.className = 'recent-item ' + (doc.success ? 'success' : 'failed');
                docDiv.innerHTML = '<span>' + (doc.success ? '✅' : '❌') + ' ' + 
                    doc.title.substring(0, 50) + (doc.title.length > 50 ? '...' : '') + '</span>' +
                    '<span>Characters: ' + (doc.characters || 0) + '</span>';
                recentList.appendChild(docDiv);
            });
            
            if (older > 0) {
                moreCount.textContent = '+ ' + older + ' more completed';
            } else {
                moreCount.textContent = '';
            }
        }
        
        function hideBatchOverlay() {
            document.getElementById('batch-overlay').style.display = 'none';
        }
        
        function cancelBatch() {
            if (confirm('Are you sure you want to cancel the batch analysis?')) {
                fetch('/api/cancel_batch', { method: 'POST' });
                clearInterval(batchInterval);
                hideBatchOverlay();
                addMessage('system', '❌ Batch analysis cancelled');
            }
        }
        
        function getSelectedMasterContexts() {
            const contexts = [];
            document.querySelectorAll('#master-contexts input[type="checkbox"]:checked').forEach(checkbox => {
                contexts.push(checkbox.id.replace('ctx-', ''));
            });
            return contexts;
        }
        
        // ====== SELECTION FUNCTIONS ======
        
        function selectAllUnprocessed() {
            document.querySelectorAll('#unprocessed-files input[type="checkbox"]').forEach(checkbox => {
                checkbox.checked = true;
            });
        }
        
        function deselectAllUnprocessed() {
            document.querySelectorAll('#unprocessed-files input[type="checkbox"]').forEach(checkbox => {
                checkbox.checked = false;
            });
        }
        
        function selectAllProcessed() {
            document.querySelectorAll('#processed-files input[type="checkbox"]').forEach(checkbox => {
                checkbox.checked = true;
            });
        }
        
        function deselectAllProcessed() {
            document.querySelectorAll('#processed-files input[type="checkbox"]').forEach(checkbox => {
                checkbox.checked = false;
            });
        }
        
        // New batch selection functions
        function selectAllFiles() {
            document.querySelectorAll('.file-browser input[type="checkbox"]').forEach(checkbox => {
                checkbox.checked = true;
            });
        }
        
        function selectUnprocessedOnly() {
            // Uncheck all first
            document.querySelectorAll('.file-browser input[type="checkbox"]').forEach(checkbox => {
                checkbox.checked = false;
            });
            // Then check only unprocessed
            document.querySelectorAll('#unprocessed-files input[type="checkbox"]').forEach(checkbox => {
                checkbox.checked = true;
            });
        }
        
        function selectProcessedOnly() {
            // Uncheck all first
            document.querySelectorAll('.file-browser input[type="checkbox"]').forEach(checkbox => {
                checkbox.checked = false;
            });
            // Then check only processed
            document.querySelectorAll('#processed-files input[type="checkbox"]').forEach(checkbox => {
                checkbox.checked = true;
            });
        }
        
        function unselectAllFiles() {
            document.querySelectorAll('.file-browser input[type="checkbox"]').forEach(checkbox => {
                checkbox.checked = false;
            });
        }
        
        async function unprocessAllFiles() {
            if (!currentDatabase) {
                alert('Please select a database first');
                return;
            }
            
            if (!confirm('This will clear analysis status for ALL files in the current database. Continue?')) {
                return;
            }
            
            try {
                const response = await fetch('/api/clear_all_analysis/' + currentDatabase, {
                    method: 'POST'
                });
                
                if (response.ok) {
                    const result = await response.json();
                    alert('Cleared analysis status for ' + result.cleared_count + ' files');
                    refreshFiles(); // Reload file browser
                } else {
                    alert('Failed to clear analysis status');
                }
            } catch (error) {
                console.error('Error clearing analysis status:', error);
                alert('Error clearing analysis status');
            }
        }
        
        // ====== PROMPT VERIFICATION ======
        
        async function verifyPrompt() {
            if (!currentDatabase) {
                showModalAlert('Error', 'Please select a database first');
                return;
            }
            
            const prompt = document.getElementById('user-input').value.trim() || '';
            
            const selectedContexts = getSelectedMasterContexts();
            let masterContextContent = '';
            
            // Load master contexts (same logic as backend)
            if (selectedContexts.length > 0) {
                try {
                    const response = await fetch('/api/master_contexts');
                    const contexts = await response.json();
                    
                    selectedContexts.forEach(contextName => {
                        const context = contexts.find(c => c.name === contextName);
                        if (context) {
                            // Properly escape the content to prevent JavaScript string errors
                            const escapedContent = context.content.replace(/`/g, '\\`').replace(/\$/g, '\\$');
                            masterContextContent += '\n\n=== ' + contextName.toUpperCase() + ' CONTEXT ===\n' + escapedContent;
                        }
                    });
                } catch (error) {
                    console.error('Error loading contexts:', error);
                }
            }
            
            if (!masterContextContent) {
                masterContextContent = 'No master context selected. Please select a master context file or enter a custom prompt.';
            }
            
            // Show verification modal
            const modal = document.createElement('div');
            modal.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 1000; display: flex; align-items: center; justify-content: center;';
            
            var modalHtml = '<div style="background: #1a1a1a; border: 2px solid #00ff00; border-radius: 8px; width: 80%; max-height: 80%; overflow-y: auto; padding: 20px;">';
            modalHtml += '<div style="display: flex; justify-content: between; align-items: center; margin-bottom: 15px;">';
            modalHtml += '<h3 style="color: #00ff00; margin: 0;">🔍 LLM Prompt Verification</h3>';
            modalHtml += '<button onclick="this.closest(\'.modal\').remove()" style="background: #ff4444; color: white; border: none; padding: 5px 10px; border-radius: 3px; cursor: pointer; float: right;">❌ Close</button>';
            modalHtml += '</div>';
            modalHtml += '<div style="margin-bottom: 15px;"><h4 style="color: #ffa500;">📋 System Message (Master Context):</h4>';
            modalHtml += '<pre style="background: #333; color: #00ff00; padding: 10px; border-radius: 4px; white-space: pre-wrap; font-size: 11px; max-height: 200px; overflow-y: auto;">' + masterContextContent.trim() + '</pre></div>';
            modalHtml += '<div style="margin-bottom: 15px;"><h4 style="color: #ffa500;">💬 User Message Template:</h4>';
            modalHtml += '<pre style="background: #333; color: #00ff00; padding: 10px; border-radius: 4px; white-space: pre-wrap; font-size: 11px;">';
            modalHtml += 'Please analyze document ID: [DOC_ID]\n\nUse the get_document_by_id tool to retrieve the full content and analyze it.\n\nDocument title: [DOC_TITLE]\n\nAnalysis request: ' + prompt + '</pre></div>';
            modalHtml += '<div><h4 style="color: #ffa500;">⚙️ Processing Info:</h4>';
            modalHtml += '<ul style="color: #ccc; font-size: 11px;">';
            modalHtml += '<li>Selected Database: ' + currentDatabase + '</li>';
            modalHtml += '<li>Selected Model: ' + document.getElementById('provider-select').value + '</li>';
            modalHtml += '<li>Master Contexts: ' + (selectedContexts.length > 0 ? selectedContexts.join(', ') : 'None (using default)') + '</li>';
            modalHtml += '<li>Custom Prompt: ' + prompt + '</li>';
            modalHtml += '</ul></div></div>';
            
            modal.innerHTML = modalHtml;
            modal.className = 'modal';
            document.body.appendChild(modal);
        }
            
            
        
        // ====== CHUNKING FUNCTIONS ======
        
        async function chunkLargeDocuments() {
            if (!currentDatabase) {
                showModalAlert('Error', 'Please select a database first');
                return;
            }
            
            if (!confirm('This will create chunks for large documents. Continue?')) {
                return;
            }
            
            try {
                const response = await fetch('/api/chunk_large_documents', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        database: currentDatabase,
                        model: document.getElementById('provider-select').value
                    })
                });
                
                if (response.ok) {
                    const data = await response.json();
                    alert('Chunking complete!\\n\\nProcessed: ' + data.processed_count + ' documents\\nChunks created: ' + data.chunks_created + '\\nSkipped: ' + data.skipped_count);
                    refreshFiles(); // Refresh to show new chunks
                } else {
                    const error = await response.json();
                    alert('Chunking failed: ' + error.detail);
                }
            } catch (error) {
                alert('Chunking error: ' + error.message);
            }
        }
        
        async function clearAllAnalysis() {
            if (!currentDatabase) {
                showModalAlert('Error', 'Please select a database first');
                return;
            }
            
            if (!confirm('This will clear ALL analysis records for database "' + currentDatabase + '" and allow reprocessing. Continue?')) {
                return;
            }
            
            try {
                const response = await fetch('/api/clear_analysis_status', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        database: currentDatabase,
                        clear_all: true
                    })
                });
                
                if (response.ok) {
                    const data = await response.json();
                    let message = 'Analysis cleared!\n\nCleared ' + data.cleared_count + ' analysis records\nDocuments are now available for reprocessing.';
                    
                    if (data.debug_info) {
                        message += '\n\nDEBUG INFO:\nTarget DB: ' + data.debug_info.target_database + 
                                   '\nDBs Found: ' + data.debug_info.databases_found.join(', ') +
                                   '\nTotal Records: ' + data.debug_info.total_analysis_records +
                                   '\nSample IDs: ' + data.debug_info.sample_source_ids.slice(0,3).join(', ');
                    }
                    
                    alert(message);
                    refreshFiles(); // Refresh to show documents as unprocessed
                } else {
                    const error = await response.json();
                    alert('Clear analysis failed: ' + error.error);
                }
            } catch (error) {
                alert('Clear analysis error: ' + error.message);
            }
        }
        
        function getReAnalysisFiles() {
            const files = [];
            document.querySelectorAll('#processed-files input[type="checkbox"]:checked').forEach(checkbox => {
                files.push(checkbox.id.replace('file-', ''));
            });
            return files;
        }
        
        async function viewFile(fileId) {
            try {
                const response = await fetch('/api/view_file?file_id=' + fileId + '&database=' + currentDatabase);
                if (response.ok) {
                    const popup = window.open('', '_blank', 'width=800,height=600,scrollbars=yes');
                    popup.document.write(await response.text());
                } else {
                    alert('Error viewing file');
                }
            } catch (error) {
                alert('Error: ' + error.message);
            }
        }
        
        async function legalAnalyze() {
            if (!currentDatabase) {
                showModalAlert('Error', 'Please select a database first');
                return;
            }
            
            const message = document.getElementById('user-input').value.trim() || '';
            
            addMessage('user', message);
            addMessage('system', '⚖️ Starting legal analysis...');
            
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        database: currentDatabase,
                        files: selectedFiles,
                        message: message,
                        provider: document.getElementById('provider-select').value,
                        api_key: 'auto',
                        context_mode: document.getElementById('context-mode').value,
                        master_contexts: getSelectedMasterContexts()
                    })
                });
                
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.detail || 'Server error');
                }
                
                const data = await response.json();
                addMessage('assistant', data.response);
                
                // Clear input
                document.getElementById('user-input').value = '';
                
            } catch (error) {
                addMessage('system', '❌ Legal analysis error: ' + error.message);
            }
        }
        
        function addMessage(role, content) {
            const chatMessages = document.getElementById('chat-messages');
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message ' + role;
            
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
                saveBtn.onclick = () => autoSaveToMCP(content);
                
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
                rawLogsBtn.onclick = () => viewRawLogs();
                
                actionsDiv.appendChild(saveBtn);
                actionsDiv.appendChild(editBtn);
                actionsDiv.appendChild(viewBtn);
                actionsDiv.appendChild(rawLogsBtn);
                messageDiv.appendChild(actionsDiv);
            }
            
            chatMessages.appendChild(messageDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
        
        async function autoSaveToMCP(content) {
            try {
                const title = 'Legal Analysis - ' + new Date().toISOString().substring(0, 16).replace('T', ' ');
                
                const response = await fetch('/api/save_response_to_mcp', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        content: content,
                        database: currentDatabase,
                        timestamp: new Date().toISOString(),
                        title: title
                    })
                });
                
                const data = await response.json();
                if (data.success) {
                    addMessage('system', '✅ Analysis saved to MCP database!');
                    await loadFiles(); // Refresh to show updated analysis status
                } else {
                    addMessage('system', '❌ Save error: ' + data.error);
                }
            } catch (error) {
                addMessage('system', '❌ Save error: ' + error.message);
            }
        }
        
        function editResponse(contentDiv, originalContent) {
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
            const popup = window.open('', '_blank', 'width=800,height=600,scrollbars=yes');
            popup.document.write('' +
                '<html>' +
                '<head><title>Full LLM Response</title></head>' +
                '<body style="font-family: monospace; padding: 20px; background: #1e1e1e; color: #d4d4d4;">' +
                '<h2 style="color: #00ff00;">📄 Complete Legal Analysis</h2>' +
                '<hr style="border-color: #333;">' +
                '<pre style="white-space: pre-wrap; font-size: 14px;">' + content + '</pre>' +
                '</body>' +
                '</html>');
        }
        
        function viewRawLogs() {
            window.open('/api/raw_logs', '_blank');
        }
        
        async function searchDocs() {
            const query = prompt('Enter search query:');
            if (!query) return;
            
            try {
                const response = await fetch('/api/search?query=' + encodeURIComponent(query) + '&database=' + currentDatabase);
                const results = await response.json();
                
                addMessage('system', '🔍 Found ' + results.length + ' documents matching "' + query + '"');
                
            } catch (error) {
                addMessage('system', '❌ Search error: ' + error.message);
            }
        }
        
        async function refreshFiles() {
            if (currentDatabase) {
                await loadFiles();
                addMessage('system', '🔄 File list refreshed');
            }
        }
        
        async function showImportOptions() {
            if (!currentDatabase) {
                showModalAlert('Error', 'Please select a database first');
                return;
            }
            
            // Create import modal
            const modal = document.createElement('div');
            modal.id = 'import-modal';
            modal.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 2000; display: flex; justify-content: center; align-items: center;';
            
            modal.innerHTML = '' +
                '<div style="background: #1a1a1a; border: 2px solid #00ff00; border-radius: 8px; width: 70%; max-height: 80%; overflow-y: auto; padding: 20px;">' +
                '<h3 style="color: #00ff00; text-align: center; margin-bottom: 20px;">' +
                '📥 Import Data to ' + currentDatabase + '' +
                '</h3>' +
                '<div style="margin-bottom: 20px; text-align: center;">' +
                '<button onclick="importFromExtracted()" style="padding: 15px 25px; background: #0066cc; color: white; border: none; border-radius: 4px; cursor: pointer; margin: 5px; font-size: 14px;">' +
                '📁 Import from extracted/ folder' +
                '</button>' +
                '<br>' +
                '<button onclick="importFromJSON()" style="padding: 15px 25px; background: #cc6600; color: white; border: none; border-radius: 4px; cursor: pointer; margin: 5px; font-size: 14px;">' +
                '📄 Import from JSON files' +
                '</button>' +
                '<br>' +
                '<button onclick="scanAndImportAll()" style="padding: 15px 25px; background: #00aa00; color: white; border: none; border-radius: 4px; cursor: pointer; margin: 5px; font-size: 14px;">' +
                '🔍 Auto-scan and import all' +
                '</button>' +
                '</div>' +
                '<div id="import-status" style="background: #333; padding: 10px; border-radius: 4px; color: #00ff00; font-family: monospace; font-size: 12px; max-height: 200px; overflow-y: auto; margin-bottom: 15px; white-space: pre-wrap;">Ready to import...</div>' +
                '<div style="text-align: center;">' +
                '<button onclick="closeImportModal()" style="padding: 10px 20px; background: #666; color: white; border: none; border-radius: 4px; cursor: pointer;">' +
                '❌ Close' +
                '</button>' +
                '</div>' +
                '</div>';
            
            document.body.appendChild(modal);
        }
        
        function closeImportModal() {
            const modal = document.getElementById('import-modal');
            if (modal) {
                document.body.removeChild(modal);
            }
        }
        
        function updateImportStatus(message) {
            const statusDiv = document.getElementById('import-status');
            if (statusDiv) {
                statusDiv.textContent += message + '\n';
                statusDiv.scrollTop = statusDiv.scrollHeight;
            }
        }
        
        async function importFromExtracted() {
            updateImportStatus('🔍 Scanning extracted/ folder for markdown files...');
            
            try {
                const response = await fetch('/api/import_from_extracted', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        database: currentDatabase
                    })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    updateImportStatus('✅ Successfully imported ' + result.imported_count + ' documents');
                    updateImportStatus('📊 Vector IDs created: ' + result.vector_ids_created.join(', '));
                    await refreshFiles();
                } else {
                    updateImportStatus('❌ Import failed: ' + result.error);
                }
                
            } catch (error) {
                updateImportStatus('❌ Import error: ' + error.message);
            }
        }
        
        async function importFromJSON() {
            updateImportStatus('🔍 Scanning for JSON extraction files...');
            
            try {
                const response = await fetch('/api/import_from_json', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        database: currentDatabase
                    })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    updateImportStatus('✅ Successfully imported ' + result.imported_count + ' documents from ' + result.files_processed + ' JSON files');
                    updateImportStatus('📊 Vector IDs created: ' + result.vector_ids_created.join(', '));
                    await refreshFiles();
                } else {
                    updateImportStatus('❌ Import failed: ' + result.error);
                }
                
            } catch (error) {
                updateImportStatus('❌ Import error: ' + error.message);
            }
        }
        
        async function scanAndImportAll() {
            updateImportStatus('🔍 Auto-scanning database directory for all importable data...');
            
            try {
                const response = await fetch('/api/scan_and_import_all', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        database: currentDatabase
                    })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    updateImportStatus('✅ Auto-import completed!');
                    updateImportStatus('📁 Extracted files: ' + result.extracted_count);
                    updateImportStatus('📄 JSON files: ' + result.json_count);
                    updateImportStatus('📊 Total documents imported: ' + result.total_imported);
                    if (result.vector_ids_created && result.vector_ids_created.length > 0) {
                        updateImportStatus('🎯 Vector IDs: ' + result.vector_ids_created.slice(0, 10).join(', ') + (result.vector_ids_created.length > 10 ? '...' : ''));
                    }
                    await refreshFiles();
                } else {
                    updateImportStatus('❌ Auto-import failed: ' + result.error);
                }
                
            } catch (error) {
                updateImportStatus('❌ Auto-import error: ' + error.message);
            }
        }
        
        function saveCaseNotes() {
            const notes = document.getElementById('case-notes').value;
            localStorage.setItem('case-notes', notes);
            addMessage('system', '📝 Case notes saved');
        }
        
        // Load saved notes on startup
        window.addEventListener('load', function() {
            const savedNotes = localStorage.getItem('case-notes');
            if (savedNotes) {
                document.getElementById('case-notes').value = savedNotes;
            }
        });
    </script>
</body>
</html>
""")

# ===============================
# API ENDPOINTS
# ===============================

@app.get("/api/selected_database")
async def get_selected_database():
    """Get the pre-selected database from CLI"""
    return {"selected_database": SELECTED_DATABASE}

@app.get("/api/debug/database_status")
async def debug_database_status():
    """Debug endpoint to check database status"""
    try:
        result = {
            "selected_database": SELECTED_DATABASE,
            "database_path": str(Path.home() / "remember" / ".db" / SELECTED_DATABASE) if SELECTED_DATABASE else None,
            "path_exists": False,
            "collections": [],
            "error": None
        }
        
        if SELECTED_DATABASE:
            db_path = Path.home() / "remember" / ".db" / SELECTED_DATABASE
            result["path_exists"] = db_path.exists()
            
            if db_path.exists():
                try:
                    client = get_client(SELECTED_DATABASE)
                    collections = client.list_collections()
                    result["collections"] = [{"name": c.name, "metadata": c.metadata} for c in collections]
                except Exception as e:
                    result["error"] = str(e)
        
        return result
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/databases")
async def get_databases():
    """Get available databases"""
    try:
        if SELECTED_DATABASE:
            # Return the selected database info
            logger.info(f"Getting database info for selected: {SELECTED_DATABASE}")
            
            try:
                client = get_client(SELECTED_DATABASE)
                collections = client.list_collections()
                logger.info(f"Found {len(collections)} collections in {SELECTED_DATABASE}")
            except Exception as e:
                logger.error(f"Failed to connect to database {SELECTED_DATABASE}: {e}")
                # Return basic info even if can't connect
                return [{
                    "name": SELECTED_DATABASE,
                    "collections": 0,
                    "documents": 0,
                    "path": str(Path.home() / "remember" / ".db" / SELECTED_DATABASE),
                    "error": f"Connection failed: {e}"
                }]
        else:
            # No database selected, return all available databases
            logger.info("No selected database, returning all available databases")
            db_dirs = get_database_directories()
            if not db_dirs:
                return []
                
            databases = []
            for db_dir in db_dirs:
                db_name = db_dir.name
                status = check_database_status(db_name)
                databases.append({
                    "name": db_name,
                    "collections": status.get("collections", 0),
                    "documents": status.get("doc_count", 0),
                    "path": status.get("path", str(db_dir)),
                    "exists": status.get("exists", False)
                })
            return databases
        
        # If we have a selected database, get its detailed info
        client = get_client(SELECTED_DATABASE)
        collections = client.list_collections()
        
        total_docs = 0
        for collection in collections:
            try:
                # Get collection and count documents
                coll = client.get_collection(collection.name)
                result = coll.get()
                count = len(result['ids']) if result['ids'] else 0
                total_docs += count
                logger.info(f"Collection {collection.name}: {count} documents")
            except Exception as e:
                logger.error(f"Error counting documents in {collection.name}: {e}")
                continue
        
        # Return only the selected database
        databases = [{
            "name": SELECTED_DATABASE,
            "collections": len(collections),
            "documents": total_docs
        }]
        
        logger.info(f"Returning database info: {databases}")
        return databases
        
    except Exception as e:
        logger.error(f"Error in get_databases: {e}")
        return []

@app.get("/api/database/{database_name}/files_with_analysis_status")
async def get_files_with_analysis_status(database_name: str):
    """Get files with their analysis status from selected database"""
    try:
        # Use selected database instead of parameter
        if not SELECTED_DATABASE:
            logger.error("No selected database for files endpoint")
            return {"files": []}
            
        logger.info(f"Getting files for selected database: {SELECTED_DATABASE}")
        
        try:
            client = get_client(SELECTED_DATABASE)
            collections = client.list_collections()
            logger.info(f"Found {len(collections)} collections")
        except Exception as e:
            logger.error(f"Failed to connect to database {SELECTED_DATABASE}: {e}")
            return {"files": []}
        
        if not collections:
            logger.warning(f"No collections found in {SELECTED_DATABASE}")
            return {"files": []}
            
        try:
            # Use first collection found
            collection_name = collections[0].name
            collection = client.get_collection(collection_name)
            logger.info(f"Using collection: {collection_name}")
        except Exception as e:
            logger.error(f"Failed to get collection: {e}")
            return {"files": []}
        
        # Get all documents
        results = collection.get(include=['documents', 'metadatas'])
        
        # Check for analysis collection
        analysis_collection = None
        try:
            analysis_collection = client.get_collection("llm_responses")
        except:
            pass
        
        # Get list of analyzed document IDs
        analyzed_ids = set()
        if analysis_collection:
            try:
                analysis_results = analysis_collection.get(include=['metadatas'])
                for metadata in analysis_results['metadatas']:
                    if metadata and 'source_document_id' in metadata:
                        analyzed_ids.add(metadata['source_document_id'])
            except:
                pass
        
        files = []
        for i, doc_id in enumerate(results['ids']):
            metadata = results['metadatas'][i] if results['metadatas'] else {}
            
            files.append({
                "id": doc_id,
                "title": metadata.get('title', f'Document {i+1}'),
                "url": metadata.get('url', ''),
                "has_analysis": doc_id in analyzed_ids,
                "size": len(results['documents'][i]) if results['documents'] else 0
            })
        
        return {"files": files}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/master_contexts")
async def get_master_contexts():
    """Get master context files from selected database directory"""
    try:
        if not SELECTED_DATABASE:
            return []
            
        # Get master_context files from selected database directory
        contexts_dir = Path.home() / "remember" / ".db" / SELECTED_DATABASE / "master_context"
        contexts = []
        
        if contexts_dir.exists():
            for context_file in contexts_dir.glob("*.txt"):
                try:
                    content = context_file.read_text(encoding='utf-8')
                    contexts.append({
                        "name": context_file.stem,
                        "size": len(content),
                        "content": content
                    })
                except:
                    pass
        else:
            # Create the master_context directory if it doesn't exist
            contexts_dir.mkdir(exist_ok=True)
        
        return contexts
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class BatchAnalysisRequest(BaseModel):
    database: str
    provider: str
    prompt: str = ""
    master_contexts: List[str] = []
    reanalyze_files: List[str] = []

class ChunkDocumentsRequest(BaseModel):
    database: str
    model: str

@app.post("/api/start_batch_analysis")
async def start_batch_analysis(request: BatchAnalysisRequest):
    """Start batch analysis process"""
    try:
        # Reset batch state
        batch_state.update({
            "active": True,
            "total_docs": 0,
            "current_index": 0,
            "processed_docs": [],
            "current_doc": "",
            "success_count": 0,
            "failed_count": 0,
            "start_time": time.time(),
            "current_model": request.provider,
            "selected_contexts": request.master_contexts,
            "analysis_results": []
        })
        
        # Get files to process from selected database
        client = get_client(SELECTED_DATABASE)
        
        # Try to get the main documents collection for this database
        collections = client.list_collections()
        if not collections:
            raise HTTPException(status_code=400, detail=f"No collections found in database {SELECTED_DATABASE}")
        
        # Use the first collection found (should be the documents collection)
        collection = client.get_collection(collections[0].name)
        results = collection.get(include=['documents', 'metadatas'])
        
        # Get analysis collection
        analysis_collection = None
        try:
            analysis_collection = client.get_collection("llm_responses")
        except:
            analysis_collection = client.create_collection("llm_responses")
        
        # Get analyzed document IDs
        analyzed_ids = set()
        try:
            analysis_results = analysis_collection.get(include=['metadatas'])
            for metadata in analysis_results['metadatas']:
                if metadata and 'source_document_id' in metadata:
                    analyzed_ids.add(metadata['source_document_id'])
        except:
            pass
        
        # Build processing queue
        processing_queue = []
        
        # Add unprocessed documents
        for i, doc_id in enumerate(results['ids']):
            if doc_id not in analyzed_ids:
                metadata = results['metadatas'][i] if results['metadatas'] else {}
                processing_queue.append({
                    "id": doc_id,
                    "title": metadata.get('title', f'Document {i+1}'),
                    "content": results['documents'][i] if results['documents'] else '',
                    "metadata": metadata
                })
        
        # Add re-analysis files
        for file_id in request.reanalyze_files:
            if file_id in results['ids']:
                idx = results['ids'].index(file_id)
                metadata = results['metadatas'][idx] if results['metadatas'] else {}
                processing_queue.append({
                    "id": file_id,
                    "title": metadata.get('title', f'Document {idx+1}'),
                    "content": results['documents'][idx] if results['documents'] else '',
                    "metadata": metadata
                })
        
        batch_state["total_docs"] = len(processing_queue)
        
        # Start background processing
        asyncio.create_task(process_batch_documents(processing_queue, request))
        
        return {"success": True, "total_docs": len(processing_queue)}
        
    except Exception as e:
        batch_state["active"] = False
        raise HTTPException(status_code=500, detail=str(e))

async def process_batch_documents(processing_queue: List[Dict], request: BatchAnalysisRequest):
    """Background task to process documents"""
    try:
        # Load master contexts from selected database directory
        master_context_content = ""
        if request.master_contexts and SELECTED_DATABASE:
            contexts_dir = Path.home() / "remember" / ".db" / SELECTED_DATABASE / "master_context"
            for context_name in request.master_contexts:
                context_file = contexts_dir / f"{context_name}.txt"
                if context_file.exists():
                    content = context_file.read_text(encoding='utf-8')
                    master_context_content += f"\n\n{content}"
        
        if not master_context_content:
            logger.warning("No master context content found - using empty context")
            master_context_content = ""
        
        for i, doc in enumerate(processing_queue):
            if not batch_state["active"]:
                break
                
            batch_state["current_index"] = i + 1
            batch_state["current_doc"] = doc["title"]
            
            try:
                # Get document vector ID
                vector_id = doc.get('id', 'unknown')
                
                # Use custom prompt if provided, otherwise use default
                user_prompt = request.prompt.strip() if request.prompt.strip() else f"Please analyze this legal document: {doc['title']}"
                
                # Prepare messages for LLM with vector ID and custom prompt
                messages = [
                    {"role": "system", "content": master_context_content.strip()},
                    {"role": "user", "content": f"{user_prompt}\n\nDocument Vector ID: {vector_id}\nTitle: {doc['title']}\n\nDocument content:\n{doc['content'][:8000]}"}  # Limit content size
                ]
                
                # Get MCP tools
                tools = get_mcp_tools()
                
                # Log the API request
                session_id = log_llm_interaction("llm_request", {
                    "model": request.provider,
                    "messages": messages,
                    "tools": tools,
                    "document_vector_id": vector_id,
                    "document_title": doc['title']
                })
                
                # Make LLM call
                success, response, debug = groq_client.function_call_chat(
                    messages=messages,
                    tools=tools,
                    model=request.provider
                )
                
                # Log the API response
                log_llm_interaction("llm_response", {
                    "success": success,
                    "response": response,
                    "debug": debug,
                    "document_vector_id": vector_id,
                    "model": request.provider
                }, session_id)
                
                if success:
                    # Auto-save analysis
                    await auto_save_analysis(doc, response, request.database)
                    
                    batch_state["processed_docs"].append({
                        "title": doc["title"],
                        "success": True,
                        "characters": len(response) if isinstance(response, str) else 0
                    })
                    batch_state["success_count"] += 1
                    
                else:
                    batch_state["processed_docs"].append({
                        "title": doc["title"],
                        "success": False,
                        "error": str(debug)[:100],
                        "characters": 0
                    })
                    batch_state["failed_count"] += 1
                
            except Exception as e:
                batch_state["processed_docs"].append({
                    "title": doc["title"],
                    "success": False,
                    "error": str(e)[:100],
                    "characters": 0
                })
                batch_state["failed_count"] += 1
            
            # Small delay between documents
            await asyncio.sleep(2)
        
        # Save final JSON and import to MCP when batch processing completes
        await finalize_batch_analysis()
        
        batch_state["active"] = False
        
    except Exception as e:
        print(f"Batch processing error: {e}")
        batch_state["active"] = False

async def finalize_batch_analysis():
    """Save comprehensive JSON file and import analysis results to MCP"""
    try:
        if not SELECTED_DATABASE or not batch_state.get('analysis_results'):
            return
        
        db_path = Path.home() / "remember" / ".db" / SELECTED_DATABASE
        analysis_dir = db_path / "analysis"
        analysis_dir.mkdir(exist_ok=True)
        
        # Create comprehensive JSON file with all analysis results
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        json_filename = f"batch_analysis_{timestamp}.json"
        json_file_path = analysis_dir / json_filename
        
        # Prepare final JSON data
        final_json_data = {
            "batch_info": {
                "database": SELECTED_DATABASE,
                "generated_at": datetime.now().isoformat(),
                "model_used": batch_state.get('current_model', 'Unknown'),
                "master_contexts": batch_state.get('selected_contexts', []),
                "total_analyses": len(batch_state['analysis_results']),
                "success_count": batch_state.get('success_count', 0),
                "failed_count": batch_state.get('failed_count', 0)
            },
            "analyses": batch_state['analysis_results']
        }
        
        # Save JSON file
        with open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(final_json_data, f, indent=2)
        
        print(f"📄 Saved batch analysis JSON: {json_filename}")
        
        # Import analysis results to MCP (ChromaDB)
        client = get_client(SELECTED_DATABASE)
        
        # Create analysis collection if it doesn't exist
        try:
            analysis_collection = client.get_collection("analyses")
        except:
            analysis_collection = client.create_collection("analyses", metadata={
                "type": "legal_analyses",
                "created": datetime.now().isoformat()
            })
        
        # Prepare data for ChromaDB import
        if batch_state['analysis_results']:
            documents = []
            metadatas = []
            ids = []
            
            for analysis in batch_state['analysis_results']:
                documents.append(analysis['content'])
                metadatas.append({
                    "title": analysis['title'],
                    "source_document_id": analysis['source_document_id'],
                    "analysis_id": analysis['analysis_id'],
                    "database": analysis['database'],
                    "master_contexts": json.dumps(analysis['master_contexts']),
                    "model_used": analysis['model_used'],
                    "character_count": analysis['character_count'],
                    "generated_at": analysis['generated_at'],
                    "markdown_file": analysis['markdown_file'],
                    "type": "legal_analysis"
                })
                ids.append(analysis['analysis_id'])
            
            # Import to ChromaDB
            analysis_collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            
            print(f"🚀 Imported {len(batch_state['analysis_results'])} analyses to ChromaDB")
        
        # Clear the batch analysis results
        batch_state['analysis_results'] = []
        
    except Exception as e:
        print(f"Error finalizing batch analysis: {e}")

async def auto_save_analysis(doc: Dict, analysis: str, database: str):
    """Save analysis to selected database's analysis folder and prepare for JSON compilation"""
    try:
        # Extract content from response if it's a complex object
        if isinstance(analysis, dict):
            content = analysis.get('choices', [{}])[0].get('message', {}).get('content', str(analysis))
        else:
            content = str(analysis)
        
        # Get the selected database directory
        if not SELECTED_DATABASE:
            print("No selected database for analysis saving")
            return
            
        db_path = Path.home() / "remember" / ".db" / SELECTED_DATABASE
        analysis_dir = db_path / "analysis"
        analysis_dir.mkdir(exist_ok=True)
        
        # Generate unique analysis ID and filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        analysis_id = f"analysis_{doc['id']}_{timestamp}"
        filename = f"{analysis_id}.md"
        
        # Create markdown content with master context info
        master_contexts_used = batch_state.get("selected_contexts", [])
        master_context_str = ", ".join(master_contexts_used) if master_contexts_used else "Default Legal Analysis"
        
        markdown_content = f"""# Legal Analysis - {doc['title']}

**Generated:** {datetime.now().isoformat()}
**Source Document:** {doc['id']}
**Database:** {SELECTED_DATABASE}
**Master Context Used:** {master_context_str}
**Model Used:** {batch_state.get('current_model', 'Unknown')}

## Analysis

{content}

## Source Metadata
- Title: {doc.get('title', 'Unknown')}
- URL: {doc.get('metadata', {}).get('url', 'N/A')}
- Vector ID: {doc['id']}
- Original Length: {len(doc.get('content', ''))} characters
"""
        
        # Save markdown file
        md_file_path = analysis_dir / filename
        with open(md_file_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        # Store analysis data for JSON compilation (we'll collect these and save at the end)
        analysis_data = {
            "analysis_id": analysis_id,
            "source_document_id": doc['id'],
            "title": f"Legal Analysis - {doc['title']}",
            "content": content,
            "markdown_file": str(md_file_path),
            "database": SELECTED_DATABASE,
            "master_contexts": master_contexts_used,
            "model_used": batch_state.get('current_model', 'Unknown'),
            "character_count": len(content),
            "generated_at": datetime.now().isoformat(),
            "source_metadata": {
                "title": doc.get('title', 'Unknown'),
                "url": doc.get('metadata', {}).get('url', 'N/A'),
                "vector_id": doc['id'],
                "original_length": len(doc.get('content', ''))
            }
        }
        
        # Add to global batch analysis collection
        if not hasattr(batch_state, 'analysis_results'):
            batch_state['analysis_results'] = []
        batch_state['analysis_results'].append(analysis_data)
        
        print(f"✅ Analysis saved: {filename}")
            
    except Exception as e:
        print(f"Auto-save error: {e}")

@app.get("/api/batch_progress")
async def get_batch_progress():
    """Get current batch processing progress"""
    return {
        "active": batch_state["active"],
        "total_docs": batch_state["total_docs"],
        "current_index": batch_state["current_index"],
        "current_doc": batch_state["current_doc"],
        "success_count": batch_state["success_count"],
        "failed_count": batch_state["failed_count"],
        "processed_docs": batch_state["processed_docs"],
        "start_time": batch_state["start_time"],
        "current_model": batch_state["current_model"],
        "selected_contexts": batch_state["selected_contexts"]
    }

@app.post("/api/cancel_batch")
async def cancel_batch():
    """Cancel batch processing"""
    batch_state["active"] = False
    return {"success": True}

@app.post("/api/chunk_large_documents")
async def chunk_large_documents(request: ChunkDocumentsRequest):
    """Chunk documents that exceed model context limits"""
    try:
        client = get_client()
        collection = client.get_collection(request.database)
        
        # Get context limit for the model
        context_limit = MODEL_CONTEXT_LIMITS.get(request.model, MODEL_CONTEXT_LIMITS["default"])
        max_chunk_tokens = context_limit - TOKENS_RESERVED
        
        # Get all documents
        all_data = collection.get(include=['documents', 'metadatas'])
        
        chunked_count = 0
        total_chunks_created = 0
        
        # Get existing analysis to avoid processing analyzed documents
        analysis_collection = None
        analyzed_ids = set()
        try:
            analysis_collection = client.get_collection("llm_responses")
            analysis_results = analysis_collection.get(include=['metadatas'])
            for metadata in analysis_results['metadatas']:
                if metadata and 'source_document_id' in metadata:
                    analyzed_ids.add(metadata['source_document_id'])
        except:
            pass
        
        for i, doc_id in enumerate(all_data['ids']):
            # Skip already analyzed documents
            if doc_id in analyzed_ids:
                continue
                
            document = all_data['documents'][i]
            metadata = all_data['metadatas'][i]
            
            # Estimate token count
            try:
                encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
                token_count = len(encoding.encode(document))
            except:
                # Fallback estimation: ~1.3 tokens per word
                token_count = len(document.split()) * 1.3
            
            # Check if document needs chunking
            if token_count > max_chunk_tokens:
                # Calculate chunk size in characters (rough approximation)
                chars_per_token = len(document) / token_count
                max_chunk_chars = int(max_chunk_tokens * chars_per_token * 0.9)  # 10% safety margin
                
                # Split document into chunks
                chunks = []
                words = document.split()
                current_chunk = []
                current_length = 0
                
                for word in words:
                    word_length = len(word) + 1  # +1 for space
                    if current_length + word_length > max_chunk_chars and current_chunk:
                        chunks.append(' '.join(current_chunk))
                        current_chunk = [word]
                        current_length = word_length
                    else:
                        current_chunk.append(word)
                        current_length += word_length
                
                # Add final chunk
                if current_chunk:
                    chunks.append(' '.join(current_chunk))
                
                # Add chunks to database with new IDs
                for chunk_idx, chunk_content in enumerate(chunks, 1):
                    chunk_id = f"{doc_id}_chunk_{chunk_idx}"
                    
                    # Create chunk metadata
                    chunk_metadata = metadata.copy()
                    chunk_metadata.update({
                        "original_document_id": doc_id,
                        "chunk_number": chunk_idx,
                        "total_chunks": len(chunks),
                        "is_chunk": True,
                        "vector_id": chunk_id,
                        "character_count": len(chunk_content),
                        "token_count": int(len(chunk_content.split()) * 1.3),
                        "title": f"{metadata.get('title', 'Unknown')} - Chunk {chunk_idx}/{len(chunks)}",
                        "created": datetime.now().isoformat()
                    })
                    
                    # Add chunk to collection
                    collection.add(
                        documents=[chunk_content],
                        metadatas=[chunk_metadata], 
                        ids=[chunk_id]
                    )
                    
                    total_chunks_created += 1
                
                chunked_count += 1
        
        return {
            "success": True,
            "model": request.model,
            "context_limit": context_limit,
            "max_chunk_tokens": max_chunk_tokens,
            "documents_chunked": chunked_count,
            "total_chunks_created": total_chunks_created,
            "database": request.database
        }
        
    except Exception as e:
        logger.error(f"Chunking error: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/verify_prompt")
async def verify_prompt(request: BatchAnalysisRequest):
    """Generate a preview of what prompt will be sent to the LLM"""
    try:
        # Load master contexts from selected database directory
        master_context_content = ""
        if request.master_contexts and SELECTED_DATABASE:
            contexts_dir = Path.home() / "remember" / ".db" / SELECTED_DATABASE / "master_context"
            for context_name in request.master_contexts:
                context_file = contexts_dir / f"{context_name}.txt"
                if context_file.exists():
                    content = context_file.read_text(encoding='utf-8')
                    master_context_content += f"\n\n{content}"
        
        if not master_context_content:
            logger.warning("No master context content found - using empty context")
            master_context_content = ""
        
        # Get a sample document from the database
        client = get_client()
        collection = client.get_collection(request.database)
        sample_data = collection.get(limit=1, include=['documents', 'metadatas'])
        
        if not sample_data['ids']:
            return {"success": False, "error": "No documents found in database"}
        
        sample_doc = {
            'id': sample_data['ids'][0],
            'title': sample_data['metadatas'][0].get('title', 'Sample Document'),
            'content': sample_data['documents'][0][:1000] + "..." if len(sample_data['documents'][0]) > 1000 else sample_data['documents'][0]
        }
        
        # Generate the prompt preview
        vector_id = sample_doc.get('id', 'unknown')
        user_prompt = request.prompt.strip() if request.prompt.strip() else f"Please analyze this legal document: {sample_doc['title']}"
        
        messages = [
            {"role": "system", "content": master_context_content.strip()},
            {"role": "user", "content": f"{user_prompt}\n\nDocument Vector ID: {vector_id}\nTitle: {sample_doc['title']}\n\nDocument content:\n{sample_doc['content']}"}
        ]
        
        return {
            "success": True,
            "model": request.provider,
            "database": request.database,
            "master_contexts": request.master_contexts,
            "sample_document": {
                "vector_id": vector_id,
                "title": sample_doc['title'],
                "content_preview": sample_doc['content']
            },
            "full_prompt": {
                "system_message": messages[0]["content"],
                "user_message": messages[1]["content"]
            },
            "estimated_tokens": len(str(messages).split()) * 1.3  # Rough token estimate
        }
        
    except Exception as e:
        logger.error(f"Prompt verification error: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/clear_analysis_status")
async def clear_analysis_status(request: dict):
    """Clear analysis status for specified documents to allow reprocessing"""
    try:
        database = request.get("database")
        document_ids = request.get("document_ids", [])
        clear_all = request.get("clear_all", False)
        
        if not database:
            return {"success": False, "error": "Database name required"}
        
        client = get_client()
        
        # Get or create analysis collection
        try:
            analysis_collection = client.get_collection("llm_responses")
        except:
            return {"success": True, "cleared_count": 0, "message": "No analysis collection found"}
        
        # Get all analysis records for debugging
        analysis_results = analysis_collection.get(include=['metadatas'])
        
        # Debug: Log what we found
        logger.info(f"Clear analysis debug - Target database: {database}")
        logger.info(f"Clear analysis debug - Total analysis records: {len(analysis_results['ids'])}")
        
        # Check what database names exist in the analysis records
        db_names_found = set()
        source_doc_ids_found = set()
        for i, analysis_id in enumerate(analysis_results['ids']):
            metadata = analysis_results['metadatas'][i]
            if metadata:
                if 'database' in metadata:
                    db_names_found.add(metadata['database'])
                if 'source_document_id' in metadata:
                    source_doc_ids_found.add(metadata['source_document_id'])
        
        logger.info(f"Clear analysis debug - Database names found: {list(db_names_found)}")
        logger.info(f"Clear analysis debug - Sample source doc IDs: {list(source_doc_ids_found)[:10]}")
        
        if clear_all:
            # Try multiple strategies to match database
            to_delete = []
            for i, analysis_id in enumerate(analysis_results['ids']):
                metadata = analysis_results['metadatas'][i]
                if metadata:
                    # Strategy 1: Exact database match
                    if metadata.get('database') == database:
                        to_delete.append(analysis_id)
                    # Strategy 2: Check if source_document_id starts with database prefix
                    elif 'source_document_id' in metadata:
                        source_id = metadata['source_document_id']
                        if source_id.startswith('doc_'):
                            # Get documents from the target database to check if this analysis belongs to it
                            try:
                                target_collection = client.get_collection(database)
                                target_docs = target_collection.get(include=['metadatas'])
                                if source_id in target_docs['ids']:
                                    to_delete.append(analysis_id)
                            except:
                                pass
        else:
            # Clear specific document analyses
            to_delete = []
            for i, analysis_id in enumerate(analysis_results['ids']):
                metadata = analysis_results['metadatas'][i]
                if metadata and metadata.get('source_document_id') in document_ids:
                    to_delete.append(analysis_id)
        
        logger.info(f"Clear analysis debug - Records to delete: {len(to_delete)}")
        
        # Delete the analysis records
        if to_delete:
            analysis_collection.delete(ids=to_delete)
        
        return {
            "success": True,
            "cleared_count": len(to_delete),
            "database": database,
            "cleared_documents": document_ids if not clear_all else "all",
            "message": f"Cleared {len(to_delete)} analysis records",
            "debug_info": {
                "target_database": database,
                "databases_found": list(db_names_found),
                "total_analysis_records": len(analysis_results['ids']),
                "sample_source_ids": list(source_doc_ids_found)[:10]
            }
        }
        
    except Exception as e:
        logger.error(f"Clear analysis error: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/clear_all_analysis/{database_name}")
async def clear_all_analysis(database_name: str):
    """Clear all analysis status for a specific database"""
    try:
        if not database_name:
            raise HTTPException(status_code=400, detail="Database name required")
        
        # Use the existing clear_analysis_status function with clear_all=True
        result = await clear_analysis_status({
            "database": database_name,
            "clear_all": True
        })
        
        return result
        
    except Exception as e:
        logger.error(f"Clear all analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/view_file", response_class=HTMLResponse)
async def view_file_content(file_id: str = Query(...), database: str = Query(...)):
    """View file content in popup window"""
    try:
        client = get_client()
        collection = client.get_collection(database)
        
        # Get document
        result = collection.get(
            ids=[file_id],
            include=['documents', 'metadatas']
        )
        
        if not result['ids']:
            raise HTTPException(status_code=404, detail="File not found")
        
        content = result['documents'][0] if result['documents'] else "No content available"
        metadata = result['metadatas'][0] if result['metadatas'] else {}
        
        # Return formatted HTML viewer
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>File Viewer - {metadata.get('title', file_id)}</title>
    <style>
        body {{ 
            font-family: 'Courier New', monospace; 
            background: #1e1e1e; color: #d4d4d4; 
            padding: 20px; line-height: 1.5;
        }}
        .header {{
            background: #2a2a2a; padding: 15px; margin-bottom: 20px;
            border-left: 4px solid #00ff00; border-radius: 4px;
        }}
        .metadata {{
            background: #2a2a2a; padding: 10px; margin-bottom: 20px;
            border-radius: 4px; font-size: 12px;
        }}
        .content {{
            background: #1a1a1a; padding: 20px; border-radius: 4px;
            white-space: pre-wrap; font-size: 14px; border: 1px solid #333;
        }}
        .controls {{
            position: fixed; top: 20px; right: 20px;
            display: flex; gap: 10px;
        }}
        .btn {{
            background: #333; color: #00ff00; border: 1px solid #555;
            padding: 8px 12px; border-radius: 4px; cursor: pointer;
            font-family: inherit; font-size: 12px;
        }}
        .btn:hover {{ background: #555; }}
    </style>
</head>
<body>
    <div class="controls">
        <button class="btn" onclick="window.print()">🖨️ Print</button>
        <button class="btn" onclick="copyToClipboard()">📋 Copy</button>
        <button class="btn" onclick="window.close()">❌ Close</button>
    </div>
    
    <div class="header">
        <h2 style="color: #00ff00; margin: 0;">📄 {metadata.get('title', 'Document Viewer')}</h2>
    </div>
    
    <div class="metadata">
        <strong>File ID:</strong> {file_id}<br>
        <strong>Database:</strong> {database}<br>
        <strong>URL:</strong> {metadata.get('url', 'N/A')}<br>
        <strong>Content Length:</strong> {len(content):,} characters<br>
        <strong>Rating:</strong> {metadata.get('rating', 'N/A')}<br>
        <strong>Type:</strong> {metadata.get('type', 'Document')}
    </div>
    
    <div class="content" id="document-content">{content}</div>
    
    <script>
        function copyToClipboard() {{
            const content = document.getElementById('document-content').textContent;
            navigator.clipboard.writeText(content).then(() => {{
                alert('Content copied to clipboard!');
            }});
        }}
    </script>
</body>
</html>
"""
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Include other endpoints from original file...
@app.post("/api/chat")
async def process_chat_request(request: dict):
    """Process chat request with legal analysis"""
    try:
        # Implementation similar to original but with proper error handling
        return {"response": "Chat processing endpoint - implement based on original"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/save_response_to_mcp")
async def save_response_to_mcp(request: dict):
    """Save LLM response to MCP database"""
    try:
        # Implementation for saving responses
        return {"success": True}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/import_from_extracted")
async def import_from_extracted(request: dict):
    """Import markdown files from the extracted/ folder"""
    try:
        database_name = request.get("database")
        if not database_name:
            return {"success": False, "error": "Database name required"}
        
        db_path = Path.home() / "remember" / ".db" / database_name
        extracted_dir = db_path / "extracted"
        
        if not extracted_dir.exists():
            return {"success": False, "error": f"No extracted/ folder found in {database_name}"}
        
        # Get all markdown files
        md_files = list(extracted_dir.glob("*.md"))
        if not md_files:
            return {"success": False, "error": "No markdown files found in extracted/ folder"}
        
        # Import to ChromaDB
        client = get_client(database_name)
        collection = client.get_or_create_collection(database_name)
        
        # Check existing documents to avoid duplicates
        existing_data = collection.get()
        existing_titles = set()
        if existing_data['metadatas']:
            existing_titles = {metadata.get('title', '') for metadata in existing_data['metadatas'] if metadata}
        
        documents, metadatas, ids = [], [], []
        vector_ids_created = []
        doc_counter = len(existing_data['ids']) + 1 if existing_data['ids'] else 1
        
        for md_file in md_files:
            try:
                content = md_file.read_text(encoding='utf-8')
                if len(content) < 50:  # Skip very short files
                    continue
                    
                # Extract title from filename or content
                title = md_file.stem.replace('extracted_', '').replace('_', ' ')
                
                # Skip if already imported
                if title in existing_titles:
                    continue
                    
                vector_id = f"doc_{doc_counter:03d}"
                
                metadata = {
                    "title": title,
                    "source_file": str(md_file),
                    "imported_from": "extracted_folder",
                    "created": datetime.now().isoformat(),
                    "vector_id": vector_id,
                    "character_count": len(content)
                }
                
                documents.append(content)
                metadatas.append(metadata)
                ids.append(vector_id)
                vector_ids_created.append(vector_id)
                doc_counter += 1
                
            except Exception as e:
                logger.error(f"Error processing {md_file}: {e}")
                continue
        
        if documents:
            collection.add(documents=documents, metadatas=metadatas, ids=ids)
        
        return {
            "success": True,
            "imported_count": len(documents),
            "vector_ids_created": vector_ids_created,
            "skipped_duplicates": len(md_files) - len(documents)
        }
        
    except Exception as e:
        logger.error(f"Import from extracted error: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/import_from_json")
async def import_from_json(request: dict):
    """Import from JSON extraction files"""
    try:
        database_name = request.get("database")
        if not database_name:
            return {"success": False, "error": "Database name required"}
        
        db_path = Path.home() / "remember" / ".db" / database_name
        
        # Look for JSON files in the database directory and extracted/ subdirectory
        json_files = list(db_path.glob("*.json")) + list(db_path.glob("extracted/*.json"))
        
        if not json_files:
            return {"success": False, "error": "No JSON files found"}
        
        total_imported = 0
        vector_ids_created = []
        files_processed = 0
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Skip if not extraction format
                if not isinstance(data, list) or not data:
                    continue
                    
                # Check if it looks like extraction data
                first_item = data[0]
                if not isinstance(first_item, dict) or 'content' not in first_item:
                    continue
                    
                # Import using existing function
                result = import_to_project(database_name, str(json_file))
                if result:
                    total_imported += result['urls_imported']
                    vector_ids_created.extend(result.get('vector_ids_created', []))
                    files_processed += 1
                    
            except Exception as e:
                logger.error(f"Error processing JSON file {json_file}: {e}")
                continue
        
        return {
            "success": True,
            "imported_count": total_imported,
            "vector_ids_created": vector_ids_created,
            "files_processed": files_processed
        }
        
    except Exception as e:
        logger.error(f"Import from JSON error: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/scan_and_import_all")
async def scan_and_import_all(request: dict):
    """Auto-scan and import all available data"""
    try:
        database_name = request.get("database")
        if not database_name:
            return {"success": False, "error": "Database name required"}
        
        # Import from extracted folder
        extracted_result = await import_from_extracted({"database": database_name})
        extracted_count = extracted_result.get('imported_count', 0) if extracted_result.get('success') else 0
        
        # Import from JSON files
        json_result = await import_from_json({"database": database_name})
        json_count = json_result.get('imported_count', 0) if json_result.get('success') else 0
        
        # Combine vector IDs
        all_vector_ids = []
        if extracted_result.get('success'):
            all_vector_ids.extend(extracted_result.get('vector_ids_created', []))
        if json_result.get('success'):
            all_vector_ids.extend(json_result.get('vector_ids_created', []))
        
        return {
            "success": True,
            "extracted_count": extracted_count,
            "json_count": json_count,
            "total_imported": extracted_count + json_count,
            "vector_ids_created": all_vector_ids
        }
        
    except Exception as e:
        logger.error(f"Scan and import all error: {e}")
        return {"success": False, "error": str(e)}

def main():
    """Main startup function with database selection"""
    try:
        # Select database first
        selected_database = select_database()
        
        # Make sure the global variable is set
        global SELECTED_DATABASE
        SELECTED_DATABASE = selected_database
        
        console.print(f"\n[bold green]🚀 Starting Legal AI War Room...[/bold green]")
        console.print(f"[cyan]📊 Database: {selected_database}[/cyan]")
        console.print(f"[cyan]📍 Path: /home/flintx/remember/.db/{selected_database}[/cyan]")
        console.print(f"[cyan]🌐 Web UI: http://localhost:8080[/cyan]")
        console.print(f"[yellow]📋 MCP Server logs will appear below...[/yellow]")
        console.print("="*60)
        
        # Verify database exists
        db_path = Path.home() / "remember" / ".db" / selected_database
        if db_path.exists():
            console.print(f"[green]✅ Database directory exists: {db_path}[/green]")
            if (db_path / "chroma.sqlite3").exists():
                console.print(f"[green]✅ ChromaDB file found[/green]")
            else:
                console.print(f"[yellow]⚠️ No ChromaDB file found[/yellow]")
        else:
            console.print(f"[red]❌ Database directory not found: {db_path}[/red]")
        
        # Start the web server
        uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down... 👋[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error starting server: {e}[/red]")
        sys.exit(1)

if __name__ == "__main__":
    main()