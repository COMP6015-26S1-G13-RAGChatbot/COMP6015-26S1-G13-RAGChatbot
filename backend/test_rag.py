# test_rag.py
from services.rag_wrapper import RAGWrapper

# 1. init RAG system
rag = RAGWrapper()

# 2. Ask a question
question = "What is the required timeframe to fill a vacancy for a Vice President, and does the Constitution support this specific duration?"
print(f"🤔 Question: {question}")

# 3. Get the answer
result = rag.ask(question)

print("\n🤖 Bot Answer:")
print(result["answer"])

print("\n📚 Sources Used:")
print(result["sources"])