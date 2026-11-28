import re
from typing import Any

OBLIGATION_DEFINITIONS = {
    "renewal_period": {"family": "renewal", "description": "Contract renewal duration"},
    "renewal_notice": {"family": "renewal", "description": "Advance notice required for non-renewal"},
    "payment_deadline": {"family": "payment", "description": "Payment deadline"},
    "fee_increase_notice": {"family": "payment", "description": "Notice required before fee increases"},
    "breach_cure_period": {"family": "termination", "description": "Time allowed to cure a material breach"},
    "termination_notice": {"family": "termination", "description": "Notice required for termination"},
    "liability_cap": {"family": "liability", "description": "Contractual liability cap"},
    "liability_exceptions": {"family": "liability", "description": "Liability exceptions and carve-outs"},
    "damages_exclusion": {"family": "liability", "description": "Exclusion of specified damages"},
    "data_security_safeguards": {"family": "data_protection", "description": "Data security obligations"},
    "security_incident_notification": {"family": "data_protection", "description": "Security incident notification"},
    "confidentiality_obligation": {"family": "confidentiality", "description": "Confidential information protection"},
    "confidential_information_use": {"family": "confidentiality", "description": "Permitted use of confidential information"},
    "subprocessor_change_notice": {"family": "subprocessors", "description": "Subprocessor change notification"},
    "intellectual_property_indemnity": {"family": "indemnification", "description": "Intellectual property indemnification"},
}

_WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "ninety": 90}
_NUMBER_WORD = r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|ninety"
_NUMBER_TOKEN = rf"(?:\d+|(?:{_NUMBER_WORD})(?:\s*\(\s*\d+\s*\))?)"
DURATION_PATTERN = re.compile(rf"\b(?P<number>{_NUMBER_TOKEN})\s*[- ]?(?P<unit>days?|weeks?|months?|years?)\b", re.I)


def normalize_unit(unit: str) -> str:
    unit = unit.lower().strip()
    for prefix, normalized in (("day", "days"), ("week", "weeks"), ("month", "months"), ("year", "years")):
        if unit.startswith(prefix):
            return normalized
    return unit


def _parse_number_token(token: str) -> int | None:
    token = token.strip().lower()
    parenthetical = re.search(r"\(\s*(\d+)\s*\)", token)
    if parenthetical:
        return int(parenthetical.group(1))
    if token.isdigit():
        return int(token)
    return _WORD_NUMBERS.get(token)


def extract_duration(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    match = DURATION_PATTERN.search(text)
    if not match:
        return None
    value = _parse_number_token(match.group("number"))
    return {"value": value, "unit": normalize_unit(match.group("unit"))} if value else None


def _extract_multiplier(text: str) -> float | None:
    if not text:
        return None
    lower = text.lower()
    match = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:x|Ã—|times)\b", lower)
    if match:
        return float(match.group(1))
    match = re.search(rf"\b({_NUMBER_WORD})(?:\s*\(\s*(\d+(?:\.\d+)?)\s*\))?\s+times\b", lower)
    if match:
        return float(match.group(2)) if match.group(2) else float(_WORD_NUMBERS[match.group(1)])
    if re.search(r"\btwice\b|\bdouble\b", lower):
        return 2.0
    if re.search(r"\btriple\b", lower):
        return 3.0
    return None


_SCOPE_PATTERNS = {
    "confidentiality": r"\b(confidentiality|confidential information)\b",
    "data_protection": r"\b(data protection|personal data|data privacy)\b",
    "intellectual_property": r"\b(intellectual property|ip infringement)\b",
    "security": r"\b(security(?: incident| obligations?| requirements?| controls?)?|information security|cybersecurity|security breach)\b",
    "indemnity": r"\bindemniti(?:es|ed|fy)\b",
}
_EXCEPTION_PATTERNS = {
    "fraud": r"\bfraud\b",
    "wilful_misconduct": r"\b(wilful|willful) misconduct\b",
    "gross_negligence": r"\bgross negligence\b",
    "death_or_personal_injury": r"\bdeath|personal injury\b",
    "intellectual_property_indemnity": r"\b(?:ip|intellectual property)\s+indemnit(?:y|ies)\b|\bindemnity for (?:infringement of )?(?:intellectual property|ip)\b",
    "confidentiality_breach": r"\b(confidentiality|confidential information)\b",
    "data_protection_breach": r"\b(data protection|personal data|data privacy)\b",
    "security_breach": r"\b(security breach|security incident|cybersecurity|security obligations?|security requirements?|security controls?)\b",
}


def extract_liability_attributes(text: str) -> dict[str, Any]:
    """Extract only explicit attributes from the supplied source passage."""
    source = text or ""
    lower = source.lower()
    scopes = sorted(key for key, pattern in _SCOPE_PATTERNS.items() if re.search(pattern, lower))
    if not scopes:
        scopes = ["general"] if re.search(r"\b(liability|damages)\b", lower) else ["unknown"]

    if re.search(r"fees? paid or payable|fees? paid", lower):
        cap_basis = "fees_paid_or_payable"
    elif re.search(r"\b(revenue|annual revenue)\b", lower):
        cap_basis = "revenue"
    elif re.search(r"(?:\$\s*\d|\busd\s*\d|\d+\s*(?:usd|dollars?))", lower):
        cap_basis = "fixed_monetary"
    else:
        cap_basis = "unknown"

    has_exception_language = bool(re.search(r"except(?:ion)?s?|excluding|does not apply|shall not apply|carve[- ]?out|notwithstanding|will not limit|shall not limit", lower))
    exceptions = sorted(key for key, pattern in _EXCEPTION_PATTERNS.items() if has_exception_language and re.search(pattern, lower))
    return {
        "scope": scopes,
        "cap_multiplier": _extract_multiplier(source),
        "reference_period": extract_duration(source),
        "cap_basis": cap_basis,
        "exceptions": exceptions,
        "exception_language_detected": has_exception_language,
        "cap_tier": ("general" if scopes == ["general"] else "unknown" if scopes == ["unknown"] else "enhanced"),
        "source_supported": bool(source.strip()),
    }


def get_obligation_definition(evidence_type: str) -> dict[str, str] | None:
    return OBLIGATION_DEFINITIONS.get(evidence_type)


def normalize_evidence_record(evidence, contract_id=None, contract_title=None) -> dict[str, Any] | None:
    definition = get_obligation_definition(evidence.evidence_type)
    if definition is None:
        return None
    normalized = {
        "evidence_id": str(evidence.id),
        "contract_id": str(contract_id) if contract_id is not None else None,
        "contract_title": contract_title,
        "obligation_type": evidence.evidence_type,
        "obligation_family": definition["family"],
        "description": definition["description"],
        "claim": evidence.claim,
        "original_text": evidence.evidence_text,
        "duration": extract_duration(evidence.claim or ""),
        "verification_status": evidence.verification_status,
        "confidence": evidence.confidence,
        "extraction_method": evidence.extraction_method,
        "provenance": {
            "document_id": str(evidence.document_id) if evidence.document_id else None,
            "clause_id": str(evidence.clause_id) if evidence.clause_id else None,
            "page_number": evidence.page_number,
            "char_start": evidence.char_start,
            "char_end": evidence.char_end,
        },
    }
    if evidence.evidence_type in {"liability_cap", "liability_exceptions"}:
        normalized["liability_attributes"] = extract_liability_attributes(evidence.evidence_text)
    return normalized


def normalize_evidence_records(evidence_records: list, contract_id=None, contract_title=None) -> list[dict[str, Any]]:
    normalized = []
    for evidence in evidence_records:
        item = normalize_evidence_record(evidence, contract_id=contract_id, contract_title=contract_title)
        if item is not None:
            normalized.append(item)
    return normalized


def group_obligations_by_family(obligations: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = {}
    for obligation in obligations:
        grouped.setdefault(obligation["obligation_family"], []).append(obligation)
    return grouped


def group_obligations_by_type(obligations: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = {}
    for obligation in obligations:
        grouped.setdefault(obligation["obligation_type"], []).append(obligation)
    return grouped
