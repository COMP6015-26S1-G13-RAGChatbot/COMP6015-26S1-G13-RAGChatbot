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
            bylaw_article: str | None = None
            bylaw_section: str | None = None
            bylaw_section_title: str | None = None
            bylaw_subsection: str | None = None
            for page_number, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text() or ""
                article_matches = list(re.finditer(
                    r"(?m)^I-\s*(\d)\s*(\d)\s*(\d)\.\s*([^\n]+)", page_text))
                pending_articles = [(f"I-{match.group(1)}{match.group(2)}{match.group(3)}",
                                     " ".join(match.group(4).split())) for match in article_matches]
                if article_matches and article_matches[0].start() < 300:
                    bylaw_article, _ = pending_articles.pop(0)
                    bylaw_section = None
                    bylaw_section_title = None
                    bylaw_subsection = None
                for part, (section, heading, text) in enumerate(self.split_page(page_text), start=1):
                    if pending_articles and heading:
                        pending_article, pending_title = pending_articles[0]
                        normalized_heading = re.sub(r"[^a-z0-9]+", " ", heading.lower()).strip()
                        normalized_title = re.sub(r"[^a-z0-9]+", " ", pending_title.lower()).strip()
                        if normalized_title and (normalized_heading.startswith(normalized_title) or
                                                 normalized_title.startswith(normalized_heading[:30]) or
                                                 section == "1"):
                            bylaw_article = pending_article
                            bylaw_section = None
                            bylaw_section_title = None
                            bylaw_subsection = None
                            pending_articles.pop(0)
                    if section and heading:
                        clean_heading = re.sub(rf"^{re.escape(section)}[\s.:-]*", "", heading).strip()
                        section_label = f"{section}. {clean_heading}" if clean_heading else section
                    else:
                        section_label = section or heading
                    # IEEE-style Bylaws use a persistent I-NNN article followed by numbered
                    # sections and parenthesised subclauses that can continue onto the next page.
                    if bylaw_article and section and section.isdigit():
                        number = int(section)
                        is_subclause = bool(heading and heading.lstrip().startswith(")"))
                        if is_subclause and bylaw_section:
                            bylaw_subsection = section
                            section_label = f"{bylaw_article}.{bylaw_section}({section})"
                            if bylaw_section_title:
                                section_label += f" — {bylaw_section_title}"
                        elif number <= 20:
                            bylaw_section = section
                            bylaw_subsection = None
                            title_match = re.match(r"^\d+[.)]?\s*(.+?)(?:\.\s|$)", " ".join(text.split()))
                            derived_title = title_match.group(1).strip() if title_match else (heading or "").strip()
                            derived_title = re.sub(r"^([A-Z])\s+([a-z])", r"\1\2", derived_title)
                            bylaw_section_title = derived_title[:90] or None
                            section_label = f"{bylaw_article}.{section}"
                            if bylaw_section_title:
                                section_label += f" — {bylaw_section_title}"
                        elif bylaw_section and bylaw_subsection and len(tokens := re.findall(r"[A-Za-z]+", text)) >= 5:
                            section_label = f"{bylaw_article}.{bylaw_section}({bylaw_subsection}) — continuation"
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
