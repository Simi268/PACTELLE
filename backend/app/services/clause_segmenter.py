import re


# Detect numbered clause headings.
HEADING_PATTERN = re.compile(
    r"^\s*(\d+(?:\.\d+)*)[.)]\s+(.+?)\s*$"
)


CATEGORY_KEYWORDS = {
    "renewal": [
        "renewal",
        "auto-renew",
        "automatic renewal"
    ],

    "termination": [
        "termination",
        "terminate"
    ],

    "payment": [
        "payment",
        "fees",
        "invoice"
    ],

    "liability": [
        "liability",
        "limitation of liability"
    ],

    "indemnification": [
        "indemnification",
        "indemnify"
    ],

    "confidentiality": [
        "confidentiality",
        "confidential information"
    ],

    "data_protection": [
        "data protection",
        "security",
        "customer data"
    ],

    "subprocessors": [
        "subprocessors",
        "subcontractors"
    ],

    "governing_law": [
        "governing law",
        "jurisdiction"
    ],

    "services": [
        "services",
        "scope of work"
    ]
}


def classify_clause(title: str) -> str:

    normalized_title = title.lower()

    for category, keywords in CATEGORY_KEYWORDS.items():

        if any(
            keyword in normalized_title
            for keyword in keywords
        ):
            return category

    return "general"


def segment_clauses(text: str, page_number: int):

    lines = text.splitlines()

    headings = []

    current_position = 0

    for line in lines:

        match = HEADING_PATTERN.match(line)

        if match:

            headings.append({
                "number": match.group(1),
                "title": match.group(2).strip(),
                "position": current_position
            })

        current_position += len(line) + 1

    clauses = []

    for index, heading in enumerate(headings):

        start = heading["position"]

        if index + 1 < len(headings):

            end = headings[index + 1]["position"]

        else:

            end = len(text)

        raw_source = text[start:end]

        # Calculate the actual boundaries after trimming whitespace.
        leading_trim = len(raw_source) - len(raw_source.lstrip())
        source_text = raw_source.strip()

        actual_start = start + leading_trim
        actual_end = actual_start + len(source_text)

        if not source_text:
            continue

        clauses.append({

            "clause_number": heading["number"],

            "clause_title": heading["title"],

            "category": classify_clause(
                heading["title"]
            ),

            "source_text": source_text,

            "page_number": page_number,

            "char_start": actual_start,
            "char_end": actual_end,

            "extraction_method": "rule_based"

        })

    return clauses