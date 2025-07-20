#!/usr/bin/env python3
"""
🗑️ Remember CLI - Collection Delete Handler
Manage and delete entire collections from ChromaDB
"""

import sys
from pathlib import Path
from typing import List, Optional
from core.database import get_client
import json

class CollectionDeleteHandler:
    def __init__(self):
        self.client = get_client()
    
    def list_collections(self) -> List[dict]:
        """List all collections with metadata"""
        collections = self.client.list_collections()
        collection_info = []
        
        for collection in collections:
            col_data = self.client.get_collection(collection.name)
            count = col_data.count()
            
            # Get sample metadata
            if count > 0:
                sample = col_data.get(limit=1, include=['metadatas'])
                sample_meta = sample['metadatas'][0] if sample['metadatas'] else {}
            else:
                sample_meta = {}
            
            collection_info.append({
                'name': collection.name,
                'count': count,
                'created': sample_meta.get('created', 'unknown'),
                'type': 'extraction' if 'extraction' in collection.name else 'other'
            })
        
        return collection_info
    
    def show_collections(self):
        """Display all collections in a formatted table"""
        collections = self.list_collections()
        
        print("🗂️  REMEMBER DATABASE COLLECTIONS")
        print("=" * 80)
        print(f"{'#':<3} {'Name':<45} {'Docs':<8} {'Type':<12} {'Created'}")
        print("-" * 80)
        
        for i, col in enumerate(collections, 1):
            print(f"{i:<3} {col['name']:<45} {col['count']:<8} {col['type']:<12} {col['created']}")
        
        print("-" * 80)
        print(f"Total: {len(collections)} collections, {sum(c['count'] for c in collections)} documents")
        print()
    
    def delete_collection(self, collection_name: str, force: bool = False) -> bool:
        """Delete a collection after confirmation"""
        try:
            # Check if collection exists
            collections = [c.name for c in self.client.list_collections()]
            if collection_name not in collections:
                print(f"❌ Collection '{collection_name}' not found")
                return False
            
            # Get collection info
            col_data = self.client.get_collection(collection_name)
            count = col_data.count()
            
            print(f"🗑️  COLLECTION DELETE WARNING")
            print(f"Collection: {collection_name}")
            print(f"Documents: {count}")
            print(f"This action cannot be undone!")
            print()
            
            if not force:
                confirm = input("Type 'DELETE' to confirm: ")
                if confirm != 'DELETE':
                    print("❌ Deletion cancelled")
                    return False
            
            # Delete the collection
            self.client.delete_collection(collection_name)
            print(f"✅ Collection '{collection_name}' deleted successfully")
            print(f"📊 Removed {count} documents from database")
            return True
            
        except Exception as e:
            print(f"❌ Error deleting collection: {e}")
            return False
    
    def find_duplicates(self) -> dict:
        """Find duplicate collections and content"""
        collections = self.list_collections()
        duplicates = {
            'similar_collections': [],
            'duplicate_titles': {},
            'duplicate_urls': {}
        }
        
        # Find similar collection names
        extraction_collections = [c for c in collections if 'extraction' in c['name']]
        if len(extraction_collections) > 1:
            duplicates['similar_collections'] = extraction_collections
        
        # Check for duplicate content within collections
        for collection in collections:
            col_data = self.client.get_collection(collection['name'])
            data = col_data.get(include=['metadatas'])
            
            # Track titles and URLs
            titles = {}
            urls = {}
            
            for i, metadata in enumerate(data['metadatas']):
                title = metadata.get('title', '[no-title]')
                url = metadata.get('url', '')
                
                if title in titles:
                    if collection['name'] not in duplicates['duplicate_titles']:
                        duplicates['duplicate_titles'][collection['name']] = []
                    duplicates['duplicate_titles'][collection['name']].append(title)
                else:
                    titles[title] = i
                
                if url and url in urls:
                    if collection['name'] not in duplicates['duplicate_urls']:
                        duplicates['duplicate_urls'][collection['name']] = []
                    duplicates['duplicate_urls'][collection['name']].append(url)
                else:
                    urls[url] = i
        
        return duplicates
    
    def show_duplicates(self):
        """Display duplicate analysis"""
        duplicates = self.find_duplicates()
        
        print("🔍 DUPLICATE ANALYSIS")
        print("=" * 60)
        
        # Similar collections
        if duplicates['similar_collections']:
            print("📂 SIMILAR COLLECTIONS (likely duplicates):")
            for col in duplicates['similar_collections']:
                print(f"  - {col['name']} ({col['count']} docs)")
            print()
        
        # Duplicate titles
        if duplicates['duplicate_titles']:
            print("📄 DUPLICATE TITLES:")
            for collection, titles in duplicates['duplicate_titles'].items():
                print(f"  Collection: {collection}")
                for title in set(titles):
                    print(f"    - {title}")
            print()
        
        # Duplicate URLs
        if duplicates['duplicate_urls']:
            print("🔗 DUPLICATE URLS:")
            for collection, urls in duplicates['duplicate_urls'].items():
                print(f"  Collection: {collection}")
                for url in set(urls):
                    print(f"    - {url}")
            print()
        
        if not any(duplicates.values()):
            print("✅ No duplicates found")

def main():
    """CLI interface for collection management"""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python collection_delete.py list")
        print("  python collection_delete.py duplicates")
        print("  python collection_delete.py delete <collection_name>")
        print("  python collection_delete.py delete <collection_name> --force")
        return
    
    handler = CollectionDeleteHandler()
    command = sys.argv[1]
    
    if command == 'list':
        handler.show_collections()
    
    elif command == 'duplicates':
        handler.show_duplicates()
    
    elif command == 'delete':
        if len(sys.argv) < 3:
            print("❌ Please specify collection name")
            return
        
        collection_name = sys.argv[2]
        force = '--force' in sys.argv
        handler.delete_collection(collection_name, force)
    
    else:
        print(f"❌ Unknown command: {command}")

if __name__ == "__main__":
    main()
