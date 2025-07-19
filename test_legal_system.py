#!/usr/bin/env python3
"""Test legal system integration"""

import sys
import os
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent.absolute()))

def test_imports():
    """Test all critical imports"""
    try:
        print("🧪 Testing imports...")
        
        # Test infrastructure imports
        from groq_client import GroqClient
        from request_router import RequestRouter
        from api_key_manager import APIKeyManager
        from proxy_manager import ProxyManager
        from context_manager import ContextManager
        
        print("✅ Groq infrastructure imports successful")
        
        # Test command imports
        from commands.legal_handler import LegalHandler
        from commands.command_registry import CommandRegistry
        
        print("✅ Command system imports successful")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def test_api_keys():
    """Test API key loading"""
    try:
        from api_key_manager import APIKeyManager
        
        manager = APIKeyManager()
        key_count = len(manager.api_keys)
        
        if key_count > 0:
            print(f"✅ Loaded {key_count} API keys")
            return True
        else:
            print("❌ No API keys loaded - check .env file")
            return False
            
    except Exception as e:
        print(f"❌ API key test failed: {e}")
        return False

def test_groq_connection():
    """Test Groq connection"""
    try:
        from groq_client import GroqClient
        
        client = GroqClient()
        success, response, debug = client.simple_chat("Test", "Say OK")
        
        if success:
            print("✅ Groq connection successful")
            return True
        else:
            print(f"❌ Groq connection failed: {debug}")
            return False
            
    except Exception as e:
        print(f"❌ Groq test failed: {e}")
        return False

def test_legal_handler():
    """Test legal handler"""
    try:
        from commands.legal_handler import LegalHandler
        
        handler = LegalHandler()
        help_output = handler.get_help()
        
        if help_output:
            print("✅ Legal handler initialized")
            return True
        else:
            print("❌ Legal handler initialization failed")
            return False
            
    except Exception as e:
        print(f"❌ Legal handler test failed: {e}")
        return False

if __name__ == "__main__":
    print("\n🧪 LEGAL SYSTEM INTEGRATION TEST\n")
    
    tests = [
        ("Import Test", test_imports),
        ("API Key Test", test_api_keys),
        ("Groq Connection", test_groq_connection),
        ("Legal Handler", test_legal_handler)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}:")
        if test_func():
            passed += 1
    
    print(f"\n📊 TEST RESULTS: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All tests passed! Legal AI system is ready!")
    else:
        print("⚠️  Some tests failed. Check configuration and dependencies.")
