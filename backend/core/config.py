from pathlib import Path
import os


class Config:
    BASE_DIR = Path(__file__).resolve().parents[2]
    DATA_DIR = BASE_DIR / "RAG_data"
    REGISTRY_PATH = DATA_DIR / "document_registry.json"
    INDEX_PATH = BASE_DIR / "backend" / "section_index.json"
    GOLDEN_SET_PATH = DATA_DIR / "COMP6016_Operations_Manual_Golden_Set.xlsx"
    MAX_RESULTS = 6
    MIN_RETRIEVAL_SCORE = 0.08
    MIN_HYBRID_SCORE = float(os.getenv("MIN_HYBRID_SCORE", "0.12"))
    EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "local_lsa")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4.1-mini")
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    DEVELOPMENT_MODE = os.getenv("APP_ENV", "development").lower() == "development"
    CORS_ORIGINS = tuple(
        origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    )
    ENABLE_EVALUATION_API = (
        os.getenv("ENABLE_EVALUATION_API", "true" if DEVELOPMENT_MODE else "false").lower()
        in {"1", "true", "yes", "on"}
    )
    CHAT_CACHE_TTL_SECONDS = float(os.getenv("CHAT_CACHE_TTL_SECONDS", "300"))
    CHAT_CACHE_MAX_ENTRIES = int(os.getenv("CHAT_CACHE_MAX_ENTRIES", "256"))
