import re


# =====================================================
# NORMALISE TEXT
# =====================================================

def normalize_text(text):

    text = str(text or "").lower()

    text = text.replace("–", "-")
    text = text.replace("—", "-")

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# =====================================================
# ADD UNIQUE CLAIM
# =====================================================

def add_claim(
    claims,
    topic,
    value,
    evidence
):

    key = (
        topic,
        value
    )

    for claim in claims:

        existing_key = (
            claim["topic"],
            claim["value"]
        )

        if existing_key == key:
            return

    claims.append({
        "topic": topic,
        "value": value,
        "evidence": evidence
    })


# =====================================================
# EXTRACT CLAIMS
# =====================================================

def get_claims(text):

    text = normalize_text(text)

    claims = []

    # -------------------------------------------------
    # PROXY VOTING
    # -------------------------------------------------

    if (
        "proxy voting is not allowed"
        in text
        or
        "proxy voting is prohibited"
        in text
    ):

        add_claim(
            claims,
            "proxy_voting",
            "prohibited",
            "Proxy voting is not allowed."
        )

    permission_patterns = [
        r"proxy voting is allowed",
        r"permits .*? voting proxy",
        r"appoint .*? voting proxy",
        r"allows .*? voting proxy"
    ]

    permission_found = False

    for pattern in permission_patterns:

        if re.search(
            pattern,
            text
        ):

            if (
                pattern
                == r"proxy voting is allowed"
                and
                "proxy voting is not allowed"
                in text
            ):
                continue

            permission_found = True
            break

    if permission_found:

        add_claim(
            claims,
            "proxy_voting",
            "permitted",
            "Proxy voting is permitted."
        )

    # -------------------------------------------------
    # BOARD OF GOVERNORS QUORUM
    # -------------------------------------------------

    if re.search(
        r"majority .*? voting .*? members .*? quorum",
        text
    ):

        add_claim(
            claims,
            "bog_quorum",
            "majority",
            "A majority of voting members "
            "constitutes a quorum."
        )

    if re.search(
        r"one[- ]third .*? quorum",
        text
    ):

        add_claim(
            claims,
            "bog_quorum",
            "one_third",
            "One-third constitutes a quorum."
        )

    # -------------------------------------------------
    # PROXY COUNTING FOR QUORUM
    # -------------------------------------------------

    not_counted_patterns = [
        # Exact wording used by SMCS Constitution Article VII:
        # "proxy is not counted in the determination of a quorum"
        r"\bproxy\s+is\s+not\s+counted\s+in\s+the\s+determination\s+of\s+a\s+quorum\b",
        r"\bproxy(?:ies)?\b.{0,80}\bnot\s+(?:be\s+)?count(?:ed)?\b.{0,80}\bquorum\b",
        r"\bproxy(?:ies)?\b.{0,80}\bdo(?:es)?\s+not\s+count\b.{0,80}\bquorum\b",
        r"\bproxy(?:ies)?\b.{0,80}\bexcluded\b.{0,80}\bquorum\b",
        r"\bquorum\b.{0,80}\bproxy(?:ies)?\b.{0,80}\bnot\s+(?:be\s+)?count(?:ed)?\b"
    ]

    not_counted_found = any(
        re.search(
            pattern,
            text
        )
        is not None
        for pattern
        in not_counted_patterns
    )

    if not_counted_found:

        add_claim(
            claims,
            "proxy_quorum",
            "not_counted",
            "Proxy is not counted "
            "for determining quorum."
        )

    counted_patterns = [
        # Exact wording used by synthetic Scenario 01:
        # "submitted proxies count toward quorum"
        r"\bsubmitted\s+proxies\s+count\s+toward\s+quorum\b",
        r"\bproxy(?:ies)?\b.{0,80}\bcount(?:s|ed)?\b.{0,40}\b(?:toward|towards|for|in|when determining)?\s*(?:the\s+)?quorum\b",
        r"\bproxy(?:ies)?\b.{0,80}\b(?:included|include)\b.{0,80}\bquorum\b",
        r"\bquorum\b.{0,80}\b(?:include|includes|count|counts|counted)\b.{0,80}\bproxy(?:ies)?\b"
    ]

    counted_found = False

    for pattern in counted_patterns:

        for match in re.finditer(
            pattern,
            text
        ):

            matched_text = match.group(0)

            # Do not interpret the negative baseline phrase itself
            # ("not counted") as a positive counted claim. A separate
            # positive statement elsewhere in the same synthetic chunk
            # is still retained.
            if re.search(
                r"\bnot\s+(?:be\s+)?count(?:ed)?\b",
                matched_text
            ):
                continue

            counted_found = True
            break

        if counted_found:
            break

    if counted_found:

        add_claim(
            claims,
            "proxy_quorum",
            "counted",
            "Proxy counts toward quorum."
        )

    # -------------------------------------------------
    # TECHNICAL COMMITTEE REPORTING
    #
    # Require TC context so generic IEEE annual-report language
    # cannot be misclassified as a TC reporting rule.
    # -------------------------------------------------

    tc_context = (
        re.search(
            r"\btechnical committee(s)?\b",
            text
        )
        is not None
        or
        re.search(
            r"\btc chair(s)?\b",
            text
        )
        is not None
        or
        re.search(
            r"\btc co-chair(s)?\b",
            text
        )
        is not None
        or
        re.search(
            r"\btcs\b",
            text
        )
        is not None
        or
        re.search(
            r"\btc\b",
            text
        )
        is not None
    )

    reporting_context = (
        re.search(
            r"\breport(s|ing)?\b",
            text
        )
        is not None
    )

    biannual_found = (
        "bi-annually" in text
        or
        "biannually" in text
        or
        "bi-annual" in text
        or
        "biannual" in text
        or
        "semi-annual" in text
        or
        "semi annual" in text
        or
        "twice a year" in text
        or
        "twice annually" in text
        or
        "twice per year" in text
    )

    if (
        tc_context
        and
        reporting_context
        and
        biannual_found
    ):

        add_claim(
            claims,
            "tc_reporting",
            "biannual",
            "Technical Committee reporting "
            "is required twice per year."
        )

    annual_reporting_patterns = [
        r"\breport annually\b",
        r"\breports annually\b",
        r"\breporting annually\b",
        r"\bone annual report\b",
        r"\bonly one annual report\b",
        r"\bannual activity report\b",
        r"\bannual tc report\b"
    ]

    annual_found = any(
        re.search(
            pattern,
            text
        )
        is not None
        for pattern
        in annual_reporting_patterns
    )

    if (
        tc_context
        and
        reporting_context
        and
        annual_found
    ):

        # A synthetic stress-test chunk intentionally contains both
        # the source-derived biannual baseline and the fabricated
        # annual rule ("requires only one annual report"). Keep both
        # claims so the detector can expose the contradiction.
        add_claim(
            claims,
            "tc_reporting",
            "annual",
            "Technical Committee reporting "
            "is required annually."
        )

    # -------------------------------------------------
    # GOVERNANCE HIERARCHY
    #
    # Scenario 20 tests whether lower-level manuals/policies
    # must conform to higher-level IEEE governing documents
    # or may override them.
    # -------------------------------------------------

    hierarchy_context = (
        re.search(
            r"\bgovernance\b",
            text
        )
        is not None
        or
        re.search(
            r"\bgoverning document(s)?\b",
            text
        )
        is not None
        or
        re.search(
            r"\bieee constitution\b",
            text
        )
        is not None
        or
        re.search(
            r"\bieee bylaw(s)?\b",
            text
        )
        is not None
        or
        (
            re.search(
                r"\borganizational[- ]unit\b",
                text
            )
            is not None
            and
            re.search(
                r"\bmanual(s)?\b|\bpolicy statements?\b|\bbylaws?\b",
                text
            )
            is not None
        )
    )

    conform_patterns = [
        r"\bmust conform to\b",
        r"\bshall conform to\b",
        r"\bconform to higher[- ]level\b",
        r"\bmust not conflict with\b",
        r"\bshall not conflict with\b",
        r"\bsubject to .*? higher[- ]level .*? governing document",
        r"\bsubordinate to .*? constitution",
        r"\bsubordinate to .*? bylaws?"
    ]

    lower_must_conform = (
        hierarchy_context
        and
        any(
            re.search(
                pattern,
                text
            )
            is not None
            for pattern
            in conform_patterns
        )
    )

    if lower_must_conform:

        add_claim(
            claims,
            "governance_hierarchy",
            "higher_authority_controls",
            "Lower-level organizational documents "
            "must conform to higher-level IEEE "
            "governing documents."
        )

    override_patterns = [
        r"\bmay override an ieee bylaw\b",
        r"\bmay override ieee bylaws?\b",
        r"\bcan override an ieee bylaw\b",
        r"\bcan override ieee bylaws?\b",
        r"\boverride .*? higher[- ]level .*? governing document",
        r"\boverride .*? ieee .*? bylaw"
    ]

    lower_may_override = (
        hierarchy_context
        and
        any(
            re.search(
                pattern,
                text
            )
            is not None
            for pattern
            in override_patterns
        )
    )

    if lower_may_override:

        add_claim(
            claims,
            "governance_hierarchy",
            "lower_authority_may_override",
            "A lower-level organizational document "
            "is claimed to be able to override a "
            "higher-level IEEE governing document."
        )

    return claims


# =====================================================
# CONFLICT DEFINITIONS
# =====================================================

CONFLICT_PAIRS = {

    "proxy_voting": {
        frozenset([
            "prohibited",
            "permitted"
        ])
    },

    "bog_quorum": {
        frozenset([
            "majority",
            "one_third"
        ])
    },

    "proxy_quorum": {
        frozenset([
            "counted",
            "not_counted"
        ])
    },

    "tc_reporting": {
        frozenset([
            "annual",
            "biannual"
        ])
    },

    "governance_hierarchy": {
        frozenset([
            "higher_authority_controls",
            "lower_authority_may_override"
        ])
    }
}


# =====================================================
# CLAIM CONFLICT CHECK
# =====================================================

def claims_conflict(
    claim_a,
    claim_b
):

    if (
        claim_a["topic"]
        != claim_b["topic"]
    ):

        return False

    pair = frozenset([
        claim_a["value"],
        claim_b["value"]
    ])

    valid_pairs = (
        CONFLICT_PAIRS.get(
            claim_a["topic"],
            set()
        )
    )

    return pair in valid_pairs


# =====================================================
# EXTRACT METADATA
# =====================================================

def get_metadata(item):

    doc = item["doc"]

    metadata = doc.metadata

    return {
        "source": metadata.get(
            "source",
            "Unknown"
        ),

        "page": metadata.get(
            "page",
            "Unknown"
        ),

        "source_type": str(
            metadata.get(
                "source_type",
                "unknown"
            )
        ).lower(),

        "authority_rank": int(
            metadata.get(
                "authority_rank",
                0
            )
        )
    }


# =====================================================
# CONTROLLING SOURCE
# =====================================================

def determine_controller(
    record_a,
    record_b
):

    rank_a = (
        record_a[
            "authority_rank"
        ]
    )

    rank_b = (
        record_b[
            "authority_rank"
        ]
    )

    if rank_a > rank_b:

        return record_a[
            "source"
        ]

    if rank_b > rank_a:

        return record_b[
            "source"
        ]

    if (
        record_a[
            "source_type"
        ]
        == "authoritative"
        and
        record_b[
            "source_type"
        ]
        != "authoritative"
    ):

        return record_a[
            "source"
        ]

    if (
        record_b[
            "source_type"
        ]
        == "authoritative"
        and
        record_a[
            "source_type"
        ]
        != "authoritative"
    ):

        return record_b[
            "source"
        ]

    return (
        "Equal authority - "
        "manual review required"
    )


# =====================================================
# INTERNAL CONFLICT DETECTION
# =====================================================

def detect_internal_conflicts(
    ranked_results
):

    conflicts = []

    for item in ranked_results:

        doc = item["doc"]

        metadata = get_metadata(
            item
        )

        claims = get_claims(
            doc.page_content
        )

        for i in range(
            len(claims)
        ):

            for j in range(
                i + 1,
                len(claims)
            ):

                claim_a = claims[i]
                claim_b = claims[j]

                if not claims_conflict(
                    claim_a,
                    claim_b
                ):
                    continue

                conflicts.append({

                    "conflict_type":
                        "within_chunk",

                    "topic":
                        claim_a["topic"],

                    "claim_a":
                        claim_a["value"],

                    "claim_b":
                        claim_b["value"],

                    "evidence_a":
                        claim_a["evidence"],

                    "evidence_b":
                        claim_b["evidence"],

                    "source_a":
                        metadata["source"],

                    "page_a":
                        metadata["page"],

                    "rank_a":
                        metadata[
                            "authority_rank"
                        ],

                    "source_b":
                        metadata["source"],

                    "page_b":
                        metadata["page"],

                    "rank_b":
                        metadata[
                            "authority_rank"
                        ],

                    "controlling_source":
                        "Internal contradiction "
                        "inside test chunk"
                })

    return conflicts


# =====================================================
# BUILD BEST CLAIM RECORDS
# =====================================================

def build_best_claim_records(
    ranked_results
):

    best = {}

    for item in ranked_results:

        doc = item["doc"]

        metadata = get_metadata(
            item
        )

        claims = get_claims(
            doc.page_content
        )

        for claim in claims:

            key = (
                claim["topic"],
                claim["value"]
            )

            record = {
                "topic":
                    claim["topic"],

                "value":
                    claim["value"],

                "evidence":
                    claim["evidence"],

                "source":
                    metadata["source"],

                "page":
                    metadata["page"],

                "source_type":
                    metadata[
                        "source_type"
                    ],

                "authority_rank":
                    metadata[
                        "authority_rank"
                    ]
            }

            if key not in best:

                best[key] = record

                continue

            existing = best[key]

            if (
                record[
                    "authority_rank"
                ]
                >
                existing[
                    "authority_rank"
                ]
            ):

                best[key] = record

    return best


# =====================================================
# CROSS-SOURCE CONFLICT DETECTION
# =====================================================

def detect_cross_conflicts(
    ranked_results
):

    conflicts = []

    best_claims = (
        build_best_claim_records(
            ranked_results
        )
    )

    topics = set(
        topic
        for topic, value
        in best_claims.keys()
    )

    for topic in topics:

        topic_records = []

        for (
            claim_topic,
            claim_value
        ), record in best_claims.items():

            if claim_topic == topic:

                topic_records.append(
                    record
                )

        for i in range(
            len(topic_records)
        ):

            for j in range(
                i + 1,
                len(topic_records)
            ):

                record_a = (
                    topic_records[i]
                )

                record_b = (
                    topic_records[j]
                )

                claim_a = {
                    "topic":
                        record_a[
                            "topic"
                        ],

                    "value":
                        record_a[
                            "value"
                        ]
                }

                claim_b = {
                    "topic":
                        record_b[
                            "topic"
                        ],

                    "value":
                        record_b[
                            "value"
                        ]
                }

                if not claims_conflict(
                    claim_a,
                    claim_b
                ):
                    continue

                if (
                    record_a["source"]
                    == record_b["source"]
                    and
                    record_a["page"]
                    == record_b["page"]
                ):
                    continue

                controller = (
                    determine_controller(
                        record_a,
                        record_b
                    )
                )

                conflicts.append({

                    "conflict_type":
                        "cross_source",

                    "topic":
                        topic,

                    "claim_a":
                        record_a[
                            "value"
                        ],

                    "claim_b":
                        record_b[
                            "value"
                        ],

                    "evidence_a":
                        record_a[
                            "evidence"
                        ],

                    "evidence_b":
                        record_b[
                            "evidence"
                        ],

                    "source_a":
                        record_a[
                            "source"
                        ],

                    "page_a":
                        record_a[
                            "page"
                        ],

                    "rank_a":
                        record_a[
                            "authority_rank"
                        ],

                    "source_b":
                        record_b[
                            "source"
                        ],

                    "page_b":
                        record_b[
                            "page"
                        ],

                    "rank_b":
                        record_b[
                            "authority_rank"
                        ],

                    "controlling_source":
                        controller
                })

    return conflicts


# =====================================================
# MAIN DETECTION
# =====================================================

def detect_conflicts(
    ranked_results
):

    conflicts = []

    internal_conflicts = (
        detect_internal_conflicts(
            ranked_results
        )
    )

    cross_conflicts = (
        detect_cross_conflicts(
            ranked_results
        )
    )

    conflicts.extend(
        internal_conflicts
    )

    conflicts.extend(
        cross_conflicts
    )

    return conflicts


# =====================================================
# PRINT CONFLICT REPORT
# =====================================================

def print_conflict_report(
    conflicts
):

    print(
        "\n========================================"
    )

    print(
        "CONFLICT DETECTION"
    )

    print(
        "========================================\n"
    )

    if not conflicts:

        print(
            "No genuine rule conflict detected."
        )

        return

    print(
        f"Meaningful conflicts detected: "
        f"{len(conflicts)}\n"
    )

    for index, conflict in enumerate(
        conflicts,
        start=1
    ):

        print(
            f"CONFLICT {index}"
        )

        print(
            f"Type: "
            f"{conflict['conflict_type']}"
        )

        print(
            f"Topic: "
            f"{conflict['topic']}"
        )

        print()

        print(
            f"Source A: "
            f"{conflict['source_a']}"
        )

        print(
            f"Page A: "
            f"{conflict['page_a']}"
        )

        print(
            f"Claim A: "
            f"{conflict['claim_a']}"
        )

        print(
            f"Evidence A: "
            f"{conflict['evidence_a']}"
        )

        print(
            f"Authority Rank A: "
            f"{conflict['rank_a']}"
        )

        print()

        print(
            f"Source B: "
            f"{conflict['source_b']}"
        )

        print(
            f"Page B: "
            f"{conflict['page_b']}"
        )

        print(
            f"Claim B: "
            f"{conflict['claim_b']}"
        )

        print(
            f"Evidence B: "
            f"{conflict['evidence_b']}"
        )

        print(
            f"Authority Rank B: "
            f"{conflict['rank_b']}"
        )

        print()

        print(
            f"Controlling Source: "
            f"{conflict['controlling_source']}"
        )

        print(
            "\n----------------------------------------\n"
        )
