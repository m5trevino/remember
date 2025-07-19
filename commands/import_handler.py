"""
🔗 Remember - Import Handler
Import JSON extraction results into database
"""

from typing import List, Optional
from pathlib import Path
import questionary

from commands.base_command import BaseCommand
from core.database import import_extraction_session

class ImportHandler(BaseCommand):
    """Handle import commands for JSON extraction results"""
    
    def get_aliases(self) -> List[str]:
        return ["import", "load"]
    
    def execute(self, command_input: str) -> Optional[str]:
        """Execute import command"""
        parts = command_input.strip().split()
        
        if len(parts) == 1:
            # Interactive mode
            return self._interactive_import()
        else:
            # Direct file path provided
            json_file = parts[1]
            return self._import_file(json_file)
    
    def _interactive_import(self) -> str:
        """Interactive import mode"""
        json_file = questionary.path(
            "📁 Enter path to extraction JSON file:",
            validate=lambda x: Path(x).exists() or "File not found"
        ).ask()
        
        if not json_file:
            return self.format_warning(["Import cancelled"])
        
        return self._import_file(json_file)
    
    def _import_file(self, json_file: str) -> str:
        """Import JSON extraction file"""
        try:
            json_path = Path(json_file).expanduser().resolve()
            
            if not json_path.exists():
                return self.format_error([f"File not found: {json_file}"])
            
            result = import_extraction_session(str(json_path))
            
            return self.format_success([
                f"✅ Imported extraction session: {result['session_id']}",
                f"📋 URLs imported: {result['urls_imported']}",
                f"🗂️ Collection: {result['collection_name']}"
            ])
            
        except Exception as e:
            return self.format_error([f"Import failed: {str(e)}"])
    
    def get_help(self) -> str:
        """Return help text"""
        return self.format_info([
            "🔗 Remember Import Handler",
            "",
            "Usage:",
            "  import                    Interactive import",
            "  import <json_file>        Import specific file",
            "",
            "Imports JSON extraction results into Remember database"
        ])
