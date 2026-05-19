from services.search_service import SearchService
from services.llm_service import LLMService

class RAGWrapper:
    def __init__(self):
        self.search_service = SearchService()
        self.llm_service = LLMService()

    def ask(self, user_query):
        # Retrieve top 2 documents for each type
        docs_op = self.search_service.search(user_query, doc_type='operational', k=2)  
        docs_legal = self.search_service.search(user_query, doc_type='legal', k=2)

        # llm generate answer (LLMService)
        final_answer = self.llm_service.generate_answer(user_query, {"operational": docs_op, "legal": docs_legal})

        detailed_source = []
        all_docs = docs_op + docs_legal  # Combine all retrieved documents for source details
        
        for doc in all_docs:
            source_name = doc.metadata.get("source", "Unknown Source")
            page = doc.metadata.get("page", "?")
            snippet = (doc.page_content[:400] + "..") if len(doc.page_content) > 400 else doc.page_content.strip().replace("\n", " ") 
            doc_type = doc.metadata.get("type", "general").upper()

            source_info = f"[{doc_type}] {source_name} (Page: {page}) | Snippet: \"{snippet}\""
            detailed_source.append(source_info)

        return {
            "answer": final_answer,
            "sources": list(set(detailed_source))  # Remove duplicates if any
        }