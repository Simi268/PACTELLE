
import re


# --------------------------------------------------
# RENEWAL EVIDENCE PATTERNS
# --------------------------------------------------

RENEWAL_PERIOD_PATTERN = re.compile(
    r"\bautomatically\s+renews?\s+for\s+successive\b.*?\bperiods?\b",
    re.IGNORECASE | re.DOTALL
)

RENEWAL_NOTICE_PATTERN = re.compile(
    r"\bnotice\s+of\s+non-renewal\b.*?\bcurrent\s+term\b",
    re.IGNORECASE | re.DOTALL
)


# --------------------------------------------------
# SENTENCE SPLITTER
# --------------------------------------------------

def split_sentences_with_offsets(text: str):
    """
    Split contractual text into sentences while preserving
    exact character offsets in the original source text.
    """

    sentences = []

    lines = text.splitlines(keepends=True)
    text_start = 0

    if lines:
        first_line = lines[0].strip()

        heading_pattern = re.compile(
            r"^\d+(?:\.\d+)*[.)]?\s+\S.*$"
        )

        if heading_pattern.match(first_line):
            text_start = len(lines[0])

    content = text[text_start:]

    # Normalize line breaks while retaining original positions.
    normalized_chars = []
    original_positions = []

    index = 0

    while index < len(content):
        char = content[index]

        if char in "\r\n":
            original_positions.append(text_start + index)
            normalized_chars.append(" ")

            while (
                index < len(content)
                and content[index] in "\r\n"
            ):
                index += 1

            continue

        normalized_chars.append(char)
        original_positions.append(text_start + index)
        index += 1

    normalized_content = "".join(normalized_chars)

    pattern = re.compile(r"[^.!?]+(?:[.!?]+|$)")

    for match in pattern.finditer(normalized_content):

        raw_sentence = match.group()

        left = len(raw_sentence) - len(raw_sentence.lstrip())
        right = len(raw_sentence.rstrip())

        if left >= right:
            continue

        normalized_start = match.start() + left
        normalized_end = match.start() + right

        original_start = original_positions[normalized_start]
        original_end = original_positions[normalized_end - 1] + 1

        source_sentence = text[original_start:original_end]

        if not source_sentence.strip():
            continue

        sentences.append({
            "text": source_sentence,
            "start": original_start,
            "end": original_end,
        })

    return sentences


# --------------------------------------------------
# NUMBER EXTRACTION
# --------------------------------------------------

def extract_number(pattern_text: str, unit: str) -> int | None:
    """
    Extract numeric values from formats such as:
    thirty (30) days
    30 days
    twelve (12) months
    twelve (12) month periods
    """

    unit_pattern = re.escape(unit.rstrip("s")) + r"s?"

    pattern = rf"""
        (?:
            [a-z]+\s*
            \(\s*(\d+)\s*\)
            |
            (\d+)
        )
        \s*[- ]?{unit_pattern}
    """

    match = re.search(
        pattern,
        pattern_text,
        re.IGNORECASE | re.VERBOSE
    )

    if not match:
        return None

    number = match.group(1) or match.group(2)

    return int(number)


# --------------------------------------------------
# EVIDENCE EXTRACTION
# --------------------------------------------------

def extract_evidence_from_clause(clause):
    """
    Extract structured claims supported by exact source passages.
    Supports both sentence-level and phrase-level evidence.
    """

    category = clause.category

    sentences = split_sentences_with_offsets(
        clause.source_text
    )

    results = []

    # --------------------------------------------------
    # EVIDENCE CREATION HELPER
    # --------------------------------------------------

    def add_evidence(
        evidence_type,
        claim,
        sentence_data,
        phrase_match=None
    ):

        if phrase_match:

            relative_start = (
                sentence_data["start"] + phrase_match.start()
            )

            relative_end = (
                sentence_data["start"] + phrase_match.end()
            )

        else:

            relative_start = sentence_data["start"]
            relative_end = sentence_data["end"]

        evidence_text = clause.source_text[
            relative_start:relative_end
        ]

        results.append({
            "evidence_type": evidence_type,
            "claim": claim,
            "evidence_text": evidence_text,
            "page_number": clause.page_number,
            "char_start": clause.char_start + relative_start,
            "char_end": clause.char_start + relative_end,
            "extraction_method": "rule_based",
            "confidence": None,
            "verification_status": "unverified"
        })

    # --------------------------------------------------
    # PROCESS SENTENCES
    # --------------------------------------------------

    for sentence_data in sentences:

        sentence = sentence_data["text"]
        lower = sentence.lower()

        # --------------------------------
        # PAYMENT
        # --------------------------------

        if category == "payment":

            if "payable" in lower or "payment" in lower:

                days = extract_number(sentence, "days")

                if days is not None:

                    add_evidence(
                        "payment_deadline",
                        f"Payment is due within {days} days.",
                        sentence_data
                    )

            if "fee increase" in lower:

                days = extract_number(sentence, "days")

                if days is not None:

                    add_evidence(
                        "fee_increase_notice",
                        f"Fee increases require at least {days} days' advance written notice.",
                        sentence_data
                    )

        # --------------------------------
        # RENEWAL
        # --------------------------------

        elif category == "renewal":

            renewal_period_match = (
                RENEWAL_PERIOD_PATTERN.search(sentence)
            )

            if renewal_period_match:

                months = extract_number(
                    renewal_period_match.group(),
                    "months"
                )

                if months is not None:

                    add_evidence(
                        "renewal_period",
                        f"The agreement automatically renews for successive {months}-month periods.",
                        sentence_data,
                        renewal_period_match
                    )

            renewal_notice_match = (
                RENEWAL_NOTICE_PATTERN.search(sentence)
            )

            if renewal_notice_match:

                days = extract_number(
                    renewal_notice_match.group(),
                    "days"
                )

                if days is not None:

                    add_evidence(
                        "renewal_notice",
                        f"Non-renewal requires at least {days} days' advance written notice.",
                        sentence_data,
                        renewal_notice_match
                    )

        # --------------------------------
        # TERMINATION
        # --------------------------------

        elif category == "termination":

            if "material breach" in lower and "cure" in lower:

                days = extract_number(sentence, "days")

                if days is not None:

                    add_evidence(
                        "breach_cure_period",
                        f"A material breach has a {days}-day cure period.",
                        sentence_data
                    )

            if "terminate for convenience" in lower:

                days = extract_number(sentence, "days")

                if days is not None:

                    add_evidence(
                        "termination_notice",
                        f"Customer may terminate for convenience with {days} days' written notice.",
                        sentence_data
                    )

        # --------------------------------
        # LIABILITY
        # --------------------------------

        elif category == "liability":

            # Capture general and enhanced caps, including caps expressed
            # with a multiplier, without requiring a reference period.
            has_cap_language = bool(re.search(
                r"\b(aggregate liability|total liability|liability .*? shall not exceed|liability .*? will not exceed|liability .*? capped)\b",
                lower,
            )) and bool(re.search(r"\b(exceed|capped|cap|limit)\b", lower))

            if has_cap_language:
                multiplier = re.search(
                    r"\b(\d+(?:\.\d+)?\s*(?:x|×|times)|one|two|three|four|five(?:\s*\(\s*\d+\s*\))?\s+times|twice|double|triple)\b",
                    lower,
                )
                period = extract_number(sentence, "months") or extract_number(sentence, "years")
                tier = "enhanced" if re.search(
                    r"\b(confidentiality|data protection|personal data|security|indemnity|indemnification|intellectual property)\b",
                    lower,
                ) else "general"
                description = f"{tier.title()} liability cap provision detected"
                if multiplier:
                    description += f" with multiplier wording: {multiplier.group(0)}"
                if period:
                    description += f" and a stated {period}-unit reference period"
                add_evidence("liability_cap", description + ".", sentence_data)

            # Preserve carve-outs/exceptions as separate evidence so they
            # can be compared without conflating them with the cap amount.
            if re.search(
                r"\b(except|excluding|excludes?|shall not apply|does not apply|carve[- ]?out|notwithstanding|will not limit|shall not limit)\b",
                lower,
            ) and re.search(r"\b(liability|cap|limit|damages|fraud|misconduct|negligence|indemnity)\b", lower):
                add_evidence(
                    "liability_exceptions",
                    "A liability exception or carve-out provision was detected; the listed categories require review.",
                    sentence_data,
                )

            if "consequential damages" in lower:

                add_evidence(
                    "damages_exclusion",
                    "The agreement excludes certain categories of damages.",
                    sentence_data
                )

        # --------------------------------
        # DATA PROTECTION
        # --------------------------------

        elif category == "data_protection":

            if "safeguards" in lower:

                add_evidence(
                    "data_security_safeguards",
                    "The vendor must maintain administrative, technical, and physical safeguards.",
                    sentence_data
                )

            if "security incident" in lower:

                add_evidence(
                    "security_incident_notification",
                    "The vendor must notify the customer of confirmed security incidents affecting customer data.",
                    sentence_data
                )

        # --------------------------------
        # CONFIDENTIALITY
        # --------------------------------

        elif category == "confidentiality":

            if "confidential information" in lower and "protect" in lower:

                add_evidence(
                    "confidentiality_obligation",
                    "Each party must protect the other party's confidential information.",
                    sentence_data
                )

            if "may be used only" in lower:

                add_evidence(
                    "confidential_information_use",
                    "Confidential information may only be used for purposes permitted by the agreement.",
                    sentence_data
                )

        # --------------------------------
        # SUBPROCESSORS
        # --------------------------------

        elif category == "subprocessors":

            if "advance notice" in lower:

                add_evidence(
                    "subprocessor_change_notice",
                    "The vendor must provide advance notice of material subprocessor changes upon customer request.",
                    sentence_data
                )

        # --------------------------------
        # INDEMNIFICATION
        # --------------------------------

        elif category == "indemnification":

            if "third-party claims" in lower and "infringe" in lower:

                add_evidence(
                    "intellectual_property_indemnity",
                    "The vendor must defend the customer against specified third-party intellectual property infringement claims.",
                    sentence_data
                )

    return results
