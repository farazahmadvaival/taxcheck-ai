# Active Anomaly Detection Ruleset

This document lists the active anomaly detection rules currently implemented in [app/services/anomaly_engine.py](file:///home/ubuntu/taxcheck-ai/app/services/anomaly_engine.py).

---

## 1. Core Missing Document Checks

These rules check for the absolute presence of mandatory documents required to start any business or individual return preparation.

| Rule ID | Rule Name | Severity | Target |
| :--- | :--- | :--- | :--- |
| **A** | Prior Year Tax Return Missing | HIGH | All returns |
| **B** | Balance Sheet Missing | HIGH | All returns |
| **C** | Income Statement Missing | HIGH | All returns |
| **D** | Trial Balance Missing | HIGH | Returns with P&L and Balance Sheet |
| **E** | General Ledger Detail Missing | MEDIUM | Returns with TB or Balance Sheet |

---

## 2. Contextual / Trigger-Based Document Checks

These rules scan the text of uploaded documents for trigger keywords. If a keyword is found but the corresponding supporting document is missing, the rule flags the anomaly.

| Rule ID | Rule Name | Severity | Trigger / Target |
| :--- | :--- | :--- | :--- |
| **F** | Payroll Support Missing | HIGH | Payroll/wage terms found in text |
| **G** | Depreciation Schedule Missing | MEDIUM | Depreciation/fixed asset terms |
| **H** | Loan / Interest Statement Missing | MEDIUM | Loan/interest terms found in text |
| **I** | Bank Statement Missing | HIGH | Cash/bank account terms in text |
| **J** | Accounts Receivable Aging Missing | MEDIUM | Accounts receivable/trade terms |
| **K** | Accounts Payable Aging Missing | MEDIUM | Accounts payable/trade terms |
| **M** | Shareholder Distribution Support Missing | MEDIUM | Shareholder/partner draw terms |

---

## 3. Financial & Mathematical Anomalies

These rules perform mathematical cross-checks within the current year's documents.

| Rule ID | Rule Name | Severity | Logic / Threshold |
| :--- | :--- | :--- | :--- |
| **L** | High Miscellaneous Expense | MEDIUM | Misc expense $> \$10,000$ OR $> 2\%$ of Gross Receipts |
| **N** | Account Balance Sign Warning | LOW | Flag negative assets/receivables or positive contra-assets |
| **BS-001** | Balance Sheet Equation Mismatch | HIGH | Total Assets $\neq$ Liabilities $+$ Equity (tolerance $\$5.00$) |

---

## 4. Phase 1 Advanced Rules

These rules compare metrics across current and prior years, tie out ledger balances to statements, or verify entity/metadata consistency.

| Rule ID | Rule Name | Severity | Logic |
| :--- | :--- | :--- | :--- |
| **PY-001** | Beginning Balance Mismatch | HIGH | Beginning assets $\neq$ prior ending assets (tolerance $\$5.00$) |
| **PY-002** | Retained Earnings Rollforward | HIGH | Beg RE $+$ Net Income $-$ Distributions $\neq$ Ending RE (tolerance $\$5.00$) |
| **BST-001** | Cash Books vs Bank Mismatch | HIGH | Ending Cash $\neq$ Bank Statement Ending balance (tolerance $\$5.00$) |
| **BST-002** | AR Aging Tie-Out Mismatch | MEDIUM | Accounts Receivable per books $\neq$ AR aging total (tolerance $\$5.00$) |
| **BST-003** | AP Aging Tie-Out Mismatch | MEDIUM | Accounts Payable per books $\neq$ AP aging total (tolerance $\$5.00$) |
| **REV-001** | 1099-K Revenue Exceeds Sales | HIGH | Card gross volume (1099-K) $>$ reported sales (tolerance $\$5.00$) |
| **REV-002** | 1099-NEC/MISC Income Exceeds Sales | HIGH | Sum of 1099 earnings $>$ reported sales (tolerance $\$5.00$) |
| **PAY-002** | Wages Discrepancy | HIGH | Wages on P&L $\neq$ payroll summary/W-2 total (tolerance $\$5.00$) |
| **RT-001** | Filing Entity Return Type Mismatch | HIGH | Selected filing form does not match document text signatures |
| **OCR-004** | Wrong Tax Year Detected | HIGH | Years found in document $\neq$ target filing year |
| **OCR-005** | Multiple EINs Detected | HIGH | More than one unique EIN found across package |
