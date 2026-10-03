import sys
import re

with open('app.py', 'r', encoding='utf-8') as f:
    app_code = f.read()

# Replace the text area with file uploader logic
old_ui = """    paper_input = st.text_area("Paste your research methodology here (max ~1000 words):", height=250)
    audit_btn = st.button("Run Automated Ethics Audit", type="primary")
    
    if audit_btn and paper_input.strip():"""

new_ui = """    uploaded_file = st.file_uploader("Upload your Research Paper (PDF)", type=["pdf"])
    
    if uploaded_file is not None:
        with st.spinner("Extracting sections from PDF..."):
            from user_parser import parse_scientific_paper
            # Cache the parsed sections in session state so it doesn't re-parse on every interaction
            if "parsed_sections" not in st.session_state or st.session_state.get("last_uploaded") != uploaded_file.name:
                sections = parse_scientific_paper(uploaded_file.read())
                st.session_state["parsed_sections"] = sections
                st.session_state["last_uploaded"] = uploaded_file.name
            
            sections = st.session_state["parsed_sections"]
            
        st.success(f"Successfully extracted {len(sections)} sections from your paper!")
        
        # Let user choose which section to audit
        selected_section = st.selectbox("Select a section to audit:", list(sections.keys()))
        paper_input = sections[selected_section]
        
        with st.expander("Preview Selected Section"):
            st.write(paper_input[:1000] + ("..." if len(paper_input) > 1000 else ""))
            
        audit_btn = st.button(f"Run Ethics Audit on {selected_section}", type="primary")
        
        if audit_btn and paper_input.strip():"""

app_code = app_code.replace(old_ui, new_ui)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(app_code)
