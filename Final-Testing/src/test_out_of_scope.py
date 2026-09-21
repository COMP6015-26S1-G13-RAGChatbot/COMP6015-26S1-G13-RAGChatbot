import json
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.llms import Ollama


JSON_FILE = "out_of_scope_questions.json"


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

    results = db.similarity_search(query, k=3)

    context = "\n\n".join([
        doc.page_content[:1000]
        for doc in results
    ])

    prompt = f"""
You are testing a RAG chatbot.

Use ONLY the context below.

If the context does not contain the answer, reply exactly:
The answer was not found in the provided documents.

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
        "sources": list(set([
            doc.metadata.get("source", "Unknown")
            for doc in results
        ]))
    }


def main():
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        questions = json.load(f)

    results = []

    for item in questions:
        print(f"\nTesting {item['id']}: {item['question']}")

        result = test_question(item)
        results.append(result)

        print("Expected:", result["expected"])
        print("Actual:", result["actual"])
        print("Sources:", result["sources"])

    with open("out_of_scope_test_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n✅ Testing complete.")
    print("Results saved to: out_of_scope_test_results.json")


if __name__ == "__main__":
    main()