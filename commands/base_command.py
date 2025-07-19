"""
🔗 Remember - Base Command Interface
Abstract base class for all command handlers
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from core.visuals import format_grouped_output

class BaseCommand(ABC):
    """Base class for all command handlers"""
    
    def __init__(self):
        self.name = self.__class__.__name__.replace("Handler", "").lower()
    
    @abstractmethod
    def get_aliases(self) -> List[str]:
        """Return list of command aliases this handler responds to"""
        pass
    
    @abstractmethod
    def execute(self, command_input: str) -> Optional[str]:
        """Execute the command and return formatted output"""
        pass
    
    @abstractmethod
    def get_help(self) -> str:
        """Return help text for this command"""
        pass
    
    def format_success(self, messages: List[str]) -> str:
        """Format success messages"""
        return format_grouped_output(messages, "success")
    
    def format_error(self, messages: List[str]) -> str:
        """Format error messages"""
        return format_grouped_output(messages, "error")
    
    def format_info(self, messages: List[str]) -> str:
        """Format info messages"""
        return format_grouped_output(messages, "info")
    
    def format_warning(self, messages: List[str]) -> str:
        """Format warning messages"""
        return format_grouped_output(messages, "warning")
    
    def format_data(self, messages: List[str]) -> str:
        """Format data messages"""
        return format_grouped_output(messages, "data")
