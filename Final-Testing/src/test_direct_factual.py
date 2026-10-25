import json
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.llms import Ollama


JSON_FILE = "20_Direct_Factual_Qs.json"


embedding = HuggingFaceEmbeddings(
    model_name="BAAI/bge-small-en-v1.5"
)

db = Chroma(
    persist_directory="chroma_db",
    embedding_function=embedding
)

llm = Ollama(model="llama3")


def test_question(item):
    query = item["question"]

    results = db.similarity_search(query, k=4)

    context = "\n\n".join([
        doc.page_content[:1200]
        for doc in results
    ])

    sources = list(set([
        doc.metadata.get("source", "Unknown")
        for doc in results
    ]))

    prompt = f"""
You are testing a RAG chatbot.

Answer ONLY using the provided context.

Context:
{context}

Question:
{query}

Answer:
"""

    response = llm.invoke(prompt)

    return {
        "id": item["id"],
        "question": query,
        "expected": item["ground_truth"],
        "actual": response.strip(),
        "sources": sources,
        "retrieved_context": context[:2000]
    }


def main():
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        questions = json.load(f)

    results = []

    for item in questions:
        print(f"\nTesting {item['id']}: {item['question']}")

        result = test_question(item)
        results.append(result)

        print("\nExpected:")
        print(result["expected"])

        print("\nActual:")
        print(result["actual"])

        print("\nSources:")
        print(result["sources"])

        print("-" * 80)

    with open("direct_factual_test_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n✅ Direct factual testing complete.")
    print("Results saved to: direct_factual_test_results.json")


if __name__ == "__main__":
    main()