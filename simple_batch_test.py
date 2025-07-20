#!/usr/bin/env python3
import requests
import json
import time

# Test the working manual processing in a simple loop
def test_batch_processing():
    base_url = "http://localhost:8080"
    
    # Test with just a few documents first
    test_docs = ["doc_001", "doc_002", "doc_003"]
    
    for doc_id in test_docs:
        print(f"🔄 Processing {doc_id}...")
        
        # Use the exact same request that works manually
        payload = {
            "database": "remember_db",
            "files": [doc_id],
            "message": "tpa_defense_analysis",
            "provider": "deepseek-r1-distill-llama-70b",
            "api_key": "auto",
            "context_mode": "fresh",
            "master_contexts": ["tpa"]
        }
        
        try:
            response = requests.post(f"{base_url}/api/chat", json=payload, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    print(f"✅ {doc_id}: {len(result.get('response', ''))} chars")
                else:
                    print(f"❌ {doc_id}: Failed - {result}")
            else:
                print(f"❌ {doc_id}: HTTP {response.status_code}")
        except Exception as e:
            print(f"❌ {doc_id}: Error - {e}")
        
        time.sleep(1)  # Small delay between requests

if __name__ == "__main__":
    test_batch_processing()