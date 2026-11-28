from app.services.obligation_normalizer import (
    extract_duration,
    extract_liability_attributes,
)


def test_extract_duration_from_six_parenthetical_six_months():
    assert extract_duration("fees paid or payable in the six (6) months preceding the event") == {
        "value": 6,
        "unit": "months",
    }


def test_extract_duration_from_twelve_parenthetical_twelve_months():
    assert extract_duration("two (2) times the fees paid in the twelve (12) months preceding the event") == {
        "value": 12,
        "unit": "months",
    }


def test_extract_duration_from_written_number_without_parentheses():
    assert extract_duration("notice must be provided within twelve months") == {
        "value": 12,
        "unit": "months",
    }


def test_liability_attributes_include_reference_period_and_multiplier():
    attributes = extract_liability_attributes(
        "Liability for breach of confidentiality shall not exceed two (2) times "
        "fees paid or payable in the twelve (12) months preceding the event."
    )
    assert attributes["scope"] == ["confidentiality"]
    assert attributes["cap_multiplier"] == 2.0
    assert attributes["reference_period"] == {"value": 12, "unit": "months"}
    assert attributes["cap_basis"] == "fees_paid_or_payable"
