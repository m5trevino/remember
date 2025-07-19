#!/bin/bash
"""
🏛️ Legal AI System Setup
Deploy all infrastructure files and verify system readiness
"""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}🏛️ Legal AI System Setup Starting...${NC}"

# Define paths
REMEMBER_DIR="$HOME/remember"
BACKUP_DIR="$HOME/remember_backup_$(date +%Y%m%d_%H%M%S)"

# Create backup of existing files
if [ -d "$REMEMBER_DIR" ]; then
    echo -e "${YELLOW}📋 Backing up existing Remember directory...${NC}"
    cp -r "$REMEMBER_DIR" "$BACKUP_DIR"
    echo -e "${GREEN}✅ Backup created: $BACKUP_DIR${NC}"
fi

# Ensure directory exists
mkdir -p "$REMEMBER_DIR"
cd "$REMEMBER_DIR"

echo -e "${BLUE}📦 Installing required Python packages...${NC}"

# Install required packages
pip3 install --user requests beautifulsoup4 readability-lxml html2text questionary chromadb tiktoken pathlib rich

echo -e "${BLUE}🔧 Deploying Groq infrastructure files...${NC}"

# Check if files exist and create them if needed
FILES_TO_CHECK=(
    "groq_client.py"
    "request_router.py" 
    "api_key_manager.py"
    "proxy_manager.py"
    "context_manager.py"
    "commands/legal_handler.py"
    "commands/command_registry.py"
    "commands/help_handler.py"
)

for file in "${FILES_TO_CHECK[@]}"; do
    if [ ! -f "$file" ]; then
        echo -e "${YELLOW}⚠️  Missing: $file${NC}"
        echo -e "${RED}❌ Please copy the artifact files to ~/remember/${NC}"
    else
        echo -e "${GREEN}✅ Found: $file${NC}"
    fi
done

echo -e "${BLUE}🔑 Checking .env file configuration...${NC}"

# Check .env file
if [ ! -f "$REMEMBER_DIR/.env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found in $REMEMBER_DIR${NC}"
    echo -e "${BLUE}📝 Creating .env template...${NC}"
    
    cat > "$REMEMBER_DIR/.env" << 'EOF'
# 🦚 REMEMBER API CONFIGURATION
# GROQ API Keys for rotation
GROQ_API_KEY=your_first_groq_key_here
GROQ_API_KEY_1=your_second_groq_key_here
GROQ_API_KEY_2=your_third_groq_key_here
GROQ_API_KEY_3=your_fourth_groq_key_here
GROQ_API_KEY_4=your_fifth_groq_key_here
GROQ_API_KEY_5=your_sixth_groq_key_here
GROQ_API_KEY_6=your_seventh_groq_key_here
GROQ_API_KEY_7=your_eighth_groq_key_here
GROQ_API_KEY_8=your_ninth_groq_key_here
GROQ_API_KEY_9=your_tenth_groq_key_here
GROQ_API_KEY_10=your_eleventh_groq_key_here
GROQ_API_KEY_11=your_twelfth_groq_key_here
GROQ_API_KEY_12=your_thirteenth_groq_key_here

# Application Configuration
DEBUG=true
ENVIRONMENT=development
LOG_LEVEL=info

# Server Configuration
HOST=127.0.0.1
PORT=8000
EOF
    
    echo -e "${YELLOW}📝 Please edit $REMEMBER_DIR/.env with your actual Groq API keys${NC}"
else
    echo -e "${GREEN}✅ .env file found${NC}"
    
    # Count API keys
    KEY_COUNT=$(grep -c "^GROQ_API_KEY" "$REMEMBER_DIR/.env")
    echo -e "${BLUE}🔑 Found $KEY_COUNT Groq API keys${NC}"
    
    if [ "$KEY_COUNT" -lt 5 ]; then
        echo -e "${YELLOW}⚠️  Recommend at least 5 API keys for optimal rotation${NC}"
    fi
fi

echo -e "${BLUE}🧪 Testing system integration...${NC}"

# Create test script
cat > "$REMEMBER_DIR/test_legal_system.py" << 'EOF'
#!/usr/bin/env python3
"""Test legal system integration"""

import sys
import os
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent.absolute()))

def test_imports():
    """Test all critical imports"""
    try:
        print("🧪 Testing imports...")
        
        # Test infrastructure imports
        from groq_client import GroqClient
        from request_router import RequestRouter
        from api_key_manager import APIKeyManager
        from proxy_manager import ProxyManager
        from context_manager import ContextManager
        
        print("✅ Groq infrastructure imports successful")
        
        # Test command imports
        from commands.legal_handler import LegalHandler
        from commands.command_registry import CommandRegistry
        
        print("✅ Command system imports successful")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def test_api_keys():
    """Test API key loading"""
    try:
        from api_key_manager import APIKeyManager
        
        manager = APIKeyManager()
        key_count = len(manager.api_keys)
        
        if key_count > 0:
            print(f"✅ Loaded {key_count} API keys")
            return True
        else:
            print("❌ No API keys loaded - check .env file")
            return False
            
    except Exception as e:
        print(f"❌ API key test failed: {e}")
        return False

def test_groq_connection():
    """Test Groq connection"""
    try:
        from groq_client import GroqClient
        
        client = GroqClient()
        success, response, debug = client.simple_chat("Test", "Say OK")
        
        if success:
            print("✅ Groq connection successful")
            return True
        else:
            print(f"❌ Groq connection failed: {debug}")
            return False
            
    except Exception as e:
        print(f"❌ Groq test failed: {e}")
        return False

def test_legal_handler():
    """Test legal handler"""
    try:
        from commands.legal_handler import LegalHandler
        
        handler = LegalHandler()
        help_output = handler.get_help()
        
        if help_output:
            print("✅ Legal handler initialized")
            return True
        else:
            print("❌ Legal handler initialization failed")
            return False
            
    except Exception as e:
        print(f"❌ Legal handler test failed: {e}")
        return False

if __name__ == "__main__":
    print("\n🧪 LEGAL SYSTEM INTEGRATION TEST\n")
    
    tests = [
        ("Import Test", test_imports),
        ("API Key Test", test_api_keys),
        ("Groq Connection", test_groq_connection),
        ("Legal Handler", test_legal_handler)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}:")
        if test_func():
            passed += 1
    
    print(f"\n📊 TEST RESULTS: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All tests passed! Legal AI system is ready!")
    else:
        print("⚠️  Some tests failed. Check configuration and dependencies.")
EOF

# Make test script executable
chmod +x "$REMEMBER_DIR/test_legal_system.py"

echo -e "${BLUE}🧪 Running integration test...${NC}"
cd "$REMEMBER_DIR"

# Run the integration test
python3 test_legal_system.py

echo -e "${BLUE}🔧 Setting up Remember CLI integration...${NC}"

# Check if main.py exists
if [ -f "$REMEMBER_DIR/main.py" ]; then
    echo -e "${GREEN}✅ Remember CLI main.py found${NC}"
else
    echo -e "${YELLOW}⚠️  Remember CLI main.py not found${NC}"
    echo -e "${BLUE}📝 Please ensure main.py is in the Remember directory${NC}"
fi

# Create quick start script
cat > "$REMEMBER_DIR/start_legal_ai.sh" << 'EOF'
#!/bin/bash
echo "🏛️ Starting Legal AI System..."
cd ~/remember
python3 main.py
EOF

chmod +x "$REMEMBER_DIR/start_legal_ai.sh"

# Create usage guide
cat > "$REMEMBER_DIR/LEGAL_AI_USAGE.md" << 'EOF'
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
EOF

echo -e "${GREEN}✅ Usage guide created: $REMEMBER_DIR/LEGAL_AI_USAGE.md${NC}"

echo -e "${BLUE}📋 Final system check...${NC}"

# Check directory structure
echo -e "${BLUE}📁 Directory structure:${NC}"
ls -la "$REMEMBER_DIR" | head -20

echo -e "\n${GREEN}🎉 LEGAL AI SYSTEM SETUP COMPLETE!${NC}"
echo -e "\n${BLUE}📋 Next Steps:${NC}"
echo -e "1. ${YELLOW}Edit .env file with your Groq API keys${NC}"
echo -e "2. ${YELLOW}Copy all artifact files to ~/remember/${NC}" 
echo -e "3. ${YELLOW}Run: cd ~/remember && python3 test_legal_system.py${NC}"
echo -e "4. ${YELLOW}Start system: ./start_legal_ai.sh${NC}"
echo -e "5. ${YELLOW}Import your 166 extracted documents${NC}"
echo -e "6. ${YELLOW}Run: legal batch (for analysis)${NC}"

echo -e "\n${GREEN}🏛️ Ready to process legal research and build case arguments!${NC}"
echo -e "${BLUE}📖 See LEGAL_AI_USAGE.md for detailed instructions${NC}"