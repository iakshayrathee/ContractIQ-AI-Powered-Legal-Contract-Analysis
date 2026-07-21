"""
Deterministic risk-rule extractors for contract clause analysis.

Each extractor is a pure function: str → typed result. No LLM calls.
These replace brittle substring keyword checks with regex + numeric parsing
so every rule fires on genuine language, not word fragments.

Design principles:
  - All patterns are pre-compiled at module load (fast).
  - Each function returns a typed dataclass (never bare bool/None).
  - Extractors are narrow: one concern per function.
  - Every function is independently unit-testable without a database or LLM.

Usage:
    from app.services.risk_rules.extractors import extract_liability_cap

    result = extract_liability_cap(clause.text)
    if result.has_cap:
        print(f"Cap found: {result.cap_basis} = {result.amount_text}")
    else:
        print("No liability cap detected — flag as HIGH risk")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Pre-compiled patterns — module-level for performance
# ---------------------------------------------------------------------------

# ── Liability cap patterns ───────────────────────────────────────────────────

# Dollar amount patterns: $1,000,000 | $1M | $500k | USD 250,000 | 1,000,000 USD
_DOLLAR_AMOUNT = re.compile(
    r"""
    (?:USD?\s*)?                            # optional currency prefix
    \$?\s*                                  # optional $ sign
    (?P<amount>
        \d{1,3}(?:,\d{3})*(?:\.\d+)?      # 1,000,000.00 style
        |\d+(?:\.\d+)?                     # plain number
    )
    \s*(?P<suffix>[MKBmkb](?:illion|illion)?)?  # M / K / B suffix
    """,
    re.VERBOSE,
)

# Fee-based cap — matches both orderings:
#   (A) "fees paid in the prior 12 months"
#   (B) "fees paid by Customer in the twelve (12) months preceding"
# Non-verbose to avoid whitespace-stripping issues in verbose mode.
_FEE_BASED_CAP = re.compile(
    r"(?:fees?|amounts?|payments?|charges?)\s+(?:paid|payable|received)"
    r"(?:\s+\w+){0,8}\s+"
    r"(?P<months>\d+|one|two|three|six|twelve|twenty.four)"
    r"\s*(?:\(\d+\))?\s*"
    r"(?:calendar\s+)?months?"
    r"(?:\s+(?:prior|preceding|previous|before|preceding\s+the))?",
    re.IGNORECASE,
)

# Explicit cap/limit language: "shall not exceed", "limited to", "aggregate liability of"
_CAP_TRIGGER = re.compile(
    r"""
    (?:
        shall\s+not\s+exceed                # shall not exceed $X
        | limited\s+to                      # limited to $X
        | not\s+exceed                      # not exceed $X
        | aggregate\s+(?:liability|damages) # aggregate liability of $X
        | maximum\s+(?:liability|aggregate) # maximum liability
        | liability\s+(?:shall\s+be\s+)?capped  # liability capped at
        | cap\s+(?:on\s+)?(?:liability|damages)  # cap on liability
        | in\s+no\s+event\s+shall           # in no event shall X exceed Y
        | total\s+liability\s+(?:shall\s+)?(?:not\s+)?exceed
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# False positive patterns — cap-like language that is NOT a financial limit
_FALSE_POSITIVE_CAP = re.compile(
    r"""
    (?:
        no\s+cap\s+on\s+(?!liability|damages)  # "no cap on creativity"
        | (?:capital|capitalize|recapture|escape\s+hatch)
        | (?:market\s+cap|capitalize)
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# ── Notice period patterns ───────────────────────────────────────────────────

# "30 days written notice" | "sixty (60) days prior written notice"
_NOTICE_DAYS_NUMERIC = re.compile(
    r"""
    (?P<days>\d+)                           # numeric days
    \s*(?:\(\d+\))?                         # optional "(30)"
    \s*(?:calendar\s+|business\s+)?days?    # days / calendar days / business days
    (?:\s+(?:prior|advance|written|advance\s+written))?
    \s*(?:written\s+)?notice               # ... notice
    """,
    re.VERBOSE | re.IGNORECASE,
)

# "thirty (30) days" — written-out number
_NOTICE_DAYS_WRITTEN = re.compile(
    r"""
    (?P<word>one|two|three|four|five|six|seven|eight|nine|ten|
             fourteen|fifteen|twenty|thirty|forty|forty.five|
             sixty|ninety|one\s+hundred\s+(?:and\s+)?twenty)
    (?:\s+\(\d+\))?                         # "(30)"
    \s*(?:calendar\s+|business\s+)?days?
    (?:\s+(?:prior|advance|advance\s+written|written))?
    \s*(?:written\s+)?notice
    """,
    re.VERBOSE | re.IGNORECASE,
)

_WORD_TO_DAYS: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "fourteen": 14, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
    "forty-five": 45, "forty five": 45,
    "sixty": 60, "ninety": 90,
    "one hundred and twenty": 120, "one hundred twenty": 120,
}

# ── Auto-renewal patterns ────────────────────────────────────────────────────

_AUTO_RENEWAL_TRIGGER = re.compile(
    r"""
    (?:
        automatically?\s+renew(?:s|ed|ing)?         # automatically renews/renew
        | auto(?:matic)?(?:\s+|-)?renewal            # auto-renewal / automatic renewal
        | successive\s+(?:one|two|\d+)               # successive one-year terms
        | unless\s+(?:(?:either|a)\s+party|written\s+notice)\s+.*?
          (?:terminates?|cancel|non-renew)
        | shall\s+renew\s+automatically
        | renews?\s+(?:automatically|for\s+successive)  # renews for successive
        | (?:initial|one)[- ]year\s+term.*?renew        # initial term ... renew
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

_RENEWAL_TERM = re.compile(
    r"""
    (?:successive|additional|further)\s+
    (?P<count>\d+|one|two|three|six|twelve|twenty.four)?
    \s*-?\s*
    (?P<unit>month|year|annual|calendar\s+year)
    (?:\s+period|s)?
    """,
    re.VERBOSE | re.IGNORECASE,
)

# ── Governing law patterns ───────────────────────────────────────────────────

_GOVERNING_LAW = re.compile(
    r"""
    (?:
        governed\s+by\s+(?:and\s+construed\s+in\s+accordance\s+with\s+)?
        the\s+(?:laws?\s+of\s+(?:the\s+)?)?(?P<jurisdiction_1>[A-Z][A-Za-z\s,]+?)
        (?:\.|,|\s+without)
        |
        laws?\s+of\s+(?:the\s+(?:State|Republic|Kingdom|Province|Country)\s+of\s+)?
        (?P<jurisdiction_2>[A-Z][A-Za-z\s]+?)
        (?:\s+shall\s+govern|\s+governs?|\.|,)
        |
        applicable\s+law\s*:\s*(?P<jurisdiction_3>[A-Z][A-Za-z\s,]+?)(?:\.|,)
    )
    """,
    re.VERBOSE,
)

# ── Indemnity asymmetry patterns ─────────────────────────────────────────────

_INDEMNITY_OBLIGATION = re.compile(
    r"""
    (?P<party>[A-Z][A-Za-z\s,\.]+?)         # party name (capitalised)
    \s+(?:shall|agrees?\s+to|will|must)\s+  # obligation trigger
    (?:defend,?\s+)?(?:indemnify|indemnification|hold\s+harmless)
    """,
    re.VERBOSE,
)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class CapResult:
    """Result of extract_liability_cap()."""
    has_cap: bool
    cap_basis: str = ""          # "fee_based" | "fixed_amount" | "other"
    amount_text: str = ""        # human-readable amount (e.g. "$1,000,000", "12-month fees")
    amount_usd: Optional[float] = None  # numeric USD if parseable, else None
    matched_text: str = ""       # the verbatim text snippet that matched


@dataclass
class AutoRenewalResult:
    """Result of extract_auto_renewal_terms()."""
    has_auto_renewal: bool
    renewal_period: str = ""     # e.g. "12-month", "1-year"
    opt_out_days: Optional[int] = None   # None if no opt-out notice found
    has_adequate_notice: bool = False    # True if opt_out_days >= 30
    matched_text: str = ""


# ---------------------------------------------------------------------------
# Public extractors
# ---------------------------------------------------------------------------

def extract_liability_cap(text: str) -> CapResult:
    """
    Detect and parse a liability/damages cap in clause text.

    Handles:
      - Dollar amounts: "$500,000", "$1M", "USD 250,000"
      - Fee-based caps: "fees paid in the prior 12 months"
      - "Shall not exceed", "limited to", "aggregate liability" triggers

    Returns CapResult with has_cap=False if no genuine cap is found.

    Examples:
        >>> extract_liability_cap("Liability shall not exceed $1,000,000.").has_cap
        True
        >>> extract_liability_cap("The parties have no cap on creativity.").has_cap
        False
        >>> extract_liability_cap("Limited to fees paid in the prior 12 months.").cap_basis
        'fee_based'
    """
    if not text:
        return CapResult(has_cap=False)

    # Short-circuit obvious false positives
    if _FALSE_POSITIVE_CAP.search(text):
        return CapResult(has_cap=False)

    # Must have cap trigger language before checking amounts
    cap_trigger_match = _CAP_TRIGGER.search(text)
    if not cap_trigger_match:
        return CapResult(has_cap=False)

    trigger_text = cap_trigger_match.group(0)

    # Check fee-based cap FIRST before fixed-amount check
    # (fee-based is more specific; must take priority over window dollar search)
    fee_match = _FEE_BASED_CAP.search(text)
    if fee_match:
        months_raw = fee_match.group("months")
        return CapResult(
            has_cap=True,
            cap_basis="fee_based",
            amount_text=f"{months_raw}-month fees",
            matched_text=fee_match.group(0),
        )

    # Check for fixed dollar amount near the trigger
    # Look in a 200-char window around the trigger
    trigger_pos = cap_trigger_match.start()
    window = text[max(0, trigger_pos - 50): trigger_pos + 200]

    dollar_match = _DOLLAR_AMOUNT.search(window)
    if dollar_match:
        raw_amount = dollar_match.group("amount").replace(",", "")
        suffix = (dollar_match.group("suffix") or "").upper()
        try:
            numeric = float(raw_amount)
            multiplier = {"M": 1_000_000, "K": 1_000, "B": 1_000_000_000}.get(suffix[:1] if suffix else "", 1)
            amount_usd = numeric * multiplier
        except ValueError:
            amount_usd = None

        raw_text = dollar_match.group(0).strip()
        return CapResult(
            has_cap=True,
            cap_basis="fixed_amount",
            amount_text=raw_text,
            amount_usd=amount_usd,
            matched_text=f"{trigger_text} {raw_text}",
        )

    # Cap trigger present but no parseable amount — still a cap of sorts
    return CapResult(
        has_cap=True,
        cap_basis="other",
        amount_text="(amount not parseable)",
        matched_text=trigger_text,
    )


def extract_notice_period(text: str) -> Optional[int]:
    """
    Extract the minimum notice period in days from clause text.

    Handles numeric ("30 days notice") and written-out forms ("thirty (30) days").
    Returns the shortest notice period found (most restrictive), or None if absent.

    Examples:
        >>> extract_notice_period("Terminate with 30 days written notice.")
        30
        >>> extract_notice_period("Sixty (60) days prior written notice required.")
        60
        >>> extract_notice_period("Either party may terminate immediately.")
        None
    """
    if not text:
        return None

    candidates: list[int] = []

    # Numeric form
    for m in _NOTICE_DAYS_NUMERIC.finditer(text):
        try:
            candidates.append(int(m.group("days")))
        except (ValueError, IndexError):
            pass

    # Written-out form
    for m in _NOTICE_DAYS_WRITTEN.finditer(text):
        word = m.group("word").lower().strip()
        # normalise hyphen variants
        word = re.sub(r"\s*-\s*", "-", word)
        days = _WORD_TO_DAYS.get(word)
        if days is not None:
            candidates.append(days)

    if not candidates:
        return None
    return min(candidates)  # most restrictive (shortest) notice period


def extract_auto_renewal_terms(text: str) -> AutoRenewalResult:
    """
    Detect auto-renewal clauses and extract opt-out notice requirements.

    Returns:
        AutoRenewalResult with:
          - has_auto_renewal: True if auto-renewal language present
          - renewal_period: e.g. "12-month"
          - opt_out_days: notice required to prevent renewal (None if absent)
          - has_adequate_notice: True if opt_out_days >= 30

    Examples:
        >>> r = extract_auto_renewal_terms("Shall automatically renew for successive 12-month periods unless 60 days notice.")
        >>> r.has_auto_renewal, r.opt_out_days, r.has_adequate_notice
        (True, 60, True)
        >>> extract_auto_renewal_terms("No renewal clause.").has_auto_renewal
        False
    """
    if not text:
        return AutoRenewalResult(has_auto_renewal=False)

    renewal_match = _AUTO_RENEWAL_TRIGGER.search(text)
    if not renewal_match:
        return AutoRenewalResult(has_auto_renewal=False)

    # Extract renewal period
    period_str = ""
    period_match = _RENEWAL_TERM.search(text)
    if period_match:
        count = period_match.group("count") or "1"
        unit = period_match.group("unit").lower()
        unit_norm = "year" if "year" in unit or "annual" in unit else "month"
        period_str = f"{count}-{unit_norm}"

    # Extract opt-out notice days
    opt_out_days = extract_notice_period(text)

    return AutoRenewalResult(
        has_auto_renewal=True,
        renewal_period=period_str,
        opt_out_days=opt_out_days,
        has_adequate_notice=opt_out_days is not None and opt_out_days >= 30,
        matched_text=renewal_match.group(0),
    )


def extract_governing_law(text: str) -> Optional[str]:
    """
    Extract the governing law jurisdiction from clause text.

    Returns the jurisdiction string (e.g. "State of Delaware") or None.

    Examples:
        >>> extract_governing_law("Governed by the laws of the State of Delaware.")
        'State of Delaware'
        >>> extract_governing_law("No governing law clause here.")
    """
    if not text:
        return None

    for m in _GOVERNING_LAW.finditer(text):
        # Try named groups in order
        for group_name in ("jurisdiction_1", "jurisdiction_2", "jurisdiction_3"):
            val = m.group(group_name)
            if val:
                return val.strip().rstrip(".,;")
    return None


def extract_indemnity_asymmetry(text: str) -> dict:
    """
    Detect whether indemnification obligations are one-sided.

    Scans all indemnity obligation sentences and collects the obligating parties.
    Returns a dict with:
      - 'parties_obligated': list of party names with indemnity duties
      - 'is_one_sided': True if only one party has the obligation
      - 'matched_snippets': list of verbatim matching sentences

    Examples:
        >>> r = extract_indemnity_asymmetry("Provider shall indemnify Customer.")
        >>> r['is_one_sided'], r['parties_obligated']
        (True, ['Provider'])
    """
    if not text:
        return {"parties_obligated": [], "is_one_sided": False, "matched_snippets": []}

    parties: list[str] = []
    snippets: list[str] = []

    for m in _INDEMNITY_OBLIGATION.finditer(text):
        party_raw = m.group("party").strip().rstrip(",.")
        # Ignore very short matches that are likely false positives
        if len(party_raw) >= 3:
            parties.append(party_raw)
            # Grab ~100 chars of context
            start = m.start()
            snippet = text[start: start + 120].replace("\n", " ").strip()
            snippets.append(snippet)

    unique_parties = list(dict.fromkeys(parties))  # preserve order, deduplicate
    is_one_sided = len(unique_parties) == 1

    return {
        "parties_obligated": unique_parties,
        "is_one_sided": is_one_sided,
        "matched_snippets": snippets,
    }
