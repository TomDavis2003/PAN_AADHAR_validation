import streamlit as st
import easyocr
import re
import numpy as np
from PIL import Image
from rapidfuzz import fuzz
from dateutil.parser import parse

# OCR reader (English + Hindi for Indian docs)
reader = easyocr.Reader(['en'], gpu=False)

def preprocess_ocr_text(text):
    # Improved OCR cleaning with better character handling
    text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
    text = re.sub(r'[|_®©§]', ' ', text)  # Remove special characters
    # Selective OCR error corrections (only for numbers)
    replacements = {
        'o': '0', 'O': '0', 'i': '1', 'I': '1',
        's': '5', 'S': '5', 'b': '6', 'B': '8',
        'l': '1', 'z': '2', 'Z': '2', 'g': '9'
    }
    return ''.join([replacements.get(c, c) if c.isdigit() else c for c in text])

def extract_text_from_image(uploaded_file):
    image = Image.open(uploaded_file).convert('RGB')
    image_np = np.array(image)
    result = reader.readtext(image_np, detail=0, paragraph=True)
    processed_text = preprocess_ocr_text(" ".join(result))
    return processed_text

# Update the extract_name and extract_dob functions with these improved implementations

def extract_name(text, doc_type):
    text = text.lower()
    cleaned_text = re.sub(r'[^a-zA-Z0-9/\n&, ]', '', text)  # Keep essential characters
    
    if doc_type == "aadhaar":
        # Enhanced Aadhaar patterns with flexible spacing
        patterns = [
            r'(?:gov(?:ernment)?\.?\s+of\s+india|uidai)\s*([a-z\s,]{8,}?)\s*(?:dob|d\.o\.b|yob|year|male|female)',
            r'(?:name\s*[^a-z]*)([a-z\s,]{8,}?)\s*(?:father|mother|husband)',
            r'\b([a-z\s,]{8,}?)\s*(?:\d{2}[\/\-]\d{2}[\/\-]\d{4})\b'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, cleaned_text, re.DOTALL | re.IGNORECASE)
            if match:
                name = ' '.join([w.capitalize() for w in match.group(1).strip().split()])
                if 2 <= len(name.split()) <= 4:
                    return name

    elif doc_type == "pan":
        # Enhanced PAN patterns with header exclusion
        patterns = [
            # Match name before PAN number (exclude headers)
            r'(?:income\s+tax\s+department|government\s+of\s+india|permanent\s+account\s+number)(?:.*?\n){1,3}([a-z\s,]{8,}?)\n\s*([a-z]{5}\d{4}[a-z])',
            # Match name field explicitly
            r'(?:name\s*[^a-z]*?)([a-z\s,]{8,}?)\s*(?:\d|father|mother|applicant)',
            # Match name in uppercase blocks
            r'\n([A-Z][A-Z\s,]{8,}?)\n(?:father|mother|dob|permanent)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, cleaned_text, re.DOTALL | re.IGNORECASE)
            if match:
                # Extract and clean the name group
                name_group = match.group(1).strip()
                # Remove titles and parent references
                name = re.sub(r'\b(sri|shri|smt|kum|mr|mrs|ms|father|mother).*', '', name_group, flags=re.IGNORECASE)
                name = re.sub(r',.*', '', name)  # Remove text after commas
                name = re.sub(r'\s+', ' ', name).strip()
                
                if 2 <= len(name.split()) <= 4:
                    return name.upper()

    # Improved fallback with PAN header exclusion
    candidates = re.findall(r'\b([A-Za-z]{3,}(?:\s+[A-Za-z]{3,}){1,3})\b', text)
    valid_candidates = [
        c for c in candidates
        if not any(word in c.lower() for word in [
            'father', 'mother', 'husband', 'wife',
            'permanent', 'account', 'number', 'card'
        ])
    ]
    
    if valid_candidates:
        best_candidate = max(valid_candidates, key=lambda x: (len(x), sum(c.isalpha() for c in x)))
        return best_candidate.upper()
    
    return "Not Found"

def extract_dob(text):
    # Enhanced date extraction with priority sorting
    date_formats = [
        (r'\b\d{2}/\d{2}/\d{4}\b', '%d/%m/%Y'),          # DD/MM/YYYY
        (r'\b\d{2}-\d{2}-\d{4}\b', '%d-%m-%Y'),          # DD-MM-YYYY
        (r'\b\d{4}/\d{2}/\d{2}\b', '%Y/%m/%d'),          # YYYY/MM/DD
        (r'\b\d{2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}\b', '%d %b %Y'),  # DD MMM YYYY
        (r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{2},\s+\d{4}\b', '%b %d, %Y') # MMM DD, YYYY
    ]

    found_dates = []
    for pattern, fmt in date_formats:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            try:
                date_str = match.group().replace(' ', '-')
                parsed = parse(date_str, dayfirst=True)
                if 1900 <= parsed.year <= 2100:
                    found_dates.append((parsed, match.start()))
            except:
                continue

    # Prioritize dates found earlier in the document and more complete formats
    if found_dates:
        # Sort by position and format priority
        found_dates.sort(key=lambda x: (x[1], x[0].year))
        return found_dates[0][0].strftime("%d/%m/%Y")
    
    return "Not Found"

def normalize_name(name):
    # Advanced normalization with fuzzy matching
    name = re.sub(r'[^a-zA-Z ]', '', name).strip().lower()
    name = re.sub(r'\s+', ' ', name)  # Remove extra spaces
    return name

def normalize_dob(dob):
    try:
        parsed = parse(dob, dayfirst=True)
        return parsed.strftime("%Y-%m-%d")
    except:
        return "Invalid"

def compare_fields(name1, name2, dob1, dob2):
    # Use fuzzy matching for names
    name_similarity = fuzz.ratio(normalize_name(name1), normalize_name(name2))
    name_match = name_similarity > 85  # 85% similarity threshold
    
    # Strict match for DOB
    dob1_norm = normalize_dob(dob1)
    dob2_norm = normalize_dob(dob2)
    dob_match = dob1_norm == dob2_norm and dob1_norm != "Invalid"
    
    return name_match, dob_match, dob1_norm, dob2_norm

# Streamlit UI
st.title("🆔 Aadhaar & PAN Name & DOB Match Validator")

aadhaar_image = st.file_uploader("Upload Aadhaar Card Image", type=["jpg", "jpeg", "png"])
pan_image = st.file_uploader("Upload PAN Card Image", type=["jpg", "jpeg", "png"])

if aadhaar_image and pan_image:
    with st.spinner("Extracting details..."):
        # Process images
        aadhaar_text = extract_text_from_image(aadhaar_image)
        pan_text = extract_text_from_image(pan_image)

        # Extract details with document-specific logic
        aadhaar_name = extract_name(aadhaar_text, "aadhaar")
        aadhaar_dob = extract_dob(aadhaar_text)
        pan_name = extract_name(pan_text, "pan")
        pan_dob = extract_dob(pan_text)

        # Compare fields
        name_match, dob_match, aadhaar_dob_norm, pan_dob_norm = compare_fields(
            aadhaar_name, pan_name, aadhaar_dob, pan_dob
        )
        
        # Display results
        st.subheader("🔍 Extracted Data")
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Aadhaar**")
            st.write(f"Name: {aadhaar_name}")
            st.write(f"DOB: {aadhaar_dob_norm}")
        with col2:
            st.write("**PAN**")
            st.write(f"Name: {pan_name}")
            st.write(f"DOB: {pan_dob_norm}")

        st.subheader("✅ Match Result")
        st.write(f"Name Similarity: {fuzz.ratio(normalize_name(aadhaar_name), normalize_name(pan_name))}%")
        st.write("Name Match:", "✅ Yes" if name_match else "❌ No")
        st.write("DOB Match:", "✅ Yes" if dob_match else "❌ No")

        if name_match and dob_match:
            st.success("MATCH ✅ - Same Person")
        else:
            st.error("MISMATCH ❌ - Details don't align")

        # Debug section (optional)
        with st.expander("View OCR Text"):
            col1, col2 = st.columns(2)
            with col1:
                st.write("**Aadhaar OCR Text**")
                st.code(aadhaar_text)
            with col2:
                st.write("**PAN OCR Text**")
                st.code(pan_text)