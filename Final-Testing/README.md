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
python web/server.py      # use the same Python that runs rag_chat.py
```

Open http://localhost:8000.

### Using it in another project folder

Copy the `web/` folder into the folder that holds your RAG files (for
example `RAG/`) and run the same `python web/server.py` command from that folder. The
server works out the paths itself:

- `rag_chat.py` can be in `src/` or directly in the folder
- `chroma_db/` and `data/` (the PDFs) are expected in the folder

On start-up it prints the paths it is using and flags anything missing.
To run it from somewhere else, point it at the folder explicitly:
`RAG_PROJECT_DIR=/path/to/RAG python web/server.py`.

To preview the interface without Ollama or the vector database, run it in
demo mode, which returns canned responses:

```bash
RAG_DEMO_MODE=1 python web/server.py
```

| File | Purpose |
| --- | --- |
| `web/server.py` | FastAPI app: `/api/chat`, `/api/health`, `/api/documents`, serves PDFs under `/files/` |
| `web/static/index.html` | Page layout |
| `web/static/styles.css` | Styling, light/dark themes, mobile layout |
| `web/static/app.js` | Chat logic, conversation history (saved in the browser), source and conflict cards |
