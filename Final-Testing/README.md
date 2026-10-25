# Final Testing

IEEE SMCS governance RAG chatbot: the retrieval pipeline (`src/`), its
evaluation (`evaluation/`), and a web interface (`web/`).

## Web interface

A browser front end for the chatbot. It calls the same pipeline as
`src/rag_chat.py` (unchanged) and shows each answer with its cited source,
a link to the exact PDF page, any detected rule conflicts with the
document that takes precedence, and the full pipeline log. It has light,
dark and automatic themes, saves conversations in the browser, and works
on phones. The page loads nothing from the internet (fonts are bundled).

| Light | Dark |
| --- | --- |
| ![Welcome screen, light theme](docs/screenshots/light-welcome.png) | ![Answer with source and conflict, dark theme](docs/screenshots/dark-chat.png) |
| ![Answer with source and conflict, light theme](docs/screenshots/light-chat.png) | ![Mobile layout, dark theme](docs/screenshots/mobile-dark.png) |

### Requirements

- Python with a virtual environment
- [Ollama](https://ollama.com) with the `llama3` model (`ollama pull llama3`)
- A built vector database in `chroma_db/` (run `python src/ingest.py` once)

### Setup (Windows, first time)

Run these in PowerShell from the project folder:

```powershell
python -m venv venv
venv\Scripts\activate
python -m pip install -r requirements-lock.txt
```

`requirements-lock.txt` pins the exact versions of a known-working setup.
`requirements.txt` lists only the direct dependencies, without versions.

On macOS/Linux, activate with `source venv/bin/activate` instead.

### Run

1. Start Ollama (open the Ollama app, or run `ollama serve`).
2. Activate the virtual environment: `venv\Scripts\activate`
3. Start the server with the same Python that runs `rag_chat.py`:

   ```powershell
   python web\server.py
   ```

4. Wait for `Pipeline ready in …s` in the terminal (the first start can
   take a few minutes while the embedding model downloads).
5. Open http://localhost:8000. The sidebar status turns green (**Ready**)
   when it can answer. Questions asked earlier wait and are sent
   automatically.

Press **Ctrl + C** in the terminal to stop it.

### Sign-in

![Sign-in page](docs/screenshots/sign-in.png)

The site asks users to sign in. On the sign-in page, choose **Create
account** to make the first account (username of 3–32 letters, numbers,
dots, hyphens or underscores; password of at least 8 characters).

- Accounts are stored in `web/users.db`, created automatically. Passwords
  are saved only as salted PBKDF2 hashes. The file is ignored by git, so
  never commit it.
- Each user sees only their own conversation history. History is kept in
  the browser, so it is per user and per browser.
- Five wrong passwords in a row lock that username for 60 seconds.
- Sessions last 7 days, or until the user clicks **Sign out**.

Manage accounts from the command line (run from the project folder, with
the venv active):

```powershell
python web\auth.py add alice      # create an account (asks for a password)
python web\auth.py passwd alice   # reset a forgotten password
python web\auth.py remove alice
python web\auth.py list
```

Settings (set before starting the server, e.g. `$env:RAG_ALLOW_SIGNUP="0"`):

| Variable | Effect |
| --- | --- |
| `RAG_ALLOW_SIGNUP=0` | Hide **Create account**; only accounts made with `web\auth.py add` can sign in |
| `RAG_AUTH=0` | Turn sign-in off completely (anyone who can open the page can use it) |
| `RAG_COOKIE_SECURE=1` | Mark the session cookie HTTPS-only; use when serving over HTTPS |
| `RAG_USERS_DB=path` | Keep the accounts database somewhere else |

### Administrator console

The document administration console from the `feat/admin-login` branch is
built in at **http://localhost:8000/admin**. Its code is in `web/admin/`
and is kept as on that branch (only the page styling, its import lines, and
a font permission were changed). It is separate from user sign-in and is
unlocked with an administrator token.

![Administrator console](docs/screenshots/admin-console.png)

**Enable it** (PowerShell, in the project folder, venv active):

```powershell
python -m pip install pypdf
$env:ADMIN_ACCESS_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(48))"
echo $env:ADMIN_ACCESS_TOKEN     # copy this; you paste it into the console
python web\server.py
```

The token must be at least 32 characters. Keep it private: never put it in
GitHub, chat or screenshots. Set it again each time you open a new
terminal (or use the same value each time). Without it, `/admin` opens but
stays locked.

**What it does**

- Lists the documents in the index, with version, status and authority.
- **Submit a PDF for review**: saved as *pending*; never searched.
- **Approve / Reject** with a reason. Approving does not change search yet.
- **Activate version**: builds a new index with the new PDF replacing the
  chosen document, checks it, then switches the chatbot to it. If anything
  fails, the previous index stays active. Citations then link to the new PDF.
- **Exclude from search / Enable search** for a document.
- **Rebuild current index** and **Restore** an earlier release.
- Service counters and a log of administrator actions.

Every change needs a reason and creates a new *release*; nothing is
overwritten. Questions wait while an index is being rebuilt.

**How it connects to the chatbot**

- On the first start with a token, the server writes the document list to
  `.admin_data/inventory/inventory.json`, using the same authority values as
  `src/parse_pdf.py`. All PDFs with extractable text are searchable, which
  matches the existing `chroma_db`. `financial-ops-manual.pdf` is a scanned
  document with no text layer, so it is listed but not searchable (it is not
  in the original index either).
- The chatbot keeps using the original `chroma_db` until an administrator
  activates, excludes, rebuilds or restores something. From then on it uses
  the active release, also after a restart.
- Data is stored in `.admin_data/` next to the project (not inside `web/`,
  so updating the web folder keeps it). It is ignored by git. Back it up and
  never delete `.admin_data/releases` while it is in use.
- Limits (from the original design): one shared administrator token rather
  than individual accounts; one server process.

### Using it in another project folder

Copy the `web/` folder into the folder that holds your RAG files (for
example `RAG/`) and run `python web\server.py` from that folder. The
server works out the paths itself:

- `rag_chat.py` can be in `src/` or directly in the folder
- `chroma_db/` and `data/` (the PDFs) are expected in the folder

On start-up it prints the Python executable and the paths it is using, and
flags anything missing. To point it at a folder explicitly, set
`RAG_PROJECT_DIR` (PowerShell: `$env:RAG_PROJECT_DIR="E:\RAG"`).
Set `PORT` to use a port other than 8000.

### Demo mode

To preview the interface without Ollama or the vector database (canned
responses):

```powershell
$env:RAG_DEMO_MODE="1"; python web\server.py
```

### Troubleshooting

| Problem | Fix |
| --- | --- |
| `/admin` says "Admin access is not configured" | Set `ADMIN_ACCESS_TOKEN` (32+ characters) before starting the server |
| "Admin console: unavailable (pypdf …)" at start-up | `python -m pip install pypdf` |
| "Another index operation is running" | Wait for the current rebuild or question to finish, then try again |
| Forgot a password | `python web\auth.py passwd <username>` sets a new one |
| "Too many failed attempts" | Wait 60 seconds, then try again |
| "The assistant is still loading" | The models are still loading. Wait for `Pipeline ready` in the terminal; questions now wait automatically. |
| "Missing packages in this Python environment" or "Could not import chromadb" | The server is running on a different Python from your project. Activate the venv and start it with `python web\server.py`, not `uvicorn`. The message prints the exact `pip install` command for the Python in use. |
| `cannot import name '_ExtendedAttributes' from 'opentelemetry.util.types'` | OpenTelemetry packages are on mismatched versions. Run `python -m pip install -r requirements-lock.txt`, or upgrade them together: `python -m pip install --upgrade opentelemetry-api opentelemetry-sdk opentelemetry-proto opentelemetry-exporter-otlp-proto-grpc opentelemetry-exporter-otlp-proto-common` |
| `chroma_db ... (NOT FOUND - run ingest first)` | Build the database: `python src\ingest.py` from the project folder. |
| Every answer says "Not covered by the documents" | `chroma_db/` is empty or in a different folder. Check the paths printed at start-up. |
| Page shows "Offline" | The server terminal was closed. Start it again. |
| `Address already in use` | Use another port: `$env:PORT="8001"; python web\server.py` |

Check for other package conflicts with `python -m pip check`.

### Files

| File | Purpose |
| --- | --- |
| `web/server.py` | FastAPI app: `/api/chat`, `/api/health`, `/api/documents`, sign-in routes, serves PDFs under `/files/` to signed-in users |
| `web/auth.py` | Accounts and sessions (SQLite, PBKDF2 password hashes); also the account command-line tool |
| `web/static/login.html`, `login.js` | Sign-in and create-account page |
| `web/admin/` | Administrator console from the `feat/admin-login` branch (`admin.py`, `admin_lifecycle.py`, `meet_admin_adapter.py`, restyled `admin_console.html`) |
| `web/admin_integration.py` | Connects the console to this chatbot's engine and documents |
| `web/static/index.html` | Page layout |
| `web/static/styles.css` | Styling, light/dark themes, mobile layout |
| `web/static/app.js` | Chat logic, conversation history (saved in the browser), source and conflict cards |
| `web/static/fonts/` | IBM Plex fonts (SIL Open Font License), bundled so the page works offline |

## Secrets

Copy `.env.example` to `.env` for any local secrets. `.env` files are
ignored by git and must never be committed or shared. The pipeline itself
does not currently read any token.
