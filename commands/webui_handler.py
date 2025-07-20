import subprocess
from pathlib import Path
from typing import List
from commands.base_command import BaseCommand

class WebuiHandler(BaseCommand):
    """Handles launching the FastAPI web UI."""
    
    def get_aliases(self) -> List[str]:
        return ["webui", "gui", "server"]

    def execute(self, command_input: str) -> str:
        remember_dir = Path.home() / "remember"
        web_ui_script = remember_dir / "remember_web_ui.py"

        if not web_ui_script.exists():
            return self.format_error([f"Web UI script not found!", f"Expected: {web_ui_script}"])

        try:
            print("\n🚀 Launching Legal AI War Room Web UI...")
            print(f"   Serving from: {web_ui_script}")
            print("   URL: http://localhost:8080")
            print("   Press Ctrl+C IN THIS TERMINAL to shut down the web server.")
            
            subprocess.run(
                ["python3", str(web_ui_script)],
                cwd=str(remember_dir),
                check=True
            )
            return self.format_success(["Web UI server has been shut down."])
        except KeyboardInterrupt:
            return self.format_success(["\nWeb UI server shut down by user."])
        except Exception as e:
            return self.format_error([f"Failed to launch web UI: {e}"])

    def get_help(self) -> str:
        return self.format_info(["Launches the Legal AI War Room web interface."])
