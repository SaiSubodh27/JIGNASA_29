import sys

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

prefix, main = content.split('# ── Main Area ─────────────────────────────────────────────────────────────────')

new_main = """# ── Main Area ─────────────────────────────────────────────────────────────────
st.title("⚖️ Research Ethics Guidance Assistant")

tab1, tab2 = st.tabs(["💬 Q&A Assistant", "📄 Automated Ethics Audit"])

with tab1:
    st.markdown(
        "Ask a question about **informed consent**, **data handling**, "
        "**authorship criteria**, or **publication ethics**. "
        "Answers are grounded in official, versioned documents with citations."
    )

    col_left, col_right = st.columns([3, 2], gap="large")

    with col_left:
        question = st.text_area(
            "Your ethics question",
            placeholder="e.g. What are the criteria for authorship according to ICMJE?",
            height=120,
            key="question_input",
        )

        submit = st.button("🔍 Get Guidance", type="primary", use_container_width=True)

        # Example questions
        with st.expander("💡 Example questions"):
            examples = [
                "What does informed consent require in research?",
                "What are the ICMJE criteria for authorship?",
                "What counts as duplicate publication?",
                "How should participant data be protected?",
                "What is a conflict of interest and how should it be disclosed?",
            ]
            for ex in examples:
                if st.button(ex, key=f"ex_{ex[:20]}"):
                    st.session_state["question_input"] = ex
                    st.rerun()

        if submit and question.strip():
            with st.spinner("Searching approved documents and generating guidance..."):
                try:
                    from pipeline import run_pipeline, PipelineResponse
                    response = run_pipeline(
                        question.strip(),
                        top_k=top_k,
                        retrieval_mode=retrieval_mode,
                    )
                except Exception as e:
                    st.error(f"Pipeline error: {e}")
                    st.stop()

            # Status badge
            label, css_class = BADGE_MAP.get(
                response.status, ("Unknown", "badge-not_found")
            )
            st.markdown(
                f'<span class="{css_class}">{label}</span>', unsafe_allow_html=True
            )
            st.markdown("")

            # Safety message (escalation / refusal)
            if response.safety_decision.response_hint:
                st.warning(response.safety_decision.response_hint)

            # Main answer
            if response.status in ("answered", "escalated") and response.general_guidance:
                if response.general_guidance != "NOT_FOUND":
                    st.markdown("### 📋 General Guidance")
                    st.markdown(response.general_guidance)

                    st.markdown("### 🏛️ Needs Your Ethics Committee")
                    st.info(response.needs_committee)

            elif response.status == "not_found":
                st.error(
                    "❌ The approved ethics documents do not contain specific guidance "
                    "on this topic. Please consult your institution's ethics committee."
                )

            elif response.status == "clarify":
                st.info(response.safety_decision.response_hint)

            # Citations list (bottom of left column)
            if hasattr(response, "sources") and response.sources and response.citations:
                st.markdown("### 📖 Citations Used")
                cited_indices = [c - 1 for c in response.citations if isinstance(c, int)]
                for idx in cited_indices:
                    if 0 <= idx < len(response.sources):
                        src = response.sources[idx]
                        st.markdown(
                            f"**[{idx+1}]** {src['doc_title']} (v{src['version']}) - "
                            f"Section: {src.get('section', 'N/A')}"
                        )

            # Store response in session for right column
            st.session_state["last_response"] = response

        elif submit:
            st.warning("Please enter a question before submitting.")

    # ── Right Column: Source Excerpts ──
    with col_right:
        st.markdown("### 📄 Source Excerpts")
        response = st.session_state.get("last_response")

        if response and hasattr(response, "sources") and response.sources:
            cited_nums = set(response.citations) if response.citations else set()
            for i, src in enumerate(response.sources):
                num = i + 1
                auth_level = src.get("authority", 5)
                auth_label = AUTHORITY_LABELS.get(auth_level, "Unknown")
                is_cited = num in cited_nums
                highlight = "⭐ " if is_cited else ""

                st.markdown(
                    f'''
    <div class="source-box authority-{min(auth_level, 4)}">
    <strong>{highlight}[{num}] {src['doc_title']}</strong><br/>
    <small>Version: {src['version']} · {auth_label} · 
    Section: {src.get('section', 'N/A')} · 
    Topics: {', '.join(src.get('all_topics', [src.get('topic', 'general')]))}</small>
    <br/><br/>
    <em>{src['text'][:600]}{'...' if len(src['text']) > 600 else ''}</em>
    </div>
    ''',
                    unsafe_allow_html=True,
                )
        else:
            st.info(
                "Source excerpts will appear here after you submit a question. "
                "Stars (⭐) mark sources directly cited in the answer."
            )

with tab2:
    st.markdown("### 📝 Pre-IRB Methodology Audit")
    st.markdown("Paste an excerpt of your research methodology or abstract below. The system will bypass the 'case-specific' block and automatically cross-reference your text against official ethics guidelines to flag potential issues.")
    
    paper_input = st.text_area("Paste your research methodology here (max ~1000 words):", height=250)
    audit_btn = st.button("Run Automated Ethics Audit", type="primary")
    
    if audit_btn and paper_input.strip():
        with st.spinner("Auditing against ethics guidelines..."):
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
"""

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(prefix + new_main)
