# 🏛️ Legal AI System Usage Guide

## Quick Start

1. **Start the system:**
   ```bash
   cd ~/remember
   ./start_legal_ai.sh
   ```

2. **Basic Legal Commands:**
   ```bash
   remember> legal batch          # Process all documents with custom prompt
   remember> legal analyze        # Interactive document analysis
   remember> legal chat           # Start legal chat session
   ```

## Workflow Examples

### Process Your 166 Extracted Documents
1. Import extraction results: `import extraction_results_YYYYMMDD_HHMMSS.json`
2. Batch process: `legal batch`
3. Enter your analysis prompt: "Analyze for service of process defects and violations"
4. Review results and summaries

### Interactive Legal Research
1. Search documents: `legal analyze service process`
2. Select documents to analyze
3. Enter custom prompt for analysis
4. Review extracted insights

### Legal Chat Session
1. Start chat: `legal chat`
2. Ask questions about legal research
3. Get AI analysis and insights
4. Type 'exit' to end session

## System Features

- **Deck Rotation:** 13 Groq API keys rotate automatically
- **Proxy Management:** Mobile/residential/local IP rotation
- **Auto-chunking:** Large documents processed automatically
- **Context Management:** Smart token limit handling
- **Resilient Processing:** Never breaks, adapts to failures

## File Locations

- **Configuration:** `~/remember/.env`
- **Results:** `~/remember/legal_batch_*.json`
- **Database:** `~/remember_db/`
- **Logs:** Terminal output

## Troubleshooting

1. **Import errors:** Ensure all files copied to ~/remember/
2. **API failures:** Check .env file has valid Groq keys
3. **Proxy issues:** System will fallback to local IP
4. **Context too large:** System auto-chunks content

## Commands Reference

### Data Management
- `extract` - Run URL scraper
- `import <file>` - Import extraction results
- `list` - Show available files
- `search <query>` - Search database

### Legal Analysis
- `legal batch` - Batch process with custom prompt
- `legal analyze [query]` - Interactive analysis
- `legal chat` - Legal chat session

### System Info
- `stats` - Show system statistics
- `help` - Show all commands

Ready to process your legal research and build bulletproof arguments! 🏛️
