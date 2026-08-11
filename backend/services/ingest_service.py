import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from pypdf import PdfReader

from backend.core.config import Config
from backend.services.registry_service import RegistryService


HEADING_RE = re.compile(
    r"(?im)^(?P<section>(?:article\s+[ivxlcdm]+|\d+(?:\.\d+)*|section\s+\d+(?:\.\d+)*))"
    r"[\s.:-]*(?P<heading>[^\n]{0,120})$"
)


@dataclass
class SectionChunk:
    chunk_id: str
    text: str
    document_id: str
    document_title: str
    version: str
    approval_status: str
    authority_level: int
    usage: str
    section: str | None
    heading: str | None
    page: int


class IngestService:
    def __init__(self, registry: RegistryService | None = None, index_path: Path = Config.INDEX_PATH):
        self.registry = registry or RegistryService()
        self.index_path = index_path

    @staticmethod
    def split_page(text: str) -> list[tuple[str | None, str | None, str]]:
        text = re.sub(r"[ \t]+", " ", text.replace("\x00", " ")).strip()
        # PDF page numbers are layout artifacts, not document sections.
        text = re.sub(r"^\d+\s+(?=[a-z])", "", text)
        if not text:
            return []
        matches = list(HEADING_RE.finditer(text))
        if not matches:
            return [(None, None, text)]
        chunks = []
        if matches[0].start() > 0:
            chunks.append((None, None, text[:matches[0].start()].strip()))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            chunks.append((match.group("section"), match.group("heading").strip() or None, text[match.start():end].strip()))
        return [chunk for chunk in chunks if chunk[2]]

    def build(self) -> list[SectionChunk]:
        chunks: list[SectionChunk] = []
        for record in self.registry.production_documents():
            path = self.registry.data_dir / record.source_path
            if path.suffix.lower() != ".pdf":
                continue
            reader = PdfReader(str(path))
            for page_number, page in enumerate(reader.pages, start=1):
                for part, (section, heading, text) in enumerate(self.split_page(page.extract_text() or ""), start=1):
                    if section and heading:
                        clean_heading = re.sub(rf"^{re.escape(section)}[\s.:-]*", "", heading).strip()
                        section_label = f"{section}. {clean_heading}" if clean_heading else section
                    else:
                        section_label = section or heading
                    chunks.append(SectionChunk(
                        chunk_id=f"{record.document_id}:p{page_number}:c{part}", text=text,
                        document_id=record.document_id, document_title=record.title,
                        version=record.version, approval_status=record.approval_status,
                        authority_level=record.authority_level, usage=record.usage,
                        section=section_label, heading=heading, page=page_number,
                    ))
        self.index_path.write_text(json.dumps([asdict(c) for c in chunks], indent=2), encoding="utf-8")
        return chunks

    def run_full_pipeline(self) -> bool:
        return bool(self.build())
