import base64
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from backend.admin import install_admin


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"ADMIN_ACCESS_TOKEN": "a" * 48, "ADMIN_STORAGE_DIR": self.tmp.name})
        self.env.start()
        self.app = FastAPI()
        install_admin(self.app)
        @self.app.post('/api/chat')
        def chat():
            return {'answer': 'test'}
        self.client = TestClient(self.app)
        self.headers = {'Authorization': 'Bearer ' + 'a' * 48}
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        stream = io.BytesIO()
        writer.write(stream)
        self.pdf = stream.getvalue()
        self.payload = {'title': 'New rules', 'version': 'draft 1',
                        'content_base64': base64.b64encode(self.pdf).decode()}

    def tearDown(self):
        self.client.close()
        self.env.stop()
        self.tmp.cleanup()

    def test_all_data_routes_require_server_side_access(self):
        for path in ('/api/admin/overview', '/api/admin/audit', '/api/admin/uploads/'+'a'*32+'/download'):
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.post('/api/admin/uploads', json=self.payload).status_code, 401)
        with patch.dict(os.environ, {'ADMIN_ACCESS_TOKEN': ''}):
            self.assertEqual(self.client.get('/api/admin/overview', headers=self.headers).status_code, 503)

    def test_upload_is_pending_download_protected_and_audited(self):
        response = self.client.post('/api/admin/uploads', json=self.payload, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.text)
        record = response.json()
        self.assertFalse(record['retrieval_enabled'])
        self.assertEqual(record['approval_status'], 'pending')
        overview = self.client.get('/api/admin/overview', headers=self.headers).json()
        self.assertEqual(len(overview['pending_uploads']), 1)
        self.assertEqual(overview['documents'], [])
        download = '/api/admin/uploads/'+record['id']+'/download'
        self.assertEqual(self.client.get(download, headers=self.headers).content, self.pdf)
        self.assertEqual(self.client.get(download).status_code, 401)
        audit = self.client.get('/api/admin/audit', headers=self.headers)
        self.assertEqual(audit.json()[0]['event'], 'pending_pdf_uploaded')
        self.assertEqual(audit.headers['cache-control'], 'no-store')

    def test_invalid_pdf_title_and_encrypted_documents_rejected(self):
        for value in ('not base64!', base64.b64encode(b'%PDF-fake').decode()):
            payload = {**self.payload, 'content_base64': value}
            self.assertEqual(self.client.post('/api/admin/uploads', json=payload, headers=self.headers).status_code, 422)
        self.assertEqual(self.client.post('/api/admin/uploads', json={**self.payload, 'title': ' '}, headers=self.headers).status_code, 422)
        writer = PdfWriter(); writer.add_blank_page(width=100, height=100); writer.encrypt('secret')
        stream = io.BytesIO(); writer.write(stream)
        payload = {**self.payload, 'content_base64': base64.b64encode(stream.getvalue()).decode()}
        self.assertEqual(self.client.post('/api/admin/uploads', json=payload, headers=self.headers).status_code, 422)
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_oversize_body_rejected_before_parsing(self):
        from backend.admin import MAX_PDF_BYTES
        response = self.client.post('/api/admin/uploads', content=b'x'*(MAX_PDF_BYTES*2), headers=self.headers)
        self.assertEqual(response.status_code, 413)

    def test_provider_and_usage_counts_do_not_store_questions(self):
        self.app.state.admin_document_provider = lambda: [{'title': 'Approved document'}]
        self.client.post('/api/chat', json={'question': 'PRIVATE QUESTION'})
        response = self.client.get('/api/admin/overview', headers=self.headers)
        self.assertEqual(response.json()['requests']['/api/chat'], 1)
        self.assertEqual(response.json()['documents'][0]['title'], 'Approved document')
        self.assertNotIn('PRIVATE QUESTION', response.text)
        self.assertNotIn('authorization', response.text.lower())

    def test_download_paths_are_not_user_filesystem_paths(self):
        response = self.client.get('/api/admin/uploads/not-a-valid-id/download', headers=self.headers)
        self.assertEqual(response.status_code, 404)

    def test_console_has_no_stored_token_or_embedded_secrets(self):
        response = self.client.get('/admin')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('localStorage', response.text)
        self.assertNotIn('a'*48, response.text)
        self.assertIn("frame-ancestors 'none'", response.headers['content-security-policy'])


if __name__ == '__main__':
    unittest.main()
