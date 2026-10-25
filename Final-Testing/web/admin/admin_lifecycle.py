"""Immutable releases and an atomic active-release pointer (single process)."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from threading import RLock
from uuid import uuid4


def atomic_json(path, data):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    try:
        with temp.open('x') as stream:
            json.dump(data, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temp.chmod(0o600)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class DocumentLifecycle:
    """A builder returns a new runtime; publishing replaces one runtime reference.

    Changes operate on registered approved production identities only. Source
    authority is inherited, never assigned from browser input.
    """
    def __init__(self, folder, records, build, publish, active_path=None):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.build, self.publish = build, publish
        self.pointer = self.folder / 'current.json'
        self.status = {'state': 'idle', 'error': None}
        if not self.pointer.exists():
            identifier = uuid4().hex
            release = self.folder / identifier
            release.mkdir()
            self._save(release, records, 'Initial document inventory', None)
            if active_path and Path(active_path).exists():
                shutil.copy2(active_path, release / 'index.json')
            atomic_json(self.pointer, {'release_id': identifier})

    def current(self):
        identifier = json.loads(self.pointer.read_text())['release_id']
        return self.release(identifier)

    def release(self, identifier):
        if not re.fullmatch('[a-f0-9]{32}', identifier):
            raise ValueError('Invalid release identifier')
        path = self.folder / identifier / 'release.json'
        if not path.exists():
            raise ValueError('Release not found')
        return json.loads(path.read_text())

    def history(self):
        active = self.current()['release_id']
        result = []
        for path in self.folder.glob('*/release.json'):
            record = json.loads(path.read_text())
            result.append({k: record[k] for k in ('release_id', 'created_at', 'reason', 'parent')}
                          | {'active': record['release_id'] == active})
        return sorted(result, key=lambda item: item['created_at'], reverse=True)

    def _save(self, directory, records, reason, parent):
        rows = deepcopy(records)
        sources = directory / 'sources'
        sources.mkdir()
        # Archive every production PDF, even temporarily excluded versions.
        for row in rows:
            if row['usage'] != 'production':
                continue
            source = Path(row['source_path'])
            if not source.is_file():
                raise ValueError('A registered production source is missing')
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            expected_hash = row.get('content_hash')
            if expected_hash and expected_hash != 'auto' and expected_hash != digest:
                raise ValueError('A registered source changed outside the review process')
            target = sources / (digest + '.pdf')
            if not target.exists():
                shutil.copyfile(source, target)
                target.chmod(0o600)
            row['source_path'] = str(target.resolve())
            row['content_hash'] = digest
        record = {'release_id': directory.name, 'created_at': datetime.now(timezone.utc).isoformat(),
                  'reason': reason, 'parent': parent, 'records': rows}
        atomic_json(directory / 'release.json', record)
        atomic_json(directory / 'registry.json', rows)
        return record

    def change(self, reason, transform=None, restore=None):
        if not self.lock.acquire(blocking=False):
            raise ValueError('Another index operation is running; try again after it finishes')
        directory = None
        try:
            self.status = {'state': 'building', 'error': None}
            current = self.current()
            rows = deepcopy(self.release(restore)['records'] if restore else current['records'])
            if transform:
                transform(rows)
            if not any(r['usage'] == 'production' and r['approval_status'] == 'approved'
                       and r['retrieval_enabled'] for r in rows):
                raise ValueError('At least one approved document must remain searchable')
            directory = self.folder / uuid4().hex
            directory.mkdir()
            record = self._save(directory, rows, reason, current['release_id'])
            runtime = self.build(directory, record['records'])
            # Build/validation failures above leave the active pointer unchanged.
            # Readers see either old or new immutable runtime, never half a graph.
            old_pointer = {'release_id': current['release_id']}
            atomic_json(self.pointer, {'release_id': directory.name})
            try:
                self.publish(runtime)
            except Exception:
                atomic_json(self.pointer, old_pointer)
                raise
            self.status = {'state': 'succeeded', 'error': None, 'release_id': directory.name}
            return {k: record[k] for k in ('release_id', 'created_at', 'reason', 'parent')}
        except Exception:
            self.status = {'state': 'failed', 'error': 'Index update failed; the previous release remains active'}
            if directory:
                shutil.rmtree(directory, ignore_errors=True)
            raise
        finally:
            self.lock.release()

    @staticmethod
    def target(rows, document_id):
        row = next((r for r in rows if r['document_id'] == document_id), None)
        if not row or row['usage'] != 'production' or row['approval_status'] != 'approved':
            raise ValueError('Choose an existing approved production document')
        return row

    def toggle(self, document_id, enabled, reason):
        def change(rows):
            self.target(rows, document_id)['retrieval_enabled'] = enabled
        return self.change(reason, change)

    def activate(self, document_id, upload, path, reason):
        if upload['approval_status'] != 'approved':
            raise ValueError('The upload must be approved before activation')
        if upload.get('target_document_id') != document_id:
            raise ValueError('Upload approval does not match this document')
        raw = Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != upload['sha256']:
            raise ValueError('Uploaded file changed after submission')
        def change(rows):
            row = self.target(rows, document_id)
            # Title/authority/type remain the registered governance identity.
            row.update(version=upload['version'], source_path=str(Path(path).resolve()),
                       content_hash=upload['sha256'], retrieval_enabled=True)
        return self.change(reason, change)


def install_local_lifecycle(app, runtime, folder):
    from types import SimpleNamespace
    from backend.services.registry_service import RegistryService
    from backend.services.ingest_service import IngestService
    from backend.services.embedding_service import EmbeddingService
    from backend.services.search_service import SearchService
    from backend.services.rag_service import RAGService
    from backend.services.audit_service import AuditService
    from backend.services.evaluation_service import EvaluationService
    from backend.services.response_cache import TTLCache
    from backend.core.config import Config

    def build(directory, rows):
        registry = RegistryService(directory / 'registry.json', runtime.registry.data_dir)
        # Verify archived sources before rebuilding or loading on restart.
        for r in registry.records:
            if r.usage == 'production':
                if hashlib.sha256(Path(r.source_path).read_bytes()).hexdigest() != r.content_hash:
                    raise ValueError('Archived document checksum mismatch')
        chunks = IngestService(registry, directory / 'index.json').build()
        for r in registry.production_documents():
            if not any(c.document_id == r.document_id and c.text.strip() for c in chunks):
                raise ValueError('An enabled PDF has no searchable text')
        embeddings = EmbeddingService([f'{c.section or ""} {c.heading or ""} {c.text}' for c in chunks],
                                      backend=runtime.search.embeddings.backend)
        search = SearchService(registry, chunks, embeddings)
        rag = RAGService(search, llm=runtime.rag.llm)
        audit = AuditService(registry, search)
        return SimpleNamespace(registry=registry, search=search, rag=rag, audit=audit,
                               evaluation=EvaluationService(audit),
                               chat_cache=TTLCache(max_entries=Config.CHAT_CACHE_MAX_ENTRIES,
                                                   ttl_seconds=Config.CHAT_CACHE_TTL_SECONDS))

    def publish(graph):
        app.state.runtime = graph
        # Compatibility for existing health checks, tests and admin inventory.
        for name in ('registry', 'search', 'rag', 'audit', 'evaluation', 'chat_cache'):
            setattr(app.state, name, getattr(graph, name))

    records = []
    for row in runtime.registry.records:
        record = row.model_dump(mode='json')
        record['source_path'] = str((runtime.registry.data_dir / row.source_path).resolve())
        records.append(record)
    existed = (Path(folder) / 'current.json').exists()
    lifecycle = DocumentLifecycle(folder, records, build, publish, Config.INDEX_PATH)
    if existed:
        current = lifecycle.current()
        publish(build(Path(folder) / current['release_id'], current['records']))
    else:
        publish(runtime)
    app.state.document_lifecycle = lifecycle
    return lifecycle
