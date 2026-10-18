# SMCS administrator console requirements and handover

Prepared for team review on 18 October 2026.

**Update:** Document approval/rejection, version activation, search exclusion, index rebuilding, and release restoration have now been added locally. The guide `Admin_Document_Lifecycle_Guide.md` supersedes the original pending-only scope and FR4.1 status below. Meet deployment integration and individual accounts remain pending. The remaining sections preserve the initial handover record.

## Scope and deployment status

The local repository now includes a small administrator console at `/admin` on the FastAPI server. It provides protected document status, pending PDF submissions, downloads, aggregate service counters, and an upload audit trail. It does not alter the chatbot's retrieval algorithm or replace the selected BGE/ChromaDB/Llama implementation.

Meet's deployed URL, source branch, and hosting configuration were not supplied. Integration with that deployment remains unverified. The local application's document registry is connected automatically. A different FastAPI application can provide an adapter for its own document inventory. This is an integration-ready local module, not a claim that the deployed website has these features.

The supplied COMP6016 form contains example student-project requirements. They are not requirements for student registration, supervisor matching, or course administration in this chatbot. The project-specific rows below replace those examples.

## Functional requirements

Use the course form's functionality scale after deployment and user testing. The evidence here establishes local automated behaviour only; it does not justify marking the whole deployed system fully functional.

| ID | Requirement | Implementation and evidence | Current status | Contribution |
|---|---|---|---|---|
| FR1.1 | Restrict administrator data and upload operations | All `/api/admin/*` routes validate a server-side bearer token; missing configuration disables access | Local automated tests passed; deployment pending | Jueun Yoo, with AI-assisted implementation; team to confirm attribution |
| FR1.2 | Lock the console | Clears token, displayed data, and upload inputs in the browser | Implemented; browser acceptance testing pending | Same as above |
| FR2.1 | Display registered document metadata | Title, version, approval status, usage, retrieval flag, authority | Current registry adapter implemented; Meet's inventory adapter pending | Same as above |
| FR2.2 | Submit PDF versions for review | Title/version required; generated file IDs, hash, UTC time, page count; PDF validation | Local automated tests passed | Same as above |
| FR2.3 | Keep submitted PDFs out of live retrieval | Files stored outside the corpus; always pending and retrieval disabled | Local automated tests passed | Same as above |
| FR2.4 | Download pending files for manual review | Protected download endpoint and console button | API test passed; browser acceptance testing pending | Same as above |
| FR3.1 | Display basic usage | Counts `/api/chat`, `/ask`, `/api/audit` calls and HTTP failures since process startup | Local automated test passed; no historical analytics | Same as above |
| FR3.2 | Inspect administrative actions | Append-only upload-event JSONL file and latest 100 events | Local automated test passed; shared identity only | Same as above |
| FR4.1 | Approve a document and refresh the chosen search index | Requires Meet's ingestion and ChromaDB integration, with validation and rollback | Not implemented | To be assigned |
| FR4.2 | Individual accounts, roles, logout revocation, password reset, MFA | Shared operator token is not an account system | Not implemented | To be assigned |
| FR4.3 | Run the chosen 50-question evaluation from the console | Must call Meet's actual evaluator and dataset | Not implemented | To be assigned |

## Non-functional requirements

| ID | Requirement | Current evidence and limit |
|---|---|---|
| NFR1.1 | Limit upload resource usage | Maximum 8 MiB decoded PDF, bounded JSON body, 1–500 pages, up to 100 pending files. Host request timeout and proxy limits still required. |
| NFR2.1 | Protect credentials | Token is read from environment; no hardcoded secret; constant-time comparison; browser keeps it only in page memory. Requires HTTPS and operator token rotation. |
| NFR2.2 | Avoid private conversation collection | Counters do not store questions, answers, IP addresses, or bearer tokens. Existing host logging must be reviewed independently. |
| NFR2.3 | Avoid rendering untrusted metadata as HTML | Console uses `textContent` for server data. Pending PDFs download as attachments. Uploaded files are not scanned for malware. |
| NFR3.1 | Preserve live knowledge during submission | Upload never invokes ingestion or modifies the production registry/index. Pending data must be backed up by the operator if needed. |
| NFR4.1 | Make the console usable on smaller screens | Responsive CSS, explicit input labels, status announcements, horizontally scrollable tables. No full accessibility or browser certification claimed. |
| NFR5.1 | Keep administration modular | Router in `backend/admin.py`, separate HTML interface, configurable storage/token, document-provider adapter. |
| NFR6.1 | State scaling limits | This version targets a single FastAPI worker. Counters and file-write locks are process-local. Multiworker deployment requires shared durable storage and locking. |

No uptime, latency SLA, full WCAG conformance, MFA, or horizontal scaling claim is established by this implementation.

## Local startup

Generate a random token in your own terminal. Do not paste it into the report, repository, URLs, or chat.

```bash
export ADMIN_ACCESS_TOKEN="$(./venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export ADMIN_STORAGE_DIR="$PWD/.admin_data"
./venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/admin` and enter the token from that terminal's environment. The operator can inspect the value locally if needed. The token must be at least 32 characters, and should be generated randomly rather than chosen as a password. Without a valid configured token, administration is disabled.

The existing Next.js proxy forwards `/api/*`, but does not forward `/admin`. Access the backend URL directly for local use. For a hosted same-origin console, configure the deployment proxy to forward both `/admin` and `/api/admin/*` to FastAPI over HTTPS. Do not put this access token in frontend environment variables or client bundles.

## Integration with Meet's FastAPI backend

Copy `backend/admin.py` and `backend/admin_console.html` into the deployed backend package and install the existing FastAPI/Pydantic/pypdf dependencies if missing. Call installation once:

```python
from backend.admin import install_admin

# After creating the FastAPI app:
install_admin(app)
```

Supply the inventory from the chosen backend if it does not expose the registry used by this checkout:

```python
# Replace this callback with a read-only function over the selected document metadata.
app.state.admin_document_provider = list_admin_document_metadata
```

The callback should return a list of dictionaries containing `document_id`, `title`, `version`, `approval_status`, `usage`, `retrieval_enabled`, and `authority_level`. Avoid sending filesystem paths or credentials to the browser. The adapter must reflect Meet's actual metadata, not invented approval status. Indexed chunk counts currently use `app.state.search.chunks`; a different backend will show “Not connected” until an equivalent adapter is added.

Set the token and persistent storage environment variables on the host. The default `.admin_data` directory is ignored by Git. Do not put it under a public static mount. Use one worker for this version. On ephemeral hosting, pending files and audit events require a persistent private volume; in-memory counters always reset on restart.

## Administrator workflow

1. Connect using the operator token.
2. Review registered document status and basic service counters.
3. Enter a document title and version and select an authorised PDF.
4. Submit it and confirm that it appears as pending and excluded from retrieval.
5. Download it for human review and inspect the upload event.
6. Lock the console when finished.

Closing or refreshing the page clears that page's token. This is not token revocation: the operator must rotate the server environment token to invalidate it. A shared token cannot identify which individual administrator performed an action.

## Automated verification

```bash
./venv/bin/python -m unittest tests.test_admin -v
```

Seven automated tests cover server-side access controls, disabled configuration, upload isolation, protected download/audit access, invalid/encrypted/oversized PDFs, private-text-free counters, invalid download identifiers, and client secret handling. These tests do not prove compatibility with Meet's deployed host.

The administrator tests and selected existing authority, workflow, hybrid retrieval, and cache regression suites passed together: 67 tests. A separate headless Chrome smoke check used mock API responses to verify connection, document-table rendering, desktop/mobile layout, and locking. The rendered screens were inspected. This is interface verification with sample data, not a deployed end-to-end test or a full browser-accessibility audit.

## Browser and deployment acceptance checklist

- Check login failure, successful connection, refresh, and locking on the deployed HTTPS origin.
- Verify document inventory matches the selected backend.
- Upload a non-sensitive valid PDF and confirm pending status, correct download, and audit event.
- Check malformed and oversized submissions and confirm the live chatbot/index remain unchanged.
- Confirm the reverse proxy preserves the Authorization header and does not log it.
- Confirm pending data is outside static mounts and survives restart on persistent storage.
- Test a narrow viewport, keyboard navigation, focus indication, and error/status messages.
- Record the deployed version, tester, date, screenshots, and outcomes before assigning the course form's functionality ratings.

## Suggested report wording

### Implementation Details

We added a separate administrator console to support document review and basic monitoring. Administrator API requests require a server-side access token. The console shows registered document metadata and allows an administrator to submit a PDF with a title and version. Each submission is saved with a generated identifier, content hash, timestamp, and pending status. Uploaded documents are kept outside the live document corpus and are not added to search automatically.

### Validation and Limitations

Local automated tests checked access restrictions, file validation, protected downloads, pending-document isolation, and aggregate counters. The console records upload events without collecting conversation text. Integration with the selected deployed backend still needs validation. Document approval, search-index refresh, individual user accounts, and persistent multiworker analytics are outside the implemented scope.

Keep the final sentence until those features have actually been integrated and verified. Completing an admin interface does not establish that the production deployment, ingestion pipeline, or user-account system is complete.
