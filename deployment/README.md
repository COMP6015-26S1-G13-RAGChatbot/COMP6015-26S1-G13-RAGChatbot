# Selected chatbot and administrator deployment

## Connected application

Use `backend.meet_main:app`, not the older `backend.main:app`, for the selected team engine. The new application connects the Next.js frontend, Meet's selected BGE/Chroma/Llama engine, and document lifecycle operations to the same database. The original selected sources are pinned in `backend/meet_engine/provenance.json` to main commit `cedfa0de`.

The selected retrieval/conflict/generation functions are retained. Integration changes add configurable model/server/storage locations, structured final citations, query-state isolation, and CLI transcript suppression. The web response does not invent a numerical confidence score. Unconnected legacy policy-audit and 12-case evaluation views are hidden for this backend.

The deployed production corpus contains the three enabled authoritative PDFs from the pinned team sources. The financial PDF is retained in inventory but disabled because its extraction was not established. Synthetic, derived and draft test records are not inserted into public production search. Consequently, this deployment does not reproduce the earlier mixed-corpus 50-question benchmark or its reported metrics. The lifecycle adapter currently extracts with pypdf, whereas the historical ingestion used PyMuPDF; extraction/chunk counts can differ. Public policy approval and authority labels need supervisor verification before release.

## Local run with your existing Ollama

Prepare private source data once, from the pinned local Git objects:

```bash
./venv/bin/python -m backend.prepare_meet_sources --output .admin_data
```

If `.admin_data/meet_inventory.json` already exists, do not run preparation again. Review that inventory instead; subsequent updates use administrator review and activation.

In the terminal where you will start the backend:

```bash
export ADMIN_ACCESS_TOKEN="$(./venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export OLLAMA_BASE_URL=http://127.0.0.1:11434
export OLLAMA_MODEL=llama3
export WEB_FRONTEND_URL=http://localhost:3000
HF_HUB_OFFLINE=1 ./venv/bin/python -m uvicorn backend.meet_main:app --host 127.0.0.1 --port 8000
```

Keep the token private. Print it locally before starting the server if you need to copy it to the admin page. Stop the previous backend before reusing port 8000. Offline startup requires the BGE model to be cached. To download it deliberately before offline operation, run the selected model setup in a trusted environment; `MEET_ALLOW_MODEL_DOWNLOAD=1` permits that initial loading.

In another terminal:

```bash
BACKEND_URL=http://127.0.0.1:8000 npm run dev --prefix frontend
```

Open the frontend. Its administration link redirects to the backend's `/admin`, and the backend's Back to chatbot link uses `WEB_FRONTEND_URL`. New backend code must be restarted; a browser refresh alone is insufficient.

The `/api/chat` route explicitly checks that the configured Ollama server/model is available. If it is unavailable, it returns HTTP 503 rather than presenting a connection problem as a policy abstention. The selected engine can otherwise produce supported abstentions in normal operation.

## Persistent backend container

`Dockerfile.meet` builds a CPU Python backend and caches the selected BGE model at image-build time. This is a configuration prepared for deployment; a complete Docker image build must still be verified on the target host. The repository's local Python application tests do not establish that the image builds on every host.

The container requires:

- A persistent private volume mounted at `/data`, writable by UID 10001.
- A random `ADMIN_ACCESS_TOKEN` set as a host secret, at least 32 characters.
- `OLLAMA_BASE_URL` pointing to a reachable private Ollama service.
- `OLLAMA_MODEL=llama3`, with that model already downloaded on the model service.
- `WEB_FRONTEND_URL` set to the final HTTPS Vercel frontend origin.
- One backend worker; the lifecycle and selected engine's query-state guard are single-process.

The initial container startup downloads only the four pinned authoritative team PDFs when no inventory exists. Review source permissions and inventory labels before public exposure. Original secrets, `.env.txt`, databases, reports, experiment outputs and evaluation answers are excluded from the Docker context. Private data is not baked into the application image. Persistent release directories retain approved source versions and Chroma data across deployments.

For a local or self-hosted Docker Compose setup:

```bash
export ADMIN_ACCESS_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
docker compose -f compose.meet.yaml up -d ollama
docker compose -f compose.meet.yaml exec ollama ollama pull llama3
docker compose -f compose.meet.yaml up -d --build backend
```

Docker resource use for the model depends on the host. The Compose file does not expose Ollama publicly and only binds the backend to the host's loopback interface. For internet use, configure an HTTPS reverse proxy to that backend. Do not expose Ollama's inference API directly to the internet. Backend public rate limiting, operational backups, release retention and individual administrator accounts require separate deployment configuration/work; they are not supplied as completed features here.

## Vercel frontend

1. Import the team GitHub repository and select `feat/hybrid-semantic-rag` or the branch containing this integration.
2. Set **Root Directory** to `frontend` and use the Next.js framework preset.
3. Set server-side `BACKEND_URL` to the public HTTPS backend origin, with no trailing `/api`.
4. Leave `NEXT_PUBLIC_API_URL` unset for the same-origin API proxy configuration.
5. Deploy and check Chat, Documents, citation links and the Document administration link.
6. Set the backend's `WEB_FRONTEND_URL` to that resulting Vercel HTTPS origin.

Administration redirects directly to the backend so the current 8 MiB base64 upload workflow does not travel through frontend Functions. The admin token belongs only on the backend and must never be configured as a `NEXT_PUBLIC_*` variable. Citation links include the immutable release ID so a later document activation does not silently change the source behind an older answer.

For a backend on a different origin, ordinary frontend chat requests still use the `/api` proxy. If the selected model's response exceeds the frontend host's request timeout, a direct API or streaming design is needed; this configuration does not guarantee an unmeasured latency SLA. Larger source downloads may also require direct backend links according to the hosting limits.

No public deployment is created by committing these files. Actual deployment needs an authenticated Vercel project plus a backend/model host and persistent volume. Do not mark deployment complete until the public URLs have been tested.

## Verification evidence

- Local BGE/Chroma startup built 274 chunks from the enabled production documents.
- Automated selected-web tests cover engine routing, final citation requirements, immutable source downloads, capability reporting, unsupported modes, administrator lifecycle sharing, and model-service errors.
- Lifecycle tests cover review, activation, rebuild, exclusion, restoration, failed updates and cache isolation.
- Production Next.js build passed, including TypeScript checking.
- A live local Ollama smoke question, “Is proxy voting allowed?”, returned HTTP 200 with a non-abstained answer and the selected SMCS Constitution and Bylaws citation on page 6. The versioned source-download endpoint also returned HTTP 200. This confirms one integration path, not general answer accuracy.
- Public deployment acceptance testing remains pending.
