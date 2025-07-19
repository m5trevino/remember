@app.get("/api/view_file", response_class=HTMLResponse)
async def view_file_content(file_id: str = Query(...), database: str = Query(...)):
    """View file content in popup window - FIXED VERSION"""
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
        
        # Clean up content for display
        display_content = file_content.replace('<', '&lt;').replace('>', '&gt;')
        
        # Get word/character counts
        word_count = len(file_content.split())
        char_count = len(file_content)
        
        # Return formatted HTML viewer
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>File Viewer - {file_metadata.get('title', file_id)}</title>
    <style>
        body {{ 
            font-family: 'Consolas', 'Courier New', monospace; 
            background: #0a0a0a; color: #00ff00; 
            padding: 20px; line-height: 1.6; 
            margin: 0;
        }}
        
        .header {{ 
            background: #1a1a1a; padding: 15px; 
            border: 1px solid #333; border-radius: 4px; 
            margin-bottom: 20px; position: sticky; top: 0;
            z-index: 100;
        }}
        
        .file-title {{ 
            color: #00ff00; font-size: 16px; 
            font-weight: bold; margin-bottom: 10px; 
        }}
        
        .file-meta {{ 
            color: #888; font-size: 11px; 
            display: grid; grid-template-columns: 1fr 1fr 1fr; 
            gap: 15px; 
        }}
        
        .content-wrapper {{
            background: #111; border: 1px solid #333; 
            border-radius: 4px; padding: 0;
            max-height: calc(100vh - 200px); 
            overflow: hidden;
        }}
        
        .content-header {{
            background: #222; padding: 10px 15px;
            border-bottom: 1px solid #333;
            font-size: 12px; color: #888;
            display: flex; justify-content: space-between;
        }}
        
        .content {{ 
            padding: 20px; 
            white-space: pre-wrap; word-wrap: break-word; 
            overflow-y: auto; 
            height: calc(100vh - 240px);
            font-size: 12px;
            line-height: 1.5;
        }}
        
        .actions {{ 
            position: fixed; top: 10px; right: 10px; 
            display: flex; gap: 8px; z-index: 200;
        }}
        
        .btn {{ 
            background: #333; border: 1px solid #555; 
            color: #ccc; padding: 6px 10px; 
            border-radius: 3px; cursor: pointer; 
            font-size: 10px; font-family: inherit;
        }}
        
        .btn:hover {{ background: #444; }}
        .btn.primary {{ background: #0066cc; color: white; }}
        .btn.success {{ background: #006600; color: white; }}
        
        .metadata-grid {{
            display: grid;
            grid-template-columns: auto 1fr;
            gap: 5px 15px;
            align-items: center;
        }}
        
        .meta-label {{
            font-weight: bold;
            color: #ccc;
        }}
        
        .meta-value {{
            color: #00ff00;
        }}
        
        .scroll-indicator {{
            position: fixed; right: 20px; top: 50%;
            transform: translateY(-50%);
            background: rgba(0,0,0,0.7);
            padding: 5px 8px;
            border-radius: 3px;
            font-size: 10px;
            color: #888;
        }}
    </style>
</head>
<body>
    <div class="actions">
        <button class="btn success" onclick="copyToClipboard()">📋 Copy</button>
        <button class="btn" onclick="window.print()">🖨️ Print</button>
        <button class="btn primary" onclick="window.close()">❌ Close</button>
    </div>
    
    <div class="header">
        <div class="file-title">{file_metadata.get('title', file_id)}</div>
        <div class="metadata-grid">
            <span class="meta-label">ID:</span>
            <span class="meta-value">{file_id}</span>
            
            <span class="meta-label">Database:</span>
            <span class="meta-value">{database}</span>
            
            <span class="meta-label">Type:</span>
            <span class="meta-value">{file_metadata.get('type', 'Unknown')}</span>
            
            <span class="meta-label">Words:</span>
            <span class="meta-value">{word_count:,}</span>
            
            <span class="meta-label">Characters:</span>
            <span class="meta-value">{char_count:,}</span>
            
            <span class="meta-label">Rating:</span>
            <span class="meta-value">{file_metadata.get('rating', 'N/A')}/5</span>
        </div>
    </div>
    
    <div class="content-wrapper">
        <div class="content-header">
            <span>📄 Document Content ({word_count:,} words, {char_count:,} characters)</span>
            <span>Scroll to read full content ↓</span>
        </div>
        <div class="content" id="file-content">{display_content}</div>
    </div>
    
    <div class="scroll-indicator" id="scroll-indicator">
        Scroll: 0%
    </div>
    
    <script>
        function copyToClipboard() {{
            const content = document.getElementById('file-content').textContent;
            navigator.clipboard.writeText(content).then(() => {{
                const btn = event.target;
                const originalText = btn.textContent;
                btn.textContent = '✅ Copied!';
                btn.style.background = '#006600';
                setTimeout(() => {{
                    btn.textContent = originalText;
                    btn.style.background = '#333';
                }}, 2000);
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
        
        // Scroll indicator
        const contentDiv = document.getElementById('file-content');
        const scrollIndicator = document.getElementById('scroll-indicator');
        
        contentDiv.addEventListener('scroll', () => {{
            const scrollPercent = Math.round(
                (contentDiv.scrollTop / (contentDiv.scrollHeight - contentDiv.clientHeight)) * 100
            );
            scrollIndicator.textContent = `Scroll: ${{scrollPercent || 0}}%`;
        }});
        
        // Auto-focus for easier reading
        window.addEventListener('load', () => {{
            contentDiv.focus();
        }});
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {{
            if (e.ctrlKey && e.key === 'c') {{
                copyToClipboard();
                e.preventDefault();
            }}
            if (e.key === 'Escape') {{
                window.close();
            }}
        }});
    </script>
</body>
</html>"""
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File viewer error: {e}")

@app.post("/api/batch_process")
async def batch_process_documents(request: BatchProcessRequest):
    """Batch process all documents in database - FIXED VERSION WITH CONTENT LIMITS"""
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
                    
                    # Calculate content metrics
                    word_count = len(doc.split())
                    char_count = len(doc)
                    
                    all_documents.append({
                        "content": doc,
                        "word_count": word_count,
                        "char_count": char_count,
                        "metadata": metadata,
                        "collection": collection.name,
                        "id": data["ids"][i]
                    })
        
        if not all_documents:
            return {"result": "❌ No documents found in database"}
        
        print(f"📋 Total documents to process: {len(all_documents)}")
        
        # Process based on mode
        if request.processing_mode == "individual":
            # Process each document individually with content-aware limits
            results = []
            
            for i, doc in enumerate(all_documents):
                doc_title = doc['metadata'].get('title', doc['id'])
                print(f"📄 Processing {i+1}/{len(all_documents)}: {doc_title}")
                
                # Determine appropriate response length based on source content
                source_words = doc['word_count']
                max_response_words = min(source_words, 1000)  # Cap at 1000 words max
                
                prompt = f"""ANALYSIS PROMPT: {request.analysis_prompt}

DOCUMENT TITLE: {doc_title}
DOCUMENT LENGTH: {source_words} words, {doc['char_count']} characters

DOCUMENT CONTENT:
{doc['content']}

IMPORTANT: This document has {source_words} words. Your analysis should be SHORTER than the original document. 
Aim for a maximum of {max_response_words} words in your response. Be concise and focused."""
                
                try:
                    success, response, debug = groq_client.simple_chat(
                        message=prompt,
                        system_prompt=f"You are an expert legal analyst. Provide concise analysis in maximum {max_response_words} words. Be more concise than the source material."
                    )
                    
                    if success:
                        # Check response length
                        response_words = len(response.split())
                        status_emoji = "✅" if response_words <= source_words else "⚠️"
                        
                        results.append({
                            "document": doc_title,
                            "source_words": source_words,
                            "response_words": response_words,
                            "analysis": response,
                            "status": f"{status_emoji} Success"
                        })
                    else:
                        results.append({
                            "document": doc_title,
                            "source_words": source_words,
                            "response_words": 0,
                            "analysis": f"❌ Analysis failed: {debug}",
                            "status": "❌ Failed"
                        })
                        
                except Exception as e:
                    results.append({
                        "document": doc_title,
                        "source_words": source_words,
                        "response_words": 0,
                        "analysis": f"❌ Error: {str(e)}",
                        "status": "❌ Error"
                    })
            
            # Format results with length comparison
            successful = len([r for r in results if r["status"].startswith("✅")])
            appropriate_length = len([r for r in results if r.get("response_words", 0) <= r.get("source_words", 0)])
            
            result_text = f"""📊 BATCH PROCESSING COMPLETE

📋 Documents Processed: {len(results)}
✅ Successful: {successful}
📏 Appropriate Length: {appropriate_length}/{successful}
❌ Failed: {len(results) - successful}

📄 INDIVIDUAL ANALYSIS RESULTS:

"""
            
            for i, result in enumerate(results, 1):
                length_indicator = ""
                if result.get("response_words", 0) > 0:
                    ratio = result["response_words"] / max(result["source_words"], 1)
                    if ratio <= 0.5:
                        length_indicator = "📝 Concise"
                    elif ratio <= 1.0:
                        length_indicator = "📄 Appropriate"
                    else:
                        length_indicator = "📚 Too Long"
                
                result_text += f"""#{i} {result['status']} {result['document']}
Source: {result['source_words']} words | Response: {result.get('response_words', 0)} words {length_indicator}

{result['analysis'][:800]}{'...' if len(result['analysis']) > 800 else ''}

{'='*80}

"""
            
            return {"result": result_text}
            
        elif request.processing_mode == "batch":
            # Combine documents for single analysis with length awareness
            print("🔄 Processing in batch mode...")
            
            # Calculate total content size
            total_words = sum(doc['word_count'] for doc in all_documents)
            
            # Create summary of all documents (limited to prevent overflow)
            doc_summaries = []
            for doc in all_documents[:30]:  # Limit to 30 docs
                doc_title = doc['metadata'].get('title', doc['id'])
                # Use proportional preview based on document size
                preview_chars = min(500, doc['char_count'] // 2)
                doc_preview = doc['content'][:preview_chars]
                doc_summaries.append(f"Document: {doc_title} ({doc['word_count']} words)\nContent: {doc_preview}\n")
            
            combined_summary = "\n---DOCUMENT SEPARATOR---\n".join(doc_summaries)
            
            # Set appropriate response length
            max_batch_words = min(total_words // 2, 2000)  # Half the source length, max 2000 words
            
            prompt = f"""BATCH ANALYSIS REQUEST: {request.analysis_prompt}

DOCUMENTS TO ANALYZE: {len(all_documents)} documents, {total_words:,} total words

{combined_summary}

IMPORTANT: Provide comprehensive but concise batch analysis. 
Target length: Maximum {max_batch_words} words (source material has {total_words:,} words).
Focus on key findings and patterns across all documents."""
            
            try:
                success, response, debug = groq_client.simple_chat(
                    message=prompt,
                    system_prompt=f"You are an expert legal analyst. Provide comprehensive batch analysis in maximum {max_batch_words} words."
                )
                
                if success:
                    response_words = len(response.split())
                    length_status = "📝 Appropriate" if response_words <= total_words else "📚 Longer than source"
                    
                    result_text = f"""📊 BATCH ANALYSIS COMPLETE

📋 Documents Analyzed: {len(all_documents)}
📄 Total Source Words: {total_words:,}
📄 Analysis Words: {response_words:,} {length_status}
🔄 Processing Mode: Batch Summary

📄 COMPREHENSIVE ANALYSIS:

{response}

{'='*80}

💡 This analysis covers {len(all_documents)} documents from the {request.database} database.
Length Ratio: {response_words/max(total_words, 1):.2f} (analysis vs source)
"""
                    return {"result": result_text}
                else:
                    return {"result": f"❌ Batch analysis failed: {debug}"}
                    
            except Exception as e:
                return {"result": f"❌ Batch processing error: {str(e)}"}
        
        else:  # progressive mode with length control
            print("🔄 Processing in progressive mode...")
            
            progressive_context = ""
            result_text = f"""📊 PROGRESSIVE ANALYSIS

📋 Documents: {len(all_documents)}
🔄 Mode: Progressive Context Building

📄 PROGRESSIVE RESULTS:

"""
            
            for i, doc in enumerate(all_documents[:15]):  # Limit to 15 for progressive
                doc_title = doc['metadata'].get('title', doc['id'])
                print(f"📄 Progressive analysis {i+1}/15: {doc_title}")
                
                # Limit content and response based on document size
                content_limit = min(1000, doc['char_count'])
                max_response_words = min(doc['word_count'], 300)  # Max 300 words per doc
                
                context_prompt = f"""ANALYSIS PROMPT: {request.analysis_prompt}

PREVIOUS ANALYSIS CONTEXT (last 1000 chars):
{progressive_context[-1000:]}  

NEW DOCUMENT TO ANALYZE:
Title: {doc_title} ({doc['word_count']} words)
Content: {doc['content'][:content_limit]}

Analyze this document in context of previous analysis. 
Keep response under {max_response_words} words."""
                
                try:
                    success, response, debug = groq_client.simple_chat(
                        message=context_prompt,
                        system_prompt=f"Analyze concisely (max {max_response_words} words) in context of previous analysis."
                    )
                    
                    if success:
                        response_words = len(response.split())
                        progressive_context += f"\n\nDocument {i+1} Analysis: {response}"
                        
                        # Add to results with length info
                        length_indicator = "📝" if response_words <= doc['word_count'] else "📚"
                        result_text += f"""#{i+1} ✅ {doc_title} {length_indicator}
Source: {doc['word_count']} words | Analysis: {response_words} words
{response[:400]}{'...' if len(response) > 400 else ''}

"""
                    else:
                        result_text += f"#{i+1} ❌ {doc_title}\nAnalysis failed: {debug}\n\n"
                        
                except Exception as e:
                    result_text += f"#{i+1} ❌ {doc_title}\nError: {str(e)}\n\n"
            
            result_text += f"""
{'='*80}

💡 Progressive analysis maintained concise responses across {min(15, len(all_documents))} documents.
📝 = Analysis shorter than source | 📚 = Analysis longer than source
"""
            
            return {"result": result_text}
            
    except Exception as e:
        print(f"❌ Batch processing error: {e}")
        raise HTTPException(status_code=500, detail=f"Batch processing error: {e}")