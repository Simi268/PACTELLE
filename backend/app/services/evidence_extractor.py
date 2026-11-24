import re


def split_sentences_with_offsets(text: str):
    """
    Split contractual text into sentences.
    Exclude numbered clause headings and preserve offsets.
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

    pattern = re.compile(r"[^.!?]+(?:[.!?]+|$)")

    for match in pattern.finditer(content):

        raw_sentence = match.group()
        sentence = raw_sentence.strip()

        if not sentence:
            continue

        leading_spaces = (
            len(raw_sentence) - len(raw_sentence.lstrip())
        )

        start = text_start + match.start() + leading_spaces
        end = start + len(sentence)

        sentences.append({
            "text": sentence,
            "start": start,
            "end": end
        })

    return sentences


def extract_number(pattern_text: str, unit: str) -> str | None:
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


def extract_evidence_from_clause(clause):
    """
    Extract structured claims supported by exact source sentences.
    """

    category = clause.category
    sentences = split_sentences_with_offsets(clause.source_text)

    results = []

    # IMPORTANT: This helper belongs inside the main function.
    def add_evidence(
        evidence_type: str,
        claim: str,
        sentence_data: dict
    ):

        sentence = sentence_data["text"]

        results.append({
            "claim": claim,
            "evidence_type": evidence_type,
            "evidence_text": sentence,
            "page_number": clause.page_number,

            # Page-relative character positions
            "char_start": (
                clause.char_start + sentence_data["start"]
            ),

            "char_end": (
                clause.char_start + sentence_data["end"]
            ),

            "extraction_method": "rule_based",
            "confidence": None,
            "verification_status": "unverified",
        })

    # Process every sentence
    for sentence_data in sentences:

        sentence = sentence_data["text"]
        lower = sentence.lower()

        # --------------------------------
        # PAYMENT
        # --------------------------------

        if category == "payment":

            if "payable" in lower or "payment" in lower:

                days = extract_number(sentence, "days")

                if days:
                    add_evidence(
                        "payment_deadline",
                        f"Payment is due within {days} days.",
                        sentence_data
                    )

            if "fee increase" in lower:

                days = extract_number(sentence, "days")

                if days:
                    add_evidence(
                        "fee_increase_notice",
                        f"Fee increases require at least {days} days' advance written notice.",
                        sentence_data
                    )

        # --------------------------------
        # RENEWAL
        # --------------------------------

        elif category == "renewal":

            if "automatically renew" in lower or "automatic renewal" in lower:

                months = extract_number(sentence, "months")

                if months:
                    add_evidence(
                        "renewal_period",
                        f"The agreement automatically renews for successive {months}-month periods.",
                        sentence_data
                    )

            if "notice of non-renewal" in lower:

                days = extract_number(sentence, "days")

                if days:
                    add_evidence(
                        "renewal_notice",
                        f"Non-renewal requires at least {days} days' advance written notice.",
                        sentence_data
                    )

        # --------------------------------
        # TERMINATION
        # --------------------------------

        elif category == "termination":

            if "material breach" in lower and "cure" in lower:

                days = extract_number(sentence, "days")

                if days:
                    add_evidence(
                        "breach_cure_period",
                        f"A material breach has a {days}-day cure period.",
                        sentence_data
                    )

            if "terminate for convenience" in lower:

                days = extract_number(sentence, "days")

                if days:
                    add_evidence(
                        "termination_notice",
                        f"Customer may terminate for convenience with {days} days' written notice.",
                        sentence_data
                    )

        # --------------------------------
        # LIABILITY
        # --------------------------------

        elif category == "liability":

            if "aggregate liability" in lower and "exceed" in lower:

                months = extract_number(sentence, "months")

                if months:
                    add_evidence(
                        "liability_cap",
                        f"Aggregate liability is capped by fees paid or payable during the preceding {months} months.",
                        sentence_data
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