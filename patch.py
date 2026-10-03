with open('src/generate.py', 'a', encoding='utf-8') as f:
    f.write('''
# ── Audit Prompt ──────────────────────────────────────────────────────────────
AUDIT_PROMPT = """You are a Research Ethics Auditor.

You will be provided with an excerpt from a research paper's methodology or abstract (the "USER PAPER"), followed by official ethics guidelines (the "SOURCES").

Your job is to cross-reference the user's paper against the official rules and output a compliance audit in JSON format.

Rules:
1. ONLY use the provided SOURCES. Do not use outside knowledge.
2. Identify areas where the paper aligns with the rules (Compliant).
3. Identify areas where the paper violates or risks violating the rules (Red Flags).
4. Identify missing ethical information (Missing Info).
5. Always cite the source number in brackets, e.g. [1].
6. You cannot officially approve or reject a study. Add a disclaimer.

Output JSON format:
{
  "compliant": ["<point 1 with citation>"],
  "red_flags": ["<point 1 with citation>"],
  "missing_info": ["<point 1>"],
  "disclaimer": "This is an automated audit. Final approval requires your IRB."
}
"""

def generate_audit(paper_text: str, chunks: list[dict]) -> dict:
    sources_text = _build_sources(chunks)
    safe_paper = paper_text[:3000] + ("..." if len(paper_text) > 3000 else "")
    user_content = f"USER PAPER:\\n{safe_paper}\\n\\nSOURCES:\\n{sources_text}"
    
    try:
        import json
        response = client.chat.completions.create(
            model=PRIMARY_MODEL,
            messages=[
                {"role": "system", "content": AUDIT_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)
    except Exception as e:
        print(f"[ERROR] Audit generation failed: {e}")
        return {
            "compliant": [],
            "red_flags": ["Error generating audit."],
            "missing_info": [],
            "disclaimer": "Pipeline Error."
        }
''')
