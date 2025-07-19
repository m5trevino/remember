#!/usr/bin/env python3
"""
🔗 MCP Server for ChromaDB Access
Provides tool functions for LLM to query ChromaDB via MCP protocol
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
import chromadb
from datetime import datetime

# Add remember system to path
sys.path.insert(0, str(Path(__file__).parent.absolute()))

try:
    from core.database import get_client, search_extractions
except ImportError:
    print("❌ Core database module not found")
    sys.exit(1)

class MCPServer:
    """MCP Server for ChromaDB operations"""
    
    def __init__(self, port: int = 8081):
        self.port = port
        self.client = None
        self.available_tools = [
            {
                "name": "get_document_by_id",
                "description": "Get full content of a specific document by its vector ID (e.g., doc_001, doc_002)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "document_id": {
                            "type": "string",
                            "description": "Document vector ID (e.g., doc_001, doc_002, doc_003)"
                        }
                    },
                    "required": ["document_id"]
                }
            },
            {
                "name": "list_all_documents",
                "description": "List all available documents with their vector IDs and titles",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "get_multiple_documents",
                "description": "Get content of multiple documents by their vector IDs",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "document_ids": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            },
                            "description": "List of document vector IDs to retrieve"
                        }
                    },
                    "required": ["document_ids"]
                }
            }
        ]
    
    def initialize_db(self):
        """Initialize ChromaDB client"""
        try:
            self.client = get_client()
            print("✅ ChromaDB client initialized")
            return True
        except Exception as e:
            print(f"❌ Failed to initialize ChromaDB: {e}")
            return False
    
    async def handle_tool_call(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming tool calls from LLM"""
        try:
            if tool_name == "get_document_by_id":
                return await self._get_document_by_id(
                    document_id=parameters.get("document_id")
                )
            
            elif tool_name == "list_all_documents":
                return await self._list_all_documents()
            
            elif tool_name == "get_multiple_documents":
                return await self._get_multiple_documents(
                    document_ids=parameters.get("document_ids", [])
                )
            
            else:
                return {
                    "success": False,
                    "error": f"Unknown tool: {tool_name}",
                    "available_tools": [tool["name"] for tool in self.available_tools]
                }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Tool execution failed: {str(e)}",
                "tool": tool_name,
                "parameters": parameters
            }
    
    async def _get_document_by_id(self, document_id: str) -> Dict[str, Any]:
        """Get document by exact vector ID"""
        try:
            collections = self.client.list_collections()
            
            for collection_info in collections:
                if collection_info.name.startswith("extraction_"):
                    collection = self.client.get_collection(collection_info.name)
                    try:
                        # Get document by exact ID
                        result = collection.get(
                            ids=[document_id],
                            include=["metadatas", "documents"]
                        )
                        
                        if result['ids'] and len(result['ids']) > 0:
                            metadata = result['metadatas'][0] if result['metadatas'] else {}
                            document = result['documents'][0] if result['documents'] else ""
                            
                            return {
                                "success": True,
                                "document": {
                                    "id": document_id,
                                    "title": metadata.get('title', 'Unknown'),
                                    "url": metadata.get('url', ''),
                                    "rating": metadata.get('rating', 0),
                                    "markdown_file": metadata.get('markdown_file', ''),
                                    "full_content": document,
                                    "content_length": len(document),
                                    "retrieved_at": datetime.now().isoformat()
                                }
                            }
                    except Exception:
                        continue
            
            return {
                "success": False,
                "error": f"Document with ID '{document_id}' not found"
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to retrieve document: {str(e)}",
                "document_id": document_id
            }
    
    async def _list_all_documents(self) -> Dict[str, Any]:
        """List all documents with their vector IDs and titles"""
        try:
            collections = self.client.list_collections()
            all_documents = []
            
            for collection_info in collections:
                if collection_info.name.startswith("extraction_"):
                    collection = self.client.get_collection(collection_info.name)
                    try:
                        data = collection.get(include=["metadatas"])
                        
                        for i, doc_id in enumerate(data['ids']):
                            metadata = data['metadatas'][i] if data['metadatas'] else {}
                            all_documents.append({
                                "id": doc_id,
                                "title": metadata.get('title', 'Unknown'),
                                "url": metadata.get('url', ''),
                                "rating": metadata.get('rating', 0),
                                "markdown_file": metadata.get('markdown_file', '')
                            })
                    except Exception as e:
                        print(f"Error accessing collection {collection_info.name}: {e}")
                        continue
            
            return {
                "success": True,
                "documents": all_documents,
                "total_count": len(all_documents),
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to list documents: {str(e)}"
            }
    
    async def _get_multiple_documents(self, document_ids: List[str]) -> Dict[str, Any]:
        """Get multiple documents by their vector IDs"""
        try:
            results = []
            for doc_id in document_ids:
                result = await self._get_document_by_id(doc_id)
                if result["success"]:
                    results.append(result["document"])
                else:
                    results.append({
                        "id": doc_id,
                        "error": f"Document not found: {doc_id}"
                    })
            
            return {
                "success": True,
                "documents": results,
                "requested_count": len(document_ids),
                "retrieved_count": len([r for r in results if "error" not in r])
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to retrieve multiple documents: {str(e)}"
            }
    
    def get_tools_schema(self) -> List[Dict[str, Any]]:
        """Get the tools schema for function calling"""
        return self.available_tools
    
    async def start_server(self):
        """Start the MCP server"""
        if not self.initialize_db():
            print("❌ Failed to start MCP server - DB initialization failed")
            return False
        
        print(f"🚀 MCP Server started on port {self.port}")
        print(f"📊 Available tools: {[tool['name'] for tool in self.available_tools]}")
        
        # In a real implementation, this would start an actual server
        # For now, we'll make this callable directly from the web UI
        return True

# Global MCP server instance
mcp_server = MCPServer()

def get_mcp_tools():
    """Get MCP tools for function calling in Groq format"""
    if not mcp_server.client:
        mcp_server.initialize_db()
    
    # Convert MCP tools to Groq function calling format
    mcp_tools = mcp_server.get_tools_schema()
    groq_tools = []
    
    for tool in mcp_tools:
        groq_tool = {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"]
            }
        }
        groq_tools.append(groq_tool)
    
    return groq_tools

async def execute_mcp_tool(tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Execute MCP tool call"""
    if not mcp_server.client:
        mcp_server.initialize_db()
    return await mcp_server.handle_tool_call(tool_name, parameters)

if __name__ == "__main__":
    async def main():
        server = MCPServer()
        await server.start_server()
        
        # Test the tools
        print("\n🧪 Testing MCP tools:")
        
        # Test search
        result = await server.handle_tool_call("search_documents", {"query": "service", "limit": 3})
        print(f"Search result: {result.get('count', 0)} documents found")
        
        # Test list collections
        result = await server.handle_tool_call("list_collections", {})
        print(f"Collections: {[c['name'] for c in result.get('collections', [])]}")
    
    asyncio.run(main())