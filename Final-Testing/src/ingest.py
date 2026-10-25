import os
import shutil

from parse_pdf import parse_all_pdfs
from clean_text import clean_markdown
from chunk_docs import chunk_documents

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma


# =====================================================
# SETTINGS
# =====================================================

DATA_FOLDER = "data"
CHROMA_FOLDER = "chroma_db"

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


# =====================================================
# MAIN INGESTION FUNCTION
# =====================================================

def main():

    print("\n========================================")
    print("STARTING IEEE SMCS RAG INGESTION")
    print("========================================\n")

    # =================================================
    # STEP 1: PARSE PDFS
    # =================================================

    parsed_docs = parse_all_pdfs(
        DATA_FOLDER
    )

    print(
        f"\nParsed page count: "
        f"{len(parsed_docs)}"
    )

    if not parsed_docs:

        print(
            "\n❌ No documents were parsed."
        )

        return

    # =================================================
    # STEP 2: CLEAN DOCUMENTS
    # =================================================

    print(
        "\n========================================"
    )
    print("CLEANING DOCUMENTS")
    print("========================================\n")

    cleaned_docs = []

    for doc in parsed_docs:

        content = doc.get(
            "content",
            ""
        )

        cleaned_text = clean_markdown(
            content
        )

        if not cleaned_text.strip():
            continue

        cleaned_docs.append({

            "source":
                doc.get(
                    "source",
                    "unknown"
                ),

            "page":
                doc.get(
                    "page",
                    -1
                ),

            "source_type":
                doc.get(
                    "source_type",
                    "unknown"
                ),

            "authority_level":
                doc.get(
                    "authority_level",
                    0
                ),

            "authority_rank":
                doc.get(
                    "authority_rank",
                    0
                ),

            "content":
                cleaned_text
        })

    print(
        f"Cleaned page count: "
        f"{len(cleaned_docs)}"
    )

    if not cleaned_docs:

        print(
            "\n❌ No valid cleaned documents."
        )

        return

    # =================================================
    # STEP 3: CHUNK DOCUMENTS
    # =================================================

    print(
        "\n========================================"
    )
    print("CHUNKING DOCUMENTS")
    print("========================================\n")

    chunks = chunk_documents(
        cleaned_docs
    )

    print(
        f"Total chunks created: "
        f"{len(chunks)}"
    )

    if not chunks:

        print(
            "\n❌ No chunks created."
        )

        return

    # =================================================
    # STEP 4: PREPARE TEXT + METADATA
    # =================================================

    texts = []
    metadatas = []

    for chunk in chunks:

        text = chunk.get(
            "content",
            ""
        ).strip()

        if not text:
            continue

        texts.append(
            text
        )

        metadatas.append({

            "source":
                chunk.get(
                    "source",
                    "unknown"
                ),

            "page":
                int(
                    chunk.get(
                        "page",
                        -1
                    )
                ),

            "source_type":
                chunk.get(
                    "source_type",
                    "unknown"
                ),

            "authority_level":
                int(
                    chunk.get(
                        "authority_level",
                        0
                    )
                ),

            "authority_rank":
                int(
                    chunk.get(
                        "authority_rank",
                        0
                    )
                ),

            "chunk_id":
                int(
                    chunk.get(
                        "chunk_id",
                        -1
                    )
                ),

            "page_chunk_index":
                int(
                    chunk.get(
                        "page_chunk_index",
                        -1
                    )
                )
        })

    print(
        f"\nValid chunks for embedding: "
        f"{len(texts)}"
    )

    # =================================================
    # STEP 5: REMOVE OLD CHROMA DATABASE
    # =================================================

    if os.path.exists(
        CHROMA_FOLDER
    ):

        print(
            "\nExisting Chroma database found."
        )

        print(
            "Removing old database..."
        )

        try:

            shutil.rmtree(
                CHROMA_FOLDER
            )

            print(
                "✅ Old Chroma database removed."
            )

        except Exception as e:

            print(
                "\n❌ Could not delete old "
                f"database: {e}"
            )

            return

    # =================================================
    # STEP 6: LOAD EMBEDDING MODEL
    # =================================================

    print(
        "\n========================================"
    )
    print("LOADING EMBEDDING MODEL")
    print("========================================\n")

    print(
        f"Model: {EMBEDDING_MODEL}"
    )

    embedding_model = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL
    )

    # =================================================
    # STEP 7: CREATE CHROMA DATABASE
    # =================================================

    print(
        "\n========================================"
    )
    print("CREATING VECTOR DATABASE")
    print("========================================\n")

    try:

        Chroma.from_texts(

            texts=texts,

            embedding=embedding_model,

            metadatas=metadatas,

            persist_directory=CHROMA_FOLDER
        )

    except Exception as e:

        print(
            "\n❌ Failed to create "
            f"vector database: {e}"
        )

        return

    # =================================================
    # COMPLETE
    # =================================================

    print(
        "\n========================================"
    )
    print(
        "✅ VECTOR DATABASE BUILT SUCCESSFULLY"
    )
    print(
        "========================================"
    )

    print(
        f"\nTotal stored chunks: "
        f"{len(texts)}"
    )

    print(
        "\nStored metadata:"
    )

    print(
        "- source"
    )

    print(
        "- page"
    )

    print(
        "- source_type"
    )

    print(
        "- authority_level"
    )

    print(
        "- authority_rank"
    )

    print(
        "- chunk_id"
    )

    print(
        "- page_chunk_index"
    )

    print(
        "\n========================================\n"
    )


# =====================================================
# RUN
# =====================================================

if __name__ == "__main__":

    main()