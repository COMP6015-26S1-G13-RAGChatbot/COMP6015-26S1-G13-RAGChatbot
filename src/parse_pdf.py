import os
import fitz  # pymupdf


def extract_text_from_pdf(pdf_path):
    text = ""

    doc = fitz.open(pdf_path)

    for page in doc:
        text += page.get_text()

    return text


def parse_all_pdfs(folder_path):
    parsed_docs = []

    print(f"Looking for PDFs in: {os.path.abspath(folder_path)}")

    if not os.path.exists(folder_path):
        print("❌ Data folder does not exist.")
        return parsed_docs

    files = os.listdir(folder_path)
    print(f"Files found in folder: {files}")

    for filename in files:
        if filename.lower().endswith(".pdf"):
            pdf_path = os.path.join(folder_path, filename)

            try:
                text = extract_text_from_pdf(pdf_path)

                parsed_docs.append({
                    "source": filename,
                    "content": text
                })

                print(f"✅ Parsed: {filename}")

            except Exception as e:
                print(f"❌ Failed to parse {filename}: {e}")

    return parsed_docs