import sys

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

prefix, main = content.split('with tab2:')

new_tab2 = """with tab2:
    st.markdown("### 📝 Pre-IRB Methodology Audit")
    st.markdown("Upload your research paper (PDF). The system will extract the sections and let you audit specific parts (e.g., Methodology, Authorship) against official ethics guidelines.")
    
    uploaded_file = st.file_uploader("Upload your Research Paper (PDF)", type=["pdf"])
    
    paper_input = ""
    
    if uploaded_file is not None:
        with st.spinner("Extracting sections from PDF..."):
            from user_parser import parse_scientific_paper
            if "parsed_sections" not in st.session_state or st.session_state.get("last_uploaded") != uploaded_file.name:
                sections = parse_scientific_paper(uploaded_file.read())
                st.session_state["parsed_sections"] = sections
                st.session_state["last_uploaded"] = uploaded_file.name
            
            sections = st.session_state["parsed_sections"]
            
        st.success(f"Successfully extracted {len(sections)} sections from your paper!")
        
        selected_section = st.selectbox("Select a section to audit:", list(sections.keys()))
        paper_input = sections[selected_section]
        
        with st.expander("Preview Selected Section"):
            st.write(paper_input[:1000] + ("..." if len(paper_input) > 1000 else ""))
            
        audit_btn = st.button(f"Run Ethics Audit on {selected_section}", type="primary")
        
        if audit_btn and paper_input.strip():
            with st.spinner(f"Auditing '{selected_section}' against ethics guidelines..."):
                from pipeline import run_audit_pipeline
                audit_result = run_audit_pipeline(paper_input, top_k=top_k, retrieval_mode=retrieval_mode)
                
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
    
    followup_q = st.text_input("Follow-up question:", placeholder="e.g., Can I add information from my base papers here?")
    ask_btn = st.button("Ask Question", type="secondary")
    
    if ask_btn and followup_q.strip() and paper_input.strip():
        with st.spinner("Consulting the ethics guidelines..."):
            from pipeline import run_audit_chat
            answer = run_audit_chat(followup_q, paper_input, top_k=top_k, retrieval_mode=retrieval_mode)
            st.info(answer)
    elif ask_btn and not paper_input.strip():
        st.warning("Please upload a paper and select a section above first!")
"""

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(prefix + new_tab2)
