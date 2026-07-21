"""
Unit tests for app/services/risk_rules/extractors.py

Each extractor has ≥ 8 test cases covering:
  - canonical positive matches
  - written-out number variants
  - edge cases and false positives
  - empty / None input

Run with:
    cd backend
    pytest tests/test_risk_rules.py -v
"""

import pytest

from app.services.risk_rules.extractors import (
    AutoRenewalResult,
    CapResult,
    extract_auto_renewal_terms,
    extract_governing_law,
    extract_indemnity_asymmetry,
    extract_liability_cap,
    extract_notice_period,
)


# ============================================================
# extract_liability_cap
# ============================================================

class TestExtractLiabilityCap:

    def test_standard_shall_not_exceed_dollar(self):
        result = extract_liability_cap(
            "Liability shall not exceed $1,000,000 in any event."
        )
        assert result.has_cap is True
        assert result.cap_basis == "fixed_amount"
        assert result.amount_usd == pytest.approx(1_000_000)

    def test_fee_based_cap_twelve_months(self):
        result = extract_liability_cap(
            "IN NO EVENT SHALL PROVIDER'S TOTAL LIABILITY EXCEED THE FEES PAID "
            "BY CUSTOMER IN THE TWELVE (12) MONTHS PRECEDING THE CLAIM."
        )
        assert result.has_cap is True
        assert result.cap_basis == "fee_based"
        assert "12" in result.amount_text or "twelve" in result.amount_text.lower()

    def test_limited_to_fixed_amount(self):
        result = extract_liability_cap(
            "Provider's aggregate liability is limited to $50,000."
        )
        assert result.has_cap is True
        assert result.amount_usd == pytest.approx(50_000)

    def test_million_suffix(self):
        result = extract_liability_cap(
            "Aggregate liability shall not exceed $2M."
        )
        assert result.has_cap is True
        assert result.amount_usd == pytest.approx(2_000_000)

    def test_false_positive_creativity_cap(self):
        result = extract_liability_cap(
            "The parties recognize no cap on creativity or innovation."
        )
        assert result.has_cap is False

    def test_no_cap_language_at_all(self):
        result = extract_liability_cap(
            "Each party is responsible for its own acts and omissions."
        )
        assert result.has_cap is False

    def test_cap_present_but_amount_not_parseable(self):
        result = extract_liability_cap(
            "Total liability shall not exceed the amounts specified in Appendix B."
        )
        assert result.has_cap is True
        assert result.cap_basis == "other"

    def test_fee_based_three_months(self):
        result = extract_liability_cap(
            "Vendor liability shall be limited to fees paid in the prior three (3) months."
        )
        assert result.has_cap is True
        assert result.cap_basis == "fee_based"

    def test_empty_string(self):
        result = extract_liability_cap("")
        assert result.has_cap is False

    def test_usd_prefix_format(self):
        result = extract_liability_cap(
            "Maximum liability: USD 250,000 aggregate."
        )
        assert result.has_cap is True


# ============================================================
# extract_notice_period
# ============================================================

class TestExtractNoticePeriod:

    def test_numeric_30_days(self):
        assert extract_notice_period(
            "Either Party may terminate upon thirty (30) days written notice."
        ) == 30

    def test_numeric_60_days_plain(self):
        assert extract_notice_period(
            "Customer must provide 60 days advance written notice to avoid renewal."
        ) == 60

    def test_written_out_thirty(self):
        assert extract_notice_period(
            "Termination requires thirty days prior notice to the other Party."
        ) == 30

    def test_written_out_sixty(self):
        assert extract_notice_period(
            "Either Party may cancel with sixty (60) days written notice."
        ) == 60

    def test_minimum_of_multiple_periods(self):
        # Should return shortest (most restrictive)
        result = extract_notice_period(
            "Company may terminate with ninety (90) days notice; "
            "Employee may resign with fourteen (14) days notice."
        )
        assert result == 14

    def test_no_notice_language(self):
        assert extract_notice_period(
            "Either Party may terminate this Agreement immediately."
        ) is None

    def test_empty_string(self):
        assert extract_notice_period("") is None

    def test_calendar_days(self):
        assert extract_notice_period(
            "Provide 45 calendar days written notice before renewal date."
        ) == 45

    def test_business_days(self):
        assert extract_notice_period(
            "Terminate with 10 business days notice."
        ) == 10

    def test_written_fifteen(self):
        assert extract_notice_period(
            "Seller shall give fifteen days prior written notice."
        ) == 15


# ============================================================
# extract_auto_renewal_terms
# ============================================================

class TestExtractAutoRenewalTerms:

    def test_auto_renews_with_adequate_notice(self):
        result = extract_auto_renewal_terms(
            "This Agreement shall automatically renew for successive one-year terms "
            "unless either Party provides sixty (60) days written notice of non-renewal."
        )
        assert result.has_auto_renewal is True
        assert result.opt_out_days == 60
        assert result.has_adequate_notice is True

    def test_auto_renews_no_notice(self):
        result = extract_auto_renewal_terms(
            "The Agreement automatically renews each year."
        )
        assert result.has_auto_renewal is True
        assert result.opt_out_days is None
        assert result.has_adequate_notice is False

    def test_auto_renews_inadequate_notice_14_days(self):
        result = extract_auto_renewal_terms(
            "Shall automatically renew unless cancelled with fourteen (14) days notice."
        )
        assert result.has_auto_renewal is True
        assert result.opt_out_days == 14
        assert result.has_adequate_notice is False

    def test_no_auto_renewal(self):
        result = extract_auto_renewal_terms(
            "This Agreement expires on December 31, 2025 and does not renew."
        )
        assert result.has_auto_renewal is False

    def test_successive_twelve_month_periods(self):
        result = extract_auto_renewal_terms(
            "Initial term of one year; thereafter renews for successive twelve-month periods "
            "unless terminated with ninety (90) days advance written notice."
        )
        assert result.has_auto_renewal is True
        assert result.opt_out_days == 90
        assert result.has_adequate_notice is True

    def test_empty_string(self):
        result = extract_auto_renewal_terms("")
        assert result.has_auto_renewal is False

    def test_exactly_30_days_is_adequate(self):
        result = extract_auto_renewal_terms(
            "Agreement renews automatically; opt-out requires 30 days written notice."
        )
        assert result.has_auto_renewal is True
        assert result.has_adequate_notice is True

    def test_120_days_opt_out(self):
        result = extract_auto_renewal_terms(
            "Automatically renews for one-year terms. Customer must provide "
            "one hundred twenty (120) days advance written notice to prevent renewal."
        )
        assert result.has_auto_renewal is True
        assert result.opt_out_days == 120
        assert result.has_adequate_notice is True


# ============================================================
# extract_governing_law
# ============================================================

class TestExtractGoverningLaw:

    def test_state_of_delaware(self):
        result = extract_governing_law(
            "This Agreement shall be governed by and construed in accordance with "
            "the laws of the State of Delaware, without regard to conflict of laws."
        )
        assert result is not None
        assert "Delaware" in result

    def test_england_and_wales(self):
        result = extract_governing_law(
            "This Agreement shall be governed by the laws of England and Wales."
        )
        assert result is not None
        assert "England" in result

    def test_laws_of_california(self):
        result = extract_governing_law(
            "The laws of the State of California shall govern this Agreement."
        )
        assert result is not None
        assert "California" in result

    def test_new_york(self):
        result = extract_governing_law(
            "Governed by and construed in accordance with the laws of New York."
        )
        assert result is not None
        assert "New York" in result

    def test_no_governing_law(self):
        result = extract_governing_law(
            "The parties agree to perform their respective obligations hereunder."
        )
        assert result is None

    def test_empty_string(self):
        assert extract_governing_law("") is None

    def test_state_of_texas(self):
        result = extract_governing_law(
            "This contract is governed by the laws of the State of Texas."
        )
        assert result is not None
        assert "Texas" in result

    def test_laws_of_france(self):
        result = extract_governing_law(
            "This Agreement shall be governed by the laws of France."
        )
        assert result is not None
        assert "France" in result


# ============================================================
# extract_indemnity_asymmetry
# ============================================================

class TestExtractIndemnityAsymmetry:

    def test_one_sided_consultant_indemnifies(self):
        result = extract_indemnity_asymmetry(
            "Consultant shall indemnify, defend, and hold harmless Client from any "
            "claims arising out of Consultant's gross negligence or willful misconduct."
        )
        assert result["is_one_sided"] is True
        assert len(result["parties_obligated"]) == 1
        assert "Consultant" in result["parties_obligated"][0]

    def test_mutual_indemnification(self):
        result = extract_indemnity_asymmetry(
            "Provider shall indemnify Customer against third-party IP claims. "
            "Customer shall indemnify Provider against claims arising from Customer's use."
        )
        assert result["is_one_sided"] is False
        assert len(result["parties_obligated"]) == 2

    def test_client_indemnifies_vendor(self):
        result = extract_indemnity_asymmetry(
            "Client shall indemnify and hold harmless Vendor from any and all claims "
            "arising from Client's use of the deliverables."
        )
        assert result["is_one_sided"] is True
        assert "Client" in result["parties_obligated"][0]

    def test_no_indemnification_clause(self):
        result = extract_indemnity_asymmetry(
            "Each Party shall perform its obligations with reasonable care and skill."
        )
        assert result["is_one_sided"] is False
        assert result["parties_obligated"] == []

    def test_empty_string(self):
        result = extract_indemnity_asymmetry("")
        assert result["is_one_sided"] is False
        assert result["parties_obligated"] == []

    def test_matched_snippets_populated(self):
        result = extract_indemnity_asymmetry(
            "Supplier shall indemnify Buyer for all product liability claims."
        )
        assert len(result["matched_snippets"]) >= 1

    def test_vendor_indemnifies_customer(self):
        result = extract_indemnity_asymmetry(
            "Vendor shall indemnify Customer against any claims that the Software "
            "infringes a valid patent or copyright of a third party."
        )
        assert result["is_one_sided"] is True
        assert "Vendor" in result["parties_obligated"][0]

    def test_three_party_agreement(self):
        result = extract_indemnity_asymmetry(
            "Contractor shall indemnify Owner from subcontractor claims. "
            "Contractor shall also indemnify Architect from design disputes."
        )
        # Both obligations are from Contractor — still one-sided
        assert len(result["parties_obligated"]) >= 1
