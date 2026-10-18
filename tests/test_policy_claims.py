import unittest
from dataclasses import replace
from backend.services.policy_claim_service import candidate_conflict, quantities
from backend.services.rag_service import RAGService
from backend.services.ingest_service import SectionChunk
from backend.services.embedding_service import EmbeddingService


class PolicyClaimTests(unittest.TestCase):
    def test_embedding_query_cache_is_scoped_to_corpus(self):
        a = EmbeddingService(['board quorum majority', 'proxy voting prohibited', 'annual reports'], backend='local_lsa')
        b = EmbeddingService(['travel economy airfare', 'medical business airfare', 'contract approval', 'competitive bidding'], backend='local_lsa')
        self.assertEqual(len(a.similarities('board quorum')), 3)
        self.assertEqual(len(b.similarities('board quorum')), 4)

    def test_quantity_units(self):
        self.assertEqual(quantities('two weeks notice'), quantities('14 days notice'))
        self.assertEqual(quantities('two-calendar-year term'), quantities('24 months term'))
        self.assertEqual(quantities('5 percent'), quantities('5%'))

    def test_new_conflict_forms(self):
        pairs = [
            ('The council quorum is a majority of members.', 'A quorum is one-third of members.'),
            ('Proxy voting is not allowed.', 'The procedure permits proxy voting.'),
            ('The President serves a two-year term.', 'The President serves a three-year term.'),
            ('Bylaw change notice must be sent two weeks before action.', 'A bylaw change needs seven days notice.'),
            ('A petition requires 5 percent of members.', 'A petition requires 3 percent of members.'),
            ('TC Chairs report activities bi-annually.', 'TC Chairs submit only one annual report.'),
            ('Each TC must propose a special session.', 'The TC special session is optional.'),
            ('The Board shall fill a vacancy.', 'The Board may fill a vacancy.'),
        ]
        for a,b in pairs:
            with self.subTest(a=a): self.assertIsNotNone(candidate_conflict(a,b))

    def test_scope_and_non_conflicts(self):
        pairs = [
            ('The President serves a two-year term.', 'The President-Elect serves a one-year term.'),
            ('The President serves a two-year term.', 'The Vice President serves a four-year term.'),
            ('The Vice President serves a two-year term.', 'The Vice President is limited to four consecutive years of service in office.'),
            ('A bylaw change needs two weeks notice.', 'A bylaw change needs 14 days notice.'),
            ('The President serves a two-year term.', 'The President serves a 24-month term.'),
            ('A petition requires 5 percent of members.', 'A petition requires 5% of members.'),
            ('The quorum is a majority of members.', 'The note discusses quorum but does not state a binding threshold.'),
            ('Proxy voting is not allowed.', 'Proxy voting is not permitted.'),
            ('The Board shall fill a vacancy.', 'The Board may announce a vacancy.'),
            ('Staff may travel business class for medical reasons.', 'Staff must book economy airfare for routine travel.'),
            ('If a meeting is urgent, notice is seven days.', 'If a meeting is routine, notice is twenty days.'),
        ]
        for a,b in pairs:
            with self.subTest(a=a): self.assertIsNone(candidate_conflict(a,b))

    def test_neutral_question_finds_internal_conflict(self):
        a = SectionChunk('a','The President serves a two-year term.','doc','Policy','1','approved',90,'production','Terms',None,1)
        b = replace(a, chunk_id='b',text='The President serves a three-year term.',page=2)
        rag = RAGService.__new__(RAGService)
        result = rag._detect_conflicts('How long is the President term?', [(a,1,a.text),(b,1,b.text)])
        self.assertEqual(len(result),1)
        self.assertTrue(result[0].human_review_required)
        self.assertEqual(result[0].conflict_scope,'within_document')

    def test_inferred_and_draft_conflicts_are_not_auto_resolved(self):
        a = SectionChunk('a','The President serves a two-year term.','doc','Draft Policy','draft','approved',90,'production',None,None,1)
        b = replace(a,chunk_id='b',document_id='other',authority_level=50,text='The President serves a three-year term.')
        result = RAGService.__new__(RAGService)._detect_conflicts('President term', [(a,1,a.text),(b,1,b.text)])
        self.assertTrue(result[0].human_review_required)
        self.assertIsNone(result[0].higher_authority_evidence)


if __name__=='__main__': unittest.main()
