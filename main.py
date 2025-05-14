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
        # NEW OPTIMIZED PATTERNS ==============================================
        patterns = [
            # 1. Explicit NAME label with father name exclusion
            r'(?:NAME|नाम|NOME)[\s:\-]*([A-Z]+(?:\s+[A-Z]+){1,2})(?=\s*(?:FATHER|MOTHER|\())',
            
            # 2. Line before PAN number (ABCDE1234F format)
            r'([A-Z]+(?:\s+[A-Z]+){1,2})\s+(?=[A-Z]{5}\d{4}[A-Z])',
            
            # 3. Government header context (most PAN cards have this)
            r'(?:GOVT\. OF INDIA|INCOME TAX DEPT)\s*([A-Z]+(?:\s+[A-Z]+){1,2})\s+(?:PERMANENT|CARD)',
            
            # 4. First valid name before father/mother markers
            r'([A-Z]+(?:\s+[A-Z]+){1,2})\s+(?=\n\s*(?:FATHER|MOTHER))'
        ]

        for pattern in patterns:
            match = re.search(pattern, cleaned_text)
            if match:
                raw_name = match.group(1).strip()
                
                # Clean father name remnants using position analysis
                if 'FATHER' in original_text:
                    father_pos = original_text.find('FATHER')
                    name_pos = original_text.find(raw_name)
                    if father_pos != -1 and name_pos != -1:
                        # Truncate at father name position
                        clean_name = original_text[name_pos:father_pos].strip()
                        return ' '.join(clean_name.split()[:3])

                return ' '.join(raw_name.split()[:2])  # Strict 2-word limit

        # FALLBACK: Position-based extraction ================================
        pan_number = re.search(r'[A-Z]{5}\d{4}[A-Z]', cleaned_text)
        if pan_number:
            # Extract 2 words immediately before PAN number
            before_pan = cleaned_text[:pan_number.start()].strip()
            if before_pan:
                words = before_pan.split()[-2:]
                return ' '.join(words)

        # Final filter for valid names ========================================
        candidates = re.findall(r'\b([A-Z]+(?:\s+[A-Z]+){1,2})\b', cleaned_text)
        valid = [
            c for c in candidates
            if 2 <= len(c.split()) <= 3
            and not re.search(r'(FATHER|MOTHER|PAN|CARD|NUMBER|DATE)', c)
        ]
        
        if valid:
            # Return first name-like candidate near document start
            positions = [(c, original_text.find(c)) for c in valid]
            positions = [p for p in positions if p[1] != -1]
            if positions:
                best = min(positions, key=lambda x: x[1])
                return best[0].split(',')[0].strip()[:25]  # Length limit

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