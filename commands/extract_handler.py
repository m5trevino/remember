import requests
import subprocess
from bs4 import BeautifulSoup
from readability import Document
import json
from datetime import datetime
from pathlib import Path
import re
import time
import random
import fitz  # PyMuPDF
from typing import List
from commands.base_command import BaseCommand

# --- Configuration ---
RED, GREEN, BLUE, YELLOW, BOLD, RESET = '\033[91m', '\033[92m', '\033[94m', '\033[93m', '\033[1m', '\033[0m'
REMEMBER_DIR = Path.home() / "remember"
CONTENT_DIR = REMEMBER_DIR / "scraped_content"
PDF_DIR = REMEMBER_DIR / "pdfs"
URLS_FILE = REMEMBER_DIR / "urls.txt"

# --- CORRECTED PROXY_ORDER LIST - NO STRAY CHARACTERS ---
PROXY_ORDER = [
    ("Local", None),
    ("Mobile", "http://52fb2fcd77ccbf54b65c:5a02792bf800a049@gw.dataimpulse.com:823"),
    ("Residential", "http://0aa180faa467ad67809b__cr.us:6dc612d4a08ca89d@gw.dataimpulse.com:823")
]

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
]

class ExtractHandler(BaseCommand):
    def get_aliases(self) -> List[str]:
        return ["extract", "scrape", "grab"]

    def execute(self, command_input: str) -> str:
        for d in [CONTENT_DIR, PDF_DIR]: d.mkdir(exist_ok=True, parents=True)
        try:
            with open(URLS_FILE, 'r') as f:
                urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            if not urls: return self.format_error(["urls.txt is empty!"])
        except FileNotFoundError:
            return self.format_error([f"urls.txt not found in {REMEMBER_DIR}!"])

        print_border_section([f"🚀 TACTICAL EXTRACTION INITIATED", f"📋 URLs: {len(urls)}", f"⚡️ Strategy: Local First"])
        
        all_results, failed_urls = [], []
        for i, url in enumerate(urls, 1):
            print(f"\n{BLUE}--- Engaging URL {i}/{len(urls)}: {url[:70]}... ---{RESET}")
            success = False
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
                        pdf_bytes = response.content
                        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                        pdf_text = "".join(page.get_text() for page in doc)
                        doc.close()
                        
                        md_filename = self._clean_filename(url, "md")
                        md_filepath = CONTENT_DIR / md_filename
                        title = f"[PDF] {Path(url).name}"
                        with open(md_filepath, 'w', encoding='utf-8') as f:
                            f.write(f"# {title}\n\n_Source: {url}_\n\n---\n\n{pdf_text}")
                        
                        all_results.append({"url": url, "title": title, "rating": self._calculate_rating(len(pdf_text)),
                                            "markdown_file": str(md_filepath), "content": pdf_text})
                        print(f"{GREEN}✅ Success (PDF):{RESET} Extracted {len(pdf_text):,} chars")
                        success = True
                        break

                    clean_content = response.text.replace('\x00', '')
                    doc = Document(clean_content)
                    title = doc.title()
                    best_content = BeautifulSoup(doc.summary(), 'html.parser').get_text(separator='\n', strip=True)
                    
                    if not best_content or len(best_content) < 100:
                        soup = BeautifulSoup(clean_content, 'html.parser')
                        [tag.decompose() for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"])]
                        best_content = soup.get_text(separator='\n', strip=True)
                    
                    md_filename = self._clean_filename(url, "md")
                    md_filepath = CONTENT_DIR / md_filename
                    with open(md_filepath, 'w', encoding='utf-8') as f:
                        f.write(f"# {title}\n\n_Source: {url}_\n\n---\n\n{best_content}")
                    
                    rating = self._calculate_rating(len(best_content))
                    all_results.append({"url": url, "title": title, "rating": rating,
                                        "markdown_file": str(md_filepath), "content": best_content})
                    print(f"{GREEN}✅ Success (HTML):{RESET} Saved {len(best_content):,} chars")
                    success = True
                    break

                except requests.RequestException as e: print(f"{RED}   - Network Error: {e}{RESET}"); time.sleep(1)
                except Exception as e: print(f"{RED}   - Critical Error: {e}{RESET}"); break
            
            if not success: failed_urls.append(url)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = REMEMBER_DIR / f'extraction_results_{timestamp}.json'
        with open(results_file, 'w', encoding='utf-8') as f: json.dump(all_results, f, indent=2)
        
        summary_text = ["📊 MISSION SUMMARY", f"✅ Successful: {len(all_results)}/{len(urls)}", f"❌ Failed: {len(failed_urls)}/{len(urls)}", f"💾 JSON Log: {results_file.name}"]
        if failed_urls:
            summary_text.append("Failed URLs:"); summary_text.extend([f"  - {u}" for u in failed_urls])
        
        return self.format_info(summary_text)

    def _clean_filename(self, url: str, extension: str) -> str:
        clean = re.sub(r'^https?:\/\/', '', url).replace('/', '_')
        clean = re.sub(r'[\\?%*:|"<>]', '', clean)
        return f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{clean[:70]}.{extension}"

    def _calculate_rating(self, length: int) -> int:
        if length > 8000: return 5;
        if length > 4000: return 4;
        if length > 1500: return 3;
        if length > 500: return 2;
        return 1

    def get_help(self) -> str:
        return self.format_info(["Runs the resilient URL scraper on urls.txt."])

def print_border_section(content):
    max_len = max(len(re.sub(r'\033\[[0-9;]*m', '', line)) for line in content) if content else 0
    print("╔" + "═" * (max_len + 2) + "╗")
    for line in content:
        plain_line = re.sub(r'\033\[[0-9;]*m', '', line)
        padding = " " * (max_len - len(plain_line))
        print(f"║ {line}{padding} ║")
    print("╚" + "═" * (max_len + 2) + "╝")
