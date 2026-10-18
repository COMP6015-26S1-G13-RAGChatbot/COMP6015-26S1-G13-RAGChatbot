"""Generate reproducible figures and final-chat diagnostics from the stress run."""
import json
from dataclasses import asdict
from xml.sax.saxutils import escape
from experiments.new_corpus_stress_test import (
    OUT, DER, FIN, MODES, FINANCE_CASES, pages, chunk, service,
)
from backend.services.ingest_service import SectionChunk
from backend.services.rag_service import RAGService
from backend.services.search_service import semantic_similarity, normative_terms


def chart(path, title, series):
    h = 95 + len(series)*42
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="820" height="{h}" viewBox="0 0 820 {h}">',
             '<rect width="100%" height="100%" fill="white"/>',
             f'<text x="24" y="30" font-family="Arial" font-size="19">{escape(title)}</text>']
    for i, (label, value) in enumerate(series):
        y = 57+i*42
        lines += [f'<text x="24" y="{y+19}" font-family="Arial" font-size="14">{escape(label)}</text>',
                  f'<rect x="265" y="{y}" width="450" height="27" fill="#e8eef4"/>',
                  f'<rect x="265" y="{y}" width="{450*value:.1f}" height="27" fill="#276b9f"/>',
                  f'<text x="730" y="{y+19}" font-family="Arial" font-size="14">{value:.1%}</text>']
    lines += ['</svg>']
    path.write_text('\n'.join(lines))


def main():
    summaries = json.loads((OUT/'retrieval_summary.json').read_text())
    chart(OUT/'retrieval_pair_comparison.svg', 'Both conflicting records retrieved in top 5 (20 scenarios)',
          [(f"{r['chunk_size']} words / {r['mode']}", r['pair_hit_at_5']) for r in summaries])
    finance = json.loads((OUT/'financial_retrieval_cases.json').read_text())
    chart(OUT/'financial_retrieval.svg', 'Financial OCR evidence hit@5 (10 questions; 250-word chunks)',
          [(m, sum(r['evidence_hit_at_5'] for r in finance if r['mode']==m and r['chunk_size']==250)/10) for m in MODES])
    cases = json.loads((OUT/'cases.json').read_text())
    records = [SectionChunk(**c) for c in json.loads((OUT/'synthetic_records.json').read_text())]
    chunks = list(records)
    size = 100
    for name, pp in ((DER, [(i,t) for i,t in enumerate(pages(DER),1) if 2<=i<=9]),
                     (FIN, list(enumerate(json.loads((OUT/'financial_ocr_pages.json').read_text()),1)))):
        for page, text in pp:
            import re
            text = re.sub(r'^Derived RAG testing corpus[^\n]*\nPage \d+\n', '', text)
            words = text.split()
            for start in range(0, len(words), 80):
                body = ' '.join(words[start:start+size])
                if len(body)>=30:
                    chunks.append(chunk(f'{name}:p{page}:w{start}', body, name, name, page))
    search = service(chunks)
    rag = RAGService(search)
    answers = []
    for case in cases:
        response = rag.answer(case['query'], mode='hybrid')
        target = set(case['relevant_ids'])
        detected = any(target <= {e.document_id for e in c.conflicting_evidence} for c in response.conflicts)
        valid = all(any(c.document_id==e.document_id and c.page==e.page and
                        ' '.join(e.evidence_text.split()) in ' '.join(c.text.split()) for c in chunks)
                    for e in response.citations)
        answers.append({'case_id': case['id'], 'query': case['query'], 'target_conflict_detected': detected,
                        'nonempty_citations_verified': bool(response.citations) and valid,
                        'response': response.model_dump()})
    (OUT/'chat_cases.json').write_text(json.dumps(answers,indent=2))
    pairs = json.loads((OUT/'oracle_conflict_cases.json').read_text())
    diagnostics = []
    for p in pairs:
        if p['variant']=='cross_document':
            diagnostics.append({'case_id':p['case_id'], 'similarity':semantic_similarity(p['left'],p['right']),
                                'left_normative_terms':sorted(normative_terms(p['left'])),
                                'right_normative_terms':sorted(normative_terms(p['right']))})
    (OUT/'reasoning_diagnostics.json').write_text(json.dumps(diagnostics,indent=2))
    extra = '\n## Full chat service check\n\n'
    extra += ('20 scenario queries were additionally passed through RAGService.answer in hybrid mode, '
              'with 100-word background chunks. No LLM generation was requested. This checks answer/citation/abstention '
              'behaviour separately from the top-5 full-passage pair experiment.\n\n')
    extra += f"- Exact target conflict detected: {sum(a['target_conflict_detected'] for a in answers)}/20.\n"
    extra += f"- Any conflict reported: {sum(bool(a['response']['conflicts']) for a in answers)}/20.\n"
    extra += f"- Nonempty source-text-verified citations: {sum(a['nonempty_citations_verified'] for a in answers)}/20.\n"
    extra += f"- Abstained: {sum(a['response']['abstained'] for a in answers)}/20.\n"
    extra += ('\nCitation verification checks text existence, not logical correctness or authoritative status. '
              'Synthetic records remain experiment-only, even though the isolated adapter permits them for diagnostic retrieval.\n')
    extra += '\n## Changes and limitations\n\n'
    extra += ('Added quantity/unit normalisation, voting-threshold and permission/obligation candidate detection, '
              'subject/condition guards, neutral-question internal conflict detection and bounded counterpart search. '
              'New heuristic matches and draft/status-uncertain pairs require human review, not automatic policy resolution. '
              'Embedding query caches now include corpus identity.\n\n'
              'These 20 inspected scenarios are development regression data, not an unseen final benchmark. '
              'The detector remains rule-based and does not cover arbitrary logical implications or all exceptions. '
              'Source-derived paraphrases are not verified original policies. The financial manual was OCRed for '
              'this experiment only; the production ingestion service still needs an explicit OCR workflow. '
              'Neither generation quality nor real-document contradiction ground truth is established by this test.\n')
    report = OUT/'REPORT.md'
    current = report.read_text().split('\n## Full chat service check')[0]
    report.write_text(current+extra)
    baseline = OUT.parent / (OUT.name + '_baseline')
    if (baseline/'chat_cases.json').exists():
        old = json.loads((baseline/'chat_cases.json').read_text())
        old_pairs = json.loads((baseline/'oracle_conflict_cases.json').read_text())
        def count(rows, variant):
            return sum(p['detected'] for p in rows if p['variant']==variant)
        comparison = [
            '# 새 PDF 실험: 개선 전후 비교', '',
            '| 검사 | 개선 전 | 개선 후 |', '|---|---:|---:|',
            f"| 두 정답 근거를 직접 준 문서 간 충돌 후보 탐지 | {count(old_pairs,'cross_document')}/20 | {count(pairs,'cross_document')}/20 |",
            f"| 동일 문서 충돌 후보 탐지 | {count(old_pairs,'within_document')}/20 | {count(pairs,'within_document')}/20 |",
            f"| 챗봇 검색부터 응답까지 목표 충돌 탐지 (Hybrid, 100 words) | {sum(a['target_conflict_detected'] for a in old)}/20 | {sum(a['target_conflict_detected'] for a in answers)}/20 |",
            f"| 정상 대조군 오탐 | {sum(p['detected'] for p in old_pairs if not p['expected_conflict'])}/40 | {sum(p['detected'] for p in pairs if not p['expected_conflict'])}/40 |",
            '',
            '주의: 새 탐지는 확정 판정이 아니라 human review가 필요한 충돌 후보 경고이다. '
            '20개 사례는 개선에 사용한 개발 데이터이며, 이 수치를 최종 정확도로 쓰면 안 된다. '
            '40개 정상 대조군은 동일 문장/비규범적 설명으로 만든 단순 사례이므로 현실적인 오탐률을 보장하지 않는다.',
            '', '## 수행한 작업',
            '- 금융 매뉴얼 27페이지 OCR 및 근거 페이지를 지정한 질문 10개 평가.',
            '- 5개 검색 방식 × 배경 chunk 크기 3개 × 질문 30개 = 검색 평가 450회.',
            '- 별도 충돌 쌍 검사 100개와 전체 챗봇 질문 20개.',
            '- 기간 단위, 비율, 정족수, 허용/금지 및 보고 주기 비교 추가.',
            '- 서로 다른 직책/조건/임기 상한을 같은 규정으로 비교하지 않도록 제한.',
            '- 명시적인 충돌 질문에서 최대 두 번의 근거 기반 추가 검색 적용.',
            '- draft/합성/승인 불명확 근거는 권위 점수만으로 결론 내리지 않도록 처리.',
            '- 임베딩 질의 캐시에 corpus 식별자를 추가해 다른 인덱스의 점수 재사용 방지.',
            '', '## 남은 작업',
            '- 자격 대체 조건, 승인 절차 순서, 조건부 예외에 대한 논리 비교.',
            '- 독립적으로 검토된 정상/충돌 평가 데이터와 실제 원문 근거 검증.',
            '- 실제 운영 ingest의 OCR 지원 및 금융 문서의 승인/권위 확인.',
            '- 로컬 LLM 생성 답변의 논리적 근거 충실도 평가. 이번 실험은 LLM을 호출하지 않았다.',
        ]
        (OUT/'COMPARISON_KO.md').write_text('\n'.join(comparison)+'\n')
        chart(OUT/'conflict_before_after.svg', 'Development conflict candidates: before / after (20 cases)', [
            ('Oracle pairs / before',count(old_pairs,'cross_document')/20),
            ('Oracle pairs / after',count(pairs,'cross_document')/20),
            ('Full chat / before',sum(a['target_conflict_detected'] for a in old)/20),
            ('Full chat / after',sum(a['target_conflict_detected'] for a in answers)/20)])
    print(extra)


if __name__=='__main__':
    main()
