import hashlib
import json
from pathlib import Path

from backend.core.config import Config
from backend.models import DocumentRecord


class RegistryService:
    def __init__(self, registry_path: Path = Config.REGISTRY_PATH, data_dir: Path = Config.DATA_DIR):
        self.registry_path = registry_path
        self.data_dir = data_dir
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
        self.records = [self._with_hash(DocumentRecord.model_validate(item)) for item in raw]

    def _with_hash(self, record: DocumentRecord) -> DocumentRecord:
        path = self.data_dir / record.source_path
        if record.content_hash == "auto" and path.is_file():
            record.content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        return record

    def list_documents(self) -> list[DocumentRecord]:
        return self.records

    def get(self, document_id: str) -> DocumentRecord:
        for record in self.records:
            if record.document_id == document_id:
                return record
        raise KeyError(document_id)

    def production_documents(self) -> list[DocumentRecord]:
        return [
            record for record in self.records
            if record.usage == "production"
            and record.approval_status == "approved"
            and record.retrieval_enabled
        ]

    def audit_inputs(self) -> list[DocumentRecord]:
        return [record for record in self.records if record.usage in {"audit_input", "pending"}]
