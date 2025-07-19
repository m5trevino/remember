#!/usr/bin/env python3
"""
🦚 Peacock Memory - Groq Client
Unified interface combining all infrastructure modules for bulletproof API calls
"""

import json
import time
from typing import List, Dict, Optional, Any, Tuple, Generator
from datetime import datetime

from request_router import RequestRouter, RequestStatus
from context_manager import ContextManager, ContextStrategy, ContextChunk
from proxy_manager import ProxyType

class GroqClient:
    """Unified Groq client with full resilience and automation"""
    
    def __init__(self):
        self.router = RequestRouter()
        self.context_manager = ContextManager()
        
        # Client settings
        self.default_model = "llama-3.3-70b-versatile"
        self.default_max_tokens = 4000
        self.default_temperature = 0.1
        
        # Automation settings
        self.enable_auto_chunking = True
        self.enable_auto_retry = True
        self.max_chunk_retries = 3
        
        # Statistics
        self.session_stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'chunks_processed': 0,
            'auto_retries': 0,
            'route_switches': 0
        }
    
    def simple_chat(self, 
                   message: str, 
                   system_prompt: Optional[str] = None,
                   model: Optional[str] = None) -> Tuple[bool, str, str]:
        """
        Simple chat interface for basic conversations
        Returns: (success, response_content, debug_info)
        """
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": message})
        
        return self._execute_chat_request(messages, model)
    
    def conversation_chat(self,
                         messages: List[Dict[str, str]],
                         model: Optional[str] = None) -> Tuple[bool, str, str]:
        """
        Multi-turn conversation interface
        Returns: (success, response_content, debug_info)
        """
        return self._execute_chat_request(messages, model)
    
    def function_call_chat(self,
                          messages: List[Dict[str, str]],
                          tools: List[Dict[str, Any]],
                          model: Optional[str] = None) -> Tuple[bool, Dict[str, Any], str]:
        """
        Function calling interface
        Returns: (success, full_response_data, debug_info)
        """
        model = model or self.default_model
        self.session_stats['total_requests'] += 1
        
        # Check if context fits
        fits, prepared_messages, chunks = self.context_manager.prepare_context_for_model(
            messages, model, ContextStrategy.SMART_CHUNK
        )
        
        if fits:
            # Direct function call
            status, response, debug = self.router.function_call_completion(
                messages=prepared_messages,
                tools=tools,
                model=model
            )
            
            if status == RequestStatus.SUCCESS:
                self.session_stats['successful_requests'] += 1
                return True, response, debug
            else:
                return False, {"error": f"Function call failed: {status.value}"}, debug
        else:
            # Context too large for function calling - this is tricky
            return False, {"error": "Context too large for function calling"}, "Function calls require smaller context"
    
    def process_large_content(self,
                            content: str,
                            system_prompt: str,
                            model: Optional[str] = None,
                            strategy: ContextStrategy = ContextStrategy.SMART_CHUNK) -> Generator[Tuple[bool, str, str], None, None]:
        """
        Process large content in chunks with automatic handling
        Yields: (success, chunk_response, debug_info) for each chunk
        """
        model = model or self.default_model
        effective_limit = self.context_manager.get_effective_limit(model)
        
        # Create chunks
        if strategy == ContextStrategy.SMART_CHUNK:
            chunks = self.context_manager.smart_chunk_text(content, effective_limit - 500)  # Reserve for system prompt
        else:
            chunks = self.context_manager.simple_chunk_text(content, effective_limit - 500)
        
        self.session_stats['chunks_processed'] += len(chunks)
        
        for chunk in chunks:
            chunk_messages = self.context_manager.create_chunk_message(chunk, system_prompt)
            
            # Process this chunk with retries
            for attempt in range(self.max_chunk_retries):
                success, response, debug = self._execute_chat_request(chunk_messages, model)
                
                if success:
                    yield True, response, debug
                    break
                else:
                    if attempt < self.max_chunk_retries - 1:
                        self.session_stats['auto_retries'] += 1
                        yield False, f"Chunk {chunk.chunk_index + 1} failed (attempt {attempt + 1}), retrying...", debug
                        time.sleep(1.0 * (attempt + 1))  # Progressive delay
                    else:
                        yield False, f"Chunk {chunk.chunk_index + 1} failed after {self.max_chunk_retries} attempts", debug
    
    def auto_process_content(self,
                           content: str,
                           system_prompt: str,
                           model: Optional[str] = None) -> Tuple[bool, List[str], List[str]]:
        """
        Automatically process content with chunking if needed
        Returns: (overall_success, successful_responses, debug_messages)
        """
        model = model or self.default_model
        
        # Try direct processing first
        simple_message = f"{system_prompt}\n\n{content}"
        test_messages = [{"role": "user", "content": simple_message}]
        
        if self.context_manager.can_fit_context(test_messages, model):
            # Can process directly
            success, response, debug = self._execute_chat_request(test_messages, model)
            if success:
                return True, [response], [debug]
            else:
                return False, [], [debug]
        
        # Need chunking
        successful_responses = []
        debug_messages = []
        overall_success = True
        
        for success, response, debug in self.process_large_content(content, system_prompt, model):
            debug_messages.append(debug)
            
            if success and not response.startswith("Chunk") and not response.startswith("failed"):
                successful_responses.append(response)
            elif not success:
                overall_success = False
        
        return overall_success, successful_responses, debug_messages
    
    def _execute_chat_request(self, 
                            messages: List[Dict[str, str]], 
                            model: Optional[str] = None) -> Tuple[bool, str, str]:
        """
        Internal method to execute chat request with context management
        Returns: (success, response_content, debug_info)
        """
        model = model or self.default_model
        self.session_stats['total_requests'] += 1
        
        # Prepare context
        fits, prepared_messages, chunks = self.context_manager.prepare_context_for_model(
            messages, model
        )
        
        if not fits and chunks:
            return False, "Context too large - use process_large_content() method", "Context exceeds limits"
        
        # Execute request
        status, response, debug = self.router.chat_completion(
            messages=prepared_messages,
            model=model,
            max_tokens=self.default_max_tokens,
            temperature=self.default_temperature
        )
        
        if status == RequestStatus.SUCCESS:
            self.session_stats['successful_requests'] += 1
            content = response.get('choices', [{}])[0].get('message', {}).get('content', '')
            return True, content, debug
        
        elif status == RequestStatus.CONTEXT_TOO_LARGE:
            # Try with smaller context
            if self.enable_auto_retry:
                compressed_messages = self.context_manager.compress_messages(
                    prepared_messages, 
                    self.context_manager.get_effective_limit(model) // 2
                )
                
                status, response, debug = self.router.chat_completion(
                    messages=compressed_messages,
                    model=model,
                    max_tokens=self.default_max_tokens,
                    temperature=self.default_temperature
                )
                
                if status == RequestStatus.SUCCESS:
                    self.session_stats['successful_requests'] += 1
                    self.session_stats['auto_retries'] += 1
                    content = response.get('choices', [{}])[0].get('message', {}).get('content', '')
                    return True, content, f"{debug} (auto-compressed)"
        
        return False, f"Request failed: {status.value}", debug
    
    def set_model(self, model: str):
        """Set default model"""
        self.default_model = model
        self.router.set_model(model)
        print(f"🎯 Default model: {model}")
    
    def set_proxy_preference(self, proxy_type: ProxyType):
        """Set proxy preference"""
        self.router.set_proxy_preference(proxy_type)
    
    def enable_manual_routing(self, api_key: str, proxy_type: ProxyType):
        """Enable manual routing control"""
        self.router.enable_manual_routing(api_key, proxy_type)
    
    def enable_auto_routing(self):
        """Enable automatic routing"""
        self.router.enable_auto_routing()
    
    def get_available_models(self) -> List[str]:
        """Get list of available models"""
        return self.router.available_models
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get comprehensive session statistics"""
        router_stats = self.router.get_router_status()
        
        return {
            'session_stats': self.session_stats,
            'router_stats': router_stats,
            'current_model': self.default_model,
            'auto_chunking_enabled': self.enable_auto_chunking,
            'auto_retry_enabled': self.enable_auto_retry
        }
    
    def reset_session_stats(self):
        """Reset session statistics"""
        self.session_stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'chunks_processed': 0,
            'auto_retries': 0,
            'route_switches': 0
        }
        self.router.reset_routing_stats()
        print("📊 Session stats reset")

# Example usage and testing
if __name__ == "__main__":
    client = GroqClient()
    
    print("\n🧪 Testing Groq client:")
    
    # Test simple chat
    success, response, debug = client.simple_chat(
        "Hello, this is a test message.",
        "You are a helpful assistant."
    )
    
    print(f"Simple chat - Success: {success}")
    if success:
        print(f"Response: {response[:100]}...")
    print(f"Debug: {debug}")
    
    # Test large content processing
    large_content = "This is a large document. " * 1000
    
    print(f"\n🔄 Testing large content processing:")
    success, responses, debugs = client.auto_process_content(
        large_content,
        "Summarize this document in 2 sentences."
    )
    
    print(f"Large content - Success: {success}")
    print(f"Responses received: {len(responses)}")
    
    print(f"\n📊 Session Stats: {client.get_session_stats()}")