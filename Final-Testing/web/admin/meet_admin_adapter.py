"""Optional adapter for Meet's loaded BGE/Chroma engine.

Requires explicit document inventory and the selected clean/chunk functions.
Never imports the engine automatically or deletes the active Chroma directory.
"""
from pathlib import Path

from pypdf import PdfReader

from .admin_lifecycle import DocumentLifecycle


def install_meet_lifecycle(app, engine, inventory, clean_text, chunk_documents, folder,
                           vectorstore_factory=None, vectorstore_loader=None):
    """inventory rows include normal registry fields plus source_metadata.

    source_metadata must retain Meet's original source/source_type and authority
    fields so the existing retrieval and conflict logic sees the same schema.
    Install after loading the engine. Route all inference through guarded_answer.
    """
    if vectorstore_factory is None:
        from langchain_community.vectorstores import Chroma
        vectorstore_factory = Chroma.from_texts
    if vectorstore_loader is None:
        from langchain_community.vectorstores import Chroma
        vectorstore_loader = lambda path: Chroma(persist_directory=str(path), embedding_function=engine.embedding)

    def build(directory, records):
        pages = []
        enabled = [r for r in records if r['usage'] == 'production'
                   and r['approval_status'] == 'approved' and r['retrieval_enabled']]
        for row in enabled:
            import hashlib
            raw = Path(row['source_path']).read_bytes()
            if hashlib.sha256(raw).hexdigest() != row['content_hash']:
                raise ValueError('Archived document checksum mismatch')
            metadata = row.get('source_metadata')
            if not metadata or not {'source', 'source_type', 'authority_level', 'authority_rank'} <= metadata.keys():
                raise ValueError('Meet source metadata must be supplied explicitly')
            extracted = 0
            for number, page in enumerate(PdfReader(row['source_path']).pages, 1):
                text = clean_text(page.extract_text() or '')
                if not text.strip():
                    continue
                pages.append({**metadata, 'page': number, 'content': text})
                extracted += 1
            if not extracted:
                raise ValueError('An enabled PDF has no searchable text')
        chunks = chunk_documents(pages)
        texts, metadatas = [], []
        for chunk in chunks:
            if chunk['content'].strip():
                texts.append(chunk['content'])
                metadatas.append({key: chunk[key] for key in
                                  ('source', 'page', 'source_type', 'authority_level',
                                   'authority_rank', 'chunk_id', 'page_chunk_index')})
        if not texts:
            raise ValueError('No searchable chunks were produced')
        database = vectorstore_factory(texts=texts, metadatas=metadatas,
                                       embedding=engine.embedding,
                                       persist_directory=str(directory / 'chroma'))
        stored = database.get(include=['metadatas'])
        if len(stored['ids']) != len(texts):
            raise ValueError('Chroma did not store the expected chunk count')
        return database

    def publish(database):
        engine.db = database
        for key in ('_LAST_QUERY', '_LAST_AUTHORITATIVE_RESULTS', '_LAST_SUPPORTING_RESULTS', '_LAST_GENERATION_RESULTS'):
            if hasattr(engine, key):
                setattr(engine, key, '' if key == '_LAST_QUERY' else [])

    existed = (Path(folder) / 'current.json').exists()
    manager = DocumentLifecycle(folder, inventory, build, publish)
    if existed:
        current = manager.current()
        saved = Path(folder) / current['release_id'] / 'chroma'
        if saved.exists():
            publish(vectorstore_loader(saved))
        # Initial baseline has no managed Chroma; the host loaded its original DB.
    app.state.document_lifecycle = manager
    # Read the release inventory, not stale metadata from the original directory.
    app.state.admin_document_provider = lambda: [
        {key: row.get(key) for key in ('document_id', 'title', 'version', 'approval_status',
                                     'usage', 'retrieval_enabled', 'authority_level')}
        for row in manager.current()['records']]
    app.state.admin_chunk_count_provider = lambda: len(engine.db.get(include=['metadatas'])['ids'])
    return manager


def guarded_answer(manager, answer_function, question):
    """Serialise Meet's module-level query state and index switch, single worker."""
    with manager.lock:
        return answer_function(question)
