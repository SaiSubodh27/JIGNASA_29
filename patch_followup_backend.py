with open('src/generate.py', 'a', encoding='utf-8') as f:
    f.write('''

def generate_audit_chat(question: str, paper_text: str, chunks: list[dict]) -> str:
    """Follow-up chat for the audit mode, bypassing case-specific blocks."""
    sources_text = _build_sources(chunks)
    safe_paper = paper_text[:2000]
    
    sys_prompt = (
        "You are a Research Ethics Auditor. You are answering a follow-up question "
        "about the user's research paper. \\n"
        "1. ONLY use the OFFICIAL GUIDELINES provided.\\n"
        "2. Cite your sources using [1].\\n"
        "3. You are allowed to give case-specific advice here because this is the Audit Mode.\\n"
        "4. If the guidelines don't have the answer, say NOT_FOUND."
    )
    
    user_msg = f"USER PAPER:\\n{safe_paper}\\n\\nOFFICIAL GUIDELINES:\\n{sources_text}\\n\\nUSER QUESTION:\\n{question}"
    
    try:
        response = client.chat.completions.create(
            model=PRIMARY_MODEL,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
        )
        return response.choices[0].message.content or "No response."
    except Exception as e:
        return f"Error connecting to LLM: {e}"
''')

with open('src/pipeline.py', 'a', encoding='utf-8') as f:
    f.write('''

def run_audit_chat(question: str, paper_text: str, top_k: int = 5, retrieval_mode: str = "hybrid") -> str:
    """Retrieves new chunks for a follow-up question and generates an answer."""
    retriever = get_retriever()
    chunks, _ = retriever.search(question, top_k=top_k, mode=retrieval_mode)
    from generate import generate_audit_chat
    return generate_audit_chat(question, paper_text, chunks)
''')
