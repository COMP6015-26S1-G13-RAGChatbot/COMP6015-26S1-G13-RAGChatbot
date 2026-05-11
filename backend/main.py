# backend/main.py 
from fastapi import FastAPI
from backend.services.rag_wrapper import RAGWrapper

app = FastAPI()
rag = RAGWrapper()

@app.get("/ask")
def ask_question(query: str):
    return rag.ask(query)