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
                
                # Format report for download
                report_lines = ["RESEARCH ETHICS AUDIT REPORT\n" + "="*30 + "\n"]
                report_lines.append(f"SECTION AUDITED: {sel_main}\n")
                if base_input:
                    report_lines.append(f"BASE PAPER CROSS-REFERENCE: {sel_base}\n")
                
                report_lines.append("\n[ COMPLIANT AREAS ]")
                for i in audit_result.get("compliant", []): report_lines.append(f"- {i}")
                
                report_lines.append("\n[ RED FLAGS ]")
                for i in audit_result.get("red_flags", []): report_lines.append(f"- {i}")
                
                report_lines.append("\n[ MISSING INFO ]")
                for i in audit_result.get("missing_info", []): report_lines.append(f"- {i}")
                
                report_text = "\n".join(report_lines)
                st.download_button(label="📥 Download Audit Report", data=report_text, file_name="Ethics_Audit_Report.txt", mime="text/plain")

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
