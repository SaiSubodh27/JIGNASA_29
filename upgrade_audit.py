import sys
import re

# --- 1. Update generate.py ---
with open('src/generate.py', 'r', encoding='utf-8') as f:
    gen_code = f.read()

# Replace generate_audit
old_audit_func = """def generate_audit(paper_text: str, chunks: list[dict]) -> dict:
    sources_text = _build_sources(chunks)
    safe_paper = paper_text[:3000] + ("..." if len(paper_text) > 3000 else "")
    user_content = f"USER PAPER:\\n{safe_paper}\\n\\nSOURCES:\\n{sources_text}" """

new_audit_func = """def generate_audit(paper_text: str, base_paper_text: str, chunks: list[dict]) -> dict:
    sources_text = _build_sources(chunks)
    safe_paper = paper_text[:2000] + ("..." if len(paper_text) > 2000 else "")
    safe_base = base_paper_text[:2000] + ("..." if len(base_paper_text) > 2000 else "") if base_paper_text else "None provided."
    user_content = f"MAIN PAPER:\\n{safe_paper}\\n\\nBASE PAPER:\\n{safe_base}\\n\\nSOURCES:\\n{sources_text}" """
gen_code = gen_code.replace(old_audit_func, new_audit_func)

# Replace generate_audit_chat
old_chat_func = """def generate_audit_chat(question: str, paper_text: str, chunks: list[dict]) -> str:
    \"\"\"Follow-up chat for the audit mode, bypassing case-specific blocks.\"\"\"
    sources_text = _build_sources(chunks)
    safe_paper = paper_text[:2000]"""

new_chat_func = """def generate_audit_chat(question: str, paper_text: str, base_paper_text: str, chunks: list[dict]) -> str:
    \"\"\"Follow-up chat for the audit mode, bypassing case-specific blocks.\"\"\"
    sources_text = _build_sources(chunks)
    safe_paper = paper_text[:2000]
    safe_base = base_paper_text[:2000] if base_paper_text else "None" """
gen_code = gen_code.replace(old_chat_func, new_chat_func)

# Replace user_msg in generate_audit_chat
gen_code = gen_code.replace('user_msg = f"USER PAPER:\\n{safe_paper}\\n\\nOFFICIAL GUIDELINES:\\n{sources_text}\\n\\nUSER QUESTION:\\n{question}"', 'user_msg = f"MAIN PAPER:\\n{safe_paper}\\n\\nBASE PAPER:\\n{safe_base}\\n\\nOFFICIAL GUIDELINES:\\n{sources_text}\\n\\nUSER QUESTION:\\n{question}"')

with open('src/generate.py', 'w', encoding='utf-8') as f:
    f.write(gen_code)

# --- 2. Update pipeline.py ---
with open('src/pipeline.py', 'r', encoding='utf-8') as f:
    pipe_code = f.read()

old_pipe_audit = """def run_audit_pipeline(paper_text: str, top_k: int = 5, retrieval_mode: str = "hybrid") -> dict:
    \"\"\"
    RAG pipeline for Auditing a paper excerpt.
    Bypasses safety checks.
    \"\"\"
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
    return generate_audit(paper_text, chunks)"""

new_pipe_audit = """def run_audit_pipeline(paper_text: str, base_paper_text: str = "", top_k: int = 5, retrieval_mode: str = "hybrid") -> dict:
    \"\"\"
    RAG pipeline for Auditing a paper excerpt against a base paper.
    \"\"\"
    retriever = get_retriever()
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
    return generate_audit(paper_text, base_paper_text, chunks)"""
pipe_code = pipe_code.replace(old_pipe_audit, new_pipe_audit)

old_pipe_chat = """def run_audit_chat(question: str, paper_text: str, top_k: int = 5, retrieval_mode: str = "hybrid") -> str:
    \"\"\"Retrieves new chunks for a follow-up question and generates an answer.\"\"\"
    retriever = get_retriever()
    chunks, _ = retriever.search(question, top_k=top_k, mode=retrieval_mode)
    from generate import generate_audit_chat
    return generate_audit_chat(question, paper_text, chunks)"""

new_pipe_chat = """def run_audit_chat(question: str, paper_text: str, base_paper_text: str = "", top_k: int = 5, retrieval_mode: str = "hybrid") -> str:
    \"\"\"Retrieves new chunks for a follow-up question and generates an answer.\"\"\"
    retriever = get_retriever()
    chunks, _ = retriever.search(question, top_k=top_k, mode=retrieval_mode)
    from generate import generate_audit_chat
    return generate_audit_chat(question, paper_text, base_paper_text, chunks)"""
pipe_code = pipe_code.replace(old_pipe_chat, new_pipe_chat)

with open('src/pipeline.py', 'w', encoding='utf-8') as f:
    f.write(pipe_code)

# --- 3. Update app.py ---
with open('app.py', 'r', encoding='utf-8') as f:
    app_code = f.read()

prefix, main = app_code.split('with tab2:')

new_tab2 = """with tab2:
    st.markdown("### 📝 Dual-Paper Ethics Audit")
    st.markdown("Upload your Main Paper and optionally a Base Paper to check if you are ethically citing, using data, or addressing references correctly.")
    
    col_up1, col_up2 = st.columns(2)
    with col_up1:
        main_file = st.file_uploader("Upload MAIN Paper (Your study)", type=["pdf"])
    with col_up2:
        base_file = st.file_uploader("Upload BASE Paper (Reference study)", type=["pdf"])
        
    paper_input = ""
    base_input = ""
    
    from user_parser import parse_scientific_paper
    
    if main_file:
        if "main_sections" not in st.session_state or st.session_state.get("last_main") != main_file.name:
            st.session_state["main_sections"] = parse_scientific_paper(main_file.read())
            st.session_state["last_main"] = main_file.name
            
        main_sec = st.session_state["main_sections"]
        sel_main = st.selectbox("Select section from MAIN Paper to audit:", list(main_sec.keys()), key="sel_main")
        paper_input = main_sec[sel_main]
        with st.expander(f"Preview Main: {sel_main}"):
            st.write(paper_input[:500] + "...")
            
    if base_file:
        if "base_sections" not in st.session_state or st.session_state.get("last_base") != base_file.name:
            st.session_state["base_sections"] = parse_scientific_paper(base_file.read())
            st.session_state["last_base"] = base_file.name
            
        base_sec = st.session_state["base_sections"]
        sel_base = st.selectbox("Select section from BASE Paper to cross-reference:", list(base_sec.keys()), key="sel_base")
        base_input = base_sec[sel_base]
        with st.expander(f"Preview Base: {sel_base}"):
            st.write(base_input[:500] + "...")
            
    if main_file:
        audit_btn = st.button("Run Dual-Paper Ethics Audit", type="primary")
        if audit_btn and paper_input.strip():
            with st.spinner("Auditing against ethics guidelines..."):
                from pipeline import run_audit_pipeline
                audit_result = run_audit_pipeline(paper_input, base_paper_text=base_input, top_k=top_k, retrieval_mode=retrieval_mode)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.success("✅ Compliant Areas")
                    if audit_result.get("compliant"):
                        for item in audit_result["compliant"]:
                            st.markdown(f"- {item}")
                    else:
                        st.write("None identified.")
                with col2:
                    st.error("🚨 Potential Red Flags")
                    if audit_result.get("red_flags"):
                        for item in audit_result["red_flags"]:
                            st.markdown(f"- {item}")
                    else:
                        st.write("No direct violations found.")
                        
                st.warning("⚠️ Missing Information")
                if audit_result.get("missing_info"):
                    for item in audit_result["missing_info"]:
                        st.markdown(f"- {item}")
                else:
                    st.write("None identified.")
                    
                st.info(f"**Disclaimer:** {audit_result.get('disclaimer', 'This is an automated audit.')}")

        st.markdown("---")
        st.markdown("### 💬 Ask the Auditor")
        st.markdown("Have questions about your audit or want to know if you can add certain information? Ask here:")
        
        followup_q = st.text_input("Follow-up question:", placeholder="e.g., Did I properly cite the dataset from the Base Paper?")
        ask_btn = st.button("Ask Question", type="secondary")
        
        if ask_btn and followup_q.strip():
            with st.spinner("Consulting the ethics guidelines..."):
                from pipeline import run_audit_chat
                answer = run_audit_chat(followup_q, paper_input, base_paper_text=base_input, top_k=top_k, retrieval_mode=retrieval_mode)
                st.info(answer)
"""

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(prefix + new_tab2)
