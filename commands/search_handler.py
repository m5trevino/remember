"""
🔗 Remember - Search Handler
Search extracted URL content
"""

from typing import List, Optional
import questionary

from commands.base_command import BaseCommand
from core.database import search_extractions

class SearchHandler(BaseCommand):
    """Handle search commands"""
    
    def get_aliases(self) -> List[str]:
        return ["search", "find", "s"]
    
    def execute(self, command_input: str) -> Optional[str]:
        """Execute search command"""
        parts = command_input.strip().split()
        
        if len(parts) == 1:
            # Interactive mode
            query = questionary.text("🔍 Enter search query:").ask()
            if not query:
                return self.format_warning(["Search cancelled"])
        else:
            query = " ".join(parts[1:])
        
        return self._search(query)
    
    def _search(self, query: str) -> str:
        """Perform search"""
        try:
            results = search_extractions(query, limit=10)
            
            if not results:
                return self.format_warning([f"No results found for: {query}"])
            
            header_msgs = [
                f"🔍 Search Results for: '{query}'",
                f"📊 Found: {len(results)} results",
                ""
            ]
            
            result_msgs = []
            for i, result in enumerate(results, 1):
                metadata = result.get('metadata', {})
                url = metadata.get('url', 'Unknown URL')
                title = metadata.get('title', 'No Title')
                rating = metadata.get('rating', 0)
                
                result_msgs.extend([
                    f"#{i} ⭐{rating}/5 - {title}",
                    f"🔗 {url}",
                    f"📄 {result['preview']}",
                    ""
                ])
            
            all_msgs = header_msgs + result_msgs
            return self.format_data(all_msgs)
            
        except Exception as e:
            return self.format_error([f"Search failed: {str(e)}"])
    
    def get_help(self) -> str:
        """Return help text"""
        return self.format_info([
            "🔗 Remember Search Handler",
            "",
            "Usage:",
            "  search                Interactive search",
            "  search <query>        Direct search",
            "",
            "Search through extracted URL content"
        ])
