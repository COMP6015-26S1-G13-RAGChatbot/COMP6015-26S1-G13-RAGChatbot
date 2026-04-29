import os

from parse_pdf import parse_all_pdfs
from clean_text import clean_markdown
from chunk_docs import chunk_documents

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma


DATA_FOLDER = "data"


def main():

    print("\n========== STARTING INGESTION ==========\n")

    # STEP 1: Parse PDFs
    parsed_docs = parse_all_pdfs(DATA_FOLDER)

    print(f"Parsed documents count: {len(parsed_docs)}")

    if not parsed_docs:
        print("❌ No documents parsed.")
        return

    # STEP 2: Clean documents
    cleaned_docs = []

    for doc in parsed_docs:

        source = doc.get("source", "unknown")
        content = doc.get("content", "")

        print(f"\nProcessing: {source}")
        print(f"Original text length: {len(content)}")

        cleaned_text = clean_markdown(content)

        print(f"Cleaned text length: {len(cleaned_text)}")

        if cleaned_text.strip():

            cleaned_docs.append({
                "source": source,
                "content": cleaned_text
            })

    print(f"\nCleaned documents count: {len(cleaned_docs)}")

    # STEP 3: Chunk documents
    chunks = chunk_documents(cleaned_docs)

    print(f"\nTotal chunks created: {len(chunks)}")

    if not chunks:
        print("❌ No chunks created.")
        return

    # STEP 4: Prepare text + metadata
    texts = []
    metadatas = []

    for chunk in chunks:

        text = chunk["content"].strip()

        if text:

            texts.append(text)

            metadatas.append({
                "source": chunk["source"]
            })

    print(f"\nValid chunks for embedding: {len(texts)}")

    # STEP 5: Load embedding model
    print("\nLoading embedding model...\n")

    embedding_model = HuggingFaceEmbeddings(
        model_name="BAAI/bge-small-en-v1.5"
    )

    # STEP 6: Create vector database
    print("\nCreating vector database...\n")

    Chroma.from_texts(
        texts=texts,
        embedding=embedding_model,
        metadatas=metadatas,
        persist_directory="chroma_db"
    )

    print("\n✅ Vector database built successfully!\n")


if __name__ == "__main__":
    main()