with open('src/pipeline.py', 'a', encoding='utf-8') as f:
    f.write('''

def run_audit_pipeline(paper_text: str, top_k: int = 5, retrieval_mode: str = "hybrid") -> dict:
    """
    RAG pipeline for Auditing a paper excerpt.
    Bypasses safety checks.
    """
    retriever = get_retriever()
    
    # Use the first 500 characters of the paper to find relevant rules
    search_query = paper_text[:500]
    chunks, confidence_ok = retriever.search(search_query, top_k=top_k, mode=retrieval_mode)
    
    if not chunks:
        return {
            "compliant": [],
            "red_flags": [],
            "missing_info": ["No relevant ethics guidelines found for this text."],
            "disclaimer": "Pipeline Error."
        }
        
    from generate import generate_audit
    return generate_audit(paper_text, chunks)
''')
