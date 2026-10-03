"""
app.py - Streamlit UI for the Research Ethics Guidance Assistant.

Layout:
  Left column  : Question input, answer, status badge
  Right column : Source excerpts with authority level
  Sidebar      : Document list, retrieval mode toggle
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Make src importable
sys.path.insert(0, str(Path(__file__).parent / "src"))

from pipeline import run_pipeline, PipelineResponse

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Research Ethics Guidance Assistant",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
<style>
.badge-answered  { background:#1a7f4b; color:white; padding:2px 10px; border-radius:12px; font-weight:600; }
.badge-escalated { background:#d97706; color:white; padding:2px 10px; border-radius:12px; font-weight:600; }
.badge-refused   { background:#dc2626; color:white; padding:2px 10px; border-radius:12px; font-weight:600; }
.badge-not_found { background:#6b7280; color:white; padding:2px 10px; border-radius:12px; font-weight:600; }
.badge-clarify   { background:#3b82f6; color:white; padding:2px 10px; border-radius:12px; font-weight:600; }

.source-box {
    border:1px solid #e5e7eb; border-radius:8px; padding:12px 16px;
    margin-bottom:12px; background:#f9fafb;
}
.authority-1 { border-left:4px solid #dc2626; }
.authority-2 { border-left:4px solid #d97706; }
.authority-3 { border-left:4px solid #3b82f6; }
.authority-4 { border-left:4px solid #6b7280; }
</style>
""",
    unsafe_allow_html=True,
)

AUTHORITY_LABELS = {
    1: "Law / Regulation",
    2: "International / National Guideline",
    3: "Professional Standard",
    4: "Institute Policy",
    5: "Background Reading",
}

BADGE_MAP = {
    "answered": ("✅ Answered", "badge-answered"),
    "escalated": ("⚠️ Escalated to Ethics Committee", "badge-escalated"),
    "refused": ("🚫 Refused", "badge-refused"),
    "not_found": ("❓ Not Found in Sources", "badge-not_found"),
    "clarify": ("🔍 Clarification Needed", "badge-clarify"),
}

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚖️ Ethics Assistant")
    st.markdown("---")

    retrieval_mode = st.radio(
        "Retrieval Mode",
        options=["hybrid", "bm25", "embedding"],
        index=0,
        help="Hybrid = BM25 + Embeddings merged via RRF (recommended)",
    )
    top_k = st.slider("Number of source chunks", min_value=2, max_value=8, value=5)

    st.markdown("---")
    st.subheader("📚 Approved Documents")
    try:
        import json
        manifest_path = Path("data/manifest.json")
        if manifest_path.exists():
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
            for doc in manifest:
                auth_label = AUTHORITY_LABELS.get(doc["authority"], "Unknown")
                st.markdown(
                    f"**{doc['title']}**  \n"
                    f"_{doc['publisher']} · v{doc['version']}_  \n"
                    f"Authority: {auth_label}"
                )
                st.markdown("")
        else:
            st.info("No manifest found.")
    except Exception as e:
        st.error(f"Could not load manifest: {e}")

    st.markdown("---")
    st.caption(
        "⚠️ This tool provides **general guidance only**. "
        "It is not legal or ethical advice. "
        "All case-specific decisions must be reviewed by your institution's IRB."
    )

# ── Main Area ─────────────────────────────────────────────────────────────────
st.title("⚖️ Research Ethics Guidance Assistant")

tab1, tab2 = st.tabs(["💬 Q&A Assistant", "🤖 Automated Reference & Ethics Audit"])

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
    <em>{src['text'][:2000]}{'...' if len(src['text']) > 2000 else ''}</em>
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
    st.markdown("### 🤖 Fully Automated Ethics & Reference Audit")
    st.markdown("Upload your Main Paper. The system will automatically extract its references, fetch them globally via OpenAlex, and audit your paper against **BOTH** the official ethical guidelines and the fetched reference abstracts.")
    
    main_file = st.file_uploader("Upload MAIN Paper (Your study)", type=["pdf", "docx", "doc"])
    
    if main_file:
        from user_parser import parse_scientific_paper
        if "main_sections" not in st.session_state or st.session_state.get("last_main") != main_file.name:
            st.session_state["main_sections"] = parse_scientific_paper(main_file.read(), main_file.name)
            st.session_state["last_main"] = main_file.name
            
        main_sec = st.session_state["main_sections"]
        
        st.markdown("---")
        
        sel_main = st.selectbox("Select section from MAIN Paper to audit:", list(main_sec.keys()), key="sel_main")
        paper_input = main_sec[sel_main]
        with st.expander(f"Preview Main: {sel_main}"):
            st.write(paper_input[:500] + "...")
                
        if st.button("Run Automated Audit", type="primary"):
            with st.spinner("Extracting References from document..."):
                ref_text = ""
                for k, v in main_sec.items():
                    if "reference" in k.lower() or "bibliography" in k.lower():
                        ref_text += v + "\n"
            
            if not ref_text:
                st.error("Could not find a 'References' section in this document.")
            else:
                with st.spinner("Extracting top citations via LLM..."):
                    import sys
                    if 'src' not in sys.path:
                        sys.path.insert(0, 'src')
                    from src.auto_reference import generate_reference_extraction, fetch_paper_info
                    from pipeline import run_audit_pipeline
                    citations = generate_reference_extraction(ref_text)
                    
                if not citations:
                    st.warning("No specific citations could be parsed.")
                else:
                    st.success(f"Found {len(citations)} citations. Running global audit...")
                    for i, cite in enumerate(citations):
                        st.markdown("---")
                        st.markdown(f"### Reference {i+1}: `{cite}`")
                        
                        with st.spinner("Querying OpenAlex global database..."):
                            paper_data = fetch_paper_info(cite)
                        
                        if not paper_data:
                            st.error("❌ Could not resolve this paper globally.")
                            continue
                            
                        if paper_data['is_oa']:
                            st.markdown(f"**📄 Title:** {paper_data['title']} (🟢 OPEN ACCESS)")
                        else:
                            st.markdown(f"**📄 Title:** {paper_data['title']} (🔒 PAYWALLED - Using Abstract)")
                            
                        with st.spinner("Running Ethics & Citation Audit..."):
                            # We pass the fetched abstract as the base_paper_text
                            audit_result = run_audit_pipeline(paper_input, base_paper_text=paper_data['abstract'], top_k=top_k, retrieval_mode=retrieval_mode)
                            
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
        st.markdown("#### 💬 Ask the Auditor")
        followup_q = st.text_input("Follow-up question about your paper:", placeholder="e.g., Did I properly cite the dataset?")
        ask_btn = st.button("Ask Question", type="secondary")
        if ask_btn and followup_q.strip():
            with st.spinner("Consulting the ethics guidelines..."):
                from pipeline import run_audit_chat
                answer = run_audit_chat(followup_q, paper_input, base_paper_text="", top_k=top_k, retrieval_mode=retrieval_mode)
                st.info(answer)
