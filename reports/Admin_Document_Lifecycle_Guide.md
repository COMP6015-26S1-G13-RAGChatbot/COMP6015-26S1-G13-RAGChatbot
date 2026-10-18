# Administrator document lifecycle

Integration update: `backend.meet_main:app` now connects the selected engine, frontend API and administrator lifecycle. See `deployment/README.md` for startup and deployment configuration. The earlier adapter-only statements below describe the implementation stage before that integration. Local BGE/Chroma/Ollama startup and a real question/citation/source-download smoke test have passed; public hosting is still pending.

## Implemented workflow

The local console now supports review decisions, activation of replacement document versions, search exclusion/re-enablement, index rebuilding, and restoration of previous releases. These features extend the earlier pending-upload implementation.

1. Upload a PDF with a title and version. It remains pending and is not searched.
2. Select the existing approved production document that the upload replaces.
3. Choose **Approve** or **Reject** and record a reason. Approval alone does not change search.
4. For an approved upload, choose **Activate version** and provide a change reason.
5. The service copies the production source set into a new private release, builds an index, and checks that every enabled document supplies searchable text.
6. After successful construction it publishes the new runtime. Failure leaves the previous release active. In-flight local requests retain the runtime they started with, and the new runtime starts with a fresh answer cache.
7. Use **Restore** under version history to build and publish a new release from a previous inventory. Restore covers the whole document set and its search settings, not only one selected document.

Each successful activation, retrieval change, rebuild, or restoration produces a new release. Rejected uploads cannot be activated; submit a new upload if another review is needed. A submitted file's hash is checked again before activation. Registered document titles, types, and authority values are inherited; the administrator cannot enter an arbitrary authority score through this workflow.

## Starting the updated local console

Stop the existing backend with Control+C and start it again in the terminal where `ADMIN_ACCESS_TOKEN` is already set:

```bash
./venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/admin`, refresh the page, and reconnect with the same token. New controls require a server restart; refreshing the page alone does not load the new backend routes.

The lifecycle is initialised when a valid administrator token is configured. Once a release exists, it remains the active source inventory across backend restarts even if admin access is subsequently disabled. Startup verifies archived source hashes and rebuilds the local runtime from the selected release. Never delete `.admin_data/releases` while the service uses it.

## Index safety and persistence

- Builds use a new release directory instead of deleting the live index.
- Production source copies, version metadata, reasons, timestamps, and index data are retained under `.admin_data/releases` by default.
- The active release is selected by an atomically replaced `current.json` pointer.
- Approval/rejection metadata is stored with the submission; index changes record the reason in both release history and the action log when available.
- Pending, rejected, evaluation-only, and audit-input identities cannot be enabled as production documents through the toggle endpoint.
- The last searchable production document cannot be excluded.
- Documents with no searchable extracted text cannot be activated, even if the PDF is structurally valid.
- This version supports replacement of registered production sources. Registration of a completely new governance identity and changes to its authority still require an operator-reviewed inventory change.

The local implementation targets one FastAPI worker. Files and locks are local to the process/host. Multiple workers or replicas require coordinated durable state and publishing. Keep the private storage directory outside static mounts and back it up. Retained releases consume disk space; automatic retention/deletion is not implemented. A process crash between durable pointer publication and in-memory switching is recovered by loading that pointer on restart. Filesystem corruption and cross-process updates are not covered by the atomic-pointer design.

## Meet BGE and Chroma integration

The currently running checkout uses the local section-index backend. Its lifecycle adapter is wired automatically and preserves the configured embedding backend. It does not silently switch to BGE or replace Meet's engine.

`backend/services/meet_admin_adapter.py` provides a separate adapter for the chosen BGE/Chroma engine. It reuses `engine.embedding`, calls the supplied cleaning and chunking functions, preserves the source metadata schema, builds a separate Chroma directory, checks the stored count, and only then switches `engine.db`. It does not call the original ingestion script that deletes the active database.

To integrate into Meet's application, the operator must supply:

- The loaded engine module exposing `db` and `embedding`.
- A verified inventory with absolute PDF paths and registry fields: `document_id`, `title`, `version`, `approval_status`, `usage`, `retrieval_enabled`, `authority_level`, and `content_hash` (`auto` is allowed for the initial inventory).
- Per-document `source_metadata` preserving Meet's original `source`, `source_type`, `authority_level`, and `authority_rank` values. Source names must match the labels used by its retrieval and citation logic.
- The selected `clean_markdown` and `chunk_documents` functions.
- Persistent private storage and one worker.

Example host integration, replacing the capitalised names with actual host objects:

```python
from backend.admin import install_admin, storage
from backend.services.meet_admin_adapter import install_meet_lifecycle, guarded_answer

install_admin(app)
manager = install_meet_lifecycle(
    app,
    engine=LOADED_RAG_ENGINE,
    inventory=VERIFIED_DOCUMENT_INVENTORY,
    clean_text=SELECTED_CLEAN_MARKDOWN,
    chunk_documents=SELECTED_CHUNK_DOCUMENTS,
    folder=storage() / 'meet-releases',
)

# Inside a synchronous FastAPI answer route, use this wrapper for every query:
result = guarded_answer(manager, EXISTING_ANSWER_FUNCTION, question)
```

Meet's engine uses module-level query state. Every answer call must use the guard to avoid overlapping inference and index publication. For an async route, call the guarded synchronous function in a worker thread rather than blocking the event loop. Restarting opens the saved Chroma release without inserting all chunks a second time. The initial baseline continues using the host's original database until a managed release is built.

The adapter was tested with a fake vector store for embedding reuse, metadata preservation, publication, and restart loading. Full BGE/Chroma/Llama deployment integration has not been run or claimed. The deployed URL and actual web-to-engine wiring still need verification. This adapter does not infer official approval status or authority from filenames.

## Verification

Backend tests cover access restrictions, pending uploads, review/activation separation, rejection, empty-text build failure, failed publication rollback, source-tampering detection, invalid targets, exclusion/re-enablement, restoration, and persistence. A real local search-service test checks that activation replaces searchable text and starts a fresh answer cache while preserving an in-flight old runtime.

The Meet adapter test uses a fake Chroma implementation and checks that the existing embedding object and source metadata are retained, and that restart opens an index rather than inserting duplicate records.

Browser verification uses an isolated test server, generated PDFs, and a lightweight text-validating builder. It exercises upload, approval, activation, exclusion, re-enablement, release restore, rebuild, and console locking through real HTTP APIs. It does not change the user's running server or official documents. Desktop and mobile layouts are checked separately.

```bash
./venv/bin/python -m unittest tests.test_admin tests.test_admin_lifecycle tests.test_policy_claims tests.test_policy_exceptions tests.test_authority_conflicts tests.test_vertical_slice tests.test_hybrid_rag tests.test_response_cache -q
```

## Requirements update

| Requirement | Current status |
|---|---|
| Administrator token protection and pending upload | Implemented locally |
| Approve/reject with a recorded reason | Implemented locally |
| Activate a replacement version after building the index | Implemented and locally tested |
| Exclude/re-enable eligible sources | Implemented and locally tested |
| Rebuild and restore earlier document releases | Implemented and locally tested |
| Meet BGE/Chroma deployment connection | Adapter provided; full host integration pending |
| Individual reviewer roles and account attribution | Not implemented; shared operator token |
| Arbitrary authority changes or new governing-document registration | Not exposed through the console |
| Golden Set evaluation button and user feedback queue | Not implemented in this update |
| Multiworker coordination and automatic release retention | Not implemented |

## Report wording

We extended the administrator console to review uploaded document versions and control their use in search. An administrator selects the registered source that an upload replaces and records an approval or rejection reason. Approval does not immediately change the chatbot's knowledge base. When an approved version is activated, the system builds a separate index and checks that the enabled documents provide searchable text. It switches to the new release only after successful construction.

Previous source versions and search settings are retained so an administrator can restore an earlier release. Search exclusion and re-enablement also create a new release. The registered authority values are inherited rather than entered freely in the interface. Local tests checked review decisions, activation, failed updates, restoration, and answer-cache replacement. Integration with the selected BGE/Chroma deployment remains a separate verification step. Administrator access still uses a shared token, so individual reviewer identity and role separation are not claimed.
