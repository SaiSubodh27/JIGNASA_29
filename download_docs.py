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

    # Generate ACM Code of Ethics PDF since there isn't a direct PDF link
    acm_path = Path("data/raw/acm_code_of_ethics.pdf")
    if not acm_path.exists():
        try:
            print("\nGenerating ACM Code of Ethics PDF...")
            from fpdf import FPDF
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("helvetica", size=12)
            acm_text = "ACM Code of Ethics and Professional Conduct\n\n1. GENERAL ETHICAL PRINCIPLES.\n1.1 Contribute to society and to human well-being, acknowledging that all people are stakeholders in computing.\n1.2 Avoid harm. In this document, \"harm\" means negative consequences, especially when those consequences are significant and unjust. Examples include unjustified physical or mental injury, unjustified destruction or disclosure of information, and unjustified damage to property, reputation, and the environment.\n1.3 Be honest and trustworthy.\n1.4 Be fair and take action not to discriminate.\n1.5 Respect the work required to produce new ideas, inventions, creative works, and computing artifacts. Creators of new ideas, algorithms, and software should be properly credited. Intellectual property rights must be respected. Do not claim ownership of work that is not yours. Use of software and mechanisms must respect licensing agreements and open source requirements.\n1.6 Respect privacy. Computing professionals should only use personal information for legitimate ends and without violating the rights of individuals and groups.\n1.7 Honor confidentiality.\n\n2. PROFESSIONAL RESPONSIBILITIES.\n2.1 Strive to achieve high quality in both the processes and products of professional work.\n2.2 Maintain high standards of professional competence, conduct, and ethical practice.\n2.3 Know and respect existing rules pertaining to professional work.\n2.4 Accept and provide appropriate professional review.\n2.5 Give comprehensive and thorough evaluations of computer systems and their impacts, including analysis of possible risks.\n2.6 Perform work only in areas of competence.\n2.7 Foster public awareness and understanding of computing, related technologies, and their consequences.\n2.8 Access computing and communication resources only when authorized or when compelled by the public good.\n2.9 Design and implement systems that are robustly and usably secure.\n\n3. PROFESSIONAL LEADERSHIP PRINCIPLES.\n3.1 Ensure that the public good is the central concern during all professional computing work.\n3.2 Articulate, encourage acceptance of, and evaluate fulfillment of social responsibilities by members of the organization or group.\n3.3 Manage personnel and resources to enhance the quality of working life.\n3.4 Articulate, apply, and support policies and processes that reflect the principles of the Code.\n3.5 Create opportunities for members of the organization or group to grow as professionals.\n3.6 Use care when modifying or retiring systems.\n3.7 Recognize and take special care of systems that become integrated into the infrastructure of society.\n\n4. COMPLIANCE WITH THE CODE.\n4.1 Uphold, promote, and respect the principles of the Code.\n4.2 Treat violations of the Code as inconsistent with membership in the ACM."
            pdf.multi_cell(0, 10, acm_text)
            pdf.output(acm_path)
            print("  [OK]   Generated acm_code_of_ethics.pdf")
        except Exception as e:
            print(f"  [WARN] Failed to generate ACM PDF: {e}")

    if success < len(manifest):
        print(
            "\nNote: Some PDFs could not be downloaded automatically (access "
            "restrictions). Please download them manually and place them in "
            "data/raw/ using the filenames in data/manifest.json."
        )


if __name__ == "__main__":
    main()
