import json

def generate_reference_extraction(references_text: str) -> list:
    sys_prompt = "Extract up to 10 individual citation strings from the following references section. Return ONLY a JSON list of strings (e.g. [\"citation 1\", \"citation 2\"]). Do not add markdown blocks."
    try:
        from src.generate import client, FALLBACK_MODEL
        response = client.chat.completions.create(
            model=FALLBACK_MODEL,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": references_text[:3000]}
            ],
            temperature=0.0
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
        return json.loads(content)
    except Exception as e:
        print(f"Extraction error: {e}")
        return []

def generate_reference_audit(main_text: str, ref_title: str, ref_abstract: str) -> str:
    sys_prompt = (
        "You are a Citation Verification AI.\n"
        "You are given an excerpt from a MAIN PAPER and the Title/Abstract of a REFERENCE PAPER cited within it.\n"
        "Analyze the relationship: How does the Main Paper seem to use this reference? Does it build upon it, compare against it, or use its methodology?\n"
        "Keep your response concise (3-4 sentences). Focus strictly on the academic relationship."
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
