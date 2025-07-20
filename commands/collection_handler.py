#!/usr/bin/env python3
"""
🗂️ Remember CLI - Collection Command Handler
Integrate collection management into the main CLI system
"""

from commands.base_command import BaseCommand
from core.database import get_client
from typing import List, Dict, Any

class CollectionHandler(BaseCommand):
    """Handle collection management commands"""
    
    def __init__(self):
        super().__init__()
        self.client = get_client()
    
    def get_commands(self) -> Dict[str, str]:
        return {
            'collections': 'List all collections',
            'collection list': 'List all collections with details',
            'collection delete <name>': 'Delete a collection',
            'collection duplicates': 'Find duplicate collections and content',
            'collection merge <source> <target>': 'Merge two collections',
            'collection info <name>': 'Show detailed collection information'
        }
    
    def handle_command(self, command: str, args: List[str]) -> bool:
        """Handle collection-related commands"""
        
        if command in ['collections', 'collection', 'coll']:
            if not args:
                self._list_collections()
                return True
            
            subcommand = args[0]
            
            if subcommand == 'list':
                self._list_collections()
                return True
            
            elif subcommand == 'delete':
                if len(args) < 2:
                    print("❌ Usage: collection delete <collection_name>")
                    return False
                collection_name = args[1]
                force = '--force' in args
                return self._delete_collection(collection_name, force)
            
            elif subcommand == 'duplicates':
                self._show_duplicates()
                return True
            
            elif subcommand == 'info':
                if len(args) < 2:
                    print("❌ Usage: collection info <collection_name>")
                    return False
                collection_name = args[1]
                return self._show_collection_info(collection_name)
            
            elif subcommand == 'merge':
                if len(args) < 3:
                    print("❌ Usage: collection merge <source> <target>")
                    return False
                source = args[1]
                target = args[2]
                return self._merge_collections(source, target)
        
        return False
    
    def _list_collections(self):
        """List all collections"""
        try:
            collections = self.client.list_collections()
            
            print("🗂️  REMEMBER DATABASE COLLECTIONS")
            print("=" * 80)
            print(f"{'#':<3} {'Name':<45} {'Docs':<8} {'Type':<12} {'Created'}")
            print("-" * 80)
            
            for i, collection in enumerate(collections, 1):
                col_data = self.client.get_collection(collection.name)
                count = col_data.count()
                
                # Determine type
                col_type = 'extraction' if 'extraction' in collection.name else 'other'
                
                # Get creation date if available
                if count > 0:
                    sample = col_data.get(limit=1, include=['metadatas'])
                    created = sample['metadatas'][0].get('created', 'unknown') if sample['metadatas'] else 'unknown'
                else:
                    created = 'empty'
                
                print(f"{i:<3} {collection.name:<45} {count:<8} {col_type:<12} {created}")
            
            print("-" * 80)
            total_docs = sum(self.client.get_collection(c.name).count() for c in collections)
            print(f"Total: {len(collections)} collections, {total_docs} documents")
            
        except Exception as e:
            print(f"❌ Error listing collections: {e}")
    
    def _delete_collection(self, collection_name: str, force: bool = False) -> bool:
        """Delete a collection"""
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
    
    def _show_duplicates(self):
        """Show duplicate analysis"""
        try:
            collections = self.client.list_collections()
            
            print("🔍 DUPLICATE ANALYSIS")
            print("=" * 60)
            
            # Find similar collections
            extraction_collections = []
            for collection in collections:
                if 'extraction' in collection.name:
                    col_data = self.client.get_collection(collection.name)
                    count = col_data.count()
                    extraction_collections.append({
                        'name': collection.name,
                        'count': count
                    })
            
            if len(extraction_collections) > 1:
                print("📂 SIMILAR COLLECTIONS (likely duplicates):")
                for col in extraction_collections:
                    print(f"  - {col['name']} ({col['count']} docs)")
                print()
                
                print("💡 RECOMMENDATION:")
                # Find the collection with most documents
                largest = max(extraction_collections, key=lambda x: x['count'])
                print(f"  Keep: {largest['name']} (has most documents)")
                for col in extraction_collections:
                    if col['name'] != largest['name']:
                        print(f"  Delete: {col['name']}")
                print()
            
            # Check for duplicate content within collections
            duplicate_found = False
            for collection in collections:
                col_data = self.client.get_collection(collection.name)
                data = col_data.get(include=['metadatas'])
                
                # Track titles and URLs
                seen_titles = set()
                seen_urls = set()
                duplicate_titles = []
                duplicate_urls = []
                
                for metadata in data['metadatas']:
                    title = metadata.get('title', '[no-title]')
                    url = metadata.get('url', '')
                    
                    if title in seen_titles and title not in duplicate_titles:
                        duplicate_titles.append(title)
                    seen_titles.add(title)
                    
                    if url and url in seen_urls and url not in duplicate_urls:
                        duplicate_urls.append(url)
                    seen_urls.add(url)
                
                if duplicate_titles:
                    print(f"📄 DUPLICATE TITLES in {collection.name}:")
                    for title in duplicate_titles:
                        print(f"    - {title}")
                    duplicate_found = True
                
                if duplicate_urls:
                    print(f"🔗 DUPLICATE URLS in {collection.name}:")
                    for url in duplicate_urls:
                        print(f"    - {url}")
                    duplicate_found = True
            
            if not duplicate_found and len(extraction_collections) <= 1:
                print("✅ No duplicates found")
                
        except Exception as e:
            print(f"❌ Error analyzing duplicates: {e}")
    
    def _show_collection_info(self, collection_name: str) -> bool:
        """Show detailed information about a collection"""
        try:
            collections = [c.name for c in self.client.list_collections()]
            if collection_name not in collections:
                print(f"❌ Collection '{collection_name}' not found")
                return False
            
            col_data = self.client.get_collection(collection_name)
            count = col_data.count()
            
            print(f"📊 COLLECTION INFORMATION: {collection_name}")
            print("=" * 60)
            print(f"Documents: {count}")
            
            if count > 0:
                # Get sample data
                sample = col_data.get(limit=5, include=['metadatas', 'documents'])
                
                print(f"Sample documents:")
                for i, (doc_id, metadata, content) in enumerate(zip(sample['ids'], sample['metadatas'], sample['documents'])):
                    title = metadata.get('title', '[no-title]')
                    url = metadata.get('url', '[no-url]')
                    content_length = len(content) if content else 0
                    
                    print(f"  {i+1}. {title}")
                    print(f"     ID: {doc_id}")
                    print(f"     URL: {url}")
                    print(f"     Content: {content_length} chars")
                    print()
            
            return True
            
        except Exception as e:
            print(f"❌ Error getting collection info: {e}")
            return False
    
    def _merge_collections(self, source: str, target: str) -> bool:
        """Merge source collection into target collection"""
        try:
            collections = [c.name for c in self.client.list_collections()]
            
            if source not in collections:
                print(f"❌ Source collection '{source}' not found")
                return False
            
            if target not in collections:
                print(f"❌ Target collection '{target}' not found")
                return False
            
            print(f"🔄 Merging '{source}' into '{target}'...")
            
            # Get source data
            source_col = self.client.get_collection(source)
            source_data = source_col.get(include=['documents', 'metadatas'])
            
            # Add to target collection
            target_col = self.client.get_collection(target)
            
            # Update IDs to avoid conflicts
            new_ids = []
            for i, old_id in enumerate(source_data['ids']):
                new_id = f"merged_{old_id}_{i}"
                new_ids.append(new_id)
            
            target_col.add(
                documents=source_data['documents'],
                metadatas=source_data['metadatas'],
                ids=new_ids
            )
            
            print(f"✅ Merged {len(source_data['ids'])} documents")
            print(f"🗑️  Now delete source collection: collection delete {source}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error merging collections: {e}")
            return False
