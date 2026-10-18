"""Two text PDFs only. No financial manual, OCR, external API, or production ingest.

Run with --stage before/after; named stages are immutable unless --overwrite.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import time

from experiments.new_corpus_stress_test import DATA, DER, SYN, MODES, pages, parse_scenarios, chunk, metrics, ExperimentalRegistry
from backend.services.search_service import SearchService
from backend.services.embedding_service import EmbeddingService
from backend.services.rag_service import RAGService
from backend.services.policy_claim_service import candidate_conflict

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'experiment_outputs/text_only_20260909'
PARAPHRASES = [
    ('005', 'How many people can cast a vote on the Society governing board?'),
    ('006', 'How long does an elected member at large stay on the board?'),
    ('012', 'Can proxies help reach the minimum attendance for a board meeting?'),
    ('013', 'Can an absent board member delegate their vote to someone else?'),
    ('017', 'What proportion of members can initiate a change to the constitution?'),
    ('020', 'What previous service is needed to run for Vice President?'),
    ('022', 'How long can a Vice President remain continuously in the same office?'),
    ('024', 'How far ahead must board members be told when and where a meeting will take place?'),
    ('026', 'Can the board decide by email instead of holding a meeting?'),
    ('039', 'Do technical committee leaders need to belong to the Society?'),
    ('040', 'What factors are reviewed when assessing a technical committee each year?'),
    ('041', 'Who reviews a proposed technical committee before it starts operating?'),
    ('042', 'When can an inactive technical committee be shut down?'),
    ('054', 'How do age and length of membership determine life membership?'),
    ('055', 'How much professional experience is required for senior membership?'),
]


def service(chunks):
    embeddings = EmbeddingService([f'{c.section or ""} {c.heading or ""} {c.text}' for c in chunks], backend='local_lsa')
    return SearchService(ExperimentalRegistry(chunks),chunks,embeddings=embeddings)


def clean(t):
    return re.sub(r'Derived RAG testing corpus[^\n]*\nPage \d+\n', '', t)


def load():
    pp = pages(DER)
    joined, offsets = '', []
    for page in range(2,10):
        offsets.append((len(joined),page))
        joined += clean(pp[page-1])+'\n'
    found = list(re.finditer(r'(?m)^Record (\d{3}): ([^\n]+)\n',joined))
    records=[]
    for i,m in enumerate(found):
        cid,title=m.groups()
        part=joined[m.end():found[i+1].start() if i+1<len(found) else len(joined)]
        body=part.split('Authority note:',1)[1].split('\n',1)[1]
        page=max(page for offset,page in offsets if offset<=m.start())
        c=chunk('DER-'+cid,' '.join(body.split()),DER,'Derived Governance Test Corpus',page,50)
        c.section=title
        c.heading=title
        records.append(c)
    assert len(records)==57
    question_text='\n'.join(clean(t) for t in pp[40:])
    questions=[{'id':'Q'+cid,'query':q.strip(),'relevant_ids':['DER-'+cid],'family':'template'}
               for cid,q in re.findall(r'Q(\d{3})\. (.*?)\nExpected source:',question_text,re.S)]
    assert len(questions)==57
    questions += [{'id':'P'+cid,'query':q,'relevant_ids':['DER-'+cid],'family':'paraphrase'} for cid,q in PARAPHRASES]
    scenarios,synthetic=parse_scenarios(pages(SYN))
    all_chunks=records+synthetic
    for c in all_chunks:
        assert 'Expected auditor behaviour' not in c.text and 'Reference answer:' not in c.text and 'Suggested query:' not in c.text
    return questions,scenarios,all_chunks


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--stage',required=True)
    p.add_argument('--overwrite',action='store_true')
    args=p.parse_args()
    if not re.fullmatch(r'[a-z0-9_-]+',args.stage): raise ValueError('Invalid stage')
    out=OUTPUT/args.stage
    if out.exists() and not args.overwrite: raise FileExistsError(out)
    out.mkdir(parents=True,exist_ok=True)
    questions,scenarios,chunks=load()
    search=service(chunks)
    rag=RAGService(search)
    rows=[]
    for mode in MODES:
        for q in questions+[{**s,'family':'conflict'} for s in scenarios]:
            search._score_cache.clear()
            started=time.perf_counter()
            hits=search.search(q['query'],k=10,mode=mode)
            ms=(time.perf_counter()-started)*1000
            ids=[c.chunk_id for c,_ in hits]
            rows.append({'mode':mode,'case_id':q['id'],'family':q['family'],'query':q['query'],
                         **metrics(ids,q['relevant_ids']),'retrieval_ms':ms,
                         'top10':[{'id':c.chunk_id,'page':c.page,'section':c.section,'text':c.text,'score':score} for c,score in hits]})
        print('Retrieval complete:',mode,flush=True)
    byid={c.chunk_id:c for c in chunks}
    pairs=[]
    from dataclasses import replace
    for s in scenarios:
        a,b=[byid[i] for i in s['relevant_ids']]
        for variant,right,expected in [('cross',b,True),('internal',replace(b,document_id=a.document_id),True),
                                       ('identical',replace(a,document_id='copy'),False),
                                       ('distractor',byid[s['distractor_id']],False)]:
            conflicts=rag._detect_conflicts(s['query'],[(a,1,a.text),(right,1,right.text)])
            pairs.append({'case_id':s['id'],'variant':variant,'expected':expected,'detected':bool(conflicts),
                          'reason':candidate_conflict(a.text,right.text),'human_review':any(c.human_review_required for c in conflicts)})
    chats=[]
    for s in scenarios:
        response=rag.answer(s['query'],mode='hybrid')
        target=set(s['relevant_ids'])
        chats.append({'case_id':s['id'],'topic':s['topic'],
                      'target_detected':any(target<={e.document_id for e in c.conflicting_evidence} for c in response.conflicts),
                      'citations_verified':bool(response.citations) and all(any(c.document_id==e.document_id and c.page==e.page and
                           ' '.join(e.evidence_text.split()) in ' '.join(c.text.split()) for c in chunks) for e in response.citations),
                      'response':response.model_dump()})
    summary=[]
    for family in ('template','paraphrase','conflict'):
        for mode in MODES:
            selected=[r for r in rows if r['mode']==mode and r['family']==family]
            summary.append({'family':family,'mode':mode,'n':len(selected),**{
                k:sum(r[k] for r in selected)/len(selected) for k in ('recall_at_5','pair_hit_at_5','mrr_at_10','ndcg_at_10','retrieval_ms')}})
    data={'summary':summary,'pairs':pairs,'chats':chats,'questions':questions,'scenarios':scenarios,
          'chunks':[asdict(c) for c in chunks],'retrieval_cases':rows,
          'manifest':{'sources':{f:hashlib.sha256((DATA/f).read_bytes()).hexdigest() for f in (DER,SYN)},
                      'ocr_used':False,'financial_manual_included':False,'development_only':True,
                      'chunks':len(chunks),'model':'local_lsa','stage':args.stage,
                      'code_hashes':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in
                         [Path(__file__),ROOT/'backend/services/search_service.py',ROOT/'backend/services/rag_service.py',ROOT/'backend/services/policy_claim_service.py']}}}
    for name,value in data.items(): (out/f'{name}.json').write_text(json.dumps(value,indent=2,ensure_ascii=False))
    print(json.dumps(summary,indent=2))
    print('Oracle',sum(r['detected'] for r in pairs if r['variant']=='cross'),'/20; full chat',sum(r['target_detected'] for r in chats),'/20')


if __name__=='__main__': main()
