from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.llms import Ollama


# =====================================================
# LOAD EMBEDDING MODEL
# =====================================================

print("\nLoading embedding model...\n")

embedding = HuggingFaceEmbeddings(
    model_name="BAAI/bge-small-en-v1.5"
)


# =====================================================
# LOAD VECTOR DATABASE
# =====================================================

print("\nLoading vector database...\n")

db = Chroma(
    persist_directory="chroma_db",
    embedding_function=embedding
)


# =====================================================
# ASK QUESTION FUNCTION
# =====================================================

def ask_question(query):

    # ==========================================
    # RETRIEVE RELEVANT CHUNKS
    # ==========================================

    results = db.similarity_search(query, k=3)

    # limit chunk size to reduce noise
    context = "\n\n".join([
        doc.page_content[:1200]
        for doc in results
    ])

    # ==========================================
    # SHOW RETRIEVED CONTEXT
    # ==========================================

    print("\n================ RETRIEVED CONTEXT ================\n")
    print(context[:2500])

    # ==========================================
    # SHOW SOURCES
    # ==========================================

    print("\n================ SOURCES ================\n")

    sources = set()

    for doc in results:

        source = doc.metadata.get("source", "Unknown Source")

        sources.add(source)

    for source in sources:
        print(f"- {source}")

    # ==========================================
    # LOAD OLLAMA MODEL
    # ==========================================

    llm = Ollama(model="llama3")

    # ==========================================
    # IMPROVED PROMPT
    # ==========================================

    prompt = f"""
    You are a highly accurate document question-answering assistant.

    Use ONLY the provided context to answer the question.

    Instructions:
    - Give a direct and concise answer.
    - Summarize clearly.
    - If relevant information exists, answer using that information.
    - Do NOT hallucinate.
    - Only say information is missing if absolutely no relevant information exists.

    CONTEXT:
    {context}

    QUESTION:
    {query}

    ANSWER:
    """

    # ==========================================
    # GENERATE RESPONSE
    # ==========================================

    try:

        response = llm.invoke(prompt)

        print("\n================ FINAL ANSWER ================\n")
        print(response.strip())

    except Exception as e:

        print("\n⚠️ Ollama Error")
        print(str(e))

        print("\nUsing fallback response...\n")

        sentences = [
            s.strip()
            for s in context.split(".")
            if len(s.strip()) > 40
        ]

        fallback = ". ".join(sentences[:3]) + "."

        print(fallback)

    print("\n=================================================\n")


# =====================================================
# MAIN CHAT LOOP
# =====================================================

if __name__ == "__main__":

    print("\n========= IEEE RAG CHATBOT =========")

    while True:

        query = input("\nAsk a question (type 'exit' to quit): ")

        if query.lower() == "exit":

            print("\nExiting chatbot...")
            break

        ask_question(query)