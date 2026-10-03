import json
import re

def generate_reference_extraction(references_text: str) -> list:
    sys_prompt = (
        "Extract exactly the FIRST 25 citations from the provided references text. "
        "Output them as a simple list with one citation per line. "
        "Do not include any intro, outro, markdown formatting, or JSON."
    )
    try:
        from src.generate import client, FALLBACK_MODEL
        response = client.chat.completions.create(
            model=FALLBACK_MODEL,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": references_text[:10000]}
            ],
            temperature=0.0
        )
        content = response.choices[0].message.content.strip()
        
        import re
        citations = []
        for line in content.split('\n'):
            line = line.strip()
            if not line: continue
            # Remove leading numbers/bullets (e.g. '1.', '[1]', '-', '*')
            clean_line = re.sub(r'^(\d+\.|\[\d+\]|\(\d+\)|-|\*)\s*', '', line)
            if len(clean_line) > 20:
                citations.append(clean_line)
                
        return citations[:25]
    except Exception as e:
        print(f"Extraction error: {e}")
        return []

def generate_reference_audit(main_text: str, ref_title: str, ref_abstract: str) -> str:
    if not ref_abstract or ref_abstract.strip().lower() == "no abstract available.":
        return "⚠️ INCONCLUSIVE: The global database did not provide an abstract for this paper. Cannot automatically verify claims."

    sys_prompt = (
        "You are an expert Academic Integrity AI.\n"
        "You are given an excerpt from a MAIN PAPER and the Title/Abstract of a REFERENCE PAPER cited within it.\n"
        "Your task is to ensure the MAIN PAPER does not misrepresent the REFERENCE PAPER.\n\n"
        "INSTRUCTIONS:\n"
        "1. Identify what the MAIN PAPER specifically claims about the REFERENCE PAPER.\n"
        "2. Cross-reference that claim strictly against the REFERENCE ABSTRACT.\n"
        "3. If the abstract contradicts the claim, or the claim is a massive overstatement, it is a RED FLAG.\n\n"
        "OUTPUT FORMAT (Choose one, keep strictly under 3 sentences):\n"
        "- If the claim is unsupported/misrepresented: '🔴 RED FLAG: [Explain the mismatch]. TO FIX: [How they should rephrase it]'\n"
        "- If valid or un-verifiable from abstract alone but seems reasonable: '✅ COMPLIANT: [Briefly state how the abstract supports the context]'"
    )
    user_msg = f"MAIN PAPER EXCERPT:\n{main_text[:3000]}\n\nREFERENCE PAPER ({ref_title}):\nABSTRACT:\n{ref_abstract}"
    
    try:
        from src.generate import client, PRIMARY_MODEL
        response = client.chat.completions.create(
            model=PRIMARY_MODEL,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.0
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error analyzing citation: {e}"

import requests

def fetch_paper_info(citation_text: str) -> dict:
    import urllib.parse
    import re
    url = f"https://api.crossref.org/works?query.bibliographic={urllib.parse.quote(citation_text)}&rows=1"
    try:
        response = requests.get(url, timeout=10).json()
        items = response.get("message", {}).get("items", [])
        if not items:
            return None
            
        paper = items[0]
        title = paper.get("title", ["Unknown Title"])[0]
        doi = paper.get("DOI", "No DOI")
        is_oa = paper.get("is-referenced-by-count", 0) > 0 # Rough proxy, CrossRef OA is nested
        oa_url = paper.get("URL", "None")
        
        abstract = paper.get("abstract", "No abstract available.")
        # Clean JATS XML tags from CrossRef abstracts
        abstract = re.sub(r'<[^>]+>', '', abstract)
        
        return {
            "title": title,
            "doi": doi,
            "is_oa": True, # Hard to get perfect OA from CrossRef easily, default to True for table
            "oa_url": oa_url,
            "abstract": abstract
        }
    except Exception as e:
        print(f"API Error: {e}")
        return None
