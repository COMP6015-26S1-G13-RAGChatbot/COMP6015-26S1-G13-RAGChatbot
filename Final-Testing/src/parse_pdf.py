import os
import fitz  # PyMuPDF


# =====================================================
# AUTHORITY LEVELS
# =====================================================

AUTHORITY_LEVELS = {
    "authoritative": 4,
    "draft": 3,
    "derived": 2,
    "synthetic": 1
}


# =====================================================
# DETAILED AUTHORITY RANK
# =====================================================

def get_authority_rank(filename, source_type):

    name = filename.lower()

    # IEEE Constitution and Bylaws
    if "ieee" in name and "constitution" in name:
        return 100

    # SMCS Constitution and Bylaws
    if (
        "smc" in name
        and "constitution" in name
        and "ieee" not in name
    ):
        return 90

    # SMCS Technical Manual
    if ("technical" in name or "techncal" in name) and "manual" in name:
        return 80

    # Financial Operations Manual
    if "financial" in name:
        return 80

    # Draft documents
    if source_type == "draft":
        return 40

    # Derived test corpus
    if source_type == "derived":
        return 20

    # Synthetic conflict corpus
    if source_type == "synthetic":
        return 0

    # Other authoritative documents
    if source_type == "authoritative":
        return 70

    return 0


# =====================================================
# EXTRACT PDF PAGE BY PAGE
# =====================================================

def extract_pages_from_pdf(pdf_path):

    pages = []

    doc = fitz.open(pdf_path)

    for page_number, page in enumerate(doc, start=1):

        text = page.get_text("text")

        if text.strip():

            pages.append({
                "page": page_number,
                "content": text
            })

    doc.close()

    return pages


# =====================================================
# PARSE ALL PDFs RECURSIVELY
# =====================================================

def parse_all_pdfs(folder_path):

    parsed_docs = []

    absolute_path = os.path.abspath(folder_path)

    print(f"\nLooking for PDFs in: {absolute_path}\n")

    if not os.path.exists(folder_path):

        print("❌ Data folder does not exist.")

        return parsed_docs

    # Search inside all folders and subfolders
    for root, dirs, files in os.walk(folder_path):

        for filename in files:

            if not filename.lower().endswith(".pdf"):
                continue

            pdf_path = os.path.join(
                root,
                filename
            )

            # Folder name:
            # authoritative / draft / derived / synthetic
            source_type = os.path.basename(
                root
            ).lower()

            authority_level = AUTHORITY_LEVELS.get(
                source_type,
                0
            )

            authority_rank = get_authority_rank(
                filename,
                source_type
            )

            print(
                "\n========================================"
            )

            print(f"Parsing: {filename}")
            print(f"Type: {source_type}")
            print(
                f"Authority level: {authority_level}"
            )
            print(
                f"Authority rank: {authority_rank}"
            )

            try:

                pages = extract_pages_from_pdf(
                    pdf_path
                )

                for page in pages:

                    parsed_docs.append({

                        "source": filename,

                        "page": page["page"],

                        "source_type": source_type,

                        "authority_level":
                            authority_level,

                        "authority_rank":
                            authority_rank,

                        "content":
                            page["content"]
                    })

                print(
                    f"✅ Parsed {len(pages)} pages"
                )

            except Exception as e:

                print(
                    f"❌ Failed to parse "
                    f"{filename}: {e}"
                )

    print(
        "\n========================================"
    )

    print(
        f"Total parsed pages: "
        f"{len(parsed_docs)}"
    )

    return parsed_docs