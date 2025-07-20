"""
🔗 Remember - List Handler
Clean file listing - no bullshit
"""

from typing import List, Optional
from pathlib import Path
from datetime import datetime
from commands.base_command import BaseCommand

class ListHandler(BaseCommand):
    
    def get_aliases(self) -> List[str]:
        return ["list", "ls", "l"]
    
    def execute(self, command_input: str) -> Optional[str]:
        """List files clean"""
        remember_dir = Path("~/remember").expanduser()
        
        output = "\n📁 REMEMBER FILES:\n\n"
        
        # Get all files
        files = list(remember_dir.glob("*.json"))
        
        if not files:
            return "No JSON files found in ~/remember/"
        
        for f in sorted(files, key=lambda x: x.stat().st_mtime, reverse=True):
            stat = f.stat()
            size_kb = stat.st_size // 1024
            date = datetime.fromtimestamp(stat.st_mtime).strftime("%m/%d %H:%M")
            
            # Clean one-liner format
            output += f"{f.name:<40} {size_kb:>4}KB  {date}\n"
        
        return output
    
    def get_help(self) -> str:
        return "List extraction files"
