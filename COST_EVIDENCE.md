# Inventory cost-evidence audit — diagnostic, NOT COGS

## Scope (2026-11-12)

Only read-only GET `/api/reports/cost-evidence?limit=50&after=<product_id>`, available to owner/admin and accountant. The **รายงาน** interface presents received purchase-price evidence and stock-movement reconciliation.

- Counts only purchases in `received` status. Draft purchases do not enter evidence totals.
- Computes ex-purchase-VAT cost by summing immutable PurchaseOrderLine quantity × unit_cost for received purchases.
- Independently compares Product.stock with the total of StockMovement deltas. A mismatch is an audit flag, not an automatic correction.
- `unattributed_inbound_units` is the difference between all positive stock movements and known received purchase quantity. It is **not** the units of unsold old stock, an allocated cost, or a verified count of current uncosted items.
- Reports `cogs_ex_vat: null`, `gross_profit_ex_vat: null`, `gross_profit_status: "unavailable"`. A sales total or supplier unit cost cannot make an unsupported gross-profit figure accurate.
- No tables, Sale, SaleLine, Product, StockMovement or Payment values are written by this endpoint. Existing company routes remain intact.

## Missing prerequisites for auditable gross profit

1. Reconcile opening stock quantities and source-document-supported opening values at a cut-off date.
2. Agree to a documented perpetual inventory policy (e.g. FIFO or moving weighted average), unit definitions, discount and freight allocation and purchase VAT treatment.
3. Record immutable cost-at-sale snapshots, including POS, wholesale, quotation conversions and LINE accepted orders, within original atomic stock transactions.
4. Track all receipts, stock adjustments, resellable/damaged returns and cost reversals consistently. Prevent uncosted or unknown stock from silently entering “verified gross profit”.
5. Reconcile stock and cost subledgers and have the accountant sign off on reporting logic, sample invoices and opening balances. Never backfill historical profit by guessing.

## Validation

`tests/test_cost_evidence.py` exercises role restrictions, missing-cost safeguards, receipt-only evidence, unchanged business records, discrepancy detection, paging and invalid filters. Mobile `tests/ui_smoke.py` checks the report is actually visible. CI uses disposable synthetic PostgreSQL and SQLite; no Render data or real stock is used.
