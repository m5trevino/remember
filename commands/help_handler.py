#!/usr/bin/env python3
"""
Help Handler - Clean command help with Legal commands
"""
from typing import List, Optional
from commands.base_command import BaseCommand

class HelpHandler(BaseCommand):
    """Handle help commands"""
    
    def get_aliases(self) -> List[str]:
        return ["help", "h", "?"]
    
    def execute(self, command_input: str) -> Optional[str]:
        """Show help"""
        help_lines = [
            "🔗 REMEMBER COMMANDS",
            "",
            "📊 DATA EXTRACTION:",
            "extract    - Scrape URLs from urls.txt",
            "import     - Load JSON results to database", 
            "",
            "🔍 SEARCH & ANALYSIS:",
            "search     - Find content in database",
            "legal      - Legal document analysis (NEW!)",
            "",
            "📁 FILE MANAGEMENT:",
            "list       - Show files (clean format)",
            "read       - Open file in sublime/cli",
            "",
            "📈 SYSTEM INFO:",
            "stats      - Show extraction stats",
            "help       - This help",
            "",
            "💡 LEGAL COMMANDS:",
            "legal batch         - Process all docs with custom prompt",
            "legal analyze       - Interactive document analysis", 
            "legal chat          - Legal chat session",
            "",
            "Examples:",
            "  extract                    # Run URL scraper",
            "  import results_*.json      # Import to database",
            "  legal batch                # Batch legal analysis",
            "  search \"service process\"    # Find service docs"
        ]
        
        return self.format_info(help_lines)
    
    def get_help(self) -> str:
        return "Shows available commands including legal analysis"