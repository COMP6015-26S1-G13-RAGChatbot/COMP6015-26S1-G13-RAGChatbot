import os 

class Config:
    # PATH CONFIG
    # backend/core/config.py  -> backend/core -> backend -> project root
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    CHROMA_PATH = os.path.join(BASE_DIR, "chroma_db")
    DATA_SOURCE = {
        "legal": os.path.join(BASE_DIR, "data/legal"),
        "operational": os.path.join(BASE_DIR, "data/operational")
    }

    # RAG PARAMETER CONFIG
    CHUNK_SIZE = 1000
    CHUNK_OVERLAP = 200
    MODEL_NAME = "BAAI/bge-small-en-v1.5"
    FLASHRANK_MODEL_NAME = "ms-marco-Multi-BERT-L-12"

    # singleton pattern for embedding model
    @staticmethod
    def get_embedding_model():
        from langchain_huggingface import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(model_name=Config.MODEL_NAME)
    
    @staticmethod
    def get_current_time():
        import datetime
        return datetime.datetime.now().isoformat()