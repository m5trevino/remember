import chromadb
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import hashlib
import json

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
    except ValueError:
        return client.create_collection(
            name=name,
            metadata=metadata or {"created": datetime.now().isoformat()}
        )

def import_extraction_session(json_file_path: str) -> Dict[str, Any]:
    """Import JSON extraction results, using the full content for the DB record."""
    with open(json_file_path, 'r', encoding='utf-8') as f:
        extraction_data = json.load(f)
    
    session_id = Path(json_file_path).stem
    collection_name = f"extraction_{session_id}"
    collection = get_or_create_collection(collection_name)
    
    documents, metadatas, ids = [], [], []
    
    for result in extraction_data:
        full_content = result.get('content', '')
        if not full_content:
            continue

        doc_id = f"url_{hashlib.md5(result.get('url', '').encode()).hexdigest()}"
        
        metadata = {
            "url": result.get('url', ''),
            "title": result.get('title', 'No Title'),
            "rating": result.get('rating', 0),
            "markdown_file": result.get('markdown_file', ''),
            "session": session_id,
            "created": datetime.now().isoformat(),
        }
        
        documents.append(full_content)
        metadatas.append(metadata)
        ids.append(doc_id)
    
    if documents:
        collection.add(documents=documents, metadatas=metadatas, ids=ids)
    
    return {
        "session_id": session_id,
        "urls_imported": len(documents),
        "collection_name": collection_name
    }

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
