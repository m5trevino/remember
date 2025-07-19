#!/usr/bin/env python3
import sys
from pathlib import Path
from rich.console import Console
from core.visuals import format_grouped_output

sys.path.insert(0, str(Path(__file__).parent.absolute()))
from commands.command_registry import CommandRegistry

console = Console()

class RememberMemory:
    def __init__(self):
        self.registry = CommandRegistry()
        self.running = True

    def run(self):
        console.print("\n🔗 [bold cyan]REMEMBER - Command Line Interface[/bold cyan] 🔗\n")
        console.print(format_grouped_output([
            "System Ready. Type 'help' for commands.",
            "To start the web interface, type 'webui'."
        ], "info"))
        
        while self.running:
            try:
                command_input = input("remember> ").strip()
                if not command_input: continue
                if command_input.lower() in ['exit', 'quit', 'q']:
                    self.running = False
                    continue
                
                result = self.registry.execute_command(command_input)
                if result: console.print(result)
            except KeyboardInterrupt:
                self.running = False
            except Exception as e:
                console.print(format_grouped_output([f"❌ UNEXPECTED ERROR: {e}"], "error"))
        
        console.print(format_grouped_output(["Remember system shut down."], "success"))

if __name__ == "__main__":
    app = RememberMemory()
    app.run()
