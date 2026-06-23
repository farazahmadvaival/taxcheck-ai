# TaxCheck AI – Additional Anomaly Detection Rules Specification

## Purpose

This document defines additional anomaly detection logic for the existing tax return anomaly detection application.

The app currently targets the following US return types:

- **1120-S** – S-Corporation Return
- **1065** – Partnership Return
- **1120** – C-Corporation Return
- **1040 / Schedule C** – Individual Sole Proprietor Return

The current app already supports the following base rule groups:

1. Core Missing Document Checks
2. Contextual / Trigger-Based Document Checks
3. Financial & Mathematical Anomalies

This document extends the existing logic with more advanced checks that can better identify missing support, inconsistent financial data, return-type mismatches, and tax-preparation review risks.

> Important: These rules are intended to assist tax preparers. They should flag anomalies for review, not make final tax/legal determinations.

---

# 1. Recommended Rule Output Format

Every anomaly rule should return a structured object.

```json
{
  "rule_id": "PY-001",
  "rule_name": "Beginning Balance Mismatch",
  "return_type": "1120-S",
  "severity": "HIGH",
  "status": "FLAGGED",
  "confidence_score": 0.86,
  "category": "PRIOR_YEAR_ROLL_FORWARD",
  "evidence_document": "balance_sheet_2025.pdf",
  "evidence_text": "Total Assets beginning of year: 245,000",
  "extracted_amount": 245000.00,
  "expected_amount": 250000.00,
  "difference": 5000.00,
  "tolerance": 5.00,
  "missing_support": [],
  "recommended_action": "Review prior-year ending balance sheet and current-year beginning balances.",
  "review_required_by": "TAX_PREPARER"
}
```

## Required Fields

| Field | Description |
|---|---|
| `rule_id` | Unique ID for the rule |
| `rule_name` | Human-readable rule name |
| `return_type` | 1120-S, 1065, 1120, 1040_SCHEDULE_C, or ALL |
| `severity` | HIGH, MEDIUM, LOW |
| `status` | FLAGGED, PASSED, SKIPPED |
| `confidence_score` | Confidence from document detection, OCR, extraction, and rule match |
| `category` | Rule group/category |
| `evidence_document` | Source document where evidence was found |
| `evidence_text` | Short extracted text that triggered the rule |
| `extracted_amount` | Amount found in current package, if applicable |
| `expected_amount` | Expected amount, if applicable |
| `difference` | Difference between extracted and expected amount |
| `tolerance` | Allowed tolerance |
| `missing_support` | Required supporting documents not found |
| `recommended_action` | What the preparer should review |
| `review_required_by` | TAX_PREPARER, CPA, CLIENT, SYSTEM |

---

# 2. Document Type Enums

Add or confirm support for the following document types.

```text
PRIOR_YEAR_RETURN
CURRENT_YEAR_RETURN
BALANCE_SHEET
INCOME_STATEMENT
TRIAL_BALANCE
GENERAL_LEDGER
BANK_STATEMENT
BANK_RECONCILIATION
PAYROLL_SUMMARY
W2_W3
FORM_941_940
DEPRECIATION_SCHEDULE
FIXED_ASSET_LISTING
LOAN_STATEMENT
CREDIT_CARD_STATEMENT
AR_AGING
AP_AGING
SHAREHOLDER_DISTRIBUTION
PARTNER_DISTRIBUTION
OWNER_DRAW_SUPPORT
K1_WORKSHEET
OWNERSHIP_SCHEDULE
CAPITAL_ACCOUNT_SCHEDULE
SALES_REPORT
MERCHANT_STATEMENT
FORM_1099_K
FORM_1099_NEC
FORM_1099_MISC
INVENTORY_REPORT
COGS_SUPPORT
VEHICLE_MILEAGE_LOG
HOME_OFFICE_SUPPORT
FORM_8829
CONTRACTOR_LISTING
W9
TAX_PAYMENT_SUPPORT
SALES_TAX_REPORT
```

---

# 3. Existing Rules to Keep

The following existing rules should remain active.

## Core Missing Document Checks

| Rule ID | Rule Name | Severity |
|---|---|---|
| A | Prior Year Return Missing | HIGH |
| B | Balance Sheet Missing | HIGH |
| C | Income Statement Missing | HIGH |
| D | Trial Balance Missing | HIGH |
| E | General Ledger Detail Missing | MEDIUM |

## Contextual / Trigger-Based Document Checks

| Rule ID | Rule Name | Severity |
|---|---|---|
| F | Payroll Support Missing | HIGH |
| G | Depreciation Schedule Missing | MEDIUM |
| H | Loan / Interest Statement Missing | MEDIUM |
| I | Bank Statement Missing | HIGH |
| J | Accounts Receivable Aging Missing | MEDIUM |
| K | Accounts Payable Aging Missing | MEDIUM |
| M | Shareholder Distribution Support Missing | MEDIUM |

## Financial & Mathematical Checks

| Rule ID | Rule Name | Severity |
|---|---|---|
| L | High Miscellaneous Expense | MEDIUM |
| N | Negative Balance Warning | LOW |
| BS-001 | Balance Sheet Equation Mismatch | HIGH |

---

# 4. New Rule Group: Prior-Year Roll-Forward Checks

These are high-value checks and should be prioritized.

## PY-001: Beginning Balance Mismatch

**Applies To:** 1120-S, 1065, 1120, 1040 Schedule C if balance sheet is available  
**Severity:** HIGH

### Logic

Compare current-year beginning balance sheet values with prior-year ending balance sheet values.

Flag if:

```text
current_year_beginning_total_assets != prior_year_ending_total_assets
```

Use a default tolerance of `$5.00`.

### Required Data

- Prior year return or prior year balance sheet
- Current year balance sheet

### Recommended Action

Ask preparer to verify beginning balances and prior-year ending balances.

---

## PY-002: Retained Earnings Rollforward Mismatch

**Applies To:** 1120, 1120-S  
**Severity:** HIGH

### Logic

Flag if:

```text
beginning_retained_earnings
+ current_year_book_income
- distributions_or_dividends
+/- book_adjustments
!= ending_retained_earnings
```

### Triggers / Keywords

```text
retained earnings
accumulated adjustments account
AAA
dividends
distributions
book income
net income
```

### Recommended Action

Review retained earnings, AAA schedule, dividends, distributions, and book-tax adjustments.

---

## PY-003: Partner / Shareholder Capital Mismatch

**Applies To:** 1120-S, 1065  
**Severity:** HIGH

### Logic

Flag if owner-level beginning capital does not match prior-year ending K-1/capital account data.

```text
current_beginning_capital != prior_year_ending_capital
```

### Required Support

- K1_WORKSHEET
- CAPITAL_ACCOUNT_SCHEDULE
- OWNERSHIP_SCHEDULE

---

## PY-004: Depreciation Carryforward Mismatch

**Applies To:** ALL business returns  
**Severity:** MEDIUM

### Logic

Flag if current depreciation schedule opening accumulated depreciation differs from prior-year ending accumulated depreciation.

### Required Support

- PRIOR_YEAR_RETURN
- DEPRECIATION_SCHEDULE
- FIXED_ASSET_LISTING

---

## PY-005: Loan Balance Rollforward Mismatch

**Applies To:** ALL business returns  
**Severity:** MEDIUM

### Logic

Flag if current-year opening loan balance does not equal prior-year closing loan balance.

### Required Support

- LOAN_STATEMENT
- BALANCE_SHEET
- PRIOR_YEAR_RETURN

---

# 5. New Rule Group: Balance Sheet Tie-Out Checks

## BST-001: Cash Per Books vs Bank Statement Mismatch

**Applies To:** ALL  
**Severity:** HIGH

### Logic

Extract cash/checking/savings balances from balance sheet and compare with bank statement or bank reconciliation ending balance.

Flag if difference exceeds configured tolerance.

```text
cash_per_books != bank_statement_ending_balance
```

### Required Support

- BANK_STATEMENT or BANK_RECONCILIATION

### Triggers

```text
cash
checking
savings
bank account
operating account
```

---

## BST-002: AR Aging Tie-Out Mismatch

**Applies To:** 1120-S, 1065, 1120  
**Severity:** MEDIUM

### Logic

Flag if accounts receivable balance on balance sheet does not equal AR aging total.

```text
balance_sheet_accounts_receivable != ar_aging_total
```

### Required Support

- AR_AGING

---

## BST-003: AP Aging Tie-Out Mismatch

**Applies To:** 1120-S, 1065, 1120  
**Severity:** MEDIUM

### Logic

Flag if accounts payable balance on balance sheet does not equal AP aging total.

```text
balance_sheet_accounts_payable != ap_aging_total
```

### Required Support

- AP_AGING

---

## BST-004: Loan Statement Tie-Out Mismatch

**Applies To:** ALL  
**Severity:** MEDIUM

### Logic

Flag if notes payable / mortgage / loan balance on balance sheet does not equal lender statement ending balance.

### Required Support

- LOAN_STATEMENT

---

## BST-005: Credit Card Balance Support Missing

**Applies To:** ALL  
**Severity:** MEDIUM

### Logic

If credit card liability is detected but no credit card statement is uploaded, flag missing support.

### Triggers

```text
credit card
visa
mastercard
amex
american express
card payable
```

### Required Support

- CREDIT_CARD_STATEMENT

---

## BST-006: Inventory Balance Support Missing

**Applies To:** ALL business returns  
**Severity:** MEDIUM

### Logic

If inventory exists on balance sheet but no inventory report or COGS support is uploaded, flag anomaly.

### Triggers

```text
inventory
merchandise
raw materials
finished goods
work in process
cost of goods sold
COGS
```

### Required Support

- INVENTORY_REPORT
- COGS_SUPPORT

---

## BST-007: Fixed Asset Tie-Out Mismatch

**Applies To:** ALL business returns  
**Severity:** MEDIUM

### Logic

Compare fixed assets on balance sheet with fixed asset listing/depreciation schedule.

Flag if:

```text
balance_sheet_fixed_assets != fixed_asset_listing_cost_basis
```

### Required Support

- FIXED_ASSET_LISTING
- DEPRECIATION_SCHEDULE

---

# 6. New Rule Group: Income Statement Reasonableness Checks

## ISR-001: Large Expense Variance

**Applies To:** ALL  
**Severity:** MEDIUM

### Logic

Compare current-year expense categories with prior-year expense categories.

Flag if variance exceeds configured threshold.

Example:

```text
abs(current_year_expense - prior_year_expense) / prior_year_expense > 40%
```

### Configurable Threshold

```json
{
  "expense_variance_percent_threshold": 0.40,
  "minimum_amount_threshold": 5000
}
```

---

## ISR-002: New Material Expense Category

**Applies To:** ALL  
**Severity:** LOW / MEDIUM

### Logic

Flag if a new expense category appears this year and the amount exceeds threshold.

Example:

```text
prior_year_expense_category_missing = true
current_year_amount > 5000
```

---

## ISR-003: Expense Ratio Outlier

**Applies To:** ALL  
**Severity:** MEDIUM

### Logic

Flag if certain expenses are unusually high as a percentage of gross receipts.

Example categories:

```text
meals
travel
auto
professional fees
rent
advertising
repairs
miscellaneous
office expense
```

Example:

```text
expense_amount / gross_receipts > configured_category_ratio
```

---

## ISR-004: Revenue Drop but Expenses Increase

**Applies To:** ALL  
**Severity:** MEDIUM

### Logic

Flag if revenue drops materially but major expenses increase materially.

Example:

```text
revenue_decrease_percent > 25%
AND payroll_or_rent_increase_percent > 20%
```

---

## ISR-005: Gross Margin Anomaly

**Applies To:** Businesses with COGS  
**Severity:** MEDIUM

### Logic

Calculate gross margin:

```text
gross_margin = (gross_receipts - cost_of_goods_sold) / gross_receipts
```

Flag if gross margin changes significantly from prior year.

Example threshold:

```text
abs(current_gross_margin - prior_gross_margin) > 15%
```

---

## ISR-006: Net Income vs Cash Flow Conflict

**Applies To:** ALL  
**Severity:** LOW / MEDIUM

### Logic

Flag unusual mismatch between profitability and cash movement.

Examples:

```text
net_income_high_positive AND cash_decreased_materially
net_loss_large AND cash_increased_materially_without_loan_or_capital_contribution
```

---

## ISR-007: Enhanced Miscellaneous Expense Rule

**Applies To:** ALL  
**Severity:** MEDIUM

### Logic

Current Rule L checks if miscellaneous expense exceeds `$10,000`.

Improve it to use both amount and percentage of revenue.

Flag if:

```text
misc_expense > 10000
OR misc_expense / gross_receipts > 0.02
```

---

# 7. New Rule Group: Revenue and 1099 Reconciliation

## REV-001: 1099-K Exceeds Reported Revenue

**Applies To:** 1040 Schedule C, 1120-S, 1065, 1120  
**Severity:** HIGH

### Logic

If Form 1099-K is uploaded, compare 1099-K gross amount with reported gross receipts.

Flag if:

```text
form_1099_k_amount > reported_gross_receipts + tolerance
```

### Required Support

- FORM_1099_K
- SALES_REPORT
- MERCHANT_STATEMENT

---

## REV-002: 1099-NEC / 1099-MISC Income Missing

**Applies To:** 1040 Schedule C, 1120-S, 1065, 1120  
**Severity:** HIGH

### Logic

If 1099-NEC or 1099-MISC income forms are detected, verify that amounts are included in gross receipts.

Flag if:

```text
sum_1099_income > reported_gross_receipts + tolerance
```

or if material 1099 income has no corresponding income category.

---

## REV-003: Bank Deposits Exceed Revenue

**Applies To:** ALL business returns  
**Severity:** MEDIUM / HIGH

### Logic

Compare total business bank deposits with reported revenue.

Flag if bank deposits materially exceed reported revenue.

```text
total_business_deposits > reported_gross_receipts + configured_tolerance
```

### Note

This rule should exclude:

- Owner contributions
- Loan proceeds
- Transfers between accounts
- Tax refunds
- Non-income deposits

---

## REV-004: Sales Tax Included in Revenue

**Applies To:** Businesses with sales tax  
**Severity:** LOW / MEDIUM

### Logic

If sales tax collected/payable is detected, verify whether revenue is reported net of sales tax where applicable.

### Triggers

```text
sales tax payable
sales tax collected
state sales tax
tax collected
```

---

## REV-005: Refunds / Chargebacks / Merchant Fees Missing

**Applies To:** Businesses using payment processors  
**Severity:** LOW / MEDIUM

### Logic

If 1099-K gross amount differs from net sales, check if refunds, chargebacks, and merchant fees are supported.

### Required Support

- MERCHANT_STATEMENT
- SALES_REPORT

---

# 8. New Rule Group: Payroll and Contractor Support

## PAY-001: Payroll Tax Reports Missing

**Applies To:** ALL business returns  
**Severity:** HIGH

### Logic

If payroll tax expense is detected, require payroll tax reports.

### Triggers

```text
payroll tax
941
940
FUTA
SUTA
employment tax
```

### Required Support

- FORM_941_940
- PAYROLL_SUMMARY

---

## PAY-002: Wages Do Not Tie to Payroll Summary

**Applies To:** ALL business returns  
**Severity:** HIGH

### Logic

Compare wages/salaries on income statement with payroll summary and W-2/W-3 totals.

Flag if difference exceeds tolerance.

```text
pnl_wages != payroll_summary_wages
```

### Required Support

- PAYROLL_SUMMARY
- W2_W3

---

## PAY-003: Officer Compensation Support Missing

**Applies To:** 1120-S, 1120  
**Severity:** HIGH

### Logic

If officer compensation is found, require officer payroll or W-2 support.

### Triggers

```text
officer compensation
compensation of officers
shareholder wages
owner wages
```

### Required Support

- PAYROLL_SUMMARY
- W2_W3

---

## PAY-004: Contractor Support Missing

**Applies To:** ALL business returns  
**Severity:** MEDIUM

### Logic

If contract labor or subcontractor expense is detected, require 1099-NEC summary or contractor listing.

### Triggers

```text
contract labor
subcontractor
contractor
outside services
1099
nonemployee compensation
```

### Required Support

- FORM_1099_NEC
- CONTRACTOR_LISTING
- W9

---

## PAY-005: Benefits / Health Insurance Support Missing

**Applies To:** ALL business returns  
**Severity:** MEDIUM

### Logic

If employee benefits, health insurance, retirement plan, or 401k expense is detected, require supporting schedule.

### Triggers

```text
health insurance
employee benefits
retirement
401k
pension
group insurance
```

---

# 9. New Rule Group: Depreciation, Fixed Assets, and Disposals

## DEP-001: Depreciation Expense Without Fixed Assets

**Applies To:** ALL business returns  
**Severity:** MEDIUM

### Logic

If depreciation expense exists on income statement but no fixed assets or depreciation schedule exists, flag.

### Required Support

- DEPRECIATION_SCHEDULE
- FIXED_ASSET_LISTING

---

## DEP-002: Fixed Asset Additions Without Invoice Support

**Applies To:** ALL business returns  
**Severity:** MEDIUM

### Logic

If fixed asset additions are detected, require invoice or asset purchase support.

### Triggers

```text
equipment
furniture
vehicle
machinery
computer
leasehold improvement
fixed asset addition
```

---

## DEP-003: Asset Disposal Without Support

**Applies To:** ALL business returns  
**Severity:** MEDIUM

### Logic

If sale/disposal/gain/loss on asset is detected, require disposal schedule.

### Triggers

```text
gain on sale
loss on sale
asset disposal
sold equipment
sold vehicle
sale of business property
```

---

## DEP-004: Accumulated Depreciation Rollforward Mismatch

**Applies To:** ALL business returns  
**Severity:** MEDIUM

### Logic

Flag if:

```text
beginning_accumulated_depreciation
+ current_year_depreciation
- accumulated_depreciation_on_disposals
!= ending_accumulated_depreciation
```

---

## DEP-005: Vehicle Asset Without Mileage / Business Use Support

**Applies To:** ALL business returns, especially Schedule C  
**Severity:** MEDIUM

### Logic

If vehicle asset or auto expense is detected, require mileage log or business-use support.

### Required Support

- VEHICLE_MILEAGE_LOG

---

# 10. New Rule Group: Schedule C-Specific Rules

## SC-001: COGS Without Inventory Support

**Applies To:** 1040 Schedule C  
**Severity:** MEDIUM

### Logic

If cost of goods sold exists, require inventory or purchase support.

### Required Support

- INVENTORY_REPORT
- COGS_SUPPORT

---

## SC-002: Inventory Business Without COGS

**Applies To:** 1040 Schedule C  
**Severity:** MEDIUM

### Logic

If business appears to sell products but no COGS/inventory section is found, flag for review.

### Triggers

```text
retail
store
merchandise
inventory
products
goods
resale
supplies for resale
```

---

## SC-003: Vehicle Expense Support Missing

**Applies To:** 1040 Schedule C  
**Severity:** MEDIUM

### Logic

If car and truck expense exists, require mileage log or vehicle-use detail.

### Triggers

```text
car and truck
auto expense
vehicle
mileage
fuel
gas
repairs and maintenance vehicle
```

### Required Support

- VEHICLE_MILEAGE_LOG

---

## SC-004: Home Office Support Missing

**Applies To:** 1040 Schedule C  
**Severity:** MEDIUM

### Logic

If home office expense is detected, require home office support or Form 8829.

### Triggers

```text
home office
business use of home
Form 8829
utilities home office
rent home office
```

### Required Support

- HOME_OFFICE_SUPPORT
- FORM_8829

---

## SC-005: Multiple Businesses Combined

**Applies To:** 1040 Schedule C  
**Severity:** MEDIUM

### Logic

Flag if multiple unrelated business activities are detected in one Schedule C package.

Example:

```text
consulting revenue
AND retail inventory
AND restaurant expenses
```

---

# 11. New Rule Group: M-1, M-2, M-3 and Book-Tax Reconciliation

## MREC-001: M-1 / M-3 Missing

**Applies To:** 1120, 1120-S, 1065  
**Severity:** HIGH

### Logic

If book income differs materially from taxable income and no M-1 or M-3 schedule is detected, flag.

### Triggers

```text
book income
tax income
M-1
M-2
M-3
reconciliation
Schedule L
Schedule M
```

---

## MREC-002: Book Income vs Tax Income Not Reconciled

**Applies To:** 1120, 1120-S, 1065  
**Severity:** HIGH

### Logic

Flag if:

```text
net_income_per_books != taxable_income
```

and no reconciling items are found.

---

## MREC-003: Non-Deductible Expense Support Missing

**Applies To:** 1120, 1120-S, 1065  
**Severity:** MEDIUM

### Logic

If non-deductible expense keywords are detected, verify that they are treated as book-tax adjustments.

### Triggers

```text
penalties
fines
political contribution
meals
entertainment
life insurance
nondeductible
non-deductible
```

---

## MREC-004: Retained Earnings / AAA / Capital M-2 Mismatch

**Applies To:** 1120, 1120-S, 1065  
**Severity:** HIGH

### Logic

Flag if equity/capital rollforward does not reconcile.

Examples:

For C-Corp:

```text
beginning_retained_earnings
+ net_income
- dividends
+/- adjustments
!= ending_retained_earnings
```

For S-Corp:

```text
beginning_AAA
+ ordinary_business_income
+ separately_stated_income
- distributions
- nondeductible_expenses
!= ending_AAA
```

For Partnership:

```text
beginning_partner_capital
+ contributions
+ allocated_income
- distributions
- allocated_losses
!= ending_partner_capital
```

---

# 12. New Rule Group: Owner, Shareholder, and Partner Transactions

## OWN-001: Shareholder / Partner Loan Support Missing

**Applies To:** 1120-S, 1065, 1120  
**Severity:** MEDIUM / HIGH

### Logic

If loan to shareholder, due from owner, or due to partner is detected, require loan support.

### Triggers

```text
loan to shareholder
loan from shareholder
due from owner
due to owner
due from partner
due to partner
shareholder receivable
partner receivable
```

### Required Support

- LOAN_STATEMENT
- SHAREHOLDER_DISTRIBUTION
- PARTNER_DISTRIBUTION

---

## OWN-002: Distribution Exceeds Capital / Basis Warning

**Applies To:** 1120-S, 1065  
**Severity:** MEDIUM

### Logic

Flag if distributions appear higher than available capital or basis indicators.

```text
distributions > beginning_capital + current_income + contributions
```

---

## OWN-003: Unequal S-Corp Distribution Warning

**Applies To:** 1120-S  
**Severity:** HIGH

### Logic

S-corp distributions should generally be proportional to ownership.

Flag if:

```text
owner_distribution_percentage != owner_ownership_percentage
```

### Required Support

- OWNERSHIP_SCHEDULE
- SHAREHOLDER_DISTRIBUTION
- K1_WORKSHEET

---

## OWN-004: Partner Guaranteed Payments Support Missing

**Applies To:** 1065  
**Severity:** MEDIUM

### Logic

If guaranteed payments are detected, require partner allocation detail.

### Triggers

```text
guaranteed payment
partner payment
partner salary
partner compensation
```

### Required Support

- K1_WORKSHEET
- CAPITAL_ACCOUNT_SCHEDULE

---

## OWN-005: Contributions / Distributions Rollforward Mismatch

**Applies To:** 1120-S, 1065  
**Severity:** MEDIUM

### Logic

Flag if capital activity does not tie to K-1 or capital schedule.

---

# 13. New Rule Group: OCR and Document Quality Rules

## OCR-001: Low OCR Confidence

**Applies To:** ALL  
**Severity:** MEDIUM

### Logic

Flag if OCR confidence is below threshold for important documents.

Example threshold:

```json
{
  "minimum_ocr_confidence": 0.75
}
```

---

## OCR-002: Missing Page Warning

**Applies To:** ALL  
**Severity:** HIGH

### Logic

Detect page numbering gaps.

Examples:

```text
Page 1 of 5
Page 2 of 5
Page 4 of 5
```

Flag missing page 3.

---

## OCR-003: Duplicate Document Uploaded

**Applies To:** ALL  
**Severity:** LOW

### Logic

Use file hash, text similarity, or extracted document metadata to detect duplicate uploads.

---

## OCR-004: Wrong Tax Year Detected

**Applies To:** ALL  
**Severity:** HIGH

### Logic

If uploaded document year does not match target filing year, flag.

Example:

```text
target_tax_year = 2025
document_tax_year = 2024
```

---

## OCR-005: Wrong Entity / EIN / SSN Detected

**Applies To:** ALL  
**Severity:** HIGH

### Logic

Compare taxpayer name, entity name, EIN, or SSN fragments against client profile.

Flag if mismatch is detected.

---

## OCR-006: Mixed Client Documents

**Applies To:** ALL  
**Severity:** HIGH

### Logic

Flag if multiple taxpayer names, EINs, or unrelated entities appear in the same upload package.

---

## OCR-007: Draft / Unaudited Document Warning

**Applies To:** ALL  
**Severity:** LOW / MEDIUM

### Logic

Flag if uploaded documents appear to be draft or preliminary.

### Triggers

```text
draft
preliminary
unaudited
for review only
not final
```

---

# 14. New Rule Group: Bank Reconciliation and Cash Activity

## BANK-001: Bank Reconciliation Missing

**Applies To:** ALL business returns  
**Severity:** HIGH

### Logic

If cash/checking/savings account exists, require bank statement or bank reconciliation.

### Required Support

- BANK_STATEMENT
- BANK_RECONCILIATION

---

## BANK-002: Old Outstanding Checks Warning

**Applies To:** ALL business returns  
**Severity:** MEDIUM

### Logic

If bank reconciliation has old outstanding checks above threshold, flag.

Example:

```text
outstanding_check_age_days > 90
AND outstanding_check_amount > 1000
```

---

## BANK-003: Large Deposits in Transit

**Applies To:** ALL business returns  
**Severity:** MEDIUM

### Logic

Flag if deposits in transit are unusually large or old.

---

## BANK-004: Negative Cash with Positive Bank Statement

**Applies To:** ALL business returns  
**Severity:** HIGH

### Logic

Flag if books show negative cash but bank statement shows positive ending balance.

---

## BANK-005: Possible Personal Expense in Business Account

**Applies To:** ALL business returns  
**Severity:** MEDIUM

### Logic

Scan general ledger or bank transactions for personal expense indicators.

### Example Keywords

```text
grocery
vacation
school
tuition
personal rent
personal mortgage
family
clothing
entertainment personal
```

### Note

This rule should be low confidence unless supported by transaction-level details.

---

# 15. New Rule Group: General Ledger Anomaly Checks

## GL-001: Duplicate Vendor Payment

**Applies To:** ALL  
**Severity:** MEDIUM

### Logic

Flag same vendor, same amount, and same or near date.

Example:

```text
same_vendor = true
same_amount = true
date_difference <= 7 days
```

---

## GL-002: Large Round-Dollar Expense

**Applies To:** ALL  
**Severity:** LOW / MEDIUM

### Logic

Flag large round-dollar expenses.

Example:

```text
amount >= 5000
AND amount % 1000 == 0
```

---

## GL-003: Unusual Weekend / Holiday Posting Spike

**Applies To:** ALL  
**Severity:** LOW

### Logic

Flag many manual entries posted on weekends or holidays.

---

## GL-004: Manual Journal Entry to Revenue

**Applies To:** ALL  
**Severity:** MEDIUM

### Logic

Flag manual journal entries posted directly to revenue accounts.

### Triggers

```text
journal entry
manual entry
adjusting entry
revenue
sales
income
```

---

## GL-005: Expense Posted to Balance Sheet

**Applies To:** ALL  
**Severity:** MEDIUM

### Logic

Flag expense-like descriptions posted to asset/liability accounts.

Example:

```text
meal expense posted to loan account
office supplies posted to fixed assets
```

---

## GL-006: Balance Sheet Item Posted to P&L

**Applies To:** ALL  
**Severity:** MEDIUM

### Logic

Flag possible balance sheet items recorded as expense.

Examples:

```text
loan principal payment recorded as expense
owner draw recorded as expense
asset purchase recorded as repairs expense
```

---

## GL-007: Uncategorized / Ask My Accountant Balance High

**Applies To:** ALL  
**Severity:** MEDIUM

### Logic

Flag if suspense or uncategorized accounts exceed threshold.

### Triggers

```text
uncategorized
ask my accountant
suspense
clearing account
temporary account
unknown
```

---

# 16. New Rule Group: Return-Type Routing Checks

## RT-001: Possible Wrong Return Type

**Applies To:** ALL  
**Severity:** HIGH

### Logic

Flag if selected return type does not match uploaded documents.

Examples:

```text
selected_return_type = 1120-S
documents contain "Form 1065", "partner", "partnership"
```

```text
selected_return_type = 1040_SCHEDULE_C
documents contain corporation, shareholder, partnership, K-1
```

---

## RT-002: Schedule C vs Entity Return Mismatch

**Applies To:** 1040 Schedule C  
**Severity:** HIGH

### Logic

Flag if Schedule C is selected but documents indicate corporation or partnership.

### Triggers

```text
corporation
S corporation
partnership
shareholder
partner
Form 1120
Form 1120-S
Form 1065
K-1
EIN
```

---

## RT-003: S-Corp Election / Entity Type Support Warning

**Applies To:** 1120-S  
**Severity:** MEDIUM

### Logic

If 1120-S is selected but documents mention C-corp treatment or lack shareholder/pass-through information, flag for review.

---

## RT-004: Multiple Entities Detected

**Applies To:** ALL  
**Severity:** HIGH

### Logic

Flag if multiple EINs, entity names, or taxpayer names appear across uploaded files.

---

# 17. Improved Negative Balance Rule

Current Rule N should be improved because some negative balances are normal.

## Current Issue

Some accounts are normally negative or contra accounts, such as:

```text
accumulated depreciation
allowance for doubtful accounts
owner distributions
treasury stock
```

## Improved Logic

Use account-type-aware sign validation.

### Flag Negative Values For

```text
cash
accounts receivable
inventory
prepaid expenses
fixed asset cost
```

### Flag Positive Values For

```text
accumulated depreciation
allowance for doubtful accounts
owner distributions
draws
```

### Review Carefully

```text
accounts payable
credit card payable
notes payable
loans payable
tax payable
```

These may appear negative because of overpayment, misclassification, or data export format.

---

# 18. Suggested Rule Execution Flow

Recommended execution order:

```text
1. Classify documents
2. Extract text and tables
3. Detect taxpayer/entity/tax year
4. Detect return type
5. Extract key financial values
6. Run core missing document checks
7. Run return-type package checks
8. Run trigger-based support checks
9. Run financial tie-out checks
10. Run prior-year roll-forward checks
11. Run GL and transaction-level checks
12. Score severity and confidence
13. Generate anomaly report
```

---

# 19. Suggested Data Model Additions

## Table: `anomaly_rules`

```sql
CREATE TABLE anomaly_rules (
    id UUID PRIMARY KEY,
    rule_id VARCHAR(50) UNIQUE NOT NULL,
    rule_name TEXT NOT NULL,
    category VARCHAR(100) NOT NULL,
    return_types TEXT[] NOT NULL,
    severity VARCHAR(20) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    config JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

## Table: `detected_anomalies`

```sql
CREATE TABLE detected_anomalies (
    id UUID PRIMARY KEY,
    client_id UUID,
    filing_id UUID,
    rule_id VARCHAR(50) NOT NULL,
    rule_name TEXT NOT NULL,
    category VARCHAR(100),
    severity VARCHAR(20),
    status VARCHAR(20),
    confidence_score NUMERIC(5, 4),
    evidence_document TEXT,
    evidence_text TEXT,
    extracted_amount NUMERIC(14, 2),
    expected_amount NUMERIC(14, 2),
    difference NUMERIC(14, 2),
    tolerance NUMERIC(14, 2),
    missing_support TEXT[],
    recommended_action TEXT,
    review_required_by VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);
```

## Table: `extracted_financial_values`

```sql
CREATE TABLE extracted_financial_values (
    id UUID PRIMARY KEY,
    client_id UUID,
    filing_id UUID,
    document_id UUID,
    value_key VARCHAR(100) NOT NULL,
    value_label TEXT,
    amount NUMERIC(14, 2),
    period_type VARCHAR(50),
    period_start DATE,
    period_end DATE,
    source_page INT,
    source_text TEXT,
    confidence_score NUMERIC(5, 4),
    created_at TIMESTAMP DEFAULT NOW()
);
```

Example `value_key` values:

```text
total_assets_beginning
total_assets_ending
total_liabilities_beginning
total_liabilities_ending
total_equity_beginning
total_equity_ending
gross_receipts
cost_of_goods_sold
gross_profit
net_income
cash_ending
accounts_receivable_ending
accounts_payable_ending
inventory_ending
fixed_assets_cost
accumulated_depreciation
notes_payable
shareholder_distributions
partner_distributions
retained_earnings_beginning
retained_earnings_ending
```

---

# 20. Rule Configuration Example

Use configurable thresholds instead of hardcoding all values.

```json
{
  "default_tolerance_amount": 5.00,
  "materiality_minimum_amount": 1000.00,
  "misc_expense_threshold": 10000.00,
  "misc_expense_percent_of_revenue": 0.02,
  "expense_variance_percent_threshold": 0.40,
  "gross_margin_variance_threshold": 0.15,
  "revenue_drop_threshold": 0.25,
  "major_expense_increase_threshold": 0.20,
  "minimum_ocr_confidence": 0.75,
  "large_round_dollar_amount": 5000.00,
  "old_outstanding_check_days": 90,
  "old_outstanding_check_amount": 1000.00
}
```

---

# 21. Implementation Priority

## Phase 1 – High-Impact Checks

Implement these first:

1. PY-001: Beginning Balance Mismatch
2. PY-002: Retained Earnings Rollforward Mismatch
3. BST-001: Cash Per Books vs Bank Statement Mismatch
4. BST-002: AR Aging Tie-Out Mismatch
5. BST-003: AP Aging Tie-Out Mismatch
6. REV-001: 1099-K Exceeds Reported Revenue
7. REV-002: 1099-NEC / 1099-MISC Income Missing
8. PAY-002: Wages Do Not Tie to Payroll Summary
9. RT-001: Possible Wrong Return Type
10. OCR-004: Wrong Tax Year Detected
11. OCR-005: Wrong Entity / EIN / SSN Detected

## Phase 2 – Entity-Specific Checks

1. PY-003: Partner / Shareholder Capital Mismatch
2. OWN-002: Distribution Exceeds Capital / Basis Warning
3. OWN-003: Unequal S-Corp Distribution Warning
4. OWN-004: Partner Guaranteed Payments Support Missing
5. MREC-001: M-1 / M-3 Missing
6. MREC-004: Retained Earnings / AAA / Capital M-2 Mismatch

## Phase 3 – GL and Transaction-Level Checks

1. GL-001: Duplicate Vendor Payment
2. GL-002: Large Round-Dollar Expense
3. GL-004: Manual Journal Entry to Revenue
4. GL-005: Expense Posted to Balance Sheet
5. GL-006: Balance Sheet Item Posted to P&L
6. BANK-005: Possible Personal Expense in Business Account

---

# 22. Suggested Developer Tasks for Antigravity

## Task 1: Add New Rule Definitions

Create rule definitions for all rule IDs in this document.

Each rule should include:

```json
{
  "rule_id": "PY-001",
  "name": "Beginning Balance Mismatch",
  "category": "PRIOR_YEAR_ROLL_FORWARD",
  "severity": "HIGH",
  "return_types": ["1120-S", "1065", "1120", "1040_SCHEDULE_C"],
  "required_documents": ["PRIOR_YEAR_RETURN", "BALANCE_SHEET"],
  "trigger_keywords": [],
  "config": {
    "tolerance": 5.00
  }
}
```

---

## Task 2: Add Financial Value Extractor

Implement extraction for the following values:

```text
total_assets_beginning
total_assets_ending
total_liabilities_beginning
total_liabilities_ending
total_equity_beginning
total_equity_ending
gross_receipts
cost_of_goods_sold
gross_profit
net_income
cash_ending
accounts_receivable_ending
accounts_payable_ending
inventory_ending
fixed_assets_cost
accumulated_depreciation
notes_payable
shareholder_distributions
partner_distributions
retained_earnings_beginning
retained_earnings_ending
```

---

## Task 3: Add Tie-Out Engine

Create a generic tie-out utility.

```python
def check_tie_out(
    extracted_amount: float,
    expected_amount: float,
    tolerance: float = 5.0
) -> dict:
    difference = abs(extracted_amount - expected_amount)

    return {
        "passed": difference <= tolerance,
        "difference": difference,
        "tolerance": tolerance
    }
```

---

## Task 4: Add Trigger-Based Support Checker

Create a generic function that checks:

1. Whether trigger keywords exist in extracted document text
2. Whether required supporting documents exist
3. Whether the rule should be flagged

```python
def check_trigger_support(
    all_text: str,
    uploaded_doc_types: list[str],
    trigger_keywords: list[str],
    required_doc_types: list[str]
) -> dict:
    triggered_keywords = [
        keyword for keyword in trigger_keywords
        if keyword.lower() in all_text.lower()
    ]

    missing_docs = [
        doc for doc in required_doc_types
        if doc not in uploaded_doc_types
    ]

    return {
        "triggered": len(triggered_keywords) > 0,
        "triggered_keywords": triggered_keywords,
        "missing_docs": missing_docs,
        "flagged": len(triggered_keywords) > 0 and len(missing_docs) > 0
    }
```

---

## Task 5: Add Return-Type Validator

Implement logic to compare selected return type with detected form/entity terms.

Example:

```python
RETURN_TYPE_KEYWORDS = {
    "1120-S": ["1120-S", "S corporation", "shareholder", "Schedule K-1"],
    "1065": ["1065", "partnership", "partner", "Schedule K-1"],
    "1120": ["1120", "C corporation", "corporation", "dividends"],
    "1040_SCHEDULE_C": ["Schedule C", "sole proprietor", "business income"]
}
```

Flag if detected terms strongly indicate a different return type.

---

# 23. Final Recommendation

The anomaly engine should not only say:

```text
Payroll document missing.
```

It should say:

```text
Payroll expense of $184,500 was detected in the income statement, but no payroll summary, W-2/W-3, or payroll tax report was uploaded. Please verify payroll support before filing.
```

The best implementation approach is:

1. Extract evidence
2. Classify documents
3. Run rules
4. Attach reason and source text
5. Produce an accountant-friendly review report

This will make the system much more useful for tax preparers and reduce false positives.
