"""Offline development benchmark; never changes the production index or registry.

Run: ./venv/bin/python -m experiments.new_corpus_stress_test
Synthetic records are exposed only through a temporary in-memory adapter. Their
adapter approval/authority values are experimental assumptions, not real policy.
"""
from pathlib import Path
from dataclasses import asdict, replace
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import re
import subprocess
import time

from pypdf import PdfReader
from backend.services.ingest_service import SectionChunk
from backend.services.embedding_service import EmbeddingService
from backend.services.search_service import SearchService
from backend.services.rag_service import RAGService

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiment_outputs/new_corpus_20260908'
DATA = ROOT / 'RAG_data'
SYN = 'SMCS_RAG_Synthetic_Conflict_Stress_Test_Corpus.pdf'
DER = 'SMCS_RAG_Derived_Governance_Test_Corpus.pdf'
FIN = 'financial-ops-manual.pdf'
MODES = ('deterministic', 'bm25', 'dense', 'rrf', 'hybrid')
FINANCE_CASES = [
    ('F01', 'Under what conditions may IEEE reimburse business class airfare?', 15, 'over eight'),
    ('F02', 'Who may grant business class travel for medical reasons?', 15, 'medical reasons'),
    ('F03', 'What is the travel reimbursement limit for the IEEE President spouse or companion?', 15, '60,000'),
    ('F04', 'How many written bids should IEEE obtain for purchases of 50000 dollars?', 25, 'three written bids'),
    ('F05', 'When is a formal competitive bidding process required?', 25, 'USD250,000'),
    ('F06', 'Are conference hotels and catering exempt from competitive bidding?', 25, 'exempt from this'),
    ('F07', 'Who approves a contractual arrangement of ten million dollars before execution?', 25, 'USD10,000,000'),
    ('F08', 'Who must approve contracts involving personally identifiable information PII?', 24, 'IT Security'),
    ('F09', 'When must purchases receive an authorized purchase order before work begins?', 24, 'USD1,000'),
    ('F10', 'What contribution amount must be reported to the IEEE Development Office?', 8, 'USD250'),
]


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def pages(name):
    return [p.extract_text() or '' for p in PdfReader(DATA / name).pages]


def ocr_finance():
    folder = OUT / 'ocr'
    folder.mkdir(parents=True, exist_ok=True)
    if len(list(folder.glob('financial-*.png'))) != 27:
        subprocess.run(['pdftoppm', '-r', '120', '-png', str(DATA / FIN), str(folder / 'financial')], check=True)
    def convert(p):
        dest = p.with_suffix('.txt')
        if not dest.exists():
            subprocess.run(['tesseract', str(p), str(p.with_suffix('')), '-l', 'eng'], check=True, capture_output=True)
        return dest.read_text()
    images = sorted(folder.glob('financial-*.png'))
    with ThreadPoolExecutor(max_workers=3) as pool:
        return list(pool.map(convert, images))


def chunk(cid, text, doc, title, page, authority=50):
    return SectionChunk(cid, text, doc, title, 'experiment-only', 'approved', authority,
                        'production', None, None, page)


def parse_scenarios(texts):
    cases, records = [], []
    for page, text in enumerate(texts, 1):
        m = re.search(r'Scenario (\d+): ([^\n]+)', text)
        if not m:
            continue
        number, topic = m.groups()
        sections = re.split(r'Record [ABC] [—–-] [^\n]+\n', text)[1:]
        assert len(sections) == 3, (page, len(sections))
        ids = []
        for idx, section in enumerate(sections):
            section = section.split('Expected auditor behaviour')[0]
            match = re.search(r'record_id: ([^\n]+)\n(?:effective_date:[^\n]+\n)?([\s\S]+)', section)
            assert match, page
            cid, body = match.groups()
            body = ' '.join(body.split())
            assert 'Golden questions' not in body and 'Expected auditor' not in body
            # All IDs are virtual documents: the PDF packages multiple fictional documents.
            records.append(chunk(cid, body, cid, 'TEST record ' + cid, page, 90 if idx == 0 else 50))
            ids.append(cid)
        cases.append({'id': number, 'topic': topic, 'page': page, 'relevant_ids': ids[:2],
                      'distractor_id': ids[2], 'query': f'Do the available documents conflict about {topic.lower()}?',
                      'draft_baseline': 'Draft ' in records[-3].text,
                      'expected_note': text.split('Expected auditor behaviour')[1].split('Golden questions')[0].strip()})
    assert len(cases) == 20 and len(records) == 60
    return cases, records


class ExperimentalRegistry:
    def __init__(self, chunks):
        self.docs = [SimpleNamespace(document_id=i) for i in sorted({c.document_id for c in chunks})]
    def production_documents(self):
        return self.docs


def service(chunks):
    # Clear shared query scores so configurations have equivalent cold queries.
    EmbeddingService._query_cache.clear()
    embed = EmbeddingService([c.text for c in chunks], backend='local_lsa')
    return SearchService(ExperimentalRegistry(chunks), chunks, embeddings=embed)


def metrics(ids, gold):
    ranks = [i + 1 for i, cid in enumerate(ids) if cid in gold]
    dcg = sum(1 / math.log2(i + 1) for i in ranks[:10])
    ideal = sum(1 / math.log2(i + 2) for i in range(len(gold)))
    return {'recall_at_5': len(set(ids[:5]) & set(gold)) / len(gold),
            'pair_hit_at_5': int(set(gold) <= set(ids[:5])),
            'mrr_at_10': 1 / ranks[0] if ranks else 0,
            'ndcg_at_10': dcg / ideal}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sources = {f: pages(f) for f in (SYN, DER, FIN)}
    inventory = [{'file': f, 'sha256': hashlib.sha256((DATA / f).read_bytes()).hexdigest(),
                  'pages': len(pp), 'extracted_characters': sum(map(len, pp))} for f, pp in sources.items()]
    sources[FIN] = ocr_finance()
    inventory[-1]['ocr_characters'] = sum(map(len, sources[FIN]))
    save('inventory.json', inventory)
    save('financial_ocr_pages.json', sources[FIN])
    cases, records = parse_scenarios(sources[SYN])
    save('cases.json', cases)
    save('synthetic_records.json', [asdict(c) for c in records])
    # Exclude derived question banks/test instructions; only canonical summaries
    # (pages 2-9, before expanded/question-context/auditor records) are retained.
    derived = []
    for page, text in enumerate(sources[DER], 1):
        if 2 <= page <= 9:
            text = re.sub(r'^Derived RAG testing corpus[^\n]*\nPage \d+\n', '', text)
            text = text.split('Retrieval Variants')[0].split('Question Bank')[0]
            derived.append((page, text))
    all_rows, summaries, finance_rows = [], [], []
    for size in (100, 250, 500):
        chunks = list(records)
        for name, pp in ((DER, derived), (FIN, list(enumerate(sources[FIN], 1)))):
            for page, text in pp:
                words = text.split()
                for start in range(0, len(words), max(1, size - size // 5)):
                    body = ' '.join(words[start:start+size])
                    if len(body) < 30:
                        continue
                    chunks.append(chunk(f'{name}:p{page}:w{start}', body, name, name, page, 50))
        search = service(chunks)
        rag = RAGService(search)
        for mode in MODES:
            rows = []
            for case in cases:
                query = case['query']
                search._score_cache.clear()
                EmbeddingService._query_cache.clear()
                started = time.perf_counter()
                hits = search.search(query, k=10, mode=mode)
                latency = (time.perf_counter() - started) * 1000
                ids = [c.chunk_id for c, _ in hits]
                # Call the production conflict detector directly. Only retrieved
                # policy passages are provided, not labels/expected explanations.
                conflicts = rag._detect_conflicts(query, [(c, s, c.text) for c, s in hits[:5]])
                expected = set(case['relevant_ids'])
                matched = [c for c in conflicts if expected <= {e.document_id for e in c.conflicting_evidence}]
                row = {'chunk_size': size, 'mode': mode, 'case_id': case['id'], 'topic': case['topic'],
                       **metrics(ids, expected), 'retrieval_ms': latency,
                       'target_conflict_detected': bool(matched), 'any_conflict_detected': bool(conflicts),
                       'top10': [{'id': c.chunk_id, 'page': c.page, 'score': s, 'text': c.text} for c, s in hits],
                       'conflicts': [c.model_dump() for c in conflicts]}
                rows.append(row)
            all_rows.extend(rows)
            summary = {'chunk_size': size, 'chunks': len(chunks), 'mode': mode, 'cases': len(rows)}
            for key in ('recall_at_5', 'pair_hit_at_5', 'mrr_at_10', 'ndcg_at_10', 'retrieval_ms', 'target_conflict_detected'):
                summary[key] = sum(r[key] for r in rows) / len(rows)
            summaries.append(summary)
            print(json.dumps(summary), flush=True)
            for cid, query, page, needle in FINANCE_CASES:
                hits = search.search(query, k=10, mode=mode)
                ranks = [i+1 for i, (c, _) in enumerate(hits)
                         if c.document_id == FIN and c.page == page and needle.lower() in c.text.lower()]
                finance_rows.append({'case_id': cid, 'query': query, 'expected_page': page,
                                     'evidence_anchor': needle, 'chunk_size': size, 'mode': mode,
                                     'evidence_hit_at_5': bool(ranks and ranks[0] <= 5),
                                     'mrr_at_10': 1/ranks[0] if ranks else 0,
                                     'top10': [{'page': c.page, 'document': c.document_id, 'text': c.text} for c, _ in hits]})
    # Oracle pairs isolate reasoning errors from retrieval misses. Controls are
    # baseline + distractor and identical baseline in a different virtual document.
    rag = RAGService(service(records))
    by_id = {c.chunk_id: c for c in records}
    pairs = []
    for case in cases:
        a, b = [by_id[i] for i in case['relevant_ids']]
        d = by_id[case['distractor_id']]
        for variant, right, expected in (
            ('cross_document', b, True),
            ('equal_authority', replace(b, authority_level=a.authority_level), True),
            ('within_document', replace(b, document_id=a.document_id), True),
            ('no_issue_distractor', d, False),
            ('no_issue_identical', replace(a, document_id='copy-'+a.document_id), False)):
            result = rag._detect_conflicts(case['query'], [(a, 1, a.text), (right, 1, right.text)])
            pairs.append({'case_id': case['id'], 'topic': case['topic'], 'variant': variant,
                          'expected_conflict': expected, 'detected': bool(result),
                          'human_review': any(c.human_review_required for c in result),
                          'draft_baseline': case['draft_baseline'],
                          'left': a.text, 'right': right.text,
                          'conflicts': [c.model_dump() for c in result]})
    save('retrieval_cases.json', all_rows)
    save('retrieval_summary.json', summaries)
    save('oracle_conflict_cases.json', pairs)
    save('financial_retrieval_cases.json', finance_rows)
    save('run_manifest.json', {
        'embedding_backend': 'local_lsa', 'modes': MODES,
        'chunk_sizes': [100,250,500], 'overlap_fraction': 0.2,
        'development_only': True, 'production_registry_modified': False,
        'code_sha256': {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in [Path(__file__), ROOT/'backend/services/rag_service.py',
                                  ROOT/'backend/services/policy_claim_service.py',
                                  ROOT/'backend/services/search_service.py',
                                  ROOT/'backend/services/embedding_service.py']}})
    report = ['# New corpus development stress test', '',
              'No production registry/index was modified. No LLM or remote API was called.',
              'Synthetic PDF: 20 scenarios; 60 policy records. Labels, golden questions and expected-behaviour text excluded from retrieval.',
              'Record A/B are the strict relevant pair. Derived summaries and OCR financial pages act as additional distractors; semantically equivalent summaries are not scored as exact evidence hits.',
              'Authority 90/50 is an in-memory controlled assumption, not verified official status. Draft cases 17/18 require status review; no claim of valid real-policy resolution is made.',
              'Chunk sweep changes background document chunks only; atomic A/B/C records are preserved. No source-reference verification or final held-out generalisation claim.',
              'Latency is one local retrieval call per query/config, excluding index construction, OCR and generation; query caches cleared. Not directly comparable with old answer latency.', '',
              '| Words | Chunks | Method | Recall@5 | Pair hit@5 | MRR@10 | nDCG@10 | ms | Target conflict recall |',
              '|---:|---:|---|---:|---:|---:|---:|---:|---:|']
    for s in summaries:
        report.append(f"|{s['chunk_size']}|{s['chunks']}|{s['mode']}|{s['recall_at_5']:.3f}|{s['pair_hit_at_5']:.3f}|{s['mrr_at_10']:.3f}|{s['ndcg_at_10']:.3f}|{s['retrieval_ms']:.1f}|{s['target_conflict_detected']:.3f}|")
    report += ['', '## Oracle pair diagnostic (retrieval bypassed)', '', '| Variant | Detected | Cases | Human review |', '|---|---:|---:|---:|']
    for variant in dict.fromkeys(p['variant'] for p in pairs):
        selected = [p for p in pairs if p['variant'] == variant]
        report.append(f"|{variant}|{sum(p['detected'] for p in selected)}|{len(selected)}|{sum(p['human_review'] for p in selected)}|")
    report += ['', '## Financial OCR retrieval (10 manually constructed development questions)',
               'A hit requires the expected financial PDF page AND an evidence anchor in the returned chunk. This does not prove the whole answer is complete.',
               '', '| Words | Method | Evidence hit@5 | MRR@10 |', '|---:|---|---:|---:|']
    for size in (100, 250, 500):
        for mode in MODES:
            ff = [r for r in finance_rows if r['mode'] == mode and r['chunk_size'] == size]
            report.append(f"|{size}|{mode}|{sum(r['evidence_hit_at_5'] for r in ff)/len(ff):.3f}|{sum(r['mrr_at_10'] for r in ff)/len(ff):.3f}|")
    report += ['', 'Within-document controls relocate contradictory records into one virtual document; this is a constructed test, not a claim that the source PDF contains official contradictions.',
               'No-issue controls are mechanical diagnostics, not an expert-validated specificity benchmark.',
               'The conflict stage uses the application pair detector over retrieved full passages. It does not measure final LLM answer correctness or complete chat/audit API behaviour.',
               '', '## Failure review', '']
    for p in pairs:
        if p['variant'] == 'cross_document' and not p['detected']:
            report.append(f"- Scenario {p['case_id']}: {p['topic']} — missed even with both passages supplied.")
    (OUT / 'REPORT.md').write_text('\n'.join(report)+'\n')


if __name__ == '__main__':
    main()
