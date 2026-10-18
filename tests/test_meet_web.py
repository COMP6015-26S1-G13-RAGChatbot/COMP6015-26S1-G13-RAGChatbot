import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfReader

from backend.meet_main import create_app
from backend.services.admin_lifecycle import DocumentLifecycle
from tests.test_admin_lifecycle import text_pdf


class MeetWebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'ADMIN_STORAGE_DIR': str(self.root/'admin'),
                                          'ADMIN_ACCESS_TOKEN': 't'*48})
        self.env.start()
        pdf = self.root/'policy.pdf'
        pdf.write_bytes(text_pdf('The policy requires approval before the activity begins.'))
        rows = [{'document_id': 'policy', 'title': 'Policy', 'version': '1', 'document_type': 'manual',
                 'approval_status': 'approved', 'usage': 'production', 'retrieval_enabled': True,
                 'authority_level': 80, 'source_path': str(pdf), 'content_hash': 'auto',
                 'source_metadata': {'source': 'policy.pdf', 'source_type': 'authoritative',
                                     'authority_level': 4, 'authority_rank': 80}}]
        self.no_citations = False
        self.engine = SimpleNamespace(EMBEDDING_MODEL='BAAI/bge-small-en-v1.5',
            ABSTENTION_TEXT='I cannot determine this from the retrieved documents.',
            model_abstained=lambda text: text.startswith('I cannot'),
            get_current_conflicts=lambda: [], select_relevant_conflict=lambda q,c: None)
        def ask(question):
            row = self.manager.current()['records'][0]
            content = PdfReader(row['source_path']).pages[0].extract_text()
            self.engine._LAST_CITATION_RESULTS = [] if self.no_citations else [
                {'doc': SimpleNamespace(page_content=content, metadata={'source':'policy.pdf','page':1})}]
            return content
        self.engine.ask_question = ask
        def factory(app):
            self.manager = DocumentLifecycle(self.root/'releases', rows, lambda d,r:r, lambda _:None)
            app.state.document_lifecycle = self.manager
            app.state.admin_document_provider = lambda:self.manager.current()['records']
            return self.engine, self.manager
        self.ollama = patch('backend.meet_main.check_ollama')
        self.ollama.start()
        self.client = TestClient(create_app(factory))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.ollama.stop();self.env.stop();self.temp.cleanup()

    def test_health_hides_unconnected_legacy_workflows(self):
        health = self.client.get('/api/health').json()
        self.assertEqual(health['default_mode'], 'hybrid_llm')
        self.assertFalse(health['capabilities']['audit'])
        self.assertFalse(health['capabilities']['evaluation'])
        self.assertEqual(self.client.get('/api/documents').json()[0]['version'], '1')

    def test_question_uses_selected_engine_and_versioned_source(self):
        response = self.client.post('/api/chat',json={'question':'What is required?', 'mode':'hybrid_llm'})
        self.assertEqual(response.status_code,200,response.text)
        answer = response.json()
        self.assertFalse(answer['abstained'])
        self.assertIsNone(answer['confidence'])
        self.assertEqual(answer['citations'][0]['page'],1)
        source = self.client.get(answer['citations'][0]['source_url'])
        self.assertEqual(source.status_code,200)
        self.assertTrue(source.content.startswith(b'%PDF-'))
        self.assertNotIn(str(self.root),response.text)

    def test_missing_final_citations_forces_abstention(self):
        self.no_citations = True
        response = self.client.post('/api/chat',json={'question':'What is required?'})
        self.assertTrue(response.json()['abstained'])
        self.assertEqual(response.json()['citations'],[])

    def test_unsupported_mode_is_not_silently_substituted(self):
        self.assertEqual(self.client.post('/api/chat',json={'question':'What is required?', 'mode':'bm25'}).status_code,422)

    def test_legacy_ask_and_admin_use_the_same_manager(self):
        self.assertEqual(self.client.post('/ask',json={'query':'What is required?'}).status_code,200)
        overview=self.client.get('/api/admin/overview',headers={'Authorization':'Bearer '+'t'*48}).json()
        self.assertTrue(overview['lifecycle_enabled'])
        self.assertEqual(overview['active_release'],self.manager.current()['release_id'])

    def test_ollama_failure_is_a_service_error_not_a_policy_answer(self):
        with patch('backend.meet_main.check_ollama',side_effect=RuntimeError('Unavailable')):
            with self.assertLogs('backend.meet_main',level='ERROR'):
                response=self.client.post('/api/chat',json={'question':'What is required?'})
        self.assertEqual(response.status_code,503)

    def test_invalid_source_release_and_unknown_document_are_not_served(self):
        self.assertEqual(self.client.get('/api/documents/policy/file?release_id=bad').status_code,404)
        release=self.manager.current()['release_id']
        self.assertEqual(self.client.get('/api/documents/unknown/file?release_id='+release).status_code,404)


if __name__=='__main__':
    unittest.main()
