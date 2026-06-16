import os
import pdfplumber

def parse_pdf(file_path: str) -> tuple[str, str, float, bool]:
    """
    Parses a PDF file to extract digital text and tables cleanly.
    Returns: (extracted_text, extraction_method, confidence_score, requires_ocr)
    """
    print(f"Parsing digital PDF: {file_path}")
    
    extracted_pages = []
    total_raw_text_length = 0
    extraction_method = "DIGITAL_PDF"
    confidence_score = 1.0
    
    page_count = 0
    try:
        with pdfplumber.open(file_path) as pdf:
            page_count = len(pdf.pages)
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                tables = page.extract_tables() or []
                
                # Build clean text representation for this page
                page_content = [f"=== Page {i + 1} ===", text]
                
                # Append formatted tables if present
                if tables:
                    page_content.append("--- Extracted Tables ---")
                    for table in tables:
                        for row in table:
                            # Map None values to empty strings and tab-separate values
                            row_values = [str(cell) if cell is not None else "" for cell in row]
                            page_content.append("\t".join(row_values))
                        page_content.append("") # Spacer between tables
                
                extracted_pages.append("\n".join(page_content))
                total_raw_text_length += len(text.strip())
    except Exception as e:
        print(f"Error parsing PDF {file_path}: {e}")
        raise e
        
    # If the text yielded is empty or negligible (e.g. scanned image PDF), trigger OCR fallback
    if total_raw_text_length < 50:
        print(f"Selectable text yield is empty ({total_raw_text_length} chars). Fallback to OCR required.")
        return "", "", 0.0, page_count, True
        
    extracted_text = "\n".join(extracted_pages)
    return extracted_text, extraction_method, confidence_score, page_count, False
