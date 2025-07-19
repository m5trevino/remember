#!/usr/bin/env python3
import requests
import subprocess
from bs4 import BeautifulSoup
from readability import Document
import html2text
import json
from datetime import datetime

# Show banner
subprocess.run(["cfonts", "REMEMBER", "--font", "chrome", "--colors", "cyan,magenta", "--align", "center"])

# Proxy choices
PROXIES = {
    "1": ("Local", None),
    "2": ("Residential", "http://0aa180faa467ad67809b__cr.us:6dc612d4a08ca89d@gw.dataimpulse.com:823"),
    "3": ("Mobile", "http://52fb2fcd77ccbf54b65c:5a02792bf800a049@gw.dataimpulse.com:823")
}

# Choose proxy
print("\n🌐 Select connection type:")
for key, (name, _) in PROXIES.items():
    print(f"  {key}. {name}")

choice = input("\nEnter choice (1-3): ").strip()
if choice not in PROXIES:
    print("Invalid choice")
    exit(1)

proxy_name, proxy_url = PROXIES[choice]
print(f"📡 Using: {proxy_name}")

# Setup session
session = requests.Session()
if proxy_url:
    session.proxies = {"http": proxy_url, "https": proxy_url}
session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

# Load URLs
with open('urls.txt', 'r') as f:
    urls = [line.strip() for line in f if line.strip()]

print(f"\n🔗 Testing {len(urls)} URLs...\n")

results = []

for url in urls:
    print(f"Testing: {url}")
    
    try:
        # Fetch
        response = session.get(url, timeout=30)
        content = response.text
        print(f"  ✅ Fetched {len(content)} chars")
        
        # Method 1: BeautifulSoup
        soup = BeautifulSoup(content, 'html.parser')
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        bs_text = soup.get_text()
        bs_clean = '\n'.join(line.strip() for line in bs_text.splitlines() if line.strip())
        
        # Method 2: Readability
        doc = Document(content)
        read_html = doc.summary()
        read_soup = BeautifulSoup(read_html, 'html.parser')
        read_text = read_soup.get_text()
        
        # Method 3: html2text
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        markdown = h.handle(content)
        
        # Results
        url_result = {
            "url": url,
            "beautifulsoup": {"length": len(bs_clean), "lines": len(bs_clean.split('\n'))},
            "readability": {"length": len(read_text), "lines": len(read_text.split('\n')), "title": doc.title()},
            "html2text": {"length": len(markdown), "lines": len(markdown.split('\n'))}
        }
        
        print(f"  📊 BS: {len(bs_clean)} chars | Readability: {len(read_text)} chars | HTML2Text: {len(markdown)} chars")
        results.append(url_result)
        
    except Exception as e:
        print(f"  ❌ Failed: {e}")
    
    print()

# Save results
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
with open(f'results_{timestamp}.json', 'w') as f:
    json.dump(results, f, indent=2)

print(f"💾 Results saved to results_{timestamp}.json")
print(f"📊 Processed {len(results)}/{len(urls)} URLs successfully")
