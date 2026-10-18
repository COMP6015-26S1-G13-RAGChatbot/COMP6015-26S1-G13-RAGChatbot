# IEEE SMCS RAG experiment

Run from the repository root. Ollama must be running on macOS.

```bash
./venv/bin/python -m experiments.ieee_smcs_rag.run_experiment --smoke \
  --models llama3:latest --embedding-model nomic-embed-text:latest

./venv/bin/python -m experiments.ieee_smcs_rag.run_experiment \
  --models llama3:latest --embedding-model nomic-embed-text:latest \
  --chunk-sizes 300 600 1000
```

`OLLAMA_BASE_URL` defaults to `http://localhost:11434`. Use
`http://host.docker.internal:11434` only if the backend is later run inside Docker Desktop.

Outputs are written under `experiment_outputs/ieee_smcs_rag/`. The Chroma database is experiment-only and does not replace the application index.
