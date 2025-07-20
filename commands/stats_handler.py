"""
🔗 Remember - Stats Handler
Show extraction statistics
"""

from typing import List, Optional
from commands.base_command import BaseCommand
from core.database import get_session_stats

class StatsHandler(BaseCommand):
    """Handle stats commands"""
    
    def get_aliases(self) -> List[str]:
        return ["stats", "status", "info"]
    
    def execute(self, command_input: str) -> Optional[str]:
        """Execute stats command"""
        try:
            stats = get_session_stats()
            
            stats_msgs = [
                "📊 Remember Database Statistics",
                "",
                f"🗂️ Total Sessions: {stats['total_sessions']}",
                f"🔗 Total URLs: {stats['total_urls']}",
                "",
                "⭐ Rating Distribution:",
                f"  5 Stars: {stats['by_rating'][5]} URLs",
                f"  4 Stars: {stats['by_rating'][4]} URLs", 
                f"  3 Stars: {stats['by_rating'][3]} URLs",
                f"  2 Stars: {stats['by_rating'][2]} URLs",
                f"  1 Star:  {stats['by_rating'][1]} URLs",
                "",
                f"💾 Database: ~/remember_db/"
            ]
            
            return self.format_data(stats_msgs)
            
        except Exception as e:
            return self.format_error([f"Stats failed: {str(e)}"])
    
    def get_help(self) -> str:
        """Return help text"""
        return self.format_info([
            "🔗 Remember Stats Handler",
            "",
            "Usage:",
            "  stats               Show database statistics",
            "",
            "Displays extraction sessions and URL statistics"
        ])
