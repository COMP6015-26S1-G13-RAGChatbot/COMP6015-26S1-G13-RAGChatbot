"""Development regressions for prerequisites, sequence, and exceptions."""
import unittest
from backend.services.policy_claim_service import candidate_conflict, candidate_subjects
from backend.services.rag_service import RAGService
from backend.services.search_service import expand_hybrid_query


class PolicyExceptionsTests(unittest.TestCase):
    def test_candidate_subject_excludes_prior_office(self):
        self.assertEqual(candidate_subjects(
            'Candidates for President must have served as a Vice President.'), {'president'})

    def test_conflict_passage_retains_adjacent_requirement(self):
        text = ('IEEE governance documents have an established hierarchy. '
                'All Society rules must conform to the higher authority documents.')
        self.assertIn('must conform', RAGService._best_passage(
            text, 'Do IEEE governance documents conflict in their hierarchy?'))

    def test_query_expansion_preserves_original_and_adds_terms(self):
        query = 'What is the minimum attendance for the governing board?'
        expanded = expand_hybrid_query(query)
        self.assertIn(query, expanded)
        self.assertIn('quorum', expanded)
        self.assertIn('board of governors', expanded)

    def test_qualification_substitution(self):
        a='Candidates for President must have served at least one year as a Vice President.'
        b='Two years as a Member-at-Large is an acceptable substitute for Vice President service.'
        self.assertEqual(candidate_conflict(a,b),'potential_qualification_substitution')

    def test_substitution_negated_or_for_another_role(self):
        a='Candidates for President must have served at least one year as a Vice President.'
        for b in ['Other experience is not an acceptable substitute for Vice President service.',
                  'Teaching experience is a substitute for Secretary service.',
                  'Candidates must have served one year as a Vice President.']:
            with self.subTest(b=b):self.assertIsNone(candidate_conflict(a,b))

    def test_approval_sequence(self):
        a='A new TC requires Area Committee review and Area VP approval before activity begins.'
        b='A proposed TC may begin immediately after submitting a request, before Area Committee review.'
        self.assertEqual(candidate_conflict(a,b),'potential_prerequisite_order_mismatch')

    def test_consistent_or_negated_sequence(self):
        a='A new TC requires Area Committee review and Area VP approval before activity begins.'
        for b in ['A proposed TC must not begin before Area Committee review.',
                  'A proposed TC may begin after Area Committee review and Area VP approval.',
                  'A proposed TC may prepare an application before Area Committee review.']:
            with self.subTest(b=b):self.assertIsNone(candidate_conflict(a,b))

    def test_conditional_exception_is_potential(self):
        a='The Society shall sponsor at least one major technical conference each year.'
        b='The Society may skip all major conference sponsorship for a year whenever reserves fall below a target.'
        self.assertEqual(candidate_conflict(a,b),'potential_mandatory_activity_exception')

    def test_unrelated_activity_or_existing_exception(self):
        a='The Society shall sponsor at least one major technical conference each year.'
        for b in ['The Society may skip a conference dinner.',
                  'The Society must not skip all major conference sponsorship.',
                  'The Society may hold additional conference workshops.']:
            with self.subTest(b=b):self.assertIsNone(candidate_conflict(a,b))
        qualified=a+' unless reserves fall below a target.'
        b='The Society may skip all major conference sponsorship when reserves fall below a target.'
        self.assertIsNone(candidate_conflict(qualified,b))


if __name__=='__main__':unittest.main()
