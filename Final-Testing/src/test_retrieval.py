from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

def test_query(query: str, persist_dir="chroma_db"):
    embedding_model = HuggingFaceEmbeddings(
        model_name="BAAI/bge-small-en-v1.5"
    )

    vectorstore = Chroma(
        persist_directory=persist_dir,
        embedding_function=embedding_model
    )

    results = vectorstore.similarity_search(query, k=3)

    for i, doc in enumerate(results, 1):
        print("=" * 80)
        print(f"Result {i}")
        print("Source:", doc.metadata.get("source"))
        print("Chunk ID:", doc.metadata.get("chunk_id"))
        print(doc.page_content[:1000])

if __name__ == "__main__":
    test_query("What is retrieval-augmented generation?")