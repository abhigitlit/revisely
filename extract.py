import fitz  # PyMuPDF
import re
import json

pdf_path ="C:/Users/abhis\Downloads/67a30d64b5ddd-monthly_january_english_aparchit_super_current_affairs_best_350+.pdf"  # Change to actual PDF file
output_json_path = "./january.json"

def extract_text_from_pdf(pdf_path):
    """Extracts text from a PDF file."""
    doc = fitz.open(pdf_path)
    text = "\n".join(page.get_text("text") for page in doc)
    return text

# Extract text from PDF
text = extract_text_from_pdf(pdf_path)

# Regex pattern to extract full question blocks (from "Q." to "Answer: X")
question_block_pattern = re.compile(r"(Q\..*?Answer\s*:\s*[A-D])", re.DOTALL)

# Find all question blocks
question_blocks = question_block_pattern.findall(text)

extracted_data = []

for block in question_blocks:
    # Extract question (after "Q.")
    question_match = re.search(r"Q\.\s*(.*?)(?:A\)|Answer:)", block, re.DOTALL)
    question = question_match.group(1).strip() if question_match else "Unknown"

    # Extract options (A), B), C), D)) -> Remove indexing
    options = re.findall(r"[A-D]\)\s*(.+)", block)
    
    # Extract answer (last line)
    answer_match = re.search(r"Answer\s*:\s*([A-D])", block)
    answer = answer_match.group(1) if answer_match else "Unknown"

    # Convert answer from letter to full text
    answer_text = options[ord(answer) - ord("A")] if answer in "ABCD" and len(options) >= 4 else "Unknown"

    extracted_data.append({
        "question": question,
        "options": options,  # List of options without indexing
        "answer": answer_text  # Full answer text
    })

# Save extracted data to JSON
with open(output_json_path, "w", encoding="utf-8") as json_file:
    json.dump(extracted_data, json_file, indent=4, ensure_ascii=False)

print(f"\n✅ Extracted data saved to {output_json_path}")