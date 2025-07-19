#!/usr/bin/env python3
"""
🦚 Peacock Memory - Context Manager
Handles token limits, auto-chunking, and context compression
"""

import tiktoken
import json
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum

class ContextStrategy(Enum):
    SIMPLE_CHUNK = "simple_chunk"
    SMART_CHUNK = "smart_chunk"
    PROGRESSIVE_SUMMARY = "progressive_summary"
    ROLLING_WINDOW = "rolling_window"

@dataclass
class ContextChunk:
    content: str
    token_count: int
    chunk_index: int
    total_chunks: int
    metadata: Dict[str, Any]

class ContextManager:
    """Manages context size, chunking, and token limits"""
    
    def __init__(self):
        # Model token limits (conservative estimates)
        self.model_limits = {
            "llama-3.3-70b-versatile": 8000,
            "llama-3.1-70b-versatile": 8000,
            "llama-3.1-8b-instant": 8000,
            "llama3-groq-70b-8192-tool-use-preview": 8000,
            "llama3-groq-8b-8192-tool-use-preview": 8000
        }
        
        # Reserve tokens for response
        self.response_token_reserve = 1000
        
        # Initialize tokenizer (using GPT-3.5 as approximation)
        try:
            self.tokenizer = tiktoken.encoding_for_model("gpt-3.5-turbo")
        except:
            # Fallback to basic encoding
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        if not text:
            return 0
        try:
            return len(self.tokenizer.encode(text))
        except:
            # Fallback: rough estimation (4 chars per token)
            return len(text) // 4
    
    def count_message_tokens(self, messages: List[Dict[str, str]]) -> int:
        """Count tokens in message list"""
        total_tokens = 0
        for message in messages:
            # Add tokens for role and content
            total_tokens += self.count_tokens(message.get("role", ""))
            total_tokens += self.count_tokens(message.get("content", ""))
            total_tokens += 3  # Token overhead per message
        return total_tokens
    
    def get_effective_limit(self, model: str) -> int:
        """Get effective token limit for model (with response reserve)"""
        base_limit = self.model_limits.get(model, 8000)
        return base_limit - self.response_token_reserve
    
    def can_fit_context(self, messages: List[Dict[str, str]], model: str) -> bool:
        """Check if messages fit within model's context limit"""
        token_count = self.count_message_tokens(messages)
        limit = self.get_effective_limit(model)
        return token_count <= limit
    
    def simple_chunk_text(self, text: str, max_tokens: int) -> List[ContextChunk]:
        """Simple text chunking by token count"""
        if not text:
            return []
        
        total_tokens = self.count_tokens(text)
        if total_tokens <= max_tokens:
            return [ContextChunk(
                content=text,
                token_count=total_tokens,
                chunk_index=0,
                total_chunks=1,
                metadata={"strategy": "no_chunking_needed"}
            )]
        
        # Calculate chunks needed
        chunks_needed = (total_tokens + max_tokens - 1) // max_tokens
        chars_per_chunk = len(text) // chunks_needed
        
        chunks = []
        for i in range(chunks_needed):
            start_idx = i * chars_per_chunk
            end_idx = min((i + 1) * chars_per_chunk, len(text))
            
            chunk_text = text[start_idx:end_idx]
            chunk_tokens = self.count_tokens(chunk_text)
            
            chunks.append(ContextChunk(
                content=chunk_text,
                token_count=chunk_tokens,
                chunk_index=i,
                total_chunks=chunks_needed,
                metadata={"strategy": "simple_chunk", "char_range": (start_idx, end_idx)}
            ))
        
        return chunks
    
    def smart_chunk_text(self, text: str, max_tokens: int) -> List[ContextChunk]:
        """Smart chunking that respects paragraph boundaries"""
        if not text:
            return []
        
        total_tokens = self.count_tokens(text)
        if total_tokens <= max_tokens:
            return [ContextChunk(
                content=text,
                token_count=total_tokens,
                chunk_index=0,
                total_chunks=1,
                metadata={"strategy": "no_chunking_needed"}
            )]
        
        # Split by paragraphs
        paragraphs = text.split('\n\n')
        if len(paragraphs) == 1:
            # No paragraphs, split by sentences
            paragraphs = text.split('. ')
        
        chunks = []
        current_chunk = ""
        current_tokens = 0
        
        for paragraph in paragraphs:
            paragraph_tokens = self.count_tokens(paragraph)
            
            # If single paragraph exceeds limit, force split
            if paragraph_tokens > max_tokens:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""
                    current_tokens = 0
                
                # Split large paragraph
                simple_chunks = self.simple_chunk_text(paragraph, max_tokens)
                for chunk in simple_chunks:
                    chunks.append(chunk.content)
                continue
            
            # Check if adding this paragraph would exceed limit
            if current_tokens + paragraph_tokens > max_tokens:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = paragraph
                current_tokens = paragraph_tokens
            else:
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph
                current_tokens += paragraph_tokens
        
        # Add final chunk
        if current_chunk:
            chunks.append(current_chunk)
        
        # Convert to ContextChunk objects
        result_chunks = []
        for i, chunk_text in enumerate(chunks):
            chunk_tokens = self.count_tokens(chunk_text)
            result_chunks.append(ContextChunk(
                content=chunk_text,
                token_count=chunk_tokens,
                chunk_index=i,
                total_chunks=len(chunks),
                metadata={"strategy": "smart_chunk"}
            ))
        
        return result_chunks
    
    def compress_messages(self, messages: List[Dict[str, str]], target_tokens: int) -> List[Dict[str, str]]:
        """Compress message history to fit target token count"""
        if self.count_message_tokens(messages) <= target_tokens:
            return messages
        
        # Keep system message and recent messages
        compressed = []
        
        # Always keep system message if present
        if messages and messages[0].get("role") == "system":
            compressed.append(messages[0])
            remaining_messages = messages[1:]
        else:
            remaining_messages = messages
        
        # Calculate tokens used by system message
        used_tokens = self.count_message_tokens(compressed)
        remaining_tokens = target_tokens - used_tokens
        
        # Add messages from the end (most recent first)
        for message in reversed(remaining_messages):
            message_tokens = self.count_tokens(message.get("content", "")) + 3
            if used_tokens + message_tokens <= target_tokens:
                compressed.insert(-1 if compressed and compressed[0].get("role") == "system" else 0, message)
                used_tokens += message_tokens
            else:
                break
        
        return compressed
    
    def prepare_context_for_model(self, 
                                 messages: List[Dict[str, str]], 
                                 model: str,
                                 strategy: ContextStrategy = ContextStrategy.SMART_CHUNK) -> Tuple[bool, List[Dict[str, str]], Optional[List[ContextChunk]]]:
        """
        Prepare context for model, returning (fits_directly, prepared_messages, chunks_if_needed)
        """
        effective_limit = self.get_effective_limit(model)
        
        if self.can_fit_context(messages, model):
            return True, messages, None
        
        # Try compression first
        compressed_messages = self.compress_messages(messages, effective_limit)
        if self.can_fit_context(compressed_messages, model):
            return True, compressed_messages, None
        
        # If still too large, need chunking
        if strategy == ContextStrategy.ROLLING_WINDOW:
            # Use rolling window - keep only recent messages
            return True, compressed_messages, None
        
        # For other strategies, return chunks for separate processing
        # Combine all message content for chunking
        combined_content = "\n\n".join([
            f"**{msg.get('role', 'unknown').title()}:** {msg.get('content', '')}"
            for msg in messages
        ])
        
        if strategy == ContextStrategy.SMART_CHUNK:
            chunks = self.smart_chunk_text(combined_content, effective_limit)
        else:
            chunks = self.simple_chunk_text(combined_content, effective_limit)
        
        return False, [], chunks
    
    def create_chunk_message(self, chunk: ContextChunk, system_prompt: str = "") -> List[Dict[str, str]]:
        """Create message list for processing a single chunk"""
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        chunk_info = f"Processing chunk {chunk.chunk_index + 1} of {chunk.total_chunks}"
        if chunk.total_chunks > 1:
            chunk_info += f" (Strategy: {chunk.metadata.get('strategy', 'unknown')})"
        
        messages.append({
            "role": "user", 
            "content": f"{chunk_info}\n\n{chunk.content}"
        })
        
        return messages
    
    def get_context_stats(self, messages: List[Dict[str, str]], model: str) -> Dict[str, Any]:
        """Get detailed context statistics"""
        total_tokens = self.count_message_tokens(messages)
        effective_limit = self.get_effective_limit(model)
        
        return {
            "total_tokens": total_tokens,
            "effective_limit": effective_limit,
            "fits_directly": total_tokens <= effective_limit,
            "utilization_percent": (total_tokens / effective_limit) * 100,
            "tokens_over_limit": max(0, total_tokens - effective_limit),
            "message_count": len(messages),
            "average_tokens_per_message": total_tokens / len(messages) if messages else 0
        }

# Example usage and testing
if __name__ == "__main__":
    context_manager = ContextManager()
    
    print("\n🧪 Testing context management:")
    
    # Create test messages
    test_messages = [
        {"role": "system", "content": "You are a helpful legal assistant."},
        {"role": "user", "content": "Analyze this legal document: " + "This is a test document. " * 500},
        {"role": "assistant", "content": "I'll analyze the document for you."},
        {"role": "user", "content": "What are the key points?"}
    ]
    
    model = "llama-3.3-70b-versatile"
    
    # Get context stats
    stats = context_manager.get_context_stats(test_messages, model)
    print(f"📊 Context Stats: {stats}")
    
    # Test context preparation
    fits, prepared, chunks = context_manager.prepare_context_for_model(test_messages, model)
    
    if fits:
        print(f"✅ Context fits directly ({len(prepared)} messages)")
    else:
        print(f"📋 Chunking required: {len(chunks)} chunks")
        for i, chunk in enumerate(chunks[:2]):  # Show first 2 chunks
            print(f"   Chunk {i+1}: {chunk.token_count} tokens")