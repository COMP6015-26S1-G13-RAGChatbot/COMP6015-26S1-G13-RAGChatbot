# Final Testing


## Web interface

A browser front end for the chatbot lives in `web/`. It calls the same
pipeline as `src/rag_chat.py` (unchanged) and shows each answer with its
cited source, the matching PDF page, any detected rule conflicts, and the
full pipeline trace.

```bash
# from the Final-Testing folder, after ingesting the documents
# (chroma_db/ must exist here) and with Ollama running llama3
pip install -r requirements.txt
uvicorn web.server:app --port 8000
```

Open http://localhost:8000.

To preview the interface without Ollama or the vector database, run it in
demo mode, which returns canned responses:

```bash
RAG_DEMO_MODE=1 uvicorn web.server:app --port 8000
```

| File | Purpose |
| --- | --- |
| `web/server.py` | FastAPI app: `/api/chat`, `/api/health`, `/api/documents`, serves PDFs under `/files/` |
| `web/static/index.html` | Page layout |
| `web/static/styles.css` | Styling, light/dark themes, mobile layout |
| `web/static/app.js` | Chat logic, conversation history (saved in the browser), source and conflict cards |
