async def batch_process_generator(request: BatchProcessRequest):
    """Generator for streaming batch processing results - using working manual endpoint"""
    try:
        print(f"🚀 Starting batch_process_generator with simple approach")
        print(f"📋 Request: {request}")
        
        # Fix selected_files if it's a string instead of list
        if isinstance(request.selected_files, str):
            try:
                request.selected_files = json.loads(request.selected_files)
            except:
                request.selected_files = [request.selected_files]
        
        if not request.selected_files:
            error_data = {"type": "error", "error": "No selected documents found", "success": False}
            yield f"data: {json.dumps(error_data)}\n\n"
            return
        
        print(f"🔍 Processing {len(request.selected_files)} documents")
        
        processed_count = 0
        failed_count = 0
        
        for i, doc_id in enumerate(request.selected_files, 1):
            try:
                print(f"🔄 Processing document {i}/{len(request.selected_files)}: {doc_id}")
                
                # Create ChatRequest exactly like the working manual processing
                chat_request = ChatRequest(
                    database=request.database,
                    files=[doc_id],  # Single document like manual processing
                    message=request.analysis_prompt,
                    provider=request.provider,
                    api_key="auto",
                    context_mode="fresh",
                    master_contexts=[request.master_context] if request.master_context else []
                )
                
                # Call the working chat endpoint internally
                result = await chat_with_files(chat_request)
                
                if result.get("success"):
                    response = result.get("response", "")
                    processed_count += 1
                    
                    # Save to project if specified
                    if hasattr(request, 'project_name') and request.project_name:
                        from core.database import save_llm_response
                        save_success = save_llm_response(request.project_name, doc_id, response)
                        progress_data = {"type": "success", "message": f"✅ {doc_id}: Analysis complete and saved", "progress": f"{i}/{len(request.selected_files)}"}
                    else:
                        progress_data = {"type": "success", "message": f"✅ {doc_id}: Analysis complete", "progress": f"{i}/{len(request.selected_files)}"}
                    
                    print(f"✅ {doc_id}: Success - {len(response)} chars")
                else:
                    failed_count += 1
                    error_msg = result.get("error", "Unknown error")
                    progress_data = {"type": "error", "message": f"❌ {doc_id}: {error_msg}", "progress": f"{i}/{len(request.selected_files)}"}
                    print(f"❌ {doc_id}: Failed - {error_msg}")
                
                yield f"data: {json.dumps(progress_data)}\n\n"
                
            except Exception as e:
                failed_count += 1
                error_data = {"type": "error", "message": f"❌ Error processing {doc_id}: {str(e)}", "progress": f"{i}/{len(request.selected_files)}"}
                yield f"data: {json.dumps(error_data)}\n\n"
                print(f"❌ Exception processing {doc_id}: {e}")
                continue
        
        # Stream final summary
        final_summary = {
            "type": "complete",
            "message": f"✅ Batch complete! Processed: {processed_count}/{len(request.selected_files)} ({(processed_count/len(request.selected_files)*100):.1f}% success)",
            "processed": processed_count,
            "failed": failed_count,
            "total": len(request.selected_files)
        }
        yield f"data: {json.dumps(final_summary)}\n\n"
        
    except Exception as e:
        error_data = {"type": "error", "error": f"Critical batch processing error: {str(e)}", "success": False}
        yield f"data: {json.dumps(error_data)}\n\n"
        print(f"❌ Critical batch processing error: {e}")
        import traceback
        traceback.print_exc()