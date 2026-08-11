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
    DEVELOPMENT_MODE = os.getenv("APP_ENV", "development").lower() == "development"
