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
    
    
    def search(self, query, doc_type=None, k=2):
        """
        Search for relevant 10 documents
        Rerank the retrieved documents using Flashrank and return the top 2 results.
        """
        
        search_filter = {"type": doc_type} if doc_type else None
        raw_docs = self.db.similarity_search(query, k=10, filter=search_filter)
        return self._rerank_docs(query, raw_docs, top_n=k)
        