# Supplier Purchasing & Warehouse Receiving (2026-11-12)

## Scope

The purchasing add-on supports registering suppliers, saving purchase drafts with unit-cost snapshots, and a **single physical full-receipt** into existing stock. It **does not** create supplier payables, bank payments, expense entries, purchase-tax invoices, inventory valuation or cost of goods sold (COGS).

The feature deliberately stores costs **excluding purchase VAT**. Do not infer tax input credits, realized gross profit, stock valuation, or net profit from these recorded costs. Earlier inventory and sales have no reliable historical cost basis; a costing policy and additional data capture are required before COGS is available.

## API contracts

All routes require session authentication; POST also requires CSRF. Admin bypasses all role filters, as in the original app.

| Route | Role | Purpose |
| --- | --- | --- |
| GET /api/suppliers?limit=50&after=<id> | accountant, warehouse | Forward-paginated supplier directory |
| POST /api/suppliers | accountant | Create supplier from name (required), tax_id (optional 13 digits), address (optional) |
| GET /api/purchases?limit=50&before=<id> | accountant, warehouse | Reverse-paginated purchase list |
| GET /api/purchases/<id> | accountant, warehouse | Snapshot of supplier, product, costs and receiver |
| POST /api/purchases | accountant | Create draft without stock movement |
| POST /api/purchases/<id>/receive | warehouse | Physically verified full receipt, once per purchase |

Create purchase payload example (synthetic):
```json
{
  "request_key": "synthetic-purchase-20261112-0001",
  "supplier_id": 1,
  "note": "Synthetic sealed water packs",
  "lines": [
    {"product_id": 1, "quantity": 10, "unit_cost": "41.50"}
  ]
}
```

- `request_key` must have 16–80 characters. A replay with identical complete payload returns the same order with `duplicate=true`. Changed payload with reused key returns HTTP 409. A concurrent duplicate key that loses the database unique-key race also returns HTTP 409; callers must reconcile rather than create a new order blindly.
- Lines must have 1–100 distinct products, positive whole quantities, positive `unit_cost` strings rounded to at most two decimals. The purchase total is stored as Decimal and capped to fit the existing money range.
- At creation the supplier name, tax ID, address and product SKU/name/unit cost are snapshotted. The customer sale/receivable system is not changed.
- Receipts use `{"receipt_note": "Synthetic packs counted"}`. An attempted second receipt with the **same note** returns `duplicate=true`; a conflicting note returns 409. PostgreSQL row locks ensure stock is not credited twice, even with concurrent requests.
- A received purchase adds `StockMovement` entries with reason `Supplier purchase received #<id>`, records the receiver and receipt time, and increments `Product.stock` in the same database transaction.
- Only full receipt is currently supported. **Partial receipts, rejected/damaged supplier goods, purchase order changes, product replacement and receiving discrepancies are not yet implemented.** Do not mark a delivery received unless its exact listed quantities have physically arrived and been checked.
- UI: Open **จัดซื้อและรับสินค้า** under the additional navigation menu. Accounting staff can add suppliers/PO drafts; warehouse staff can view and confirm physical receipt; the owner can do both.

## Schema & verification

Migration `9b2a11e4d508_purchasing.py` adds only `supplier`, `purchase_order` and `purchase_order_line`. Existing product/stock/sales/payments/tax-document schemas are unchanged. The Alembic downgrade **irreversibly deletes purchase records**; run destructive downgrade tests only on disposable CI databases.

Regression tests in `tests/test_purchasing.py` cover validation, role checks, idempotent draft creation, immutable purchase cost/supplier snapshots, no draft side effects, one-time full receipt, and concurrent PostgreSQL receiving. `tests/ui_smoke.py` includes end-to-end supplier/purchase/receipt testing on a synthetic mobile browser. Verify the **latest** branch CI status after all commits.

Render staging still tracks `feature/thanabunyapat-online`, not this development branch. Backup/restore and isolation have not been proven, so no staging or production deploy, no live migration, and no production data tests are authorized. Continue work only on `feature/flow-loyverse-additions-20261112`.

## Next financial work

Design a consistent inventory cost basis: beginning stock with verified opening cost; purchased lots or weighted-average cost; captures at sale commit; returned-goods cost reversals; adjustments; allocation of freight and taxes; audit trails and discrepancy controls. Only then present a true **gross profit** measure, clearly separate from net profit. Seek accountant verification before tax document issuance or financial adjustments.
