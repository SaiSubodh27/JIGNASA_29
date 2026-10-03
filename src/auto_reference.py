import json
import re

def generate_reference_extraction(references_text: str) -> list:
    sys_prompt = "Extract up to 25 individual citation strings from the following references section. Return ONLY a JSON list of strings (e.g. [\"citation 1\", \"citation 2\"]). Output absolutely nothing else."
    try:
        from src.generate import client, FALLBACK_MODEL
        response = client.chat.completions.create(
            model=FALLBACK_MODEL,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": references_text[:6000]}
            ],
            temperature=0.0
        )
        content = response.choices[0].message.content.strip()
        
        # 1. Try strict JSON parse
        match = re.search(r'\[.*\]', content, re.DOTALL)
        if match:
            try:
                citations = json.loads(match.group(0))
                if isinstance(citations, list) and len(citations) > 0:
                    return citations[:25]
            except:
                pass
                
        # 2. Try quote extraction
        strings = re.findall(r'"([^"]{20,})"', content)
        if strings:
            return strings[:25]
            
        # 3. Try line-by-line fallback
        lines = [line.strip() for line in content.split('\n') if len(line.strip()) > 20]
        # Filter out lines that look like conversational AI filler
        lines = [l for l in lines if not l.lower().startswith("here are") and not l.lower().startswith("i have extracted")]
        if lines:
            return lines[:25]
            
        return []
            
    except Exception as e:
        print(f"Extraction error: {e}")
        return []

def generate_reference_audit(main_text: str, ref_title: str, ref_abstract: str) -> str:
    sys_prompt = (
        "You are a Citation Verification AI.\n"
        "You are given an excerpt from a MAIN PAPER and the Title/Abstract of a REFERENCE PAPER cited within it.\n"
        "1. Check for RED FLAGS: Does the main paper misrepresent or misuse this reference?\n"
        "2. If there's a red flag, briefly state WHAT TO FIX.\n"
        "3. If compliant, state '✅ Compliant' and briefly say why.\n"
        "Keep it strictly under 3 sentences. Be extremely concise and direct."
    )
    user_msg = f"MAIN PAPER EXCERPT:\n{main_text[:2000]}\n\nREFERENCE PAPER ({ref_title}):\nABSTRACT:\n{ref_abstract}"
    
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
    url = f"https://api.openalex.org/works?search={citation_text}"
    try:
        response = requests.get(url, timeout=10).json()
        if not response.get("results"):
            return None
            
        paper = response["results"][0]
        title = paper.get("title", "Unknown Title")
        doi = paper.get("doi", "No DOI")
        is_oa = paper.get("open_access", {}).get("is_oa", False)
        oa_url = paper.get("open_access", {}).get("oa_url", "None")
        
        abstract_idx = paper.get("abstract_inverted_index", {})
        abstract = "No abstract available."
        if abstract_idx:
            words = []
            for word, positions in abstract_idx.items():
                for pos in positions:
                    words.append((pos, word))
            words.sort()
            abstract = " ".join([w[1] for w in words])
            
        return {
            "title": title,
            "doi": doi,
            "is_oa": is_oa,
            "oa_url": oa_url,
            "abstract": abstract
        }
    except Exception as e:
        print(f"API Error: {e}")
        return None
