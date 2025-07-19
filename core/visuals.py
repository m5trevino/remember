"""
🔗 Remember - Clean Visual System
Real borders, clean output, no bootise ANSI codes
"""
import sys
from typing import List

# Check if we're running in MCP mode
MCP_MODE = any(arg in ['mcp', '--mcp', 'mcp-server'] for arg in sys.argv)

def format_grouped_output(lines: List[str], message_type: str = "info") -> str:
    """Format multiple lines with clean borders"""
    if not lines:
        return ""
    
    # Clean borders without ANSI bootise
    if message_type == "error":
        border_char = "═"
        prefix = "❌"
    elif message_type == "success":
        border_char = "━"
        prefix = "✅"
    elif message_type == "warning":
        border_char = "─"
        prefix = "⚠️"
    else:
        border_char = "─"
        prefix = "ℹ️"
    
    # Find max line length
    max_len = max(len(line) for line in lines) + 4
    if max_len < 50:
        max_len = 50
    
    output = f"╔{border_char * (max_len - 2)}╗\n"
    for line in lines:
        padding = max_len - len(line) - 4
        output += f"║ {prefix} {line}{' ' * padding}║\n"
    output += f"╚{border_char * (max_len - 2)}╝\n"
    
    return output

def format_single_message(message: str, message_type: str = "info") -> str:
    """Format single message clean"""
    return format_grouped_output([message], message_type)

def format_url_extraction(url: str, title: str, status: str, char_count: int, output_file: str) -> str:
    """Format URL extraction results with clean borders"""
    if status == "success":
        status_color = "✅"
        rating = "🔥" if char_count > 5000 else "👍" if char_count > 1000 else "📝"
    else:
        status_color = "❌"
        rating = "💀"
    
    lines = [
        f"»»———-　　{title[:50]}　　———-««",
        f"🔗 {url}",
        f"{status_color} Status: {status.upper()}",
        f"📊 Content: {char_count:,} chars {rating}",
        f"💾 Saved: {output_file}",
        "̶̶̶̶  «̶ ̶̶̶ ̶ «̶ ̶̶̶ 　　　　 ̶ ̶ ̶»̶ ̶̶̶ ̶ »̶ ̶̶̶"
    ]
    
    return format_grouped_output(lines, "success" if status == "success" else "error")
