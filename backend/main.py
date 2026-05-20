# backend/main.py 
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from services.rag_wrapper import RAGWrapper
from fastapi.staticfiles import StaticFiles

app = FastAPI()
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"]
)
rag = RAGWrapper()

class ChatRequest(BaseModel):
    query: str
    

app.mount("/documents/legal", StaticFiles(directory="data/legal"), name="legal")
app.mount("/documents/operational", StaticFiles(directory="data/operational"), name="operational")

@app.post("/ask")
async def ask_question(request: ChatRequest):
    return rag.ask(request.query)