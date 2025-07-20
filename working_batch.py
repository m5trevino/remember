#!/usr/bin/env python3
"""
Working batch processing using the proven manual endpoint
"""
import requests
import json
import time

def batch_process_documents():
    """Process multiple documents using the working manual endpoint"""
    base_url = "http://localhost:8080"
    
    # Get the first 5 documents to test
    docs_to_process = [f"doc_{i:03d}" for i in range(1, 6)]  # doc_001 to doc_005
    
    print(f"🚀 Starting batch processing of {len(docs_to_process)} documents")
    print(f"📋 Using TPA master context and DeepSeek R1 model")
    
    processed = 0
    failed = 0
    
    for i, doc_id in enumerate(docs_to_process, 1):
        print(f"\n🔄 Processing {i}/{len(docs_to_process)}: {doc_id}")
        
        # Use the exact same request that works manually
        payload = {
            "database": "remember_db",
            "files": [doc_id],
            "message": "tpa_defense_analysis - Extract every strategic legal angle supporting your defense under the California Tenant Protection Act (TPA) based on verified testimony.",
            "provider": "deepseek-r1-distill-llama-70b", 
            "api_key": "auto",
            "context_mode": "fresh",
            "master_contexts": ["tpa"]
        }
        
        try:
            response = requests.post(f"{base_url}/api/chat", json=payload, timeout=60)
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    response_text = result.get("response", "")
                    processed += 1
                    print(f"✅ {doc_id}: Success ({len(response_text)} chars)")
                    print(f"   Preview: {response_text[:150]}...")
                else:
                    failed += 1
                    print(f"❌ {doc_id}: Failed - {result.get('error', 'Unknown error')}")
            else:
                failed += 1
                print(f"❌ {doc_id}: HTTP {response.status_code}")
        except Exception as e:
            failed += 1
            print(f"❌ {doc_id}: Exception - {e}")
        
        # Small delay between requests
        time.sleep(2)
    
    print(f"\n🎉 Batch processing complete!")
    print(f"✅ Processed: {processed}/{len(docs_to_process)}")
    print(f"❌ Failed: {failed}/{len(docs_to_process)}")
    print(f"📊 Success rate: {(processed/len(docs_to_process)*100):.1f}%")

if __name__ == "__main__":
    batch_process_documents()