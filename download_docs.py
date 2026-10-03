"""
download_docs.py - Download official ethics PDFs listed in data/manifest.json.
Run this once before ingest.py.
"""

import json
import os
import time
from pathlib import Path
import urllib.request
import urllib.error


MANIFEST_PATH = "data/manifest.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; ResearchEthicsAssistant/1.0; "
        "+https://github.com/research-ethics-assistant)"
    )
}


def download_file(url: str, dest: Path, max_retries: int = 3) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"  [SKIP] Already exists: {dest.name}")
        return True

    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            with open(dest, "wb") as f:
                f.write(data)
            print(f"  [OK]   Downloaded {dest.name} ({len(data)//1024} KB)")
            return True
        except Exception as e:
            wait = 2 ** attempt
            print(f"  [WARN] Attempt {attempt+1} failed: {e}. Retrying in {wait}s …")
            time.sleep(wait)

    print(f"  [FAIL] Could not download {url}")
    return False


def main():
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)

    print(f"Downloading {len(manifest)} document(s) …\n")
    success = 0
    for doc in manifest:
        url = doc.get("url", "")
        dest = Path(doc["file"])
        print(f">> {doc['title']}")
        if not url:
            print("  [SKIP] No URL in manifest")
            continue
        if download_file(url, dest):
            success += 1
        time.sleep(1)  # be polite

    print(f"\n{success}/{len(manifest)} documents downloaded.")
    if success < len(manifest):
        print(
            "\nNote: Some PDFs could not be downloaded automatically (access "
            "restrictions). Please download them manually and place them in "
            "data/raw/ using the filenames in data/manifest.json."
        )


if __name__ == "__main__":
    main()
