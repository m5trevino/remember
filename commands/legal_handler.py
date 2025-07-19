#!/usr/bin/env python3
"""
🔗 Remember - Legal Handler
Universal legal document processing connecting Remember CLI to Groq infrastructure
"""

import sys
import os
from typing import List, Optional, Dict, Any
from pathlib import Path
import json
from datetime import datetime
import questionary

# Add the groq infrastructure to path
sys.path.append(str(Path.home() / "remember"))

from commands.base_command import BaseCommand
from core.database import get_client, search_extractions

# Import Groq infrastructure
try:
    from groq_client import GroqClient
    from context_manager import ContextStrategy
except ImportError:
    print("❌ Groq infrastructure not found - ensure groq_client.py is in ~/remember/")
    GroqClient = None

class LegalHandler(BaseCommand):
    """Universal legal document analysis handler"""
    
    def __init__(self):
        super().__init__()
        self.groq_client = None
    
    def get_aliases(self) -> List[str]:
        return ["legal", "analyze", "process"]
    
    def execute(self, command_input: str) -> Optional[str]:
        """Execute legal analysis command"""
        if not self._initialize_groq():
            return self.format_error([
                "❌ Groq client initialization failed",
                "Check .env file and groq_client.py in ~/remember/"
            ])
        
        parts = command_input.strip().split()
        
        if len(parts) == 1:
            return self._show_legal_help()
        
        subcommand = parts[1].lower()
        
        if subcommand == "batch":
            return self._batch_process_extractions()
        elif subcommand == "analyze":
            if len(parts) < 3:
                return self._interactive_analyze()
            query = " ".join(parts[2:])
            return self._analyze_specific_content(query)
        elif subcommand == "chat":
            return self._legal_chat_session()
        else:
            return self._show_legal_help()
    
    def _initialize_groq(self) -> bool:
        """Initialize Groq client with error handling"""
        if GroqClient is None:
            return False
        
        try:
            self.groq_client = GroqClient()
            # Test connection with minimal request
            success, response, debug = self.groq_client.simple_chat(
                "Test", "Say OK"
            )
            return success
        except Exception as e:
            print(f"❌ Groq initialization error: {e}")
            return False
    
    def _batch_process_extractions(self) -> str:
        """Process all extracted documents through user-defined analysis"""
        try:
            # Get all extraction sessions
            client = get_client()
            collections = client.list_collections()
            
            extraction_collections = [
                col for col in collections 
                if col.name.startswith("extraction_")
            ]
            
            if not extraction_collections:
                return self.format_warning([
                    "No extraction collections found",
                    "Run 'import <json_file>' first to load extracted documents"
                ])
            
            # User defines the analysis prompt
            analysis_prompt = questionary.text(
                "📝 Enter analysis prompt for all documents:"
            ).ask()
            
            if not analysis_prompt:
                return self.format_warning(["Analysis cancelled"])
            
            # Processing options
            processing_mode = questionary.select(
                "🔄 Processing mode:",
                choices=[
                    "Individual analysis (one prompt per document)",
                    "Batch summary (process all, then summarize)",
                    "Progressive analysis (build context as we go)"
                ]
            ).ask()
            
            if not processing_mode:
                return self.format_warning(["Processing cancelled"])
            
            total_processed = 0
            results = []
            
            print(f"\n🚀 Starting batch processing with mode: {processing_mode}")
            
            for collection_info in extraction_collections:
                collection = client.get_collection(collection_info.name)
                data = collection.get()
                
                if not data["documents"]:
                    continue
                
                collection_results = self._process_collection(
                    collection_info.name,
                    data["documents"],
                    data["metadatas"],
                    analysis_prompt,
                    processing_mode
                )
                
                results.extend(collection_results)
                total_processed += len(data["documents"])
            
            # Save results
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            results_file = Path.home() / "remember" / f"legal_batch_{timestamp}.json"
            
            with open(results_file, 'w') as f:
                json.dump({
                    'analysis_prompt': analysis_prompt,
                    'processing_mode': processing_mode,
                    'total_documents': total_processed,
                    'timestamp': timestamp,
                    'results': results
                }, f, indent=2)
            
            success_msgs = [
                f"🏛️ Batch Legal Processing Complete",
                f"📋 Documents Processed: {total_processed}",
                f"🔄 Mode: {processing_mode}",
                f"💾 Results saved: {results_file.name}",
                "",
                "💡 Use 'legal analyze' for individual document analysis"
            ]
            
            return self.format_success(success_msgs)
            
        except Exception as e:
            return self.format_error([f"Batch processing failed: {str(e)}"])
    
    def _process_collection(self, 
                          collection_name: str, 
                          documents: List[str], 
                          metadatas: List[Dict],
                          analysis_prompt: str,
                          processing_mode: str) -> List[Dict]:
        """Process documents based on selected mode"""
        results = []
        
        if "Individual" in processing_mode:
            # Process each document individually
            for i, (doc, metadata) in enumerate(zip(documents, metadatas)):
                print(f"🔍 Processing {i+1}/{len(documents)}: {metadata.get('title', 'Unknown')[:50]}...")
                
                analysis = self._run_analysis(doc, analysis_prompt)
                if analysis:
                    results.append({
                        'collection': collection_name,
                        'document_index': i,
                        'metadata': metadata,
                        'analysis': analysis,
                        'timestamp': datetime.now().isoformat()
                    })
        
        elif "Batch summary" in processing_mode:
            # Combine all documents, then analyze
            combined_content = "\n\n---DOCUMENT SEPARATOR---\n\n".join(documents)
            
            batch_prompt = f"{analysis_prompt}\n\nAnalyze the following combined documents:\n\n{combined_content}"
            
            analysis = self._run_analysis(batch_prompt, "Provide comprehensive analysis of all documents.")
            if analysis:
                results.append({
                    'collection': collection_name,
                    'type': 'batch_summary',
                    'document_count': len(documents),
                    'analysis': analysis,
                    'timestamp': datetime.now().isoformat()
                })
        
        elif "Progressive" in processing_mode:
            # Build context progressively
            progressive_context = ""
            
            for i, (doc, metadata) in enumerate(zip(documents, metadatas)):
                print(f"🔄 Progressive analysis {i+1}/{len(documents)}: {metadata.get('title', 'Unknown')[:50]}...")
                
                context_prompt = f"{analysis_prompt}\n\nPrevious analysis context:\n{progressive_context}\n\nNew document to analyze:\n{doc}"
                
                analysis = self._run_analysis(context_prompt, "Analyze this document in context of previous analysis.")
                if analysis:
                    progressive_context += f"\n\nDocument {i+1} Analysis: {analysis}"
                    
                    results.append({
                        'collection': collection_name,
                        'document_index': i,
                        'metadata': metadata,
                        'progressive_analysis': analysis,
                        'cumulative_context': len(progressive_context),
                        'timestamp': datetime.now().isoformat()
                    })
        
        return results
    
    def _run_analysis(self, content: str, prompt: str) -> Optional[str]:
        """Run analysis using Groq infrastructure"""
        if not self.groq_client:
            return None
        
        try:
            success, responses, debugs = self.groq_client.auto_process_content(
                content=content,
                system_prompt=prompt
            )
            
            if success and responses:
                return "\n\n".join(responses)
            else:
                print(f"⚠️ Analysis failed: {debugs}")
                return None
                
        except Exception as e:
            print(f"❌ Analysis error: {e}")
            return None
    
    def _interactive_analyze(self) -> str:
        """Interactive analysis mode"""
        try:
            # Search for documents
            query = questionary.text("🔍 Search for documents to analyze:").ask()
            if not query:
                return self.format_warning(["Search cancelled"])
            
            # Get search results
            search_results = search_extractions(query, limit=10)
            
            if not search_results:
                return self.format_warning([f"No documents found for: {query}"])
            
            # Show results for selection
            choices = []
            for i, result in enumerate(search_results):
                metadata = result.get('metadata', {})
                title = metadata.get('title', 'Unknown')
                url = metadata.get('url', '')
                choices.append(f"{i+1}. {title[:60]} - {url[:40]}")
            
            selected = questionary.checkbox(
                "📋 Select documents to analyze:",
                choices=choices
            ).ask()
            
            if not selected:
                return self.format_warning(["No documents selected"])
            
            # Get analysis prompt
            analysis_prompt = questionary.text(
                "📝 Enter analysis prompt:"
            ).ask()
            
            if not analysis_prompt:
                return self.format_warning(["Analysis cancelled"])
            
            # Process selected documents
            results = []
            for selection in selected:
                index = int(selection.split('.')[0]) - 1
                result = search_results[index]
                
                doc_content = result.get('document', '')
                metadata = result.get('metadata', {})
                
                print(f"🔍 Analyzing: {metadata.get('title', 'Unknown')[:50]}...")
                
                analysis = self._run_analysis(doc_content, analysis_prompt)
                if analysis:
                    results.append({
                        'title': metadata.get('title', 'Unknown'),
                        'url': metadata.get('url', ''),
                        'analysis': analysis
                    })
            
            # Format output
            output_msgs = [
                f"📊 Analysis Results",
                f"📋 Documents analyzed: {len(results)}",
                f"📝 Prompt: {analysis_prompt}",
                ""
            ]
            
            for i, result in enumerate(results, 1):
                output_msgs.extend([
                    f"#{i} {result['title'][:60]}",
                    f"🔗 {result['url']}",
                    f"📄 {result['analysis'][:300]}...",
                    ""
                ])
            
            return self.format_data(output_msgs)
            
        except Exception as e:
            return self.format_error([f"Interactive analysis failed: {str(e)}"])
    
    def _analyze_specific_content(self, query: str) -> str:
        """Analyze documents matching specific query"""
        try:
            search_results = search_extractions(query, limit=5)
            
            if not search_results:
                return self.format_warning([f"No documents found for: {query}"])
            
            # Simple analysis with default prompt
            default_prompt = "Analyze this legal document and provide key insights, important details, and potential legal implications."
            
            results = []
            for result in search_results:
                doc_content = result.get('document', '')
                metadata = result.get('metadata', {})
                
                analysis = self._run_analysis(doc_content, default_prompt)
                if analysis:
                    results.append({
                        'title': metadata.get('title', 'Unknown'),
                        'analysis': analysis[:200] + "..."
                    })
            
            output_msgs = [
                f"📊 Quick Analysis: {query}",
                f"📋 Documents found: {len(results)}",
                ""
            ]
            
            for i, result in enumerate(results, 1):
                output_msgs.extend([
                    f"#{i} {result['title'][:60]}",
                    f"📄 {result['analysis']}",
                    ""
                ])
            
            return self.format_data(output_msgs)
            
        except Exception as e:
            return self.format_error([f"Analysis failed: {str(e)}"])
    
    def _legal_chat_session(self) -> str:
        """Start interactive chat session with legal context"""
        try:
            print("\n💬 Legal Chat Session Started")
            print("Type 'exit' to end session")
            
            conversation_history = []
            
            while True:
                user_input = input("\nlegal> ")
                
                if user_input.lower() in ['exit', 'quit']:
                    break
                
                conversation_history.append({"role": "user", "content": user_input})
                
                # Use conversation mode
                success, response, debug = self.groq_client.conversation_chat(
                    messages=conversation_history
                )
                
                if success:
                    print(f"\n📄 {response}")
                    conversation_history.append({"role": "assistant", "content": response})
                else:
                    print(f"❌ Error: {debug}")
            
            return self.format_success(["💬 Chat session ended"])
            
        except Exception as e:
            return self.format_error([f"Chat session failed: {str(e)}"])
    
    def _show_legal_help(self) -> str:
        """Show legal handler help"""
        help_msgs = [
            "🏛️ Legal Handler Commands",
            "",
            "legal batch                Process all extracted documents",
            "legal analyze [query]      Analyze specific documents",
            "legal chat                 Interactive chat session",
            "",
            "Examples:",
            "  legal batch              # Batch process with custom prompt",
            "  legal analyze service    # Quick analysis of service docs",
            "  legal chat               # Start chat session"
        ]
        
        return self.format_info(help_msgs)
    
    def get_help(self) -> str:
        """Return help text"""
        return "Universal legal document analysis with Groq integration"