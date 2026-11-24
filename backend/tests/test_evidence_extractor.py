from types import SimpleNamespace

from app.services.evidence_extractor import (
    split_sentences_with_offsets,
    extract_number,
    extract_evidence_from_clause,
)


def test_sentence_splitter_excludes_numbered_clause_heading():
    text = (
        "3. Term and Automatic Renewal\n"
        "This Agreement begins on 1 January 2026 and continues "
        "for an initial term of twelve (12) months.\n"
        "It will automatically renew for successive twelve (12) "
        "month periods unless either party gives written notice."
    )

    sentences = split_sentences_with_offsets(text)

    assert len(sentences) == 2
    assert all(not sentence["text"].startswith("3.") for sentence in sentences)


def test_sentence_offsets_match_original_text():
    text = (
        "3. Term and Automatic Renewal\n"
        "This Agreement continues for twelve (12) months. "
        "It automatically renews for successive twelve (12) month periods."
    )

    sentences = split_sentences_with_offsets(text)

    for sentence in sentences:
        extracted_text = text[sentence["start"]:sentence["end"]]
        assert extracted_text == sentence["text"]


def test_extract_number_from_numeric_and_word_formats():
    assert extract_number("Payment is due within 30 days.", "days") == 30
    assert extract_number(
        "The agreement renews for twelve (12) months.", "months"
    ) == 12


def test_renewal_clause_extracts_two_distinct_evidence_records():
    clause_text = (
        "3. Term and Automatic Renewal\n"
        "This Agreement continues for an initial term of twelve (12) months.\n"
        "It will automatically renew for successive twelve (12) month "
        "periods unless either party gives written notice of non-renewal "
        "at least thirty (30) days before the end of the current term."
    )

    clause = SimpleNamespace(
        category="renewal",
        source_text=clause_text,
        char_start=100,
        page_number=1,
    )

    evidence = extract_evidence_from_clause(clause)

    evidence_types = [item["evidence_type"] for item in evidence]

    assert evidence_types.count("renewal_period") == 1
    assert evidence_types.count("renewal_notice") == 1
    assert len(evidence) == 2


def test_services_clause_returns_no_unsupported_evidence():
    clause = SimpleNamespace(
        category="services",
        source_text=(
            "1. Services\n"
            "The Vendor shall provide software implementation services."
        ),
        char_start=0,
        page_number=1,
    )

    evidence = extract_evidence_from_clause(clause)

    assert evidence == []

def test_extract_number_from_90_day_notice():
    assert extract_number("Either party must provide 90 days' notice.", "days") == 90


def test_extract_number_from_24_month_period():
    assert extract_number("The agreement continues for 24 months.", "months") == 24


def test_extract_number_returns_none_when_value_is_missing():
    assert extract_number("The agreement may be renewed automatically.", "months") is None


def test_evidence_offsets_match_clause_source_text():
    clause_text = (
        "3. Term and Automatic Renewal\n"
        "This Agreement continues for an initial term of twelve (12) months.\n"
        "It will automatically renew for successive twelve (12) month "
        "periods unless either party gives written notice of non-renewal "
        "at least thirty (30) days before the end of the current term."
    )

    clause = SimpleNamespace(
        category="renewal",
        source_text=clause_text,
        char_start=100,
        page_number=1,
    )

    evidence = extract_evidence_from_clause(clause)

    for item in evidence:
        relative_start = item["char_start"] - clause.char_start
        relative_end = item["char_end"] - clause.char_start

        assert clause_text[relative_start:relative_end] == item["evidence_text"]


def test_renewal_clause_does_not_generate_unrelated_evidence():
    clause = SimpleNamespace(
        category="renewal",
        source_text=(
            "3. Term and Automatic Renewal\n"
            "It will automatically renew for successive twelve (12) "
            "month periods unless either party gives written notice "
            "of non-renewal at least thirty (30) days before the end "
            "of the current term."
        ),
        char_start=0,
        page_number=1,
    )

    evidence = extract_evidence_from_clause(clause)

    evidence_types = {item["evidence_type"] for item in evidence}

    assert evidence_types == {"renewal_period", "renewal_notice"}