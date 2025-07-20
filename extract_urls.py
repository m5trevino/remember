#!/usr/bin/env python3
"""
🚀 Remember URL Extractor - Standalone Script
Extracts content from URLs and saves in Remember-compatible format
"""

import sys
import asyncio
import aiohttp
import json
from pathlib import Path
from datetime import datetime
import time
from bs4 import BeautifulSoup
from readability import Document
import tiktoken

async def extract_url_content(session, url):
    """Extract content from a single URL."""
    try:
        print(f"🔗 Extracting: {url}")
        
        async with session.get(url, timeout=30) as response:
            if response.status == 200:
                content = await response.text()
                
                # Use readability to extract main content
                doc = Document(content)
                title = doc.title() or "Untitled"  # Ensure title is never None
                main_content = doc.summary() or content  # Fallback to raw content if summary fails
                
                # Clean up the content with BeautifulSoup
                soup = BeautifulSoup(main_content, 'html.parser')
                clean_text = soup.get_text() or "No content extracted"  # Ensure content is never empty
                
                # Estimate token count
                try:
                    encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
                    token_count = len(encoding.encode(clean_text))
                except:
                    token_count = len(clean_text.split()) * 1.3  # Rough estimate
                
                return {
                    "url": url,
                    "title": title,
                    "content": clean_text,
                    "html_content": main_content,
                    "character_count": len(clean_text),
                    "token_count": int(token_count),
                    "rating": 3,  # Default rating
                    "extracted_at": datetime.now().isoformat(),
                    "status": "success"
                }
            else:
                print(f"❌ HTTP {response.status} for {url}")
                return {"url": url, "status": "failed", "error": f"HTTP {response.status}"}
                
    except Exception as e:
        print(f"❌ Error extracting {url}: {e}")
        return {"url": url, "status": "failed", "error": str(e)}

async def main():
    """Main extraction function."""
    if len(sys.argv) != 2:
        print("Usage: python extract_urls.py <path_to_urls.txt>")
        print("Example: python extract_urls.py /home/flintx/remember/urls.txt")
        sys.exit(1)
    
    urls_file = Path(sys.argv[1])
    
    if not urls_file.exists():
        print(f"❌ URLs file not found: {urls_file}")
        sys.exit(1)
    
    # Read URLs
    with open(urls_file, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
    
    if not urls:
        print("❌ No URLs found in file")
        sys.exit(1)
    
    print(f"📋 Found {len(urls)} URLs to extract")
    
    # Create output directories
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    extractions_dir = Path.home() / "remember" / "extractions"
    extractions_dir.mkdir(exist_ok=True)
    
    session_dir = extractions_dir / f"session_{timestamp}"
    session_dir.mkdir(exist_ok=True)
    
    # Output files
    json_file = extractions_dir / f"extraction_{timestamp}.json"
    
    extraction_results = []
    successful = 0
    failed = 0
    
    # Extract content
    async with aiohttp.ClientSession() as session:
        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{len(urls)}] Processing {url}")
            
            result = await extract_url_content(session, url)
            extraction_results.append(result)
            
            if result["status"] == "success":
                successful += 1
                
                # Create individual markdown file
                md_filename = f"extracted_{i:03d}_{result['title'][:50].replace('/', '_').replace(':', '_')}.md"
                md_file = session_dir / md_filename
                
                with open(md_file, 'w', encoding='utf-8') as f:
                    f.write(f"# {result['title']}\n\n")
                    f.write(f"**URL:** [{result['url']}]({result['url']})\n")
                    f.write(f"**Extracted:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"**Characters:** {result['character_count']:,}\n")
                    f.write(f"**Tokens:** ~{result['token_count']:,}\n")
                    f.write(f"**Rating:** {'⭐' * result['rating']}\n\n")
                    f.write("---\n\n")
                    f.write(result['content'])
                
                # Update result with markdown file path for Remember import
                result["markdown_file"] = str(md_file)
                
                print(f"✅ Extracted: {result['title'][:60]}...")
                print(f"   📊 {result['character_count']:,} chars, ~{result['token_count']:,} tokens")
                print(f"   📄 Saved to: {md_file.name}")
                
            else:
                failed += 1
                print(f"❌ Failed: {result.get('error', 'Unknown error')}")
            
            # Small delay between requests
            await asyncio.sleep(1)
    
    # Save JSON file for Remember import
    remember_format = []
    for result in extraction_results:
        if result["status"] == "success":
            remember_format.append({
                "url": result["url"],
                "title": result["title"],
                "content": result["content"],
                "markdown_file": result["markdown_file"],
                "rating": result["rating"],
                "extracted_at": result["extracted_at"]
            })
    
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(remember_format, f, indent=2)
    
    # Results summary
    print(f"\n🎉 Extraction Complete!")
    print(f"📊 Results: {successful} successful, {failed} failed out of {len(urls)} total")
    print(f"💾 JSON saved to: {json_file}")
    print(f"📁 Markdown files in: {session_dir}")
    print(f"\n📥 To import into Remember:")
    print(f"   1. Switch to Projects mode")
    print(f"   2. Select your project")
    print(f"   3. Click '📥 Import Data'")
    print(f"   4. The latest extraction ({json_file.name}) will be imported automatically")

if __name__ == "__main__":
    asyncio.run(main())