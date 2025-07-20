#!/usr/bin/env python3
"""
🦚 Peacock Memory - Request Router
Smart routing system combining API keys, proxies, and models with auto-fallback
"""

import requests
import time
import json
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from enum import Enum
import random

from api_key_manager import APIKeyManager
from proxy_manager import ProxyManager, ProxyType

class RequestStatus(Enum):
    SUCCESS = "success"
    RATE_LIMITED = "rate_limited"
    NETWORK_ERROR = "network_error"
    CONTEXT_TOO_LARGE = "context_too_large"
    API_ERROR = "api_error"
    PROXY_ERROR = "proxy_error"

class RequestRouter:
    """Intelligent request routing with resilience and auto-fallback"""
    
    def __init__(self):
        self.api_manager = APIKeyManager()
        self.proxy_manager = ProxyManager()
        
        # Available Groq models (function calling capable)
        self.available_models = [
            "deepseek-r1-distill-llama-70b",
            "llama-3.3-70b-versatile",
            "llama-3.1-70b-versatile",
            "llama-3.1-8b-instant",
            "gemma2-9b-it",
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "meta-llama/llama-4-maverick-17b-128e-instruct",
            "moonshotai/kimi-k2-instruct"
        ]
        
        self.current_model = "llama-3.3-70b-versatile"  # Default model
        self.groq_base_url = "https://api.groq.com/openai/v1"
        
        # Retry and backoff settings
        self.max_retries = 3
        self.base_delay = 1.0
        self.max_delay = 30.0
        
        # Request tracking
        self.request_stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'retries_triggered': 0,
            'route_switches': 0
        }
        
        # Route preferences
        self.preferred_proxy_type = ProxyType.MOBILE
        self.auto_route_selection = True
    
    def make_request(self, 
                    endpoint: str,
                    payload: Dict[str, Any],
                    max_retries: Optional[int] = None,
                    custom_headers: Optional[Dict[str, str]] = None) -> Tuple[RequestStatus, Optional[Dict], str]:
        """
        Make resilient API request with auto-fallback
        Returns: (status, response_data, debug_info)
        """
        if max_retries is None:
            max_retries = self.max_retries
        
        self.request_stats['total_requests'] += 1
        
        for attempt in range(max_retries + 1):
            # Get current routing configuration
            api_key = self.api_manager.get_next_key()
            proxy_config = self.proxy_manager.get_proxy_for_request(self.preferred_proxy_type)
            
            if not api_key:
                return RequestStatus.API_ERROR, None, "No API keys available"
            
            # Build request
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            if custom_headers:
                headers.update(custom_headers)
            
            # Add model to payload if not present
            if 'model' not in payload:
                payload['model'] = self.current_model
            
            url = f"{self.groq_base_url}/{endpoint.lstrip('/')}"
            
            try:
                start_time = time.time()
                
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    proxies=proxy_config,
                    timeout=60
                )
                
                response_time = time.time() - start_time
                
                # Handle different response statuses
                if response.status_code == 200:
                    self.request_stats['successful_requests'] += 1
                    debug_info = f"Success: {response_time:.2f}s, Key: ...{api_key[-8:]}, Proxy: {bool(proxy_config)}"
                    return RequestStatus.SUCCESS, response.json(), debug_info
                
                elif response.status_code == 429:  # Rate limited
                    self.api_manager.mark_key_error(api_key, "rate_limit")
                    self.request_stats['retries_triggered'] += 1
                    
                    if attempt < max_retries:
                        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                        print(f"⚠️ Rate limited, retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries + 1})")
                        time.sleep(delay)
                        continue
                    else:
                        return RequestStatus.RATE_LIMITED, None, f"Rate limited after {max_retries + 1} attempts"
                
                elif response.status_code == 413 or "context" in response.text.lower():
                    return RequestStatus.CONTEXT_TOO_LARGE, None, f"Context too large: {response.text}"
                
                else:
                    error_text = response.text
                    self.api_manager.mark_key_error(api_key, f"http_{response.status_code}")
                    
                    if attempt < max_retries:
                        print(f"⚠️ API error {response.status_code}, retrying...")
                        continue
                    else:
                        return RequestStatus.API_ERROR, None, f"HTTP {response.status_code}: {error_text}"
            
            except requests.exceptions.ProxyError as e:
                print(f"❌ Proxy error: {e}")
                # Force proxy rotation and try different type
                self.proxy_manager.force_rotation()
                if self.preferred_proxy_type == ProxyType.MOBILE:
                    self.preferred_proxy_type = ProxyType.RESIDENTIAL
                else:
                    self.preferred_proxy_type = ProxyType.LOCAL
                
                self.request_stats['route_switches'] += 1
                
                if attempt < max_retries:
                    continue
                else:
                    return RequestStatus.PROXY_ERROR, None, f"Proxy error: {e}"
            
            except requests.exceptions.Timeout as e:
                print(f"⚠️ Request timeout: {e}")
                if attempt < max_retries:
                    continue
                else:
                    return RequestStatus.NETWORK_ERROR, None, f"Timeout: {e}"
            
            except Exception as e:
                print(f"❌ Unexpected error: {e}")
                if attempt < max_retries:
                    continue
                else:
                    return RequestStatus.NETWORK_ERROR, None, f"Network error: {e}"
        
        self.request_stats['failed_requests'] += 1
        return RequestStatus.NETWORK_ERROR, None, "Max retries exceeded"
    
    def chat_completion(self, 
                       messages: List[Dict[str, str]], 
                       model: Optional[str] = None,
                       max_tokens: int = 8000,
                       temperature: float = 0.1,
                       tools: Optional[List[Dict]] = None) -> Tuple[RequestStatus, Optional[Dict], str]:
        """Make chat completion request"""
        payload = {
            "model": model or self.current_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        
        return self.make_request("chat/completions", payload)
    
    def function_call_completion(self,
                               messages: List[Dict[str, str]],
                               tools: List[Dict],
                               model: Optional[str] = None) -> Tuple[RequestStatus, Optional[Dict], str]:
        """Make function calling completion request"""
        # Use function calling capable model
        function_model = model or "llama-3.3-70b-versatile"
        
        return self.chat_completion(
            messages=messages,
            model=function_model,
            tools=tools,
            temperature=0.1
        )
    
    def set_model(self, model: str):
        """Set the current model"""
        if model in self.available_models:
            self.current_model = model
            print(f"🎯 Model set to: {model}")
        else:
            print(f"⚠️ Model {model} not in available models: {self.available_models}")
    
    def set_proxy_preference(self, proxy_type: ProxyType):
        """Set preferred proxy type"""
        self.preferred_proxy_type = proxy_type
        print(f"🌐 Proxy preference: {proxy_type.value}")
    
    def enable_manual_routing(self, api_key: str, proxy_type: ProxyType):
        """Enable manual routing control"""
        self.api_manager.disable_auto_rotation()
        self.api_manager.set_manual_key(api_key)
        self.preferred_proxy_type = proxy_type
        self.auto_route_selection = False
        print("🎛️ Manual routing enabled")
    
    def enable_auto_routing(self):
        """Enable automatic routing"""
        self.api_manager.enable_auto_rotation()
        self.auto_route_selection = True
        print("🤖 Auto routing enabled")
    
    def get_router_status(self) -> dict:
        """Get comprehensive router status"""
        return {
            'current_model': self.current_model,
            'available_models': self.available_models,
            'preferred_proxy': self.preferred_proxy_type.value,
            'auto_routing': self.auto_route_selection,
            'request_stats': self.request_stats,
            'api_key_status': self.api_manager.get_deck_status(),
            'proxy_status': self.proxy_manager.get_proxy_status()
        }
    
    def reset_routing_stats(self):
        """Reset request statistics"""
        self.request_stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'retries_triggered': 0,
            'route_switches': 0
        }
        print("📊 Routing stats reset")

# Example usage and testing
if __name__ == "__main__":
    router = RequestRouter()
    
    print("\n🧪 Testing request routing:")
    
    # Test simple chat completion
    test_messages = [
        {"role": "user", "content": "Hello, this is a test message."}
    ]
    
    status, response, debug = router.chat_completion(test_messages, max_tokens=100)
    print(f"Status: {status.value}")
    print(f"Debug: {debug}")
    
    if status == RequestStatus.SUCCESS and response:
        print(f"Response: {response.get('choices', [{}])[0].get('message', {}).get('content', 'No content')[:100]}...")
    
    print(f"\n📊 Router Status: {router.get_router_status()}")
