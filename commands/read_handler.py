"""
🔗 Remember - Read Handler
Open files in Sublime or clean CLI view
"""

from typing import List, Optional
from pathlib import Path
import subprocess
import json
from commands.base_command import BaseCommand

class ReadHandler(BaseCommand):
    
    def get_aliases(self) -> List[str]:
        return ["read", "view", "open", "cat"]
    
    def execute(self, command_input: str) -> Optional[str]:
        """Read file"""
        parts = command_input.strip().split()
        
        if len(parts) < 2:
            return "Usage: read <filename>"
        
        filename = parts[1]
        file_path = Path("~/remember").expanduser() / filename
        
        if not file_path.exists():
            return f"File not found: {filename}"
        
        # Ask user preference
        choice = input("Open in (s)ublime or (c)li? [s/c]: ").lower()
        
        if choice == 's':
            # Open in Sublime
            try:
                subprocess.run(["subl", str(file_path)], check=True)
                return f"Opened {filename} in Sublime"
            except:
                return "Sublime not available, showing in CLI:"
        
        # Show in CLI (clean)
        try:
            if filename.endswith('.json'):
                with open(file_path, 'r') as f:
                    data = json.load(f)
                return f"\n📄 {filename}:\n{json.dumps(data, indent=2)}"
            else:
                with open(file_path, 'r') as f:
                    content = f.read()
                return f"\n📄 {filename}:\n{content}"
        except Exception as e:
            return f"Error reading file: {e}"
    
    def get_help(self) -> str:
        return "Read file in Sublime or CLI"
