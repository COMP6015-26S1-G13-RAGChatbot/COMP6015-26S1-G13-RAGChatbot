"""Conservative, explainable candidate conflicts; not a general NLI engine.

Different quantities alone are insufficient: clauses must describe the same
policy subject. New matches require human review, including scope/exceptions.
"""
import re

NUMBERS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
           'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
           'eleven': 11, 'twelve': 12, 'fifteen': 15, 'twenty': 20,
           'thirty': 30, 'sixty': 60, 'ninety': 90, 'single': 1}
NUMBER = r'(?:\d+(?:,\d{3})*(?:\.\d+)?|' + '|'.join(NUMBERS) + ')'


def normalise(text):
    return re.sub(r'\s+', ' ', text.lower().replace('–', '-').replace('—', '-'))


def amount(value):
    return float(NUMBERS[value]) if value in NUMBERS else float(value.replace(',', ''))


def quantities(text):
    result = {}
    pattern = rf'\b({NUMBER})[ -]+(?:calendar[ -]+)?(days?|weeks?|months?|years?|hours?|percent)\b'
    for num, unit in re.findall(pattern, text):
        value, unit = amount(num), unit.rstrip('s')
        if unit == 'week':
            value, unit = value*7, 'day'
        elif unit == 'year':
            value, unit = value*12, 'month'
        result.setdefault(unit, set()).add(value)
    for num in re.findall(rf'\b({NUMBER})\s*%', text):
        result.setdefault('percent', set()).add(amount(num))
    for num in re.findall(r'\bUSD\s*([\d,]+(?:\.\d+)?)', text, flags=re.I):
        result.setdefault('usd', set()).add(amount(num))
    return result


def topics(text):
    patterns = {
        'quorum': r'\bquorum\b', 'proxy': r'\bprox(?:y|ies)\b',
        'amendment': r'\b(?:amendment|bylaw change)\b',
        'petition': r'\bpetition\b', 'notice': r'\bnotice|notified\b',
        'term': r'\bterms?\b', 'eligibility': r'\b(?:candidates?|eligib\w*|nomination|stand for)\b',
        'vacancy': r'\bvacanc(?:y|ies)\b',
        'special_session': r'\bspecial session\b', 'chair': r'\b(?:tc|committee) chairs?\b',
        'reporting': r'\breports?|reporting\b',
        'inactivity': r'\binactiv\w*\b',
        'tc_creation': r'\b(?:new|proposed) tc\b|\bactivity begins\b',
        'conference': r'\bconference\b', 'dues': r'\bdues\b',
        'rotation': r'\brotation\b', 'life_member': r'\blife member\b',
        'hierarchy': r'\b(?:hierarchy|override|conform)\b',
        'travel': r'\b(?:airfare|business class|travel)\b',
        'contract': r'\bcontract\w*\b', 'bidding': r'\bbid\w*\b',
    }
    return {key for key, pattern in patterns.items() if re.search(pattern, text)}


def roles(text):
    # Most specific roles first: President-Elect is not the President.
    result = set()
    for role, pattern in [('president_elect', r'president[ -]elect'),
                          ('vice_president', r'vice[ -]president'),
                          ('member_at_large', r'members?[ -]at[ -]large'),
                          ('chair', r'\bchair\b'), ('treasurer', r'\btreasurer\b'),
                          ('secretary', r'\bsecretary\b'),
                          ('president', r'\bpresident\b')]:
        if re.search(pattern, text):
            result.add(role)
            text = re.sub(pattern, '', text)
    return result


def candidate_subjects(text):
    """Offices being sought, excluding roles mentioned as prior experience."""
    text = normalise(text)
    match = re.search(r'\bcandidates? for ([^.;]+?)\s+(?:must|shall|requires?)\b',text)
    if match:
        return roles(match.group(1))
    match = re.search(r'((?:(?:vice )?president(?:-elect)?)(?: and (?:vice )?president(?:-elect)?)?) candidates?\b',text)
    return roles(match.group(1)) if match else set()


def candidate_conflict(left, right):
    a, b = normalise(left), normalise(right)
    if a == b or any('does not state a binding' in t for t in (a,b)):
        return None
    # A prerequisite can be contradicted by a substitute even when the second
    # clause omits the name of the office being sought. Flag for scope review.
    for required, alternative in ((a,b),(b,a)):
        prior = re.search(r'\bmust have served\b[^.;]{0,90}\bas (?:a |an )?([^.;]+)', required)
        substitution = re.search(r'\bsubstitute for ([^.;]+?) service\b', alternative)
        if (prior and substitution and prior.group(1).strip() == substitution.group(1).strip()
                and not re.search(r'\b(?:not|no|never)\b[^.;]{0,50}\bsubstitute\b',alternative)):
            return 'potential_qualification_substitution'
    common = topics(a) & topics(b)
    if not common:
        return None
    for required, alternative in ((a,b),(b,a)):
        if 'tc_creation' in common:
            prerequisite = re.search(r'\brequires?\b[^.;]{0,200}\b(?:review|approval)\b[^.;]{0,60}\bbefore activity begins\b',required)
            reversed_order = re.search(r'\bbegin\b[^.;]{0,100}\bbefore\b[^.;]{0,60}\b(?:review|approval)\b',alternative)
            negated = re.search(r'\b(?:not|never)\s+begin\b',alternative)
            if prerequisite and reversed_order and not negated:
                return 'potential_prerequisite_order_mismatch'
        if 'conference' in common:
            mandatory = re.search(r'\b(?:shall|must)\s+(?:sponsor|cosponsor)\b',required)
            skip = re.search(r'\bmay\s+skip\s+all\b[^.;]{0,60}\bconference sponsorship\b',alternative)
            if mandatory and skip and not re.search(r'\b(?:unless|except)\b',required):
                return 'potential_mandatory_activity_exception'
    # Explicit conditional rules may apply to different circumstances. Do not
    # infer a contradiction without a scope analysis in these cases.
    conditions = [re.findall(r'\bif\s+([^.;]+)', t) for t in (a,b)]
    if all(conditions) and conditions[0] != conditions[1]:
        return None
    ra, rb = roles(a), roles(b)
    if 'term' in common and (not ra or not rb):
        # A generic committee term is not necessarily an officer's term.
        return None
    if common <= {'term', 'eligibility', 'notice'} and ra and rb and ra.isdisjoint(rb):
        return None
    if 'term' in common:
        # A normal appointment and a cumulative/renewal cap measure different
        # things even when the officer and duration unit are identical.
        cap = r'\b(?:continuous|consecutive|maximum|renewal|renewed|extension|extended|limited)\b'
        if bool(re.search(cap,a)) != bool(re.search(cap,b)):
            return None
    def modal_action(t, modal):
        match = re.search(rf'\b(?:{modal})\s+(?:be\s+)?([a-z]+)', t)
        return match.group(1).removesuffix('ed').removesuffix('s') if match else None
    if not any(conditions) and common & {'vacancy', 'reporting', 'special_session'}:
        for x,y in ((a,b),(b,a)):
            action = modal_action(x,'shall|must')
            if action and action == modal_action(y,'may'):
                return 'potential_obligation_mismatch'
    qa, qb = quantities(a), quantities(b)
    numeric_topics = {'term','notice','petition','amendment','inactivity','rotation','quorum','dues','bidding','contract'}
    if common & numeric_topics:
        for unit in qa.keys() & qb.keys():
            if len(qa[unit]) == len(qb[unit]) == 1 and qa[unit].isdisjoint(qb[unit]):
                # Requirements on separate properties of a clause aren't the
                # same quantity. For example, age and prior service are distinct.
                return f'potential_{unit}_requirement_mismatch'
    if common & {'quorum','dues','petition'}:
        def fraction(t):
            if re.search(r'two[ -]thirds',t): return 'two_thirds'
            if re.search(r'one[ -]third',t): return 'one_third'
            if 'majority' in t: return 'majority'
        if fraction(a) and fraction(b) and fraction(a) != fraction(b):
            return 'potential_voting_threshold_mismatch'
    negative = r'\b(?:not allowed|not permitted|prohibited|shall not|must not|cannot)\b'
    positive = r'\b(?:permits?|allowed|may|authori[sz]es?)\b'
    if common & {'proxy','chair','travel'}:
        if any(re.search(negative,x) and re.search(positive,y) and not re.search(negative,y)
               for x,y in ((a,b),(b,a))):
            return 'potential_permission_prohibition_mismatch'
    if 'special_session' in common and any(
            re.search(r'\b(?:must|shall|required|requires)\b',x) and 'optional' in y for x,y in ((a,b),(b,a))):
        return 'potential_obligation_exception_mismatch'
    if 'reporting' in common:
        def frequency(t):
            if re.search(r'bi[ -]annually|semi[ -]annually|twice (?:a|per) year',t): return 2
            if re.search(r'\bannual(?:ly)?\b|once (?:a|per) year',t): return 1
        if frequency(a) and frequency(b) and frequency(a) != frequency(b):
            return 'potential_reporting_frequency_mismatch'
    if 'chair' in common and any('must' in x and 'members' in x and 'non-smcs' in y for x,y in ((a,b),(b,a))):
        return 'potential_membership_exception_mismatch'
    if 'eligibility' in common and any('bog' in x and 'served' in x and 'without prior bog service' in y for x,y in ((a,b),(b,a))):
        return 'potential_prior_service_exception'
    if 'life_member' in common and any('membership' in x and 'regardless of' in y for x,y in ((a,b),(b,a))):
        return 'potential_eligibility_formula_exception'
    if 'hierarchy' in common and any('conform' in x and 'override' in y for x,y in ((a,b),(b,a))):
        return 'potential_authority_override'
    return None
