from typing import Dict, List, Optional

from commands.base_command import BaseCommand
from commands.import_handler import ImportHandler
from commands.search_handler import SearchHandler
from commands.extract_handler import ExtractHandler
from commands.stats_handler import StatsHandler
from commands.help_handler import HelpHandler
from commands.list_handler import ListHandler
from commands.read_handler import ReadHandler
from commands.legal_handler import LegalHandler
from commands.webui_handler import WebuiHandler
from core.visuals import format_single_message

class CommandRegistry:
    def __init__(self):
        self.handlers: Dict[str, BaseCommand] = {}
        self.aliases: Dict[str, BaseCommand] = {}
        self._load_handlers()
    
    def _load_handlers(self):
        handler_classes = [
            ImportHandler, SearchHandler, ExtractHandler,
            StatsHandler, HelpHandler, ListHandler,
            ReadHandler, LegalHandler, WebuiHandler
        ]
        
        for handler_class in handler_classes:
            try:
                handler = handler_class()
                for alias in handler.get_aliases():
                    self.aliases[alias.lower()] = handler
            except Exception as e:
                print(f"Failed to load handler {handler_class.__name__}: {e}")
    
    def execute_command(self, command_input: str) -> Optional[str]:
        if not command_input.strip(): return None
        
        command_word = command_input.strip().split()[0].lower()
        handler = self.aliases.get(command_word)
        
        if not handler:
            return format_single_message(f"Unknown command: '{command_word}'. Type 'help'.", "error")
        
        try:
            return handler.execute(command_input)
        except Exception as e:
            return format_single_message(f"Error executing '{command_word}': {e}", "error")
