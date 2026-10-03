import re
from pypdf import PdfReader
import io
import docx

def parse_scientific_paper(file_bytes, filename=""):
    text = ""
    
    if filename.lower().endswith(".docx") or filename.lower().endswith(".doc"):
        doc = docx.Document(io.BytesIO(file_bytes))
        text = "\n".join([para.text for para in doc.paragraphs])
    else:
        # Default to PDF
        reader = PdfReader(io.BytesIO(file_bytes))
        for p in reader.pages:
            text += (p.extract_text() or "") + "\n"
            
    text = text.replace('\r', '\n')
    
    headings = [
        "ABSTRACT", "INTRODUCTION", "BACKGROUND", "METHODS", "METHODOLOGY", 
        "EXPERIMENTAL SECTION", "RESULTS", "DISCUSSION", "CONCLUSION", 
        "CONCLUSIONS", "ACKNOWLEDGEMENTS", "AUTHOR CONTRIBUTIONS", 
        "DECLARATION", "COMPETING INTERESTS", "FUNDING", "REFERENCES", "DATA AVAILABILITY"
    ]
    
    sections = {}
    current_heading = "General / Title"
    sections[current_heading] = []
    
    heading_pattern = re.compile(r'^\s*(\d+(\.\d+)*\s*)?(' + '|'.join(headings) + r')\b.*$', re.IGNORECASE)
    
    for line in text.split('\n'):
        if len(line.strip()) == 0:
            continue
            
        if len(line.strip()) < 80 and heading_pattern.match(line):
            raw_heading = line.strip()
            for h in headings:
                if h.lower() in raw_heading.lower():
                    current_heading = h.title()
                    break
            else:
                current_heading = raw_heading.title()
                
            if current_heading not in sections:
                sections[current_heading] = []
            continue
            
        sections[current_heading].append(line)
        
    return {k: " ".join(v).strip() for k, v in sections.items() if len(v) > 0}
