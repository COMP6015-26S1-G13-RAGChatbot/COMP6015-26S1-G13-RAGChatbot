from __future__ import annotations

import csv
import json
import math
import re
import time
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import chromadb
import numpy as np
import ollama
from pypdf import PdfReader


TOKEN_RE = re.compile(r"[a-z0-9]+")
SECTION_RE = re.compile(
    r"(?im)^(?P<section>(?:article\s+[ivxlcdm]+|section\s+\d+(?:\.\d+)*|I-\d{3}(?:\.\d+)?|\d+(?:\.\d+)*))"
    r"[\s.():-]*(?P<title>[^\n]{0,100})$"
)
NORMATIVE_RE = re.compile(r"\b(shall|must|required|may|should|can|cannot|prohibited)\b", re.I)


def tokens(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if len(t) > 1]


def cosine(left: np.ndarray, right: np.ndarray) -> float:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    return float(np.dot(left, right) / denominator) if denominator else 0.0


@dataclass
class Document:
    document_id: str
    name: str
    path: str
    version: str
    approval_status: str
    authority_score: int
    usage: str
    retrieval_enabled: bool


@dataclass
class Unit:
    text: str
    page: int | None
    section: str | None


@dataclass
class Chunk:
    chunk_id: str
    text: str
    document_id: str
    document_name: str
    page: int | None
    section: str | None
    version: str
    approval_status: str
    authority_score: int
    usage: str


@dataclass
class Hit:
    chunk: Chunk
    keyword_score: float
    dense_score: float
    retrieval_score: float
    rerank_score: float


@dataclass
class LLMResult:
    answer: str
    citation_ids: list[str]
    issue_type: str
    suggested_correction: str | None
    abstained: bool
    interpretations: list[str]
    human_review_required: bool
    provider: str
    model: str
    llm_called: bool
    fallback_used: bool
    fallback_reason: str | None
    latency_ms: float
    prompt_tokens: int | None
    completion_tokens: int | None


class CorpusLoader:
    """Loads real files; only approved production records may enter retrieval."""

    def __init__(self, root: Path):
        self.root = root
        self.data_dir = root / "RAG_data"

    def documents(self) -> list[Document]:
        rows = json.loads((self.data_dir / "document_registry.json").read_text(encoding="utf-8"))
        return [Document(
            document_id=row["document_id"], name=row["title"],
            path=str(self.data_dir / row["source_path"]), version=row["version"],
            approval_status=row["approval_status"], authority_score=int(row["authority_level"]),
            usage=row["usage"], retrieval_enabled=bool(row["retrieval_enabled"]),
        ) for row in rows]

    @staticmethod
    def _split_sections(text: str, page: int | None) -> list[Unit]:
        clean = re.sub(r"[ \t]+", " ", text.replace("\x00", " ")).strip()
        if not clean:
            return []
        matches = list(SECTION_RE.finditer(clean))
        if not matches:
            return [Unit(clean, page, None)]
        units: list[Unit] = []
        if matches[0].start():
            units.append(Unit(clean[:matches[0].start()].strip(), page, None))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(clean)
            title = " ".join(match.group("title").split())
            label = match.group("section").strip() + (f" — {title}" if title else "")
            units.append(Unit(clean[match.start():end].strip(), page, label[:180]))
        return [unit for unit in units if unit.text]

    def load(self, document: Document) -> list[Unit]:
        path = Path(document.path)
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            units: list[Unit] = []
            for page, item in enumerate(PdfReader(str(path)).pages, start=1):
                units.extend(self._split_sections(item.extract_text() or "", page))
            return units
        if suffix == ".docx":
            with zipfile.ZipFile(path) as archive:
                root = ET.fromstring(archive.read("word/document.xml"))
            paragraphs = ["".join(node.text or "" for node in paragraph.iter()
                           if node.tag.endswith("}t")) for paragraph in root.iter()
                          if paragraph.tag.endswith("}p")]
            return self._split_sections("\n".join(p for p in paragraphs if p.strip()), None)
        if suffix == ".txt":
            return self._split_sections(path.read_text(encoding="utf-8", errors="replace"), None)
        raise ValueError(f"Unsupported document format: {path}")

    @staticmethod
    def chunk(document: Document, units: list[Unit], target_words: int) -> list[Chunk]:
        chunks: list[Chunk] = []
        for unit_index, unit in enumerate(units, start=1):
            words = unit.text.split()
            if not words:
                continue
            overlap = min(80, max(20, target_words // 8))
            start = 0
            part = 1
            while start < len(words):
                text = " ".join(words[start:start + target_words])
                chunks.append(Chunk(
                    chunk_id=f"{document.document_id}:u{unit_index}:c{part}", text=text,
                    document_id=document.document_id, document_name=document.name,
                    page=unit.page, section=unit.section, version=document.version,
                    approval_status=document.approval_status,
                    authority_score=document.authority_score, usage=document.usage,
                ))
                if start + target_words >= len(words):
                    break
                start += target_words - overlap
                part += 1
        return chunks


class OllamaGateway:
    def __init__(self, base_url: str, embedding_model: str, generation_model: str):
        self.client = ollama.Client(host=base_url)
        self.base_url = base_url
        self.embedding_model = embedding_model
        self.generation_model = generation_model

    def installed_models(self) -> set[str]:
        response = self.client.list()
        return {getattr(item, "model", None) or item.get("model") for item in response.models}

    def embed(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            response = self.client.embed(model=self.embedding_model, input=texts[start:start + batch_size])
            vectors.extend(response.embeddings)
        return np.asarray(vectors, dtype=np.float32)

    @staticmethod
    def schema() -> dict[str, Any]:
        return {
            "type": "object", "additionalProperties": False,
            "required": ["answer", "citation_ids", "issue_type", "suggested_correction",
                         "abstained", "interpretations", "human_review_required"],
            "properties": {
                "answer": {"type": "string"},
                "citation_ids": {"type": "array", "items": {"type": "string"}},
                "issue_type": {"type": "string", "enum": ["conflict", "unsupported_claim", "missing_requirement", "ambiguous", "no_issue"]},
                "suggested_correction": {"type": ["string", "null"]},
                "abstained": {"type": "boolean"},
                "interpretations": {"type": "array", "items": {"type": "string"}},
                "human_review_required": {"type": "boolean"},
            },
        }

    def synthesize(self, question: str, hits: list[Hit], conflict_scope: str | None,
                   deterministic_answer: str) -> LLMResult:
        started = time.perf_counter()
        evidence = "\n\n".join(
            f"EVIDENCE_ID={hit.chunk.chunk_id}\nDOCUMENT={hit.chunk.document_name}\n"
            f"SECTION={hit.chunk.section or 'unavailable'}\nPAGE={hit.chunk.page or 'unavailable'}\n"
            f"VERSION={hit.chunk.version}\nAPPROVAL={hit.chunk.approval_status}\n"
            f"AUTHORITY={hit.chunk.authority_score}\nTEXT={hit.chunk.text[:1800]}"
            for hit in hits
        )
        system = (
            "You are an evidence-only IEEE SMCS policy assistant. Use only supplied evidence. "
            "The application has already filtered production documents and decided authority/conflict scope. "
            "Never change these decisions. Cite only exact EVIDENCE_ID values. If evidence is insufficient, abstain. "
            "Hierarchy: IEEE Constitution and Bylaws=100; SMCS Constitution and Bylaws=90; "
            "Corrected Operations Manual=80; SMCS Technical Manual=70. For cross_document conflict, explain the "
            "given higher-authority result. For within_document conflict, give both reasonable interpretations, "
            "do not choose one, abstain, and require human review. Return only schema-compliant JSON."
        )
        user = (f"QUESTION:\n{question}\n\nAPPLICATION_CONFLICT_SCOPE={conflict_scope or 'none'}\n"
                f"APPLICATION_DETERMINISTIC_RESULT={deterministic_answer}\n\nAPPROVED_EVIDENCE:\n{evidence}")
        try:
            response = self.client.chat(
                model=self.generation_model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                format=self.schema(), options={"temperature": 0, "seed": 0, "num_predict": 450},
            )
            payload = json.loads(response.message.content)
            required = set(self.schema()["required"])
            if not required <= payload.keys():
                raise ValueError("missing required JSON fields")
            allowed = {hit.chunk.chunk_id for hit in hits}
            citation_ids = list(dict.fromkeys(str(value) for value in payload["citation_ids"]))
            if not citation_ids or not set(citation_ids) <= allowed:
                raise ValueError("unsupported citation ID")
            answer = str(payload["answer"]).strip()
            if not answer:
                raise ValueError("empty answer")
            if conflict_scope == "within_document" and not (
                    bool(payload["abstained"]) and bool(payload["human_review_required"])
                    and len(payload["interpretations"]) >= 2):
                raise ValueError("within-document abstention contract violated")
            return LLMResult(
                answer=answer, citation_ids=citation_ids, issue_type=str(payload["issue_type"]),
                suggested_correction=payload["suggested_correction"], abstained=bool(payload["abstained"]),
                interpretations=[str(x) for x in payload["interpretations"]],
                human_review_required=bool(payload["human_review_required"]), provider="ollama",
                model=self.generation_model, llm_called=True, fallback_used=False, fallback_reason=None,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                prompt_tokens=getattr(response, "prompt_eval_count", None),
                completion_tokens=getattr(response, "eval_count", None),
            )
        except Exception as exc:
            return LLMResult(
                answer=deterministic_answer, citation_ids=[hit.chunk.chunk_id for hit in hits[:2]],
                issue_type="ambiguous", suggested_correction=None, abstained=True, interpretations=[],
                human_review_required=conflict_scope == "within_document", provider="ollama",
                model=self.generation_model, llm_called=True, fallback_used=True,
                fallback_reason=f"{type(exc).__name__}: {exc}",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                prompt_tokens=None, completion_tokens=None,
            )


class VectorExperiment:
    def __init__(self, chunks: list[Chunk], gateway: OllamaGateway, output_dir: Path,
                 collection_name: str):
        self.chunks = chunks
        self.gateway = gateway
        self.output_dir = output_dir
        self.texts = [chunk.text for chunk in chunks]
        self.counts = [Counter(tokens(text)) for text in self.texts]
        self.df = Counter(term for count in self.counts for term in count)
        self.vectors = gateway.embed(self.texts)
        client = chromadb.PersistentClient(path=str(output_dir / "chroma"))
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass
        self.collection = client.create_collection(collection_name, metadata={"hnsw:space": "cosine"})
        for start in range(0, len(chunks), 100):
            subset = chunks[start:start + 100]
            self.collection.add(
                ids=[item.chunk_id for item in subset],
                documents=[item.text for item in subset],
                embeddings=self.vectors[start:start + 100].tolist(),
                metadatas=[{"document_id": item.document_id, "authority": item.authority_score,
                            "approval": item.approval_status, "usage": item.usage} for item in subset],
            )

    def _keyword(self, query: str) -> np.ndarray:
        query_terms = Counter(tokens(query))
        scores = []
        n = len(self.chunks)
        for counts in self.counts:
            score = 0.0
            for term, qtf in query_terms.items():
                tf = counts[term]
                if tf:
                    score += qtf * (1 + math.log(tf)) * math.log((n + 1) / (self.df[term] + 0.5))
            scores.append(score)
        values = np.asarray(scores, dtype=np.float32)
        maximum = float(values.max()) if len(values) else 0.0
        return values / maximum if maximum else values

    def retrieve(self, query: str, method: str, k: int = 5) -> list[Hit]:
        keyword = self._keyword(query)
        query_vector = self.gateway.embed([query])[0]
        dense = np.asarray([max(0.0, cosine(vector, query_vector)) for vector in self.vectors])
        if method == "keyword":
            base = keyword
        elif method == "dense":
            base = dense
        elif method == "hybrid":
            base = 0.45 * keyword + 0.55 * dense
        else:
            raise ValueError(f"Unknown retrieval method: {method}")
        candidate_indices = np.argsort(base)[::-1][:max(20, k)]
        query_terms = set(tokens(query))
        hits = []
        for index in candidate_indices:
            chunk = self.chunks[int(index)]
            overlap = len(query_terms & set(self.counts[int(index)])) / max(1, len(query_terms))
            rerank = float(0.70 * base[int(index)] + 0.20 * overlap + 0.10 * chunk.authority_score / 100)
            hits.append(Hit(chunk, float(keyword[int(index)]), float(dense[int(index)]),
                            float(base[int(index)]), rerank))
        hits.sort(key=lambda hit: hit.rerank_score, reverse=True)
        deduplicated: list[Hit] = []
        for hit in hits:
            hit_terms = set(tokens(hit.chunk.text))
            if any(hit.chunk.document_id == prior.chunk.document_id and
                   len(hit_terms & set(tokens(prior.chunk.text))) / max(1, len(hit_terms | set(tokens(prior.chunk.text)))) > .82
                   for prior in deduplicated):
                continue
            deduplicated.append(hit)
            if len(deduplicated) == k:
                break
        return deduplicated


def deterministic_scope(question: str, hits: list[Hit]) -> tuple[str | None, str]:
    if not hits:
        return None, "Insufficient approved evidence; abstain."
    for index, left in enumerate(hits):
        left_terms = set(NORMATIVE_RE.findall(left.chunk.text.lower()))
        for right in hits[index + 1:]:
            right_terms = set(NORMATIVE_RE.findall(right.chunk.text.lower()))
            opposition = bool(({"shall", "must", "required"} & left_terms and "may" in right_terms) or
                              ({"shall", "must", "required"} & right_terms and "may" in left_terms))
            left_topic = set(tokens(left.chunk.text)) - left_terms
            right_topic = set(tokens(right.chunk.text)) - right_terms
            shared_topic = left_topic & right_topic
            topic_similarity = len(shared_topic) / max(1, len(left_topic | right_topic))
            if not opposition or len(shared_topic) < 5 or topic_similarity < .12:
                continue
            question_terms = set(tokens(question))
            asks_modal_difference = "may" in question_terms and bool({"shall", "must"} & question_terms)
            if left.chunk.document_id == right.chunk.document_id and asks_modal_difference:
                return "within_document", "Equal-authority clauses conflict; present both interpretations and require human review."
            high = max((left, right), key=lambda hit: hit.chunk.authority_score)
            return "cross_document", f"{high.chunk.document_name} (authority {high.chunk.authority_score}) governs."
    top = hits[0]
    return None, f"Use the retrieved approved evidence from {top.chunk.document_name}; cite or abstain."


def load_golden_rows(path: Path) -> list[dict[str, str]]:
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    with zipfile.ZipFile(path) as archive:
        strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(node.text or "" for node in item.findall(".//x:t", ns)) for item in root.findall("x:si", ns)]
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rel_id = next(sheet.attrib[f"{{{ns['r']}}}id"] for sheet in workbook.findall(".//x:sheet", ns)
                      if sheet.attrib["name"] == "Golden Set")
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = next(item.attrib["Target"] for item in relationships if item.attrib["Id"] == rel_id)
        sheet = ET.fromstring(archive.read("xl/" + target.lstrip("/").removeprefix("xl/")))
        matrix: list[list[str]] = []
        for row in sheet.findall(".//x:sheetData/x:row", ns):
            values: dict[int, str] = {}
            for cell in row.findall("x:c", ns):
                letters = re.match(r"[A-Z]+", cell.attrib["r"]).group(0)
                column = 0
                for letter in letters:
                    column = column * 26 + ord(letter) - 64
                value_node, inline = cell.find("x:v", ns), cell.find("x:is/x:t", ns)
                raw = (value_node.text if value_node is not None else inline.text if inline is not None else "") or ""
                values[column - 1] = strings[int(raw)] if cell.attrib.get("t") == "s" and raw else raw
            matrix.append([values.get(i, "") for i in range(max(values, default=-1) + 1)])
    headers = matrix[0]
    return [{headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))} for row in matrix[1:]]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def simple_bar_chart(path: Path, title: str, labels: list[str], values: list[float]) -> None:
    width, height = 900, 420
    bars = []
    maximum = max(values or [1]) or 1
    bar_width = max(25, 700 // max(1, len(values)))
    for index, (label, value) in enumerate(zip(labels, values)):
        x = 100 + index * bar_width
        bar_height = 270 * value / maximum
        y = 340 - bar_height
        bars.append(f'<rect x="{x}" y="{y:.1f}" width="{bar_width-8}" height="{bar_height:.1f}" fill="#1f5a9d"/>')
        bars.append(f'<text x="{x + (bar_width-8)/2:.1f}" y="{y-8:.1f}" text-anchor="middle" font-size="12">{value:.3f}</text>')
        bars.append(f'<text x="{x + (bar_width-8)/2:.1f}" y="360" text-anchor="end" transform="rotate(-35 {x + (bar_width-8)/2:.1f} 360)" font-size="11">{label}</text>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
           f'<rect width="100%" height="100%" fill="white"/><text x="40" y="35" font-size="22" fill="#163a70">{title}</text>'
           '<line x1="80" y1="340" x2="860" y2="340" stroke="#65758b"/>' + "".join(bars) + '</svg>')
    path.write_text(svg, encoding="utf-8")
