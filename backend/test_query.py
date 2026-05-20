# Check DB 

import os
from core.config import Config
from langchain_community.vectorstores import Chroma

def test_search():
    embedding_model = Config.get_embedding_model()
    chroma_path = Config.CHROMA_PATH
    
    print(f"checking for Chroma DB at: {chroma_path}")
        
    db = Chroma(
        persist_directory=chroma_path,
        embedding_function=embedding_model
    )
    
    query = "What are the legal implications of data breaches?"
    print(f"Query?: '{query}'")
    
    # search the vector database for similar chunks (top 3)
    docs = db.similarity_search(query, k=3)
    
    if not docs:
        print("No results found for the query. Check if the Chroma DB is populated and the query is relevant.")
    else:
        print(f"Found {len(docs)} results for the query:")
        for i, doc in enumerate(docs):
            print(f"\nResult {i+1}:")
            print(f"Content: {doc.page_content[:200]}...")  # print first 200 chars of content
            print(f"Metadata: {doc.metadata}")
            
if __name__ == "__main__":
    test_search()