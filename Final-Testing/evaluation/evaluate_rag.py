import csv
import json
import math
import re
import sys
import time
from pathlib import Path


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

GOLDEN_SET_PATH = (
    PROJECT_ROOT
    / "evaluation"
    / "golden_set.csv"
)

RESULTS_PATH = (
    PROJECT_ROOT
    / "evaluation"
    / "evaluation_results_v2.csv"
)

SUMMARY_PATH = (
    PROJECT_ROOT
    / "evaluation"
    / "evaluation_summary_v2.json"
)

sys.path.insert(
    0,
    str(SRC_DIR)
)


# ============================================================
# IMPORT EXISTING RAG SYSTEM
# ============================================================

import rag_chat

from conflict_detection import detect_conflicts


# ============================================================
# SETTINGS
# ============================================================

MODEL_NAME = "llama3"

ABSTENTION_TEXT = (
    "I cannot determine this from "
    "the retrieved documents."
)

# Semantic answer threshold using the existing BGE model.
SEMANTIC_SIMILARITY_THRESHOLD = 0.78

# Fraction of expected concepts that should appear.
CONCEPT_COVERAGE_THRESHOLD = 0.60


# ============================================================
# NUMBER NORMALISATION
# ============================================================

NUMBER_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
    "twenty-seven": "27",
    "twenty seven": "27"
}


# ============================================================
# TEXT NORMALISATION
# ============================================================

def normalise_text(text):

    if text is None:
        return ""

    text = str(text).lower()

    text = text.replace(
        "–",
        "-"
    )

    text = text.replace(
        "—",
        "-"
    )

    for word, number in NUMBER_WORDS.items():

        text = re.sub(
            rf"\b{re.escape(word)}\b",
            number,
            text
        )

    text = re.sub(
        r"[^a-z0-9\s\-]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# FILENAME NORMALISATION
# ============================================================

def normalise_filename(filename):

    filename = str(
        filename
        or ""
    ).strip()

    filename = filename.lower()

    # Windows often creates copied files such as:
    # document(1).pdf
    filename = re.sub(
        r"\(\d+\)(?=\.pdf$)",
        "",
        filename
    )

    filename = re.sub(
        r"\s+",
        "",
        filename
    )

    return filename


# ============================================================
# BOOLEAN PARSER
# ============================================================

def parse_bool(value):

    return (
        str(value)
        .strip()
        .lower()
        in {
            "true",
            "1",
            "yes"
        }
    )


# ============================================================
# PAGE NORMALISATION
# ============================================================

def normalise_page(value):

    if value is None:
        return ""

    value = str(
        value
    ).strip()

    if not value:
        return ""

    try:

        return str(
            int(
                float(
                    value
                )
            )
        )

    except Exception:

        return value


# ============================================================
# LOAD GOLDEN SET
# ============================================================

def load_golden_set():

    if not GOLDEN_SET_PATH.exists():

        raise FileNotFoundError(
            f"Golden Set not found: "
            f"{GOLDEN_SET_PATH}"
        )

    with GOLDEN_SET_PATH.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:

        reader = csv.DictReader(
            file
        )

        return list(
            reader
        )


# ============================================================
# COSINE SIMILARITY
# ============================================================

def cosine_similarity(
    vector_a,
    vector_b
):

    dot_product = sum(
        a * b
        for a, b
        in zip(
            vector_a,
            vector_b
        )
    )

    magnitude_a = math.sqrt(
        sum(
            value * value
            for value
            in vector_a
        )
    )

    magnitude_b = math.sqrt(
        sum(
            value * value
            for value
            in vector_b
        )
    )

    if (
        magnitude_a == 0
        or
        magnitude_b == 0
    ):

        return 0.0

    return (
        dot_product
        /
        (
            magnitude_a
            *
            magnitude_b
        )
    )


# ============================================================
# SEMANTIC ANSWER SIMILARITY
# ============================================================

def calculate_answer_similarity(
    actual_answer,
    expected_answer
):

    if not actual_answer:
        return 0.0

    if not expected_answer:
        return 0.0

    try:

        expected_embedding = (
            rag_chat.embedding.embed_query(
                expected_answer
            )
        )

        actual_embedding = (
            rag_chat.embedding.embed_query(
                actual_answer
            )
        )

        similarity = cosine_similarity(
            expected_embedding,
            actual_embedding
        )

        return round(
            similarity,
            4
        )

    except Exception as error:

        print(
            f"Semantic similarity error: "
            f"{error}"
        )

        return 0.0


# ============================================================
# CONCEPT TOKENISATION
# ============================================================

def concept_tokens(text):

    text = normalise_text(
        text
    )

    tokens = re.findall(
        r"\b[a-z0-9]+\b",
        text
    )

    return set(
        tokens
    )


# ============================================================
# SINGLE CONCEPT MATCH
# ============================================================

def concept_matches(
    answer,
    concept
):

    answer_normalised = (
        normalise_text(
            answer
        )
    )

    concept_normalised = (
        normalise_text(
            concept
        )
    )

    if not concept_normalised:
        return True

    # Exact phrase match.
    if (
        concept_normalised
        in answer_normalised
    ):

        return True

    expected_tokens = (
        concept_tokens(
            concept
        )
    )

    actual_tokens = (
        concept_tokens(
            answer
        )
    )

    if not expected_tokens:
        return True

    overlap = (
        expected_tokens
        &
        actual_tokens
    )

    coverage = (
        len(overlap)
        /
        len(expected_tokens)
    )

    # Allows paraphrased concepts such as:
    # "BoG meeting"
    # vs
    # "Board of Governors meeting"
    return coverage >= 0.60


# ============================================================
# CONCEPT COVERAGE
# ============================================================

def calculate_concept_coverage(
    answer,
    expected_keywords
):

    expected_keywords = (
        str(
            expected_keywords
            or ""
        ).strip()
    )

    if not expected_keywords:
        return 1.0

    concepts = [
        concept.strip()
        for concept
        in expected_keywords.split(";")
        if concept.strip()
    ]

    if not concepts:
        return 1.0

    matched = 0

    for concept in concepts:

        if concept_matches(
            answer,
            concept
        ):

            matched += 1

    return round(
        matched
        /
        len(concepts),
        4
    )


# ============================================================
# EXTRACT NUMBERS
# ============================================================

def extract_numbers(text):

    text = normalise_text(
        text
    )

    numbers = re.findall(
        r"\b\d+(?:\.\d+)?\b",
        text
    )

    return set(
        numbers
    )


# ============================================================
# CRITICAL NUMBER CHECK
# ============================================================

def critical_numbers_correct(
    actual_answer,
    expected_answer
):

    expected_numbers = (
        extract_numbers(
            expected_answer
        )
    )

    # If expected answer contains no number,
    # numeric validation is not required.
    if not expected_numbers:
        return True

    actual_numbers = (
        extract_numbers(
            actual_answer
        )
    )

    return (
        expected_numbers
        .issubset(
            actual_numbers
        )
    )


# ============================================================
# ABSTENTION CHECK
# ============================================================

def is_abstention(answer):

    return (
        normalise_text(
            ABSTENTION_TEXT
        )
        in
        normalise_text(
            answer
        )
    )


# ============================================================
# CONFLICT ANSWER COMPLETENESS
# ============================================================

def conflict_answer_complete(
    answer,
    category,
    expected_conflict
):

    if (
        category
        != "conflict"
    ):

        return True

    if not expected_conflict:
        return True

    answer_text = (
        normalise_text(
            answer
        )
    )

    conflict_signals = [
        "authoritative",
        "authority",
        "constitution",
        "official",
        "higher authority",
        "lower authority",
        "synthetic",
        "derived",
        "controls",
        "control",
        "governing",
        "govern",
        "preferred",
        "conflict",
        "contradiction",
        "not official",
        "test only"
    ]

    return any(
        normalise_text(
            signal
        )
        in answer_text
        for signal
        in conflict_signals
    )


# ============================================================
# ANSWER CORRECTNESS
# ============================================================

def evaluate_answer_correctness(
    answer,
    expected_answer,
    expected_keywords,
    should_abstain,
    category,
    expected_conflict
):

    actual_abstention = (
        is_abstention(
            answer
        )
    )

    concept_coverage = (
        calculate_concept_coverage(
            answer,
            expected_keywords
        )
    )

    semantic_similarity = (
        calculate_answer_similarity(
            answer,
            expected_answer
        )
    )

    number_correct = (
        critical_numbers_correct(
            answer,
            expected_answer
        )
    )

    conflict_complete = (
        conflict_answer_complete(
            answer,
            category,
            expected_conflict
        )
    )

    # ---------------------------------------------
    # Expected abstention
    # ---------------------------------------------

    if should_abstain:

        answer_correct = (
            actual_abstention
        )

        return {
            "answer_correct":
                answer_correct,

            "semantic_similarity":
                semantic_similarity,

            "concept_coverage":
                concept_coverage,

            "critical_numbers_correct":
                number_correct,

            "conflict_answer_complete":
                conflict_complete
        }

    # ---------------------------------------------
    # Incorrect abstention
    # ---------------------------------------------

    if actual_abstention:

        return {
            "answer_correct":
                False,

            "semantic_similarity":
                semantic_similarity,

            "concept_coverage":
                concept_coverage,

            "critical_numbers_correct":
                number_correct,

            "conflict_answer_complete":
                conflict_complete
        }

    # ---------------------------------------------
    # Semantic OR concept correctness
    # ---------------------------------------------

    semantic_pass = (
        semantic_similarity
        >=
        SEMANTIC_SIMILARITY_THRESHOLD
    )

    concept_pass = (
        concept_coverage
        >=
        CONCEPT_COVERAGE_THRESHOLD
    )

    answer_correct = (
        number_correct
        and
        conflict_complete
        and
        (
            semantic_pass
            or
            concept_pass
        )
    )

    return {
        "answer_correct":
            answer_correct,

        "semantic_similarity":
            semantic_similarity,

        "concept_coverage":
            concept_coverage,

        "critical_numbers_correct":
            number_correct,

        "conflict_answer_complete":
            conflict_complete
    }


# ============================================================
# BEST GLOBAL DISTANCE
# ============================================================

def get_best_distance(results):

    distances = [
        float(
            item["distance"]
        )
        for item
        in results
        if item.get(
            "distance"
        )
        is not None
    ]

    if not distances:
        return None

    return min(
        distances
    )


# ============================================================
# SOURCE MATCH
# ============================================================

def source_names_match(
    source_a,
    source_b
):

    if not source_b:
        return True

    return (
        normalise_filename(
            source_a
        )
        ==
        normalise_filename(
            source_b
        )
    )


# ============================================================
# SOURCE RETRIEVED
# ============================================================

def source_retrieved(
    results,
    expected_source
):

    expected_source = (
        str(
            expected_source
            or ""
        ).strip()
    )

    if not expected_source:
        return True

    for item in results:

        source = (
            item["doc"]
            .metadata
            .get(
                "source",
                ""
            )
        )

        if source_names_match(
            source,
            expected_source
        ):

            return True

    return False


# ============================================================
# PAGE RETRIEVED
# ============================================================

def page_retrieved(
    results,
    expected_source,
    expected_page
):

    expected_page = (
        normalise_page(
            expected_page
        )
    )

    if not expected_page:
        return True

    for item in results:

        metadata = (
            item["doc"].metadata
        )

        source = (
            metadata.get(
                "source",
                ""
            )
        )

        page = (
            normalise_page(
                metadata.get(
                    "page",
                    ""
                )
            )
        )

        source_ok = True

        if expected_source:

            source_ok = (
                source_names_match(
                    source,
                    expected_source
                )
            )

        if (
            source_ok
            and
            page
            ==
            expected_page
        ):

            return True

    return False


# ============================================================
# GET SELECTED CITATION
# ============================================================

def get_selected_citation(
    citation_results
):

    if not citation_results:

        return (
            "",
            ""
        )

    metadata = (
        citation_results[0]
        ["doc"]
        .metadata
    )

    source = str(
        metadata.get(
            "source",
            ""
        )
    )

    page = (
        normalise_page(
            metadata.get(
                "page",
                ""
            )
        )
    )

    return (
        source,
        page
    )


# ============================================================
# CITATION SOURCE MATCH
# ============================================================

def citation_source_match(
    actual_source,
    expected_source
):

    if not expected_source:
        return True

    return source_names_match(
        actual_source,
        expected_source
    )


# ============================================================
# CITATION PAGE MATCH
# ============================================================

def citation_page_match(
    actual_page,
    expected_page
):

    expected_page = (
        normalise_page(
            expected_page
        )
    )

    if not expected_page:
        return True

    return (
        normalise_page(
            actual_page
        )
        ==
        expected_page
    )


# ============================================================
# FLATTEN CONFLICT VALUES
# ============================================================

def flatten_values(value):

    values = []

    if isinstance(
        value,
        dict
    ):

        for key, item in value.items():

            values.append(
                str(
                    key
                )
            )

            values.extend(
                flatten_values(
                    item
                )
            )

    elif isinstance(
        value,
        list
    ):

        for item in value:

            values.extend(
                flatten_values(
                    item
                )
            )

    else:

        values.append(
            str(
                value
            )
        )

    return values


# ============================================================
# AUTHORITY RESOLUTION MATCH
# ============================================================

def controlling_source_match(
    conflicts,
    expected_source
):

    expected_source = str(
        expected_source
        or ""
    ).strip()

    if not expected_source:
        return True

    for conflict in conflicts:

        if not isinstance(
            conflict,
            dict
        ):
            continue

        controlling_source = str(
            conflict.get(
                "controlling_source",
                conflict.get(
                    "controllingSource",
                    ""
                )
            )
            or ""
        ).strip()

        if not controlling_source:
            continue

        if source_names_match(
            controlling_source,
            expected_source
        ):
            return True

    return False


# ============================================================
# CREATE LLM ONCE
# ============================================================

def create_llm():

    print(
        "\n========================================"
    )

    print(
        "LOADING LLM"
    )

    print(
        "========================================\n"
    )

    return rag_chat.Ollama(
        model=MODEL_NAME,
        temperature=0
    )


# ============================================================
# EVALUATE ONE QUESTION
# ============================================================

def evaluate_question(
    row,
    llm
):

    question_id = (
        row.get(
            "id",
            ""
        )
    )

    question = (
        row.get(
            "question",
            ""
        )
    )

    category = (
        row.get(
            "category",
            ""
        )
    )

    expected_answer = (
        row.get(
            "expected_answer",
            ""
        )
    )

    expected_keywords = (
        row.get(
            "expected_keywords",
            ""
        )
    )

    expected_source = (
        row.get(
            "expected_source",
            ""
        )
    )

    expected_page = (
        row.get(
            "expected_page",
            ""
        )
    )

    should_abstain_expected = (
        parse_bool(
            row.get(
                "should_abstain",
                False
            )
        )
    )

    expected_conflict = (
        parse_bool(
            row.get(
                "expected_conflict",
                False
            )
        )
    )

    expected_controlling_source = (
        row.get(
            "expected_controlling_source",
            ""
        )
    )

    start_time = (
        time.time()
    )

    print(
        "\n\n"
        "============================================================"
    )

    print(
        f"{question_id} | "
        f"{category.upper()}"
    )

    print(
        "============================================================"
    )

    print(
        f"Question: "
        f"{question}"
    )

    # ========================================================
    # DEFAULT VALUES
    # ========================================================

    answer = ""

    citation_source = ""

    citation_page = ""

    conflicts = []

    authoritative_results = []

    supporting_results = []

    best_distance = None

    system_abstained = False

    generation_error = ""

    # ========================================================
    # GLOBAL RETRIEVAL
    # ========================================================

    try:

        global_results = (
            rag_chat.retrieve_global(
                question
            )
        )

        best_distance = (
            get_best_distance(
                global_results
            )
        )

    except Exception as error:

        global_results = []

        generation_error = (
            f"Global retrieval error: "
            f"{error}"
        )

    # ========================================================
    # HARD ABSTENTION
    # ========================================================

    if not generation_error:

        system_abstained = (
            rag_chat.should_abstain(
                global_results
            )
        )

    if system_abstained:

        answer = (
            ABSTENTION_TEXT
        )

    # ========================================================
    # FULL PIPELINE
    # ========================================================

    elif not generation_error:

        try:

            semantic_results = (
                rag_chat
                .retrieve_authoritative_semantic(
                    question
                )
            )

            lexical_results = (
                rag_chat
                .retrieve_authoritative_lexical(
                    question
                )
            )

            hybrid_results = (
                rag_chat
                .merge_authoritative_results(
                    semantic_results,
                    lexical_results
                )
            )

            authoritative_results = (
                rag_chat
                .select_authoritative_results(
                    hybrid_results
                )
            )

            supporting_results = (
                rag_chat
                .select_supporting_results(
                    global_results
                )
            )

            analysis_results = (
                authoritative_results
                +
                supporting_results
            )

            conflicts = (
                detect_conflicts(
                    analysis_results
                )
            )

            # Keep rag_chat's internal conflict state aligned with the
            # conflicts computed by this evaluator. Current generation
            # and evidence-selection helpers consult this state.
            if hasattr(
                rag_chat,
                "_LAST_CONFLICTS"
            ):

                rag_chat._LAST_CONFLICTS = (
                    conflicts
                )

            # ---------------------------------------------
            # NO AUTHORITATIVE EVIDENCE
            # ---------------------------------------------

            if not authoritative_results:

                answer = (
                    ABSTENTION_TEXT
                )

                system_abstained = True

            else:

                generation_results = (
                    rag_chat
                    .select_generation_results(
                        authoritative_results,
                        question
                    )
                )

                citation_results = (
                    rag_chat
                    .select_controlling_conflict_citation(
                        conflicts,
                        authoritative_results,
                        question
                    )
                )

                if not citation_results:

                    query_text_for_citation = (
                        rag_chat.canonicalise_lexical_text(
                            question
                        )
                    )

                    governance_hierarchy_query = (
                        re.search(
                            r"\bgovernance\b",
                            query_text_for_citation
                        )
                        is not None
                        or
                        re.search(
                            r"\bgoverning document\b",
                            query_text_for_citation
                        )
                        is not None
                        or
                        (
                            re.search(
                                r"\bauthoritative\b",
                                query_text_for_citation
                            )
                            is not None
                            and
                            (
                                re.search(
                                    r"\bpreferred\b",
                                    query_text_for_citation
                                )
                                is not None
                                or
                                re.search(
                                    r"\boverride\b",
                                    query_text_for_citation
                                )
                                is not None
                                or
                                re.search(
                                    r"\bconflict\b",
                                    query_text_for_citation
                                )
                                is not None
                            )
                        )
                    )

                    if governance_hierarchy_query:

                        hierarchy_citation = (
                            rag_chat
                            .find_governance_hierarchy_evidence(
                                authoritative_results
                            )
                        )

                        if hierarchy_citation is not None:

                            citation_results = [
                                hierarchy_citation
                            ]

                if not citation_results:

                    citation_results = (
                        rag_chat
                        .select_citation_results(
                            generation_results,
                            question
                        )
                    )

                (
                    citation_source,
                    citation_page
                ) = (
                    get_selected_citation(
                        citation_results
                    )
                )

                # -----------------------------------------
                # PRIMARY GENERATION
                # -----------------------------------------

                answer = (
                    rag_chat.generate_answer(
                        llm,
                        question,
                        generation_results
                    )
                )

                # -----------------------------------------
                # FALLBACK
                # -----------------------------------------

                if (
                    rag_chat
                    .model_abstained(
                        answer
                    )
                    and
                    generation_results
                ):

                    top_result = (
                        generation_results[0]
                    )

                    top_lexical_score = (
                        top_result.get(
                            "lexical_score",
                            0
                        )
                    )

                    if (
                        top_lexical_score
                        >= 3
                    ):

                        answer = (
                            rag_chat
                            .generate_fallback_answer(
                                llm,
                                question,
                                top_result
                            )
                        )

                if (
                    rag_chat
                    .model_abstained(
                        answer
                    )
                ):

                    answer = (
                        ABSTENTION_TEXT
                    )

                    system_abstained = True

        except Exception as error:

            generation_error = (
                f"RAG pipeline error: "
                f"{error}"
            )

            answer = ""

    # ========================================================
    # ANSWER EVALUATION
    # ========================================================

    answer_evaluation = (
        evaluate_answer_correctness(
            answer=answer,
            expected_answer=expected_answer,
            expected_keywords=expected_keywords,
            should_abstain=should_abstain_expected,
            category=category,
            expected_conflict=expected_conflict
        )
    )

    answer_correct = (
        answer_evaluation[
            "answer_correct"
        ]
    )

    semantic_similarity = (
        answer_evaluation[
            "semantic_similarity"
        ]
    )

    concept_coverage = (
        answer_evaluation[
            "concept_coverage"
        ]
    )

    number_correct = (
        answer_evaluation[
            "critical_numbers_correct"
        ]
    )

    conflict_answer_complete = (
        answer_evaluation[
            "conflict_answer_complete"
        ]
    )

    # ========================================================
    # ABSTENTION
    # ========================================================

    actual_abstention = (
        is_abstention(
            answer
        )
    )

    abstention_correct = (
        actual_abstention
        ==
        should_abstain_expected
    )

    # ========================================================
    # RETRIEVAL
    # ========================================================

    retrieval_source_hit = (
        source_retrieved(
            authoritative_results,
            expected_source
        )
    )

    retrieval_page_hit = (
        page_retrieved(
            authoritative_results,
            expected_source,
            expected_page
        )
    )

    # ========================================================
    # CITATION
    # ========================================================

    source_correct = (
        citation_source_match(
            citation_source,
            expected_source
        )
    )

    page_correct = (
        citation_page_match(
            citation_page,
            expected_page
        )
    )

    # ========================================================
    # CONFLICT DETECTION
    # ========================================================

    actual_conflict = (
        len(
            conflicts
        )
        >
        0
    )

    conflict_correct = (
        actual_conflict
        ==
        expected_conflict
    )

    # ========================================================
    # AUTHORITY RESOLUTION
    # ========================================================

    authority_correct = (
        controlling_source_match(
            conflicts,
            expected_controlling_source
        )
    )

    # ========================================================
    # SYSTEM-LEVEL ANSWER PASS
    # ========================================================

    answer_level_pass = (
        answer_correct
        and
        abstention_correct
    )

    # ========================================================
    # FULL PIPELINE PASS
    # ========================================================

    checks = [
        answer_correct,
        abstention_correct,
        conflict_correct
    ]

    if expected_source:

        checks.append(
            retrieval_source_hit
        )

        checks.append(
            source_correct
        )

    if expected_page:

        checks.append(
            retrieval_page_hit
        )

        checks.append(
            page_correct
        )

    if expected_controlling_source:

        checks.append(
            authority_correct
        )

    if generation_error:

        full_pipeline_pass = False

    else:

        full_pipeline_pass = all(
            checks
        )

    duration = (
        time.time()
        -
        start_time
    )

    # ========================================================
    # PRINT RESULT
    # ========================================================

    print(
        f"\nAnswer: "
        f"{answer}"
    )

    print(
        f"\nExpected answer: "
        f"{expected_answer}"
    )

    print(
        f"\nSemantic similarity: "
        f"{semantic_similarity:.4f}"
    )

    print(
        f"Concept coverage: "
        f"{concept_coverage * 100:.2f}%"
    )

    print(
        f"Critical numbers correct: "
        f"{number_correct}"
    )

    print(
        f"Conflict-answer complete: "
        f"{conflict_answer_complete}"
    )

    print(
        f"\nCitation: "
        f"{citation_source or 'None'}"
        f"{', page ' + citation_page if citation_page else ''}"
    )

    print(
        f"Best retrieval distance: "
        f"{best_distance}"
    )

    print(
        f"Expected abstention: "
        f"{should_abstain_expected}"
    )

    print(
        f"Actual abstention: "
        f"{actual_abstention}"
    )

    print(
        f"Expected conflict: "
        f"{expected_conflict}"
    )

    print(
        f"Actual conflict: "
        f"{actual_conflict}"
    )

    print(
        f"\nAnswer correct: "
        f"{answer_correct}"
    )

    print(
        f"Retrieval source hit: "
        f"{retrieval_source_hit}"
    )

    print(
        f"Retrieval page hit: "
        f"{retrieval_page_hit}"
    )

    print(
        f"Citation source correct: "
        f"{source_correct}"
    )

    print(
        f"Citation page correct: "
        f"{page_correct}"
    )

    print(
        f"Conflict detection correct: "
        f"{conflict_correct}"
    )

    print(
        f"Authority resolution correct: "
        f"{authority_correct}"
    )

    print(
        f"\nANSWER-LEVEL PASS: "
        f"{answer_level_pass}"
    )

    print(
        f"FULL PIPELINE PASS: "
        f"{full_pipeline_pass}"
    )

    # ========================================================
    # RETURN RESULT
    # ========================================================

    return {
        "id":
            question_id,

        "category":
            category,

        "question":
            question,

        "expected_answer":
            expected_answer,

        "actual_answer":
            answer,

        "semantic_similarity":
            semantic_similarity,

        "concept_coverage":
            concept_coverage,

        "critical_numbers_correct":
            number_correct,

        "conflict_answer_complete":
            conflict_answer_complete,

        "expected_source":
            expected_source,

        "expected_page":
            normalise_page(
                expected_page
            ),

        "citation_source":
            citation_source,

        "citation_page":
            citation_page,

        "best_distance":
            (
                round(
                    best_distance,
                    4
                )
                if
                best_distance
                is not None
                else
                ""
            ),

        "expected_abstention":
            should_abstain_expected,

        "actual_abstention":
            actual_abstention,

        "abstention_correct":
            abstention_correct,

        "answer_correct":
            answer_correct,

        "retrieval_source_hit":
            retrieval_source_hit,

        "retrieval_page_hit":
            retrieval_page_hit,

        "citation_source_correct":
            source_correct,

        "citation_page_correct":
            page_correct,

        "expected_conflict":
            expected_conflict,

        "expected_controlling_source":
            expected_controlling_source,

        "actual_conflict":
            actual_conflict,

        "conflict_correct":
            conflict_correct,

        "authority_correct":
            authority_correct,

        "number_of_conflicts":
            len(
                conflicts
            ),

        "answer_level_pass":
            answer_level_pass,

        "full_pipeline_pass":
            full_pipeline_pass,

        "duration_seconds":
            round(
                duration,
                2
            ),

        "error":
            generation_error
    }


# ============================================================
# PERCENTAGE
# ============================================================

def percentage(
    numerator,
    denominator
):

    if denominator == 0:
        return 0.0

    return round(
        (
            numerator
            /
            denominator
        )
        *
        100,
        2
    )


# ============================================================
# ACCURACY
# ============================================================

def calculate_accuracy(
    rows,
    field
):

    if not rows:
        return 0.0

    correct = sum(
        1
        for row
        in rows
        if row[field]
    )

    return percentage(
        correct,
        len(
            rows
        )
    )


# ============================================================
# AVERAGE
# ============================================================

def calculate_average(
    rows,
    field
):

    if not rows:
        return 0.0

    values = [
        float(
            row[field]
        )
        for row
        in rows
    ]

    if not values:
        return 0.0

    return round(
        sum(values)
        /
        len(values),
        4
    )


# ============================================================
# BUILD SUMMARY
# ============================================================

def build_summary(results):

    total = len(
        results
    )

    factual = [
        row
        for row
        in results
        if row["category"]
        ==
        "factual"
    ]

    conflict = [
        row
        for row
        in results
        if row["category"]
        ==
        "conflict"
    ]

    out_of_scope = [
        row
        for row
        in results
        if row["category"]
        ==
        "out_of_scope"
    ]

    in_scope = [
        row
        for row
        in results
        if row["category"]
        !=
        "out_of_scope"
    ]

    source_expected = [
        row
        for row
        in results
        if str(
            row["expected_source"]
        ).strip()
    ]

    page_expected = [
        row
        for row
        in results
        if str(
            row["expected_page"]
        ).strip()
    ]

    authority_expected = [
        row
        for row
        in results
        if str(
            row.get(
                "expected_controlling_source",
                ""
            )
        ).strip()
    ]

    answer_level_passes = sum(
        1
        for row
        in results
        if row[
            "answer_level_pass"
        ]
    )

    full_pipeline_passes = sum(
        1
        for row
        in results
        if row[
            "full_pipeline_pass"
        ]
    )

    incorrect_in_scope_abstentions = sum(
        1
        for row
        in in_scope
        if row[
            "actual_abstention"
        ]
    )

    errors = sum(
        1
        for row
        in results
        if row[
            "error"
        ]
    )

    return {
        "total_questions":
            total,

        "answer_level_pass_rate":
            percentage(
                answer_level_passes,
                total
            ),

        "full_pipeline_pass_rate":
            percentage(
                full_pipeline_passes,
                total
            ),

        "answer_accuracy":
            calculate_accuracy(
                results,
                "answer_correct"
            ),

        "factual_answer_accuracy":
            calculate_accuracy(
                factual,
                "answer_correct"
            ),

        "conflict_answer_accuracy":
            calculate_accuracy(
                conflict,
                "answer_correct"
            ),

        "out_of_scope_answer_accuracy":
            calculate_accuracy(
                out_of_scope,
                "answer_correct"
            ),

        "abstention_accuracy":
            calculate_accuracy(
                results,
                "abstention_correct"
            ),

        "incorrect_in_scope_abstentions":
            incorrect_in_scope_abstentions,

        "retrieval_source_accuracy":
            calculate_accuracy(
                source_expected,
                "retrieval_source_hit"
            ),

        "retrieval_page_accuracy":
            calculate_accuracy(
                page_expected,
                "retrieval_page_hit"
            ),

        "citation_source_accuracy":
            calculate_accuracy(
                source_expected,
                "citation_source_correct"
            ),

        "citation_page_accuracy":
            calculate_accuracy(
                page_expected,
                "citation_page_correct"
            ),

        "conflict_detection_accuracy":
            calculate_accuracy(
                results,
                "conflict_correct"
            ),

        "authority_resolution_accuracy":
            calculate_accuracy(
                authority_expected,
                "authority_correct"
            ),

        "average_semantic_similarity":
            calculate_average(
                results,
                "semantic_similarity"
            ),

        "average_factual_similarity":
            calculate_average(
                factual,
                "semantic_similarity"
            ),

        "average_conflict_similarity":
            calculate_average(
                conflict,
                "semantic_similarity"
            ),

        "errors":
            errors
    }


# ============================================================
# SAVE RESULTS
# ============================================================

def save_results(results):

    RESULTS_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    if not results:
        return

    fieldnames = list(
        results[0].keys()
    )

    with RESULTS_PATH.open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        writer.writeheader()

        writer.writerows(
            results
        )


# ============================================================
# SAVE SUMMARY
# ============================================================

def save_summary(summary):

    with SUMMARY_PATH.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            summary,
            file,
            indent=4
        )


# ============================================================
# PRINT SUMMARY
# ============================================================

def print_summary(summary):

    print(
        "\n\n"
        "============================================================"
    )

    print(
        "GOLDEN SET EVALUATION SUMMARY V2"
    )

    print(
        "============================================================\n"
    )

    print(
        f"Total questions: "
        f"{summary['total_questions']}"
    )

    print(
        f"\nAnswer-level pass rate: "
        f"{summary['answer_level_pass_rate']}%"
    )

    print(
        f"Full pipeline pass rate: "
        f"{summary['full_pipeline_pass_rate']}%"
    )

    print(
        f"\nAnswer accuracy: "
        f"{summary['answer_accuracy']}%"
    )

    print(
        f"Factual answer accuracy: "
        f"{summary['factual_answer_accuracy']}%"
    )

    print(
        f"Conflict answer accuracy: "
        f"{summary['conflict_answer_accuracy']}%"
    )

    print(
        f"Out-of-scope answer accuracy: "
        f"{summary['out_of_scope_answer_accuracy']}%"
    )

    print(
        f"\nAbstention accuracy: "
        f"{summary['abstention_accuracy']}%"
    )

    print(
        f"Incorrect in-scope abstentions: "
        f"{summary['incorrect_in_scope_abstentions']}"
    )

    print(
        f"\nRetrieval source accuracy: "
        f"{summary['retrieval_source_accuracy']}%"
    )

    print(
        f"Retrieval page accuracy: "
        f"{summary['retrieval_page_accuracy']}%"
    )

    print(
        f"\nCitation source accuracy: "
        f"{summary['citation_source_accuracy']}%"
    )

    print(
        f"Citation page accuracy: "
        f"{summary['citation_page_accuracy']}%"
    )

    print(
        f"\nConflict detection accuracy: "
        f"{summary['conflict_detection_accuracy']}%"
    )

    print(
        f"Authority resolution accuracy: "
        f"{summary['authority_resolution_accuracy']}%"
    )

    print(
        f"\nAverage semantic similarity: "
        f"{summary['average_semantic_similarity']}"
    )

    print(
        f"Average factual similarity: "
        f"{summary['average_factual_similarity']}"
    )

    print(
        f"Average conflict similarity: "
        f"{summary['average_conflict_similarity']}"
    )

    print(
        f"\nErrors: "
        f"{summary['errors']}"
    )

    print(
        "\nResults saved to:"
    )

    print(
        RESULTS_PATH
    )

    print(
        "\nSummary saved to:"
    )

    print(
        SUMMARY_PATH
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\n============================================================"
    )

    print(
        "IEEE SMCS RAG GOLDEN SET EVALUATION V2"
    )

    print(
        "============================================================"
    )

    print(
        f"\nGolden Set: "
        f"{GOLDEN_SET_PATH}"
    )

    print(
        f"Semantic similarity threshold: "
        f"{SEMANTIC_SIMILARITY_THRESHOLD}"
    )

    print(
        f"Concept coverage threshold: "
        f"{CONCEPT_COVERAGE_THRESHOLD}"
    )

    rows = (
        load_golden_set()
    )

    print(
        f"\nQuestions loaded: "
        f"{len(rows)}"
    )

    llm = (
        create_llm()
    )

    results = []

    start_time = (
        time.time()
    )

    for index, row in enumerate(
        rows,
        start=1
    ):

        print(
            "\n\n"
            "############################################################"
        )

        print(
            f"RUNNING QUESTION "
            f"{index}/{len(rows)}"
        )

        print(
            "############################################################"
        )

        result = (
            evaluate_question(
                row,
                llm
            )
        )

        results.append(
            result
        )

        # Save progress after every question.
        save_results(
            results
        )

    summary = (
        build_summary(
            results
        )
    )

    total_duration = (
        time.time()
        -
        start_time
    )

    summary[
        "total_duration_seconds"
    ] = round(
        total_duration,
        2
    )

    save_results(
        results
    )

    save_summary(
        summary
    )

    print_summary(
        summary
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()