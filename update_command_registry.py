#!/usr/bin/env python3
"""
🔗 Remember - Command Registry
Auto-discovery and routing for extraction commands + Legal Handler
"""

import importlib
from typing import Dict, List, Optional
from pathlib import Path

from commands.base_command import BaseCommand
from commands.import_handler import ImportHandler
from commands.search_handler import SearchHandler
from commands.extract_handler import ExtractHandler
from commands.stats_handler import StatsHandler
from commands.help_handler import HelpHandler
from commands.list_handler import ListHandler
from commands.read_handler import ReadHandler
from commands.legal_handler import LegalHandler  # NEW LEGAL HANDLER
from core.visuals import format_single_message

class CommandRegistry:
    """Registry for auto-discovering and routing commands"""
    
    def __init__(self):
        self.handlers: Dict[str, BaseCommand] = {}
        self.aliases: Dict[str, str] = {}
        self._load_handlers()
    
    def _load_handlers(self):
        """Load all command handlers including legal handler"""
        handler_classes = [
            ImportHandler,
            SearchHandler,
            ExtractHandler,
            StatsHandler,
            HelpHandler,
            ListHandler,
            ReadHandler,
            LegalHandler  # LEGAL HANDLER ADDED
        ]
        
        for handler_class in handler_classes:
            try:
                handler = handler_class()
                handler_name = handler.__class__.__name__
                self.handlers[handler_name] = handler
                
                # Register aliases
                for alias in handler.get_aliases():
                    self.aliases[alias.lower()] = handler_name
                    
            except Exception as e:
                print(f"Failed to load handler {handler_class.__name__}: {e}")
    
    def get_handler(self, command_input: str) -> Optional[BaseCommand]:
        """Get appropriate handler for command"""
        if not command_input:
            return None
        
        command_word = command_input.strip().split()[0].lower()
        handler_name = self.aliases.get(command_word)
        if handler_name:
            return self.handlers.get(handler_name)
        
        return None
    
    def execute_command(self, command_input: str) -> Optional[str]:
        """Execute command through appropriate handler"""
        if not command_input.strip():
            return None
        
        handler = self.get_handler(command_input)
        if not handler:
            return format_single_message(
                f"Unknown command: {command_input.split()[0]}. Type 'help' for available commands.",
                "error"
            )
        
        try:
            return handler.execute(command_input)
        except Exception as e:
            return format_single_message(
                f"Error executing command: {str(e)}",
                "error"
            )