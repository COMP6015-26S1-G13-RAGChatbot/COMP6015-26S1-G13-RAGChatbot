"""
Connects the administrator console in web/admin (from the team's
feat/admin-login branch) to this server's rag_chat engine.

The console's own code is unchanged; this module only supplies what its
adapter asks the host for: a document inventory with the engine's source
metadata, the selected clean/chunk functions, and a private release folder.
"""

import hashlib
import json
import re
from pathlib import Path


def document_id_for(filename):
    stem = Path(filename).stem.lower()
    return re.sub(r"[^a-z0-9]+", "-", stem).strip("-")


def title_for(filename):
    return re.sub(r"[_-]+", " ", Path(filename).stem).strip()


def build_inventory(data_dir, parse_pdf):
    """One registry row per PDF under data/<category>/.

    Source metadata comes from parse_pdf's own AUTHORITY_LEVELS and
    get_authority_rank, so a rebuilt index carries exactly the fields the
    original ingest wrote and that retrieval, conflict detection and
    citations depend on. Every PDF with extractable text is enabled, which
    reproduces the existing index (including the draft, derived and
    synthetic test documents used by conflict detection). A PDF with no
    text layer (e.g. a scan) contributed nothing to the original index and
    would fail an index build, so it is listed but not searchable.
    """
    rows = []
    for pdf in sorted(Path(data_dir).rglob("*.pdf")):
        source_type = pdf.parent.name.lower()
        authority_rank = parse_pdf.get_authority_rank(pdf.name, source_type)
        has_text = bool(parse_pdf.extract_pages_from_pdf(str(pdf)))
        rows.append({
            "document_id": document_id_for(pdf.name),
            "title": title_for(pdf.name),
            "version": "Original corpus",
            "document_type": source_type,
            "approval_status": "approved",
            "usage": "production",
            "retrieval_enabled": has_text,
            "authority_level": authority_rank,
            "source_path": str(pdf.resolve()),
            "content_hash": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            "source_metadata": {
                "source": pdf.name,
                "source_type": source_type,
                "authority_level": parse_pdf.AUTHORITY_LEVELS.get(source_type, 0),
                "authority_rank": authority_rank,
            },
        })
    return rows


def load_inventory(path, data_dir, parse_pdf, atomic_json):
    """Read the operator-reviewable inventory, creating it on first use."""
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text()), False
    rows = build_inventory(data_dir, parse_pdf)
    if not rows:
        raise RuntimeError(f"No PDFs found under {data_dir}")
    atomic_json(path, rows)
    return rows, True


def release_record_for(manager, source_name):
    """Current release row whose engine source name matches a citation."""
    for row in manager.current()["records"]:
        if row.get("source_metadata", {}).get("source") == source_name:
            return row
    return None
