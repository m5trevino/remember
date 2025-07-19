#!/usr/bin/env python3
import requests
import subprocess
from bs4 import BeautifulSoup
from readability import Document
import html2text
import json
from datetime import datetime
from pathlib import Path
import re
import time
import random

# --- Configuration ---
RED, GREEN, BLUE, YELLOW, BOLD, RESET = '\033[91m', '\033[92m', '\033[94m', '\033[93m', '\033[1m', '\033[0m'
REMEMBER_DIR = Path.home() / "remember"
CONTENT_DIR = REMEMBER_DIR / "scraped_content"
PDF_DIR = REMEMBER_DIR / "pdfs"
URLS_FILE = REMEMBER_DIR / "urls.txt"

# --- NEW TACTICAL CONNECTION ORDER ---
# We try Local first, as it's the most likely to succeed against aggressive blocks.
PROXY_ORDER = [
    ("Local", None),
    ("Mobile", "http://52fb2fcd77ccbf54b65c:5a02792bf800a049@gw.dataimpulse.com:823"),
    ("Residential", "http://0aa180faa467ad67809b__cr.us:6dc612d4a08ca89d@gw.dataimpulse.com:823")
]

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'
]

# --- Helper Functions ---
def print_border_section(content):
    print("╔" + "═" * 78 + "╗")
    for line in content: print(f"║ {line:<76} ║")
    print("╚" + "═" * 78 + "╝")

def clean_filename(url: str, extension: str) -> str:
    clean_part = re.sub(r'^https?:\/\/', '', url).replace('/', '_')
    clean_part = re.sub(r'[\\?%*:|"<>]', '', clean_part)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{timestamp}_{clean_part[:70]}.{extension}"

def calculate_rating(length: int) -> int:
    if length > 8000: return 5
    if length > 4000: return 4
    if length > 1500: return 3
    if length > 500: return 2
    return 1

# --- Main Execution ---
def main():
    for d in [REMEMBER_DIR, CONTENT_DIR, PDF_DIR]: d.mkdir(exist_ok=True)
    
    try:
        with open(URLS_FILE, 'r') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except FileNotFoundError:
        print(f"{RED}{BOLD}❌ urls.txt not found!{RESET}"); return

    print_border_section([f"🚀 TACTICAL EXTRACTION INITIATED", f"📋 URLs: {len(urls)}", f"⚡️ Strategy: Local First"])

    all_results, failed_urls = [], []
    
    for i, url in enumerate(urls, 1):
        print(f"\n{BLUE}--- Engaging URL {i}/{len(urls)}: {url[:70]}... ---{RESET}")
        success = False
        # Iterate through the tactical connection order
        for attempt, (proxy_name, proxy_url) in enumerate(PROXY_ORDER):
            print(f"{YELLOW}  -> Attempt {attempt + 1}/{len(PROXY_ORDER)} via {proxy_name}...{RESET}")
            
            try:
                session = requests.Session()
                session.headers.update({'User-Agent': random.choice(USER_AGENTS)})
                if proxy_url: session.proxies = {"http": proxy_url, "https": proxy_url}

                response = session.get(url, timeout=30, stream=True)
                response.raise_for_status()
                
                content_type = response.headers.get('Content-Type', '').lower()
                if 'application/pdf' in content_type:
                    pdf_filename = clean_filename(url, "pdf")
                    pdf_filepath = PDF_DIR / pdf_filename
                    with open(pdf_filepath, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192): f.write(chunk)
                    all_results.append({"url": url, "title": f"[PDF] {Path(url).name}", "rating": 3,
                                        "markdown_file": str(pdf_filepath), "content": f"PDF saved: {pdf_filepath}"})
                    print(f"{GREEN}✅ Success (PDF):{RESET} Downloaded to {pdf_filename}")
                    success = True
                    break

                clean_content = response.text.replace('\x00', '')

                doc = Document(clean_content)
                title = doc.title()
                best_content = BeautifulSoup(doc.summary(), 'html.parser').get_text(separator='\n', strip=True)

                if not best_content: # Fallback
                    best_content = BeautifulSoup(clean_content, 'html.parser').get_text(separator='\n', strip=True)

                md_filename = clean_filename(url, "md")
                md_filepath = CONTENT_DIR / md_filename
                with open(md_filepath, 'w', encoding='utf-8') as f:
                    f.write(f"# {title}\n\n_Source: {url}_\n\n---\n\n{best_content}")
                
                rating = calculate_rating(len(best_content))
                all_results.append({"url": url, "title": title, "rating": rating,
                                    "markdown_file": str(md_filepath), "content": best_content})
                print(f"{GREEN}✅ Success (HTML):{RESET} Saved {len(best_content):,} chars. Rating: {rating}/5")
                success = True
                break

            except requests.RequestException as e:
                print(f"{RED}   - Network Error: {e}{RESET}")
                time.sleep(1)
            except Exception as e:
                print(f"{RED}   - Critical Parse Error: {e}{RESET}")
                break
        
        if not success:
            print(f"{RED}❌ FAILED FINAL:{RESET} All connection methods failed for this URL.")
            failed_urls.append(url)

    # --- Final Summary ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = REMEMBER_DIR / f'extraction_results_{timestamp}.json'
    with open(results_file, 'w', encoding='utf-8') as f: json.dump(all_results, f, indent=2)

    print_border_section([
        "📊 MISSION SUMMARY",
        f"✅ Successful: {GREEN}{len(all_results)}/{len(urls)}{RESET}",
        f"❌ Failed:     {RED}{len(failed_urls)}/{len(urls)}{RESET}",
        f"💾 JSON Log: {results_file.name}",
    ])
    if failed_urls:
        print(f"{YELLOW}The following URLs could not be reached:{RESET}")
        for failed_url in failed_urls: print(f"  - {failed_url}")

if __name__ == "__main__":
    main()
