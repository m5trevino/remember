import chromadb
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import hashlib
import json
import tiktoken

# Database path is now hardcoded for isolation
DB_PATH = Path.home() / "remember_db"

def get_client():
    """Get ChromaDB client for the dedicated remember_db."""
    DB_PATH.mkdir(exist_ok=True)
    return chromadb.PersistentClient(path=str(DB_PATH))

def get_or_create_collection(name: str, metadata: Optional[Dict] = None):
    """Get existing collection or create new one in the dedicated remember_db."""
    client = get_client()
    try:
        return client.get_collection(name)
    except Exception:
        return client.create_collection(
            name=name,
            metadata=metadata or {"created": datetime.now().isoformat()}
        )
def import_extraction_session(json_file_path: str) -> Dict[str, Any]:
    """Import JSON extraction results with structured vector IDs like doc_001, doc_002, etc."""
    with open(json_file_path, 'r', encoding='utf-8') as f:
        extraction_data = json.load(f)
    
    session_id = Path(json_file_path).stem
    collection_name = f"extraction_{session_id}"
    collection = get_or_create_collection(collection_name)
    
    documents, metadatas, ids = [], [], []
    doc_counter = 1
    
    for result in extraction_data:
        full_content = result.get('content', '')
        if not full_content:
            continue

        # Create structured vector ID: doc_001, doc_002, etc.
        doc_id = f"doc_{doc_counter:03d}"
        
        metadata = {
            "url": str(result.get('url', '')),
            "title": str(result.get('title', 'No Title')),
            "rating": int(result.get('rating', 0)) if result.get('rating') is not None else 0,
            "markdown_file": str(result.get('markdown_file', '')),
            "session": str(session_id),
            "created": datetime.now().isoformat(),
            "vector_id": doc_id  # Store the vector ID in metadata for reference
        }
        
        documents.append(full_content)
        metadatas.append(metadata)
        ids.append(doc_id)
        doc_counter += 1
    
    if documents:
        collection.add(documents=documents, metadatas=metadatas, ids=ids)
        
        # Update markdown files with vector ID headers
        update_markdown_files_with_vector_ids(extraction_data, session_id)
    
    return {
        "session_id": session_id,
        "urls_imported": len(documents),
        "collection_name": collection_name,
        "vector_ids_created": [f"doc_{i+1:03d}" for i in range(len(documents))]
    }

def update_markdown_files_with_vector_ids(extraction_data: List[Dict], session_id: str):
    """Add vector ID headers to markdown files"""
    doc_counter = 1
    
    for result in extraction_data:
        markdown_file = result.get('markdown_file', '')
        if not markdown_file or not Path(markdown_file).exists():
            continue
            
        vector_id = f"doc_{doc_counter:03d}"
        
        try:
            # Read current markdown content
            with open(markdown_file, 'r', encoding='utf-8') as f:
                current_content = f.read()
            
            # Check if vector ID header already exists
            if f"Vector ID: {vector_id}" not in current_content:
                # Add vector ID header at the top
                header = f"""---
Vector ID: {vector_id}
Title: {result.get('title', 'Unknown')}
URL: {result.get('url', '')}
Rating: {result.get('rating', 0)}⭐
Session: {session_id}
Imported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
---

"""
                
                # Write updated content
                with open(markdown_file, 'w', encoding='utf-8') as f:
                    f.write(header + current_content)
                    
                print(f"✅ Updated {markdown_file} with vector ID: {vector_id}")
            
            doc_counter += 1
            
        except Exception as e:
            print(f"❌ Failed to update {markdown_file}: {e}")
            continue

def search_extractions(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Search across all extraction sessions in remember_db."""
    client = get_client()
    collections = client.list_collections()
    
    all_results = []
    # If query is empty, fetch all documents by getting all items from collections
    if not query.strip():
        for collection_info in collections:
             if collection_info.name.startswith("extraction_"):
                collection = client.get_collection(collection_info.name)
                data = collection.get(include=["metadatas", "documents"])
                for i, doc_id in enumerate(data['ids']):
                    all_results.append({
                        "id": doc_id,
                        "metadata": data['metadatas'][i],
                        "document": data['documents'][i],
                        "relevance": 1.0
                    })
        return all_results[:limit]

    # If there is a query, perform a vector search
    for collection_info in collections:
        if collection_info.name.startswith("extraction_"):
            collection = client.get_collection(collection_info.name)
            try:
                search_results = collection.query(
                    query_texts=[query],
                    n_results=min(limit, 50),
                    include=["metadatas", "documents", "distances"]
                )
                
                if search_results and search_results["documents"]:
                    for i, doc in enumerate(search_results["documents"][0]):
                        all_results.append({
                            "id": search_results["ids"][0][i],
                            "document": doc,
                            "metadata": search_results["metadatas"][0][i],
                            "relevance": 1 - (search_results["distances"][0][i] or 1.0),
                        })
            except Exception as e:
                print(f"Could not query collection {collection_info.name}: {e}")

    all_results.sort(key=lambda x: x["relevance"], reverse=True)
    return all_results[:limit]

def get_session_stats(session_id: str = None) -> Dict[str, Any]:
    """Get extraction session statistics"""
    client = get_client()
    collections = client.list_collections()
    
    stats = {
        "total_sessions": 0,
        "total_urls": 0,
        "by_rating": {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    }
    
    for collection_info in collections:
        if collection_info.name.startswith("extraction_"):
            collection = client.get_collection(collection_info.name)
            all_data = collection.get()
            
            stats["total_sessions"] += 1
            if all_data["metadatas"]:
                stats["total_urls"] += len(all_data["metadatas"])
                
                for metadata in all_data["metadatas"]:
                    if metadata:
                        rating = metadata.get("rating", 0)
                        if rating in stats["by_rating"]:
                            stats["by_rating"][rating] += 1
    
    return stats

# Project-based database functions (keeping all existing functionality intact)
def create_project(project_name: str, description: str = "") -> Dict[str, Any]:
    """Create a new project collection."""
    collection_name = f"project_{project_name}"
    metadata = {
        "created": datetime.now().isoformat(),
        "description": description,
        "type": "project"
    }
    collection = get_or_create_collection(collection_name, metadata)
    return {
        "project_name": project_name,
        "collection_name": collection_name,
        "created": metadata["created"],
        "description": description
    }

def list_projects() -> List[Dict[str, Any]]:
    """List all projects in the database."""
    client = get_client()
    collections = client.list_collections()
    projects = []
    
    for collection_info in collections:
        if collection_info.name.startswith("project_"):
            project_name = collection_info.name.replace("project_", "")
            collection = client.get_collection(collection_info.name)
            metadata = collection.metadata or {}
            
            # Get document count
            all_data = collection.get()
            doc_count = len(all_data["ids"]) if all_data["ids"] else 0
            
            projects.append({
                "name": project_name,
                "collection_name": collection_info.name,
                "description": metadata.get("description", ""),
                "created": metadata.get("created", ""),
                "document_count": doc_count
            })
    
    return sorted(projects, key=lambda x: x["created"], reverse=True)

def import_to_project(project_name: str, json_file_path: str) -> Dict[str, Any]:
    """Import JSON extraction results into a specific project."""
    with open(json_file_path, 'r', encoding='utf-8') as f:
        extraction_data = json.load(f)
    
    collection_name = f"project_{project_name}"
    collection = get_or_create_collection(collection_name, {
        "type": "project",
        "created": datetime.now().isoformat()
    })
    
    # Get existing document count to continue numbering
    existing_data = collection.get()
    doc_counter = len(existing_data["ids"]) + 1 if existing_data["ids"] else 1
    
    documents, metadatas, ids = [], [], []
    
    for result in extraction_data:
        full_content = result.get('content', '')
        if not full_content:
            continue

        # Create structured vector ID: doc_001, doc_002, etc.
        doc_id = f"doc_{doc_counter:03d}"
        
        # Estimate token count
        try:
            import tiktoken
            encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
            token_count = len(encoding.encode(full_content))
        except:
            token_count = len(full_content.split()) * 1.3  # Rough estimate
        
        metadata = {
            "url": str(result.get('url', '')),
            "title": str(result.get('title', 'No Title')),
            "rating": int(result.get('rating', 0)) if result.get('rating') is not None else 0,
            "markdown_file": str(result.get('markdown_file', '')),
            "project": project_name,
            "created": datetime.now().isoformat(),
            "vector_id": doc_id,
            "character_count": len(full_content),
            "token_count": int(token_count),
            "llm_response": "",  # Initially no LLM response (empty string, not None)
            "llm_response_saved": False
        }
        
        documents.append(full_content)
        metadatas.append(metadata)
        ids.append(doc_id)
        doc_counter += 1
    
    if documents:
        collection.add(documents=documents, metadatas=metadatas, ids=ids)
        
        # Update markdown files with vector ID headers (reuse existing function)
        update_markdown_files_with_vector_ids(extraction_data, project_name)
    
    return {
        "project_name": project_name,
        "urls_imported": len(documents),
        "collection_name": collection_name,
        "vector_ids_created": [f"doc_{i+doc_counter-len(documents):03d}" for i in range(len(documents))]
    }

def get_project_files(project_name: str) -> List[Dict[str, Any]]:
    """Get all files in a project with detailed information."""
    collection_name = f"project_{project_name}"
    client = get_client()
    
    try:
        collection = client.get_collection(collection_name)
        all_data = collection.get(include=["metadatas", "documents"])
        
        files = []
        for i, doc_id in enumerate(all_data['ids']):
            metadata = all_data['metadatas'][i]
            document = all_data['documents'][i]
            
            files.append({
                "id": doc_id,
                "vector_id": metadata.get("vector_id", doc_id),
                "title": metadata.get("title", "No Title"),
                "url": metadata.get("url", ""),
                "rating": metadata.get("rating", 0),
                "markdown_file": metadata.get("markdown_file", ""),
                "character_count": metadata.get("character_count", len(document)),
                "token_count": metadata.get("token_count", 0),
                "created": metadata.get("created", ""),
                "llm_response_saved": metadata.get("llm_response_saved", False),
                "document": document
            })
        
        return sorted(files, key=lambda x: x["vector_id"])
    except Exception as e:
        print(f"Error getting project files: {e}")
        return []

def save_llm_response(project_name: str, document_id: str, response: str) -> bool:
    """Save LLM response for a document."""
    collection_name = f"project_{project_name}"
    client = get_client()
    
    try:
        collection = client.get_collection(collection_name)
        
        # Get current metadata
        result = collection.get(ids=[document_id], include=["metadatas"])
        if not result["metadatas"]:
            return False
        
        metadata = result["metadatas"][0]
        metadata["llm_response"] = response
        metadata["llm_response_saved"] = True
        metadata["response_saved_at"] = datetime.now().isoformat()
        
        # Update the metadata
        collection.update(ids=[document_id], metadatas=[metadata])
        return True
    except Exception as e:
        print(f"Error saving LLM response: {e}")
        return False

def get_files_without_responses(project_name: str) -> List[str]:
    """Get document IDs of files that don't have LLM responses."""
    files = get_project_files(project_name)
    return [f["id"] for f in files if not f["llm_response_saved"]]
