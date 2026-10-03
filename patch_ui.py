with open('app.py', 'a', encoding='utf-8') as f:
    f.write('''

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
        st.warning("Please paste your methodology above first!")
''')
