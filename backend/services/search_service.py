from core.config import Config
from langchain_community.vectorstores import Chroma
from flashrank import Ranker, RerankRequest
from langchain_core.documents import Document

class SearchService:
    def __init__(self):
        # initialize the embedding model and Chroma vector database connection
        self.embedding_model = Config.get_embedding_model()
        self.chroma_path = Config.CHROMA_PATH
        
        # initialize Chroma vector database connection
        self.db = Chroma(
            persist_directory=self.chroma_path,
            embedding_function=self.embedding_model
        )
    
        self.ranker = Ranker(model_name="ms-marco-MiniLM-L-12-v2", cache_dir="/tmp")
        
    def _rerank_docs(self, query, docs, top_n=2):
        if not docs:
            return []
        
        passages = [
            {"id": i, "text": doc.page_content, "meta": doc.metadata}
            for i, doc in enumerate(docs)
        ]
        
        rerank_request = RerankRequest(query=query, passages=passages)
        results = self.ranker.rerank(rerank_request)
        
        # Restore Langchain Document format with metadata after reranking
        reranked_docs = [
            Document(page_content=r["text"], metadata=r["meta"])
            for r in results[:top_n]
        ]
        
        return reranked_docs
    
    
    def search(self, query, doc_type=None, k=3):
        """
        Search for relevant 10 documents
        Rerank the retrieved documents using Flashrank and return the top 3 results.
        """
        
        search_filter = {"type": doc_type} if doc_type else None
        raw_docs = self.db.similarity_search(query, k=10, filter=search_filter)
        ranked_docs = self._rerank_docs(query, raw_docs, top_n=k)
        
        return {
            "legal": [d for d in ranked_docs if d.metadata.get("type") == "legal"],
            "operational": [d for d in ranked_docs if d.metadata.get("type") == "operational"],
            "general": [d for d in ranked_docs if d.metadata.get("type") not in ["legal", "operational"]]
        }


    def search_for_conflict_analysis(self, query):
        """
        Retrieve top documents separately for Legal and Operational types to enable cross-validation (Conflict Analysis).
        """
        
        #  Retrieve Top 2 Legal documents
        legal_raw = self.db.similarity_search(query, k=10, filter={"type": "legal"})
        legal_docs = self._rerank_docs(query, legal_raw, top_n=2)

        #  Retrieve Top 2 Operational documents
        operational_raw = self.db.similarity_search(query, k=10, filter={"type": "operational"})
        operational_docs = self._rerank_docs(query, operational_raw, top_n=2)

        #  Return combined results for conflict analysis (can be further processed in the LLM to identify conflicts)
        return {
            "legal": legal_docs,
            "operational": operational_docs
        }   