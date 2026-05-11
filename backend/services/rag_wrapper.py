from services.search_service import SearchService
from services.llm_service import LLMService

class RAGWrapper:
    def __init__(self):
        self.search_service = SearchService()
        self.llm_service = LLMService()

    def ask(self, user_query, mode="conflict"):
        if mode == "conflict":
            # dictionary ('legal' : [], 'operational': [], 'general': [])
            docs = self.search_service.search_for_conflict_analysis(user_query)
        else:
            docs = self.search_service.search(user_query)

        # llm generate answer (LLMService)
        final_answer = self.llm_service.generate_answer(user_query, docs)
        
        detailed_source = []
        all_docs = []
        for key in docs:
            all_docs.extend(docs[key])
            
        for doc in all_docs:
            source_name = doc.metadata.get("source", "Unknown Source")
            page = doc.metadata.get("page", "?")
            snippet = doc.page_content[:100].strip().replace("\n", " ")  # Get the first 100 characters of the content as a snippet
            doc_type = doc.metadata.get("type", "general").upper()
            
            source_info = f"[{doc_type}] {source_name} (Page: {page}) | Snippet: \"{snippet}...\""
            detailed_source.append(source_info)

        return {
            "answer": final_answer,
            "sources": list(set(detailed_source))  # Remove duplicates if any
        }