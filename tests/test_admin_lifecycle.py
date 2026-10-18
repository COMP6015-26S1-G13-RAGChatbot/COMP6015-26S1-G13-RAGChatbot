import base64
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from backend.admin import install_admin
from backend.services.admin_lifecycle import DocumentLifecycle


def text_pdf(text):
    writer = PdfWriter()
    page = writer.add_blank_page(width=500, height=700)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                             NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
    stream = DecodedStreamObject()
    stream.set_data(('BT /F1 12 Tf 30 600 Td ('+text+') Tj ET').encode())
    page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO(); writer.write(output)
    return output.getvalue()


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'ADMIN_STORAGE_DIR': str(self.root / 'uploads'),
                                          'ADMIN_ACCESS_TOKEN': 'x'*48})
        self.env.start()
        self.original = self.root / 'original.pdf'
        self.original.write_bytes(text_pdf('Original policy requires approval before activity starts.'))
        records = [{'document_id': 'policy', 'title': 'Policy', 'version': '1',
                    'document_type': 'operations_manual', 'approval_status': 'approved',
                    'authority_level': 80, 'effective_date': None, 'usage': 'production',
                    'retrieval_enabled': True, 'source_path': str(self.original), 'content_hash': 'auto'},
                   {'document_id': 'test', 'title': 'Golden set', 'version': '1',
                    'approval_status': 'evaluation_only', 'usage': 'evaluation_only',
                    'retrieval_enabled': False, 'source_path': 'not-used'}]
        self.published = []
        def builder(directory, rows):
            for row in rows:
                if row['usage'] == 'production' and row['retrieval_enabled']:
                    content = ''.join(p.extract_text() for p in PdfReader(row['source_path']).pages)
                    if not content.strip():
                        raise ValueError('No searchable text')
            return rows
        self.manager = DocumentLifecycle(self.root/'releases', records, builder, self.published.append)
        self.app = FastAPI(); install_admin(self.app)
        self.app.state.document_lifecycle = self.manager
        self.app.state.admin_document_provider = lambda: self.manager.current()['records']
        self.client = TestClient(self.app)
        self.headers = {'Authorization': 'Bearer '+'x'*48}

    def tearDown(self):
        self.client.close(); self.env.stop(); self.temp.cleanup()

    def submit(self, raw=None):
        response = self.client.post('/api/admin/uploads', headers=self.headers, json={
            'title': 'Policy replacement', 'version': '2',
            'content_base64': base64.b64encode(raw or text_pdf('Updated policy requires approval within thirty days.')).decode()})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['id']

    def post(self, path, **data):
        return self.client.post('/api/admin/'+path, headers=self.headers,
                                json={'reason': 'Reviewed against source documents', **data})

    def approve(self, identifier):
        return self.post('uploads/'+identifier+'/review', decision='approved', target_document_id='policy')

    def test_review_does_not_activate_then_activate_and_restore(self):
        baseline = self.manager.current()['release_id']
        upload = self.submit()
        self.assertEqual(self.approve(upload).status_code, 200)
        self.assertEqual(self.manager.current()['release_id'], baseline)
        self.assertEqual(self.published, [])
        response = self.post('uploads/'+upload+'/activate')
        self.assertEqual(response.status_code, 200, response.text)
        row = self.manager.current()['records'][0]
        self.assertEqual(row['version'], '2')
        self.assertEqual(row['authority_level'], 80)
        self.assertEqual(self.original.read_bytes(), text_pdf('Original policy requires approval before activity starts.'))
        response = self.post('releases/'+baseline+'/restore')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.manager.current()['records'][0]['version'], '1')
        self.assertEqual(len(self.manager.history()), 3)

    def test_rejection_reason_and_no_activation_of_unapproved_files(self):
        upload = self.submit()
        self.assertEqual(self.post('uploads/'+upload+'/activate').status_code, 422)
        self.assertEqual(self.post('uploads/'+upload+'/review', decision='rejected').status_code, 200)
        self.assertEqual(self.approve(upload).status_code, 409)
        self.assertEqual(self.post('uploads/'+upload+'/activate').status_code, 422)

    def test_empty_pdf_activation_fails_without_changing_current_release(self):
        writer = PdfWriter(); writer.add_blank_page(width=100, height=100)
        stream = io.BytesIO(); writer.write(stream)
        upload = self.submit(stream.getvalue()); self.approve(upload)
        before = self.manager.current()
        self.assertEqual(self.post('uploads/'+upload+'/activate').status_code, 422)
        self.assertEqual(self.manager.current(), before)
        self.assertEqual(len(self.manager.history()), 1)
        self.assertEqual(self.published, [])

    def test_exclusion_checks_identity_and_preserves_at_least_one_source(self):
        self.assertEqual(self.post('documents/policy/retrieval', enabled=False).status_code, 422)
        self.assertEqual(self.post('documents/test/retrieval', enabled=True).status_code, 422)
        self.assertEqual(self.post('documents/unknown/retrieval', enabled=True).status_code, 422)

    def test_approved_bytes_are_checked_again_before_activation(self):
        upload = self.submit(); self.approve(upload)
        (self.root/'uploads'/(upload+'.pdf')).write_bytes(text_pdf('Tampered policy text'))
        self.assertEqual(self.post('uploads/'+upload+'/activate').status_code, 422)
        self.assertEqual(len(self.manager.history()), 1)

    def test_rebuild_and_restart_use_saved_active_release(self):
        self.assertEqual(self.post('index/rebuild').status_code, 200)
        identifier = self.manager.current()['release_id']
        second = DocumentLifecycle(self.root/'releases', [], self.manager.build, self.published.append)
        self.assertEqual(second.current()['release_id'], identifier)

    def test_exclude_enable_and_restore_search_settings(self):
        rows = self.manager.current()['records']
        rows.append({**rows[0], 'document_id': 'second', 'title': 'Second policy'})
        manager = DocumentLifecycle(self.root/'two-releases', rows, self.manager.build, self.published.append)
        self.app.state.document_lifecycle = manager
        baseline = manager.current()['release_id']
        self.assertEqual(self.post('documents/policy/retrieval', enabled=False).status_code, 200)
        self.assertFalse(manager.current()['records'][0]['retrieval_enabled'])
        self.assertEqual(self.post('documents/policy/retrieval', enabled=True).status_code, 200)
        self.assertTrue(manager.current()['records'][0]['retrieval_enabled'])
        self.assertEqual(self.post('releases/'+baseline+'/restore').status_code, 200)

    def test_meet_adapter_preserves_embedding_and_metadata(self):
        from types import SimpleNamespace
        from backend.services.meet_admin_adapter import install_meet_lifecycle
        rows = self.manager.current()['records'][:1]
        rows[0]['source_metadata'] = {'source': 'Chosen policy.pdf', 'source_type': 'authoritative',
                                      'authority_level': 80, 'authority_rank': 80}
        embedding = object()
        engine = SimpleNamespace(embedding=embedding, db=object(), _LAST_QUERY='previous question')
        calls = []
        def factory(**kwargs):
            calls.append(kwargs)
            Path(kwargs['persist_directory']).mkdir()
            return SimpleNamespace(get=lambda **_: {'ids': ['chunk1']})
        def chunks(pages):
            return [{**p, 'chunk_id': i, 'page_chunk_index': 0} for i,p in enumerate(pages)]
        manager = install_meet_lifecycle(self.app, engine, rows, lambda text: text, chunks,
                                         self.root/'meet', vectorstore_factory=factory,
                                         vectorstore_loader=lambda path: 'restored-database')
        manager.change('Rebuild using selected embeddings')
        self.assertIs(calls[0]['embedding'], embedding)
        self.assertEqual(calls[0]['metadatas'][0]['source'], 'Chosen policy.pdf')
        self.assertEqual(calls[0]['metadatas'][0]['authority_rank'], 80)
        self.assertEqual(engine._LAST_QUERY, '')
        self.assertEqual(len(calls), 1)
        install_meet_lifecycle(self.app, engine, rows, lambda text: text, chunks,
                               self.root/'meet', vectorstore_factory=factory,
                               vectorstore_loader=lambda path: 'restored-database')
        self.assertEqual(engine.db, 'restored-database')
        self.assertEqual(len(calls), 1)  # Restart opens saved Chroma, never appends duplicates.

    def test_publish_failure_restores_active_pointer(self):
        before = self.manager.current()
        def fail(_):
            raise RuntimeError('Publishing failed')
        self.manager.publish = fail
        self.assertEqual(self.post('index/rebuild').status_code, 503)
        self.assertEqual(self.manager.current(), before)
        self.assertEqual(len(self.manager.history()), 1)

    def test_all_new_mutations_require_admin_and_valid_reason(self):
        for path in ['uploads/'+'a'*32+'/review', 'uploads/'+'a'*32+'/activate',
                     'documents/policy/retrieval', 'index/rebuild', 'releases/'+'a'*32+'/restore']:
            self.assertEqual(self.client.post('/api/admin/'+path, json={}).status_code, 401)
        self.assertEqual(self.post('index/rebuild', reason='x').status_code, 422)

    def test_real_local_adapter_rebuilds_search_and_clears_cache(self):
        from types import SimpleNamespace
        from backend.models import DocumentRecord
        from backend.services.registry_service import RegistryService
        from backend.services.ingest_service import IngestService
        from backend.services.embedding_service import EmbeddingService
        from backend.services.search_service import SearchService
        from backend.services.rag_service import RAGService
        from backend.services.audit_service import AuditService
        from backend.services.evaluation_service import EvaluationService
        from backend.services.response_cache import TTLCache
        from backend.services.admin_lifecycle import install_local_lifecycle
        rows = self.manager.current()['records'][:1]
        registry_file = self.root/'registry.json'
        registry_file.write_text(json.dumps(rows))
        registry = RegistryService(registry_file, self.root)
        chunks = IngestService(registry, self.root/'index.json').build()
        embeddings = EmbeddingService([c.text for c in chunks], backend='local_lsa')
        search = SearchService(registry, chunks, embeddings)
        rag = RAGService(search, llm=SimpleNamespace(available=False))
        audit = AuditService(registry, search)
        graph = SimpleNamespace(registry=registry, search=search, rag=rag, audit=audit,
                                evaluation=EvaluationService(audit), chat_cache=TTLCache(max_entries=4, ttl_seconds=30))
        graph.chat_cache.set('old', 'stale answer')
        manager = install_local_lifecycle(self.app, graph, self.root/'real-releases')
        old = self.app.state.runtime
        upload = self.submit(); self.approve(upload)
        response = self.post('uploads/'+upload+'/activate')
        self.assertEqual(response.status_code, 200, response.text)
        new = self.app.state.runtime
        self.assertIsNot(old, new)
        self.assertEqual(len(new.chat_cache), 0)
        self.assertEqual(old.chat_cache.get('old'), 'stale answer')
        self.assertIn('thirty days', ' '.join(c.text for c in new.search.chunks))
        self.assertNotIn('thirty days', ' '.join(c.text for c in old.search.chunks))
        self.assertEqual(new.registry.get('policy').version, '2')
        active = manager.current()['release_id']
        install_local_lifecycle(self.app, graph, self.root/'real-releases')
        self.assertEqual(self.app.state.document_lifecycle.current()['release_id'], active)
        self.assertEqual(self.app.state.runtime.registry.get('policy').version, '2')


if __name__ == '__main__':
    unittest.main()
